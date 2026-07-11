"""
Progress tracking endpoints
"""
from datetime import date, datetime, time, timedelta, timezone
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from app.core.local_time import get_client_local_day
from app.core.security import get_current_active_user
from app.services.child_metrics import sync_child_metrics
from app.services.analytics_foundation import (
    AnalyticsEventInput,
    AnalyticsEventType,
    write_analytics_event,
)

router = APIRouter()

MAX_SESSION_MINUTES = 90


def _engagement_to_score(engagement_level: object) -> float:
    value = getattr(engagement_level, "value", engagement_level)
    if isinstance(value, str):
        normalized = value.lower()
    else:
        normalized = str(value).lower()

    if normalized == "high":
        return 0.9
    if normalized == "medium":
        return 0.65
    if normalized == "low":
        return 0.35
    return 0.0


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _has_recorded_word_exposure(progress: WordProgress) -> bool:
    return (progress.exposure_count or 0) >= 1


def _derive_engagement_level(
    *,
    duration_minutes: int,
    interactions_count: int,
    activities_count: int,
    words_used_actively_count: int,
    words_encountered_count: int,
) -> str:
    safe_duration = max(duration_minutes, 0)
    safe_interactions = max(interactions_count, 0)
    safe_activities = max(activities_count, 0)
    safe_words_used = max(words_used_actively_count, 0)
    safe_words_encountered = max(words_encountered_count, 0)

    duration_norm = _clamp(safe_duration / 20.0)
    interactions_per_minute = safe_interactions / max(safe_duration, 1)
    interaction_norm = _clamp(interactions_per_minute / 2.0)
    activities_norm = _clamp(safe_activities / 3.0)
    active_usage_norm = _clamp(safe_words_used / max(safe_words_encountered, 1))

    engagement_index = (
        interaction_norm * 0.40
        + activities_norm * 0.25
        + active_usage_norm * 0.20
        + duration_norm * 0.15
    )

    if engagement_index >= 0.70:
        return "high"
    if engagement_index >= 0.38:
        return "medium"
    return "low"


def _is_my_collection_category_name(
    category_name: str | None,
    category_name_cantonese: str | None,
) -> bool:
    normalized_name = (category_name or "").strip().lower()
    normalized_cantonese = (category_name_cantonese or "").strip()
    return normalized_name == "my collection" or normalized_cantonese in {
        "我的",
        "我的收藏",
    }


