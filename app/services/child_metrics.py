from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import LearningSession
from app.models.daily_words import DailyWordTracking
from app.models.user import Child
from app.models.vocabulary import Word, WordProgress


def _normalize_activity_day(raw_value: object) -> date | None:
    if isinstance(raw_value, datetime):
        return raw_value.date()

    if isinstance(raw_value, date):
        return raw_value

    if isinstance(raw_value, str):
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            return None

    return None


def calculate_current_streak(
    activity_days: Iterable[date],
    *,
    as_of: date | None = None,
) -> int:
    target_day = as_of or datetime.now().date()
    normalized_days = {activity_day for activity_day in activity_days}

    if not normalized_days:
        return 0

    latest_activity_day = max(normalized_days)
    if latest_activity_day < target_day - timedelta(days=1):
        return 0

    streak = 0
    cursor = latest_activity_day

    while cursor in normalized_days:
        streak += 1
        cursor -= timedelta(days=1)

    return streak


async def derive_child_metrics(
    db: AsyncSession,
    child_id: str,
    *,
    as_of: date | None = None,
) -> dict[str, int]:
    target_day = as_of or datetime.now().date()
    start_of_day = datetime.combine(target_day, time.min)
    end_of_day = datetime.combine(target_day, time.max)

    words_learned_result = await db.execute(
        select(func.count(WordProgress.id)).where(
            and_(
                WordProgress.child_id == child_id,
                WordProgress.exposure_count >= 1,
            )
        )
    )
    words_learned = words_learned_result.scalar() or 0

    today_tracking_words_result = await db.execute(
        select(DailyWordTracking.word_id).where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.date >= start_of_day,
                DailyWordTracking.date <= end_of_day,
            )
        )
    )

    today_captured_words_result = await db.execute(
        select(Word.id).where(
            and_(
                Word.created_by_child_id == child_id,
                Word.is_active == True,
                Word.created_at >= start_of_day,
                Word.created_at <= end_of_day,
            )
        )
    )

    today_progress = len(
        set(today_tracking_words_result.scalars().all())
        | set(today_captured_words_result.scalars().all())
    )

    tracking_days_result = await db.execute(
        select(func.date(DailyWordTracking.date))
        .where(DailyWordTracking.child_id == child_id)
        .distinct()
    )
    session_days_result = await db.execute(
        select(func.date(LearningSession.start_time))
        .where(LearningSession.child_id == child_id)
        .distinct()
    )
    captured_days_result = await db.execute(
        select(func.date(Word.created_at))
        .where(
            and_(
                Word.created_by_child_id == child_id,
                Word.is_active == True,
            )
        )
        .distinct()
    )

    activity_days: set[date] = set()

    for raw_day in tracking_days_result.scalars().all():
        normalized_day = _normalize_activity_day(raw_day)
        if normalized_day is not None:
            activity_days.add(normalized_day)

    for raw_day in session_days_result.scalars().all():
        normalized_day = _normalize_activity_day(raw_day)
        if normalized_day is not None:
            activity_days.add(normalized_day)

    for raw_day in captured_days_result.scalars().all():
        normalized_day = _normalize_activity_day(raw_day)
        if normalized_day is not None:
            activity_days.add(normalized_day)

    return {
        "words_learned": words_learned,
        "today_progress": today_progress,
        "current_streak": calculate_current_streak(
            activity_days,
            as_of=target_day,
        ),
    }


async def sync_child_metrics(
    db: AsyncSession,
    child: Child,
    *,
    as_of: date | None = None,
) -> bool:
    metrics = await derive_child_metrics(db, child.id, as_of=as_of)
    changed = False

    if child.words_learned != metrics["words_learned"]:
        child.words_learned = metrics["words_learned"]
        changed = True

    if child.today_progress != metrics["today_progress"]:
        child.today_progress = metrics["today_progress"]
        changed = True

    if child.current_streak != metrics["current_streak"]:
        child.current_streak = metrics["current_streak"]
        changed = True

    return changed