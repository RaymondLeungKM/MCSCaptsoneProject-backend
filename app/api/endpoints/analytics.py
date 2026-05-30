"""
Analytics endpoints
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.analytics import DailyStatsResponse, ChildAchievementResponse
from app.models.analytics import ChildAchievement, Achievement, LearningSession
from app.models.daily_words import DailyWordTracking
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()

MAX_SESSION_MINUTES = 90
HKT = timezone(timedelta(hours=8), name="HKT")


def _local_today() -> date:
    return datetime.now(HKT).date()


def _local_day_bounds(local_day: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(local_day, time.min, tzinfo=HKT)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _local_date_window(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    start_at, _ = _local_day_bounds(start_day)
    end_at, _ = _local_day_bounds(end_day + timedelta(days=1))
    return start_at, end_at


def _normalize_activity_day(raw_value: object) -> date | None:
    if isinstance(raw_value, datetime):
        return _ensure_utc(raw_value).astimezone(HKT).date()

    if isinstance(raw_value, date):
        return raw_value

    if isinstance(raw_value, str):
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            try:
                return _normalize_activity_day(
                    datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                )
            except ValueError:
                return None

    return None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _engagement_to_score(raw_value: object) -> float:
    normalized = getattr(raw_value, "value", raw_value)
    if isinstance(normalized, str):
        normalized = normalized.lower()

    if normalized == "high":
        return 0.9
    if normalized == "medium":
        return 0.65
    if normalized == "low":
        return 0.35

    return 0.0


def _rounded_duration_minutes(start_time: datetime, end_time: datetime) -> int:
    total_seconds = max((end_time - start_time).total_seconds(), 0)
    if total_seconds <= 0:
        return 0
    return max(1, int((total_seconds + 59) // 60))


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda interval: interval[0])
    merged: list[tuple[datetime, datetime]] = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        previous_start, previous_end = merged[-1]
        if current_start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, current_end))
            continue

        merged.append((current_start, current_end))

    return merged


def _total_interval_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    return sum(
        max((end_time - start_time).total_seconds(), 0.0)
        for start_time, end_time in _merge_intervals(intervals)
    )


def _rounded_minutes_from_total_seconds(
    total_seconds: float,
    *,
    has_words: bool = False,
) -> int:
    if total_seconds <= 0:
        return 0

    rounded_minutes = int((total_seconds + 30) // 60)
    if rounded_minutes > 0:
        return rounded_minutes

    if has_words:
        return 1

    return 0


def _resolved_session_window(
    session: LearningSession,
    *,
    now_utc: datetime,
) -> tuple[datetime, datetime] | None:
    if not session.start_time:
        return None

    if session.duration_minutes is not None and session.duration_minutes > MAX_SESSION_MINUTES:
        return None

    session_start = _ensure_utc(session.start_time)
    raw_session_end = session.end_time or now_utc
    session_end = min(
        _ensure_utc(raw_session_end),
        session_start + timedelta(minutes=MAX_SESSION_MINUTES),
    )

    if session_end <= session_start:
        return None

    return session_start, session_end


def _split_session_minutes_by_day(
    session: LearningSession,
    *,
    now_utc: datetime,
) -> dict[date, int]:
    resolved_window = _resolved_session_window(session, now_utc=now_utc)
    if resolved_window is None:
        return {}

    session_start, session_end = resolved_window
    total_minutes = _rounded_duration_minutes(session_start, session_end)
    seconds_by_day: dict[date, float] = {}
    cursor = session_start

    while cursor < session_end:
        next_day_start = (
            datetime.combine(cursor.date(), time.min).replace(tzinfo=cursor.tzinfo)
            + timedelta(days=1)
        )
        segment_end = min(session_end, next_day_start)
        seconds_by_day[cursor.date()] = seconds_by_day.get(cursor.date(), 0.0) + max(
            (segment_end - cursor).total_seconds(),
            0.0,
        )
        cursor = segment_end

    minutes_by_day = {
        tracked_day: int(total_seconds // 60)
        for tracked_day, total_seconds in seconds_by_day.items()
    }
    assigned_minutes = sum(minutes_by_day.values())

    if total_minutes > assigned_minutes:
        end_day = session_end.date()
        minutes_by_day[end_day] = minutes_by_day.get(end_day, 0) + (
            total_minutes - assigned_minutes
        )

    return minutes_by_day


def _split_session_intervals_by_day(
    session: LearningSession,
    *,
    now_utc: datetime,
) -> dict[date, list[tuple[datetime, datetime]]]:
    resolved_window = _resolved_session_window(session, now_utc=now_utc)
    if resolved_window is None:
        return {}

    session_start, session_end = resolved_window
    intervals_by_day: dict[date, list[tuple[datetime, datetime]]] = {}
    cursor = session_start

    while cursor < session_end:
        local_cursor = cursor.astimezone(HKT)
        next_local_day_start = datetime.combine(
            local_cursor.date() + timedelta(days=1),
            time.min,
            tzinfo=HKT,
        ).astimezone(timezone.utc)
        segment_end = min(session_end, next_local_day_start)
        intervals_by_day.setdefault(local_cursor.date(), []).append(
            (cursor, segment_end)
        )
        cursor = segment_end

    return intervals_by_day


@router.get("/{child_id}/daily", response_model=List[DailyStatsResponse])
async def get_daily_stats(
    child_id: str,
    days: int = 7,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get daily statistics for a child"""
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

    resolved_days = max(days, 1)
    today = _local_today()
    start_day = today - timedelta(days=resolved_days - 1)
    start_at, end_at = _local_date_window(start_day, today)

    tracking_result = await db.execute(
        select(DailyWordTracking).where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_at,
                DailyWordTracking.date < end_at,
            )
        )
    )

    session_result = await db.execute(
        select(LearningSession).where(
            and_(
                LearningSession.child_id == child_id,
                LearningSession.start_time < end_at,
                or_(
                    LearningSession.end_time.is_(None),
                    LearningSession.end_time > start_at,
                ),
            )
        )
    )
    now_utc = datetime.now(timezone.utc)

    daily_buckets: dict[date, dict[str, object]] = {
        start_day + timedelta(days=offset): {
            "word_ids": set(),
            "mastered_word_ids": set(),
            "total_minutes": 0,
            "activities_completed": 0,
            "xp_earned": 0,
            "session_count": 0,
            "engagement_total": 0.0,
            "engagement_count": 0,
            "session_intervals": [],
        }
        for offset in range(resolved_days)
    }
    session_windows: list[tuple[datetime, datetime]] = []

    for tracking in tracking_result.scalars().all():
        tracked_day = _normalize_activity_day(tracking.date)
        if tracked_day not in daily_buckets:
            continue

        bucket = daily_buckets[tracked_day]
        word_ids = bucket["word_ids"]
        mastered_word_ids = bucket["mastered_word_ids"]

        if tracking.word_id:
            word_ids.add(tracking.word_id)
            if tracking.used_actively or (tracking.mastery_confidence or 0) >= 0.8:
                mastered_word_ids.add(tracking.word_id)

    for session in session_result.scalars().all():
        resolved_window = _resolved_session_window(session, now_utc=now_utc)
        if resolved_window is None:
            continue

        session_windows.append(resolved_window)

        session_day = _normalize_activity_day(session.start_time)
        if session_day in daily_buckets:
            bucket = daily_buckets[session_day]
            word_ids = bucket["word_ids"]
            mastered_word_ids = bucket["mastered_word_ids"]

            for word_id in session.words_encountered or []:
                if word_id:
                    word_ids.add(word_id)

            for word_id in session.words_used_actively or []:
                if word_id:
                    mastered_word_ids.add(word_id)

            bucket["activities_completed"] += len(session.activities_completed or [])
            bucket["xp_earned"] += session.xp_earned or 0
            bucket["engagement_total"] += _engagement_to_score(session.engagement_level)
            bucket["engagement_count"] += 1

        for tracked_day, intervals in _split_session_intervals_by_day(
            session,
            now_utc=now_utc,
        ).items():
            if tracked_day not in daily_buckets:
                continue

            daily_buckets[tracked_day]["session_intervals"].extend(intervals)

    for session_start, _ in _merge_intervals(session_windows):
        session_day = _normalize_activity_day(session_start)
        if session_day not in daily_buckets:
            continue

        daily_buckets[session_day]["session_count"] += 1

    daily_goal = max(child.daily_goal or 0, 0)
    response: list[dict[str, object]] = []

    for tracked_day in sorted(daily_buckets.keys()):
        bucket = daily_buckets[tracked_day]
        words_encountered = len(bucket["word_ids"])
        words_mastered = len(bucket["mastered_word_ids"])
        engagement_count = bucket["engagement_count"]
        total_minutes = _rounded_minutes_from_total_seconds(
            _total_interval_seconds(bucket["session_intervals"]),
            has_words=words_encountered > 0,
        )
        session_count = (
            bucket["session_count"]
            if total_minutes > 0 or words_encountered > 0
            else 0
        )
        visible_engagement_count = (
            engagement_count
            if total_minutes > 0 or words_encountered > 0
            else 0
        )

        if daily_goal > 0:
            daily_goal_progress = min(
                int(round((words_encountered / daily_goal) * 100)),
                100,
            )
            goal_achieved = words_encountered >= daily_goal
        else:
            daily_goal_progress = 0
            goal_achieved = False

        response.append(
            {
                "date": tracked_day,
                "total_minutes": total_minutes,
                "words_encountered": words_encountered,
                "words_mastered": words_mastered,
                "activities_completed": bucket["activities_completed"],
                "xp_earned": bucket["xp_earned"],
                "session_count": session_count,
                "average_engagement": round(
                    bucket["engagement_total"] / visible_engagement_count,
                    2,
                ) if visible_engagement_count > 0 else 0.0,
                "daily_goal_progress": daily_goal_progress,
                "goal_achieved": goal_achieved,
            }
        )

    return response


@router.get("/{child_id}/achievements", response_model=List[ChildAchievementResponse])
async def get_child_achievements(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all achievements earned by a child"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get child's achievements with achievement details
    result = await db.execute(
        select(ChildAchievement, Achievement)
        .join(Achievement, ChildAchievement.achievement_id == Achievement.id)
        .where(ChildAchievement.child_id == child_id)
    )
    
    achievements = []
    for child_achievement, achievement in result:
        achievements.append({
            "achievement_id": achievement.id,
            "achievement_name": achievement.name,
            "achievement_icon": achievement.icon,
            "earned_at": child_achievement.earned_at,
            "viewed": child_achievement.viewed
        })
    
    return achievements