async def _get_child_owned_collection_progress_counts(
    child_id: str,
    db: AsyncSession,
) -> tuple[int, int]:
    total_words_result = await db.execute(
        select(func.count(Word.id)).where(
            Word.is_active == True,
            Word.created_by_child_id == child_id,
        )
    )
    total_words = total_words_result.scalar_one() or 0

    if total_words == 0:
        return 0, 0

    mastered_words_result = await db.execute(
        select(func.count(WordProgress.id))
        .select_from(Word)
        .join(
            WordProgress,
            and_(
                WordProgress.word_id == Word.id,
                WordProgress.child_id == child_id,
                WordProgress.mastered.is_(True),
            ),
        )
        .where(
            Word.is_active == True,
            Word.created_by_child_id == child_id,
        )
    )
    mastered_words = mastered_words_result.scalar_one() or 0
    return total_words, mastered_words


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duration_minutes(start_time: datetime, end_time: datetime) -> int:
    total_seconds = max((end_time - start_time).total_seconds(), 0)
    if total_seconds <= 0:
        return 0
    return max(1, int((total_seconds + 59) // 60))


def _bounded_duration_minutes(start_time: datetime, end_time: datetime) -> int:
    return min(_duration_minutes(start_time, end_time), MAX_SESSION_MINUTES)


def _auto_closed_duration_minutes(start_time: datetime, end_time: datetime) -> int:
    raw_duration_minutes = _duration_minutes(start_time, end_time)
    if raw_duration_minutes > MAX_SESSION_MINUTES:
        return 0
    return raw_duration_minutes


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
        open_session.duration_minutes = _auto_closed_duration_minutes(
            open_start,
            closed_at,
        )
    
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

    await write_analytics_event(
        db,
        AnalyticsEventInput(
            event_type=AnalyticsEventType.SESSION_STARTED,
            child_id=session.child_id,
            parent_id=current_user.id,
            occurred_at=_ensure_utc(session.start_time),
            source="api.progress.start_learning_session",
            idempotency_key=f"session-started:{session.id}",
            payload={
                "session_id": session.id,
                "words_encountered_count": len(session.words_encountered or []),
                "activities_count": len(session.activities_completed or []),
            },
        ),
    )
    
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
    reported_engagement_level = getattr(
        session_data.engagement_level,
        "value",
        session_data.engagement_level,
    )
    session.interactions_count = session_data.interactions_count
    
    # Calculate duration
    if session.end_time and session.start_time:
        session.duration_minutes = _bounded_duration_minutes(
            _ensure_utc(session.start_time),
            _ensure_utc(session.end_time),
        )

    words_encountered_count = len(session.words_encountered or [])
    words_used_actively_count = len(session.words_used_actively or [])
    activities_count = len(session.activities_completed or [])
    derived_engagement_level = _derive_engagement_level(
        duration_minutes=int(session.duration_minutes or 0),
        interactions_count=int(session.interactions_count or 0),
        activities_count=activities_count,
        words_used_actively_count=words_used_actively_count,
        words_encountered_count=words_encountered_count,
    )
    session.engagement_level = derived_engagement_level
    
    # Calculate XP earned
    session.xp_earned = len(session.words_encountered) * 10 + session.interactions_count * 5
    
    await db.commit()
    await db.refresh(session)

    await write_analytics_event(
        db,
        AnalyticsEventInput(
            event_type=AnalyticsEventType.SESSION_ENDED,
            child_id=session.child_id,
            parent_id=current_user.id,
            occurred_at=_ensure_utc(session.end_time) if session.end_time else datetime.now(timezone.utc),
            source="api.progress.end_learning_session",
            idempotency_key=f"session-ended:{session.id}",
            payload={
                "session_id": session.id,
                "duration_minutes": int(session.duration_minutes or 0),
                "engagement_score": _engagement_to_score(session.engagement_level),
                "engagement_level_reported": reported_engagement_level,
                "engagement_level_derived": derived_engagement_level,
                "xp_earned": int(session.xp_earned or 0),
                "words_encountered_count": words_encountered_count,
                "words_used_actively_count": words_used_actively_count,
                "activities_count": activities_count,
                "interactions_count": int(session.interactions_count or 0),
            },
        ),
    )
    
    return session


@router.get("/{child_id}/stats", response_model=ProgressStatsResponse)
async def get_progress_stats(
    child_id: str,
    request: Request,
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

    client_local_day = get_client_local_day(request)
    if await sync_child_metrics(db, child, as_of=client_local_day.date):
        await db.commit()
    
    # Get word progress stats
    result = await db.execute(
        select(WordProgress).where(WordProgress.child_id == child_id)
    )
    all_progress = result.scalars().all()

    encountered_progress = [
        progress for progress in all_progress if _has_recorded_word_exposure(progress)
    ]

    mastered_words = sum(1 for p in encountered_progress if p.mastered)
    total_words = len(encountered_progress)
    
    # Calculate active vs passive vocabulary from explicit output signals.
    progress_word_ids = {p.word_id for p in encountered_progress}

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
        p.exposure_count or 0 for p in encountered_progress
    ) / max(total_words, 1)

    today = client_local_day.date
    week_start = today - timedelta(days=today.weekday())
    week_dates = [week_start + timedelta(days=offset) for offset in range(7)]
    weekly_counts = {day: 0 for day in week_dates}

    week_start_at, week_end_at = client_local_day.utc_bounds(
        week_start, week_start + timedelta(days=6)
    )
    weekly_tracking_result = await db.execute(
        select(DailyWordTracking.date, DailyWordTracking.word_id)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= week_start_at,
                DailyWordTracking.date < week_end_at,
            )
        )
    )

    weekly_word_ids: dict[date, set[str]] = {}
    for tracked_at, word_id in weekly_tracking_result.all():
        if not tracked_at or not word_id:
            continue
        tracked_day = client_local_day.date_for_timestamp(tracked_at)
        if tracked_day in weekly_counts:
            weekly_word_ids.setdefault(tracked_day, set()).add(word_id)

    for tracked_day, word_ids in weekly_word_ids.items():
        weekly_counts[tracked_day] = len(word_ids)

    weekly_progress = [weekly_counts[day] for day in week_dates]

    modality_coverage_total = 0.0
    modality_tracked_words = 0
    for progress in encountered_progress:
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
            mastered_for_category = row.mastered_words or 0

            if _is_my_collection_category_name(
                row.category_name,
                row.category_name_cantonese,
            ):
                total_for_category, mastered_for_category = (
                    await _get_child_owned_collection_progress_counts(
                        child_id,
                        db,
                    )
                )
                if total_for_category == 0:
                    continue

            progress_percentage = round(
                (mastered_for_category / total_for_category) * 100,
            ) if total_for_category > 0 else 0
            category_progress.append(
                {
                    "category": row.category_name_cantonese or row.category_name,
                    "progress": int(progress_percentage),
                    "mastered": mastered_for_category,
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
