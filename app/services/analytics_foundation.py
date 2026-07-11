"""
P0 analytics foundation writer.

Provides a single event writer entrypoint that records canonical events and
updates aggregate fact tables with idempotency protection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_time import get_active_client_local_day
from app.models.analytics_foundation import (
    AnalyticsEventLog,
    ChildDayAnalytics,
    ContentPerformanceAnalytics,
    MissionOutcomeAnalytics,
)
from app.models.user import Child


class AnalyticsEventType(str, Enum):
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"

    REVISION_QUEUE_VIEWED = "revision.queue_viewed"
    REVISION_CARD_REVIEWED = "revision.card_reviewed"

    MISSION_ASSIGNED = "mission.assigned"
    MISSION_STARTED = "mission.started"
    MISSION_COMPLETED = "mission.completed"
    MISSION_SKIPPED = "mission.skipped"
    MISSION_EXPIRED = "mission.expired"

    CONTENT_WORD_EXPOSED = "content.word_exposed"
    CONTENT_WORD_MASTERED = "content.word_mastered"
    CONTENT_STORY_OPENED = "content.story_opened"
    CONTENT_STORY_COMPLETED = "content.story_completed"
    CONTENT_GAME_STARTED = "content.game_started"
    CONTENT_GAME_COMPLETED = "content.game_completed"


MISSION_STATUS_EVENTS = {
    AnalyticsEventType.MISSION_ASSIGNED: "assigned",
    AnalyticsEventType.MISSION_STARTED: "started",
    AnalyticsEventType.MISSION_COMPLETED: "completed",
    AnalyticsEventType.MISSION_SKIPPED: "skipped",
    AnalyticsEventType.MISSION_EXPIRED: "expired",
}


CONTENT_EXPOSURE_EVENTS = {
    AnalyticsEventType.CONTENT_WORD_EXPOSED,
    AnalyticsEventType.CONTENT_STORY_OPENED,
    AnalyticsEventType.CONTENT_GAME_STARTED,
}


CONTENT_COMPLETION_EVENTS = {
    AnalyticsEventType.CONTENT_WORD_MASTERED,
    AnalyticsEventType.CONTENT_STORY_COMPLETED,
    AnalyticsEventType.CONTENT_GAME_COMPLETED,
}


@dataclass
class AnalyticsEventInput:
    event_type: AnalyticsEventType | str
    child_id: str | None = None
    parent_id: str | None = None
    mission_id: str | None = None
    word_id: str | None = None
    category_id: str | None = None
    content_type: str | None = None
    content_id: str | None = None
    occurred_at: datetime | None = None
    source: str = "system"
    idempotency_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def resolve_age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age <= 4:
        return "3-4"
    if age <= 6:
        return "5-6"
    return "7+"


def _normalize_event_type(value: AnalyticsEventType | str) -> str:
    if isinstance(value, AnalyticsEventType):
        return value.value
    return str(value)


def _to_client_local_day(occurred_at: datetime) -> date:
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return get_active_client_local_day().date_for_timestamp(occurred_at)


async def _get_child_and_age_band(db: AsyncSession, child_id: str | None) -> tuple[Child | None, str]:
    if not child_id:
        return None, "unknown"

    result = await db.execute(select(Child).where(Child.id == child_id))
    child = result.scalar_one_or_none()
    if child is None:
        return None, "unknown"

    return child, resolve_age_band(child.age)


async def _get_or_create_child_day(
    db: AsyncSession,
    *,
    child_id: str,
    activity_day: date,
    age_band: str,
) -> ChildDayAnalytics:
    result = await db.execute(
        select(ChildDayAnalytics).where(
            ChildDayAnalytics.child_id == child_id,
            ChildDayAnalytics.activity_day == activity_day,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    row = ChildDayAnalytics(
        child_id=child_id,
        activity_day=activity_day,
        age_band=age_band,
    )
    db.add(row)
    await db.flush()
    return row


async def _get_or_create_content_performance(
    db: AsyncSession,
    *,
    child_id: str,
    activity_day: date,
    age_band: str,
    content_type: str,
    content_id: str,
    category_id: str | None,
    word_id: str | None,
) -> ContentPerformanceAnalytics:
    result = await db.execute(
        select(ContentPerformanceAnalytics).where(
            ContentPerformanceAnalytics.child_id == child_id,
            ContentPerformanceAnalytics.activity_day == activity_day,
            ContentPerformanceAnalytics.content_type == content_type,
            ContentPerformanceAnalytics.content_id == content_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    row = ContentPerformanceAnalytics(
        child_id=child_id,
        activity_day=activity_day,
        age_band=age_band,
        content_type=content_type,
        content_id=content_id,
        category_id=category_id,
        word_id=word_id,
    )
    db.add(row)
    await db.flush()
    return row


async def _apply_child_day_updates(
    db: AsyncSession,
    *,
    child_id: str,
    activity_day: date,
    age_band: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    row = await _get_or_create_child_day(
        db,
        child_id=child_id,
        activity_day=activity_day,
        age_band=age_band,
    )

    if event_type == AnalyticsEventType.CONTENT_WORD_EXPOSED.value:
        row.words_encountered += int(payload.get("word_exposure_delta", 1))

    if event_type == AnalyticsEventType.CONTENT_WORD_MASTERED.value:
        row.words_mastered += int(payload.get("word_mastery_delta", 1))

    if event_type == AnalyticsEventType.MISSION_ASSIGNED.value:
        row.mission_assigned_count += 1

    if event_type == AnalyticsEventType.MISSION_COMPLETED.value:
        row.mission_completed_count += 1

    if event_type == AnalyticsEventType.SESSION_ENDED.value:
        row.session_minutes_total += int(payload.get("duration_minutes", 0))
        engagement_score = float(payload.get("engagement_score", 0.0))
        row.engagement_score_sum += engagement_score
        row.engagement_events_count += 1
        if row.engagement_events_count > 0:
            row.engagement_score_avg = round(
                row.engagement_score_sum / row.engagement_events_count,
                4,
            )

    # Rolling active-day counts from aggregate rows for this child.
    window_7_start = activity_day - timedelta(days=6)
    window_28_start = activity_day - timedelta(days=27)
    active_filter = (
        (ChildDayAnalytics.words_encountered > 0)
        | (ChildDayAnalytics.words_mastered > 0)
        | (ChildDayAnalytics.mission_assigned_count > 0)
        | (ChildDayAnalytics.session_minutes_total > 0)
    )

    result_7 = await db.execute(
        select(func.count(ChildDayAnalytics.id)).where(
            ChildDayAnalytics.child_id == child_id,
            ChildDayAnalytics.activity_day >= window_7_start,
            ChildDayAnalytics.activity_day <= activity_day,
            active_filter,
        )
    )
    result_28 = await db.execute(
        select(func.count(ChildDayAnalytics.id)).where(
            ChildDayAnalytics.child_id == child_id,
            ChildDayAnalytics.activity_day >= window_28_start,
            ChildDayAnalytics.activity_day <= activity_day,
            active_filter,
        )
    )
    row.active_days_7d = result_7.scalar_one() or 0
    row.active_days_28d = result_28.scalar_one() or 0


async def _apply_mission_outcome_updates(
    db: AsyncSession,
    *,
    child_id: str,
    activity_day: date,
    age_band: str,
    event_type: str,
    event: AnalyticsEventInput,
) -> None:
    if event_type not in {item.value for item in MISSION_STATUS_EVENTS.keys()}:
        return

    event_enum = AnalyticsEventType(event_type)
    row = MissionOutcomeAnalytics(
        activity_day=activity_day,
        child_id=child_id,
        mission_id=event.mission_id,
        assignment_id=event.payload.get("assignment_id"),
        source=event.source,
        context=event.payload.get("context"),
        age_band=age_band,
        status=MISSION_STATUS_EVENTS[event_enum],
        completion_minutes=event.payload.get("completion_minutes"),
        is_cluster=bool(event.payload.get("is_cluster", False)),
        cluster_id=event.payload.get("cluster_id"),
        seed_word_id=event.payload.get("seed_word_id"),
        payload=event.payload,
    )
    db.add(row)


async def _apply_content_performance_updates(
    db: AsyncSession,
    *,
    child_id: str,
    activity_day: date,
    age_band: str,
    event_type: str,
    event: AnalyticsEventInput,
) -> None:
    if not event.content_type and not event.word_id:
        return

    normalized_content_type = event.content_type or "word"
    normalized_content_id = event.content_id or event.word_id
    if not normalized_content_id:
        return

    row = await _get_or_create_content_performance(
        db,
        child_id=child_id,
        activity_day=activity_day,
        age_band=age_band,
        content_type=normalized_content_type,
        content_id=normalized_content_id,
        category_id=event.category_id,
        word_id=event.word_id,
    )

    event_enum = AnalyticsEventType(event_type)
    if event_enum in CONTENT_EXPOSURE_EVENTS:
        row.exposure_count += int(event.payload.get("exposure_delta", 1))

    if event_enum in CONTENT_COMPLETION_EVENTS:
        row.completion_count += int(event.payload.get("completion_delta", 1))
        row.success_count += int(event.payload.get("success_delta", 1))
        row.post_exposure_mastery_delta += float(
            event.payload.get("mastery_delta", 0.0)
        )

    # Keep a simple proxy score bounded to [0, 1].
    if row.exposure_count > 0:
        completion_ratio = min(row.completion_count / row.exposure_count, 1.0)
    else:
        completion_ratio = 0.0
    success_ratio = (
        min(row.success_count / max(row.completion_count, 1), 1.0)
        if row.completion_count > 0
        else 0.0
    )
    mastery_component = min(max(row.post_exposure_mastery_delta, 0.0), 1.0)
    row.retention_proxy_score = round(
        0.45 * completion_ratio + 0.45 * success_ratio + 0.10 * mastery_component,
        4,
    )


async def write_analytics_event(
    db: AsyncSession,
    event: AnalyticsEventInput,
) -> str | None:
    """
    Persist a canonical event and update foundation aggregates.

    Returns event id when written, or None when skipped due to idempotency.
    """
    event_type = _normalize_event_type(event.event_type)
    occurred_at = event.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    if event.idempotency_key:
        existing_result = await db.execute(
            select(AnalyticsEventLog.id).where(
                AnalyticsEventLog.idempotency_key == event.idempotency_key
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return None

    _, age_band = await _get_child_and_age_band(db, event.child_id)
    activity_day = _to_client_local_day(occurred_at)

    event_id = str(uuid.uuid4())
    log = AnalyticsEventLog(
        id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        child_id=event.child_id,
        parent_id=event.parent_id,
        mission_id=event.mission_id,
        word_id=event.word_id,
        category_id=event.category_id,
        content_type=event.content_type,
        content_id=event.content_id,
        source=event.source,
        idempotency_key=event.idempotency_key,
        payload=event.payload,
    )
    db.add(log)

    if event.child_id:
        await _apply_child_day_updates(
            db,
            child_id=event.child_id,
            activity_day=activity_day,
            age_band=age_band,
            event_type=event_type,
            payload=event.payload,
        )

        await _apply_mission_outcome_updates(
            db,
            child_id=event.child_id,
            activity_day=activity_day,
            age_band=age_band,
            event_type=event_type,
            event=event,
        )

        await _apply_content_performance_updates(
            db,
            child_id=event.child_id,
            activity_day=activity_day,
            age_band=age_band,
            event_type=event_type,
            event=event,
        )

    await db.commit()
    return event_id