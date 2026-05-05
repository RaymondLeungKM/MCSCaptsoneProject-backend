"""
Progress tracking endpoints
"""
from datetime import date, datetime, time, timedelta, timezone
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.analytics import (
    LearningControlStatusResponse,
    LearningSessionCreate,
    LearningSessionUpdate,
    LearningSessionResponse,
    ProgressStatsResponse
)
from app.models.analytics import LearningSession
from app.models.daily_words import DailyWordTracking
from app.models.parent_analytics import ParentalControl
from app.models.user import User, Child
from app.models.vocabulary import Category, Word, WordProgress
from app.core.security import get_current_active_user

router = APIRouter()


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duration_minutes(start_time: datetime, end_time: datetime) -> int:
    total_seconds = max((end_time - start_time).total_seconds(), 0)
    return int(total_seconds // 60)


def _merge_intervals(
    intervals: List[tuple[datetime, datetime]],
) -> List[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda interval: interval[0])
    merged: List[tuple[datetime, datetime]] = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        previous_start, previous_end = merged[-1]
        if current_start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, current_end))
            continue

        merged.append((current_start, current_end))

    return merged


def _sum_interval_minutes(intervals: List[tuple[datetime, datetime]]) -> int:
    return sum(
        _duration_minutes(start_time, end_time)
        for start_time, end_time in _merge_intervals(intervals)
    )


def _build_local_day_window(
    local_day: date | None,
    timezone_offset_minutes: int,
) -> tuple[date, datetime, datetime]:
    resolved_day = local_day or datetime.now(timezone.utc).date()
    local_start = datetime.combine(resolved_day, time.min)
    utc_start = (local_start + timedelta(minutes=timezone_offset_minutes)).replace(
        tzinfo=timezone.utc
    )
    utc_end = utc_start + timedelta(days=1)
    return resolved_day, utc_start, utc_end


@router.post("/session", response_model=LearningSessionResponse)
async def start_learning_session(
    session_data: LearningSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a new learning session"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(
            Child.id == session_data.child_id,
            Child.parent_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    new_session_start = _ensure_utc(session_data.start_time)
    open_sessions_result = await db.execute(
        select(LearningSession).where(
            LearningSession.child_id == session_data.child_id,
            LearningSession.end_time.is_(None),
        )
    )
    open_sessions = open_sessions_result.scalars().all()

    for open_session in open_sessions:
        open_start = _ensure_utc(open_session.start_time)
        closed_at = max(open_start, new_session_start)
        open_session.end_time = closed_at
        open_session.duration_minutes = _duration_minutes(open_start, closed_at)
    
    session = LearningSession(
        id=str(uuid.uuid4()),
        child_id=session_data.child_id,
        start_time=session_data.start_time,
        words_encountered=session_data.words_encountered,
        activities_completed=[act.dict() for act in session_data.activities_completed],
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    return session


@router.patch("/session/{session_id}", response_model=LearningSessionResponse)
async def end_learning_session(
    session_id: str,
    session_data: LearningSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """End a learning session and record results"""
    result = await db.execute(
        select(LearningSession).where(LearningSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Update session
    session.end_time = session_data.end_time
    session.words_encountered = session_data.words_encountered
    session.words_used_actively = session_data.words_used_actively
    session.activities_completed = [act.dict() for act in session_data.activities_completed]
    session.engagement_level = session_data.engagement_level
    session.interactions_count = session_data.interactions_count
    
    # Calculate duration
    if session.end_time and session.start_time:
        duration = (session.end_time - session.start_time).total_seconds() / 60
        session.duration_minutes = int(duration)
    
    # Calculate XP earned
    session.xp_earned = len(session.words_encountered) * 10 + session.interactions_count * 5
    
    await db.commit()
    await db.refresh(session)
    
    return session


@router.get("/{child_id}/stats", response_model=ProgressStatsResponse)
async def get_progress_stats(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get overall progress statistics for a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get word progress stats
    result = await db.execute(
        select(WordProgress).where(WordProgress.child_id == child_id)
    )
    all_progress = result.scalars().all()
    
    mastered_words = sum(1 for p in all_progress if p.mastered)
    total_words = len(all_progress)
    
    # Calculate active vs passive vocabulary from explicit output signals.
    progress_word_ids = {p.word_id for p in all_progress}

    active_word_ids: set[str] = set()

    active_tracking_result = await db.execute(
        select(DailyWordTracking.word_id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.used_actively == True,
            )
        )
        .distinct()
    )
    active_word_ids.update(
        word_id for word_id in active_tracking_result.scalars().all()
        if word_id in progress_word_ids
    )

    active_sessions_result = await db.execute(
        select(LearningSession.words_used_actively).where(
            and_(
                LearningSession.child_id == child_id,
                LearningSession.words_used_actively.is_not(None),
            )
        )
    )
    for words_used_actively in active_sessions_result.scalars().all():
        if not words_used_actively:
            continue

        active_word_ids.update(
            word_id for word_id in words_used_actively
            if word_id in progress_word_ids
        )

    active_vocab = len(active_word_ids)
    passive_vocab = total_words - active_vocab

    average_exposures_per_word = sum(
        p.exposure_count or 0 for p in all_progress
    ) / max(total_words, 1)

    weekly_dates = [date.today() - timedelta(days=offset) for offset in range(6, -1, -1)]
    weekly_counts = {day: 0 for day in weekly_dates}
    for progress in all_progress:
        if progress.last_practiced is None:
            continue

        practiced_day = progress.last_practiced.date()
        if practiced_day in weekly_counts:
            weekly_counts[practiced_day] += 1

    weekly_progress = [weekly_counts[day] for day in weekly_dates]

    modality_coverage_total = 0.0
    modality_tracked_words = 0
    for progress in all_progress:
        modalities_used = 0
        if (progress.visual_exposures or 0) > 0:
            modalities_used += 1
        if (progress.auditory_exposures or 0) > 0:
            modalities_used += 1
        if (progress.kinesthetic_exposures or 0) > 0:
            modalities_used += 1

        if modalities_used == 0:
            continue

        modality_tracked_words += 1
        modality_coverage_total += modalities_used / 3

    multi_sensory_engagement = round(
        (modality_coverage_total / max(modality_tracked_words, 1)) * 100,
        1,
    ) if modality_tracked_words > 0 else 0.0

    category_progress_result = await db.execute(
        select(
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            Category.name_cantonese.label("category_name_cantonese"),
            func.count(WordProgress.id).label("learned_words"),
            func.count(WordProgress.id).filter(
                WordProgress.mastered.is_(True)
            ).label("mastered_words"),
        )
        .select_from(WordProgress)
        .join(Word, WordProgress.word_id == Word.id)
        .join(Category, Word.category == Category.id)
        .where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.exposure_count >= 1,
                Word.is_active == True,
                Category.is_active == True,
            )
        )
        .group_by(Category.id, Category.name, Category.name_cantonese)
    )

    learned_category_rows = category_progress_result.all()
    category_progress = []
    if learned_category_rows:
        category_ids = [row.category_id for row in learned_category_rows]
        total_words_result = await db.execute(
            select(
                Word.category.label("category_id"),
                func.count(Word.id).label("total_words"),
            )
            .where(
                and_(
                    Word.category.in_(category_ids),
                    Word.is_active == True,
                )
            )
            .group_by(Word.category)
        )
        total_words_by_category = {
            row.category_id: row.total_words for row in total_words_result.all()
        }

        for row in learned_category_rows:
            total_for_category = total_words_by_category.get(row.category_id, 0)
            progress_percentage = round(
                ((row.mastered_words or 0) / total_for_category) * 100,
            ) if total_for_category > 0 else 0
            category_progress.append(
                {
                    "category": row.category_name_cantonese or row.category_name,
                    "progress": int(progress_percentage),
                    "mastered": row.mastered_words or 0,
                    "total": total_for_category,
                }
            )
    
    return {
        "total_words": total_words,
        "mastered_words": mastered_words,
        "active_vocabulary": active_vocab,
        "passive_vocabulary": passive_vocab,
        "weekly_progress": weekly_progress,
        "streak_days": child.current_streak,
        "category_progress": category_progress,
        "average_exposures_per_word": average_exposures_per_word,
        "multi_sensory_engagement": multi_sensory_engagement,
    }


@router.get("/{child_id}/usage-status", response_model=LearningControlStatusResponse)
async def get_learning_control_status(
    child_id: str,
    local_date: date | None = Query(default=None),
    timezone_offset_minutes: int = Query(default=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Return today's learning time plus the effective reminder and limit state."""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()

    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    resolved_day, day_start_utc, day_end_utc = _build_local_day_window(
        local_day=local_date,
        timezone_offset_minutes=timezone_offset_minutes,
    )
    now_utc = datetime.now(timezone.utc)

    control_result = await db.execute(
        select(ParentalControl).where(ParentalControl.child_id == child_id)
    )
    control = control_result.scalar_one_or_none()

    sessions_result = await db.execute(
        select(LearningSession).where(
            and_(
                LearningSession.child_id == child_id,
                LearningSession.start_time < day_end_utc,
                or_(
                    LearningSession.end_time.is_(None),
                    LearningSession.end_time > day_start_utc,
                ),
            )
        )
    )
    sessions = sessions_result.scalars().all()

    session_intervals: List[tuple[datetime, datetime]] = []
    active_session_intervals: List[tuple[datetime, datetime]] = []
    overlapping_session_count = 0

    for session in sessions:
        session_start = max(_ensure_utc(session.start_time), day_start_utc)
        raw_session_end = session.end_time or now_utc
        session_end = min(_ensure_utc(raw_session_end), day_end_utc, now_utc)

        if session_end <= session_start:
            continue

        session_intervals.append((session_start, session_end))
        overlapping_session_count += 1

        if session.end_time is None:
            active_session_intervals.append((session_start, session_end))

    today_minutes = _sum_interval_minutes(session_intervals)
    active_session_minutes = _sum_interval_minutes(active_session_intervals)

    time_limits_enabled = bool(control.enable_time_limits) if control else False
    daily_limit = control.daily_screen_time_limit if control else None
    warning_threshold = control.screen_time_warning_threshold if control else 20
    remaining_minutes = None
    limit_reached = False
    warning_reached = False

    if time_limits_enabled and daily_limit is not None:
        remaining_minutes = max(daily_limit - today_minutes, 0)
        limit_reached = today_minutes >= daily_limit
        warning_reached = not limit_reached and remaining_minutes <= warning_threshold

    return LearningControlStatusResponse(
        child_id=child_id,
        local_date=resolved_day,
        today_minutes=today_minutes,
        active_session_minutes=active_session_minutes,
        session_count=overlapping_session_count,
        has_activity_today=today_minutes > 0,
        daily_screen_time_limit=daily_limit,
        screen_time_warning_threshold=warning_threshold,
        enable_time_limits=time_limits_enabled,
        remaining_minutes=remaining_minutes,
        warning_reached=warning_reached,
        limit_reached=limit_reached,
        daily_reminder_enabled=control.daily_reminder_enabled if control else True,
        daily_reminder_time=control.daily_reminder_time if control else "18:00",
    )
