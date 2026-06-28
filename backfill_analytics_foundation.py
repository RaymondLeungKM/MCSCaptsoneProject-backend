"""
Backfill analytics foundation tables from existing source tables.

Usage:
  python backfill_analytics_foundation.py
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.analytics import LearningSession
from app.models.content import MissionAssignment
from app.models.daily_words import DailyWordTracking
from app.services.analytics_foundation import (
    AnalyticsEventInput,
    AnalyticsEventType,
    write_analytics_event,
)


def _to_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def backfill(days: int = 90) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        sessions_result = await db.execute(
            select(LearningSession).where(LearningSession.start_time >= cutoff)
        )
        sessions = sessions_result.scalars().all()

        print(f"[backfill] learning sessions: {len(sessions)}")
        for session in sessions:
            occurred_at = _to_utc_datetime(session.end_time or session.start_time)
            if occurred_at is None:
                continue

            duration = session.duration_minutes or 0
            engagement_score = (
                0.9
                if str(getattr(session.engagement_level, "value", session.engagement_level)).lower() == "high"
                else 0.65
                if str(getattr(session.engagement_level, "value", session.engagement_level)).lower() == "medium"
                else 0.35
            )

            await write_analytics_event(
                db,
                AnalyticsEventInput(
                    event_type=AnalyticsEventType.SESSION_ENDED,
                    child_id=session.child_id,
                    occurred_at=occurred_at,
                    source="backfill",
                    idempotency_key=f"backfill:session-ended:{session.id}",
                    payload={
                        "duration_minutes": duration,
                        "engagement_score": engagement_score,
                    },
                ),
            )

        tracking_result = await db.execute(
            select(DailyWordTracking).where(DailyWordTracking.date >= cutoff)
        )
        tracking_rows = tracking_result.scalars().all()
        print(f"[backfill] daily tracking rows: {len(tracking_rows)}")

        for row in tracking_rows:
            occurred_at = _to_utc_datetime(row.date)
            if occurred_at is None:
                continue

            await write_analytics_event(
                db,
                AnalyticsEventInput(
                    event_type=AnalyticsEventType.CONTENT_WORD_EXPOSED,
                    child_id=row.child_id,
                    word_id=row.word_id,
                    content_type="word",
                    content_id=row.word_id,
                    occurred_at=occurred_at,
                    source="backfill",
                    idempotency_key=f"backfill:word-exposed:{row.id}",
                    payload={
                        "exposure_delta": max(row.exposure_count or 1, 1),
                        "word_exposure_delta": max(row.exposure_count or 1, 1),
                    },
                ),
            )

            if row.used_actively or (row.mastery_confidence or 0.0) >= 0.8:
                await write_analytics_event(
                    db,
                    AnalyticsEventInput(
                        event_type=AnalyticsEventType.CONTENT_WORD_MASTERED,
                        child_id=row.child_id,
                        word_id=row.word_id,
                        content_type="word",
                        content_id=row.word_id,
                        occurred_at=occurred_at,
                        source="backfill",
                        idempotency_key=f"backfill:word-mastered:{row.id}",
                        payload={
                            "completion_delta": 1,
                            "success_delta": 1,
                            "mastery_delta": float(row.mastery_confidence or 1.0),
                            "word_mastery_delta": 1,
                        },
                    ),
                )

        assignment_result = await db.execute(
            select(MissionAssignment).where(MissionAssignment.created_at >= cutoff)
        )
        assignments = assignment_result.scalars().all()
        print(f"[backfill] mission assignments: {len(assignments)}")

        for assignment in assignments:
            created_at = _to_utc_datetime(assignment.created_at)
            if created_at is None:
                continue

            await write_analytics_event(
                db,
                AnalyticsEventInput(
                    event_type=AnalyticsEventType.MISSION_ASSIGNED,
                    child_id=assignment.child_id,
                    mission_id=assignment.mission_id,
                    occurred_at=created_at,
                    source="backfill",
                    idempotency_key=f"backfill:mission-assigned:{assignment.id}",
                    payload={
                        "assignment_id": assignment.id,
                        "context": str(getattr(assignment, "context", "") or ""),
                    },
                ),
            )

            status_value = str(getattr(assignment.status, "value", assignment.status)).lower()
            if status_value == "completed":
                occurred = _to_utc_datetime(assignment.completed_at) or created_at
                await write_analytics_event(
                    db,
                    AnalyticsEventInput(
                        event_type=AnalyticsEventType.MISSION_COMPLETED,
                        child_id=assignment.child_id,
                        mission_id=assignment.mission_id,
                        occurred_at=occurred,
                        source="backfill",
                        idempotency_key=f"backfill:mission-completed:{assignment.id}",
                        payload={
                            "assignment_id": assignment.id,
                            "context": str(getattr(assignment, "context", "") or ""),
                            "completion_minutes": None,
                        },
                    ),
                )
            elif status_value == "skipped":
                occurred = _to_utc_datetime(assignment.skipped_at) or created_at
                await write_analytics_event(
                    db,
                    AnalyticsEventInput(
                        event_type=AnalyticsEventType.MISSION_SKIPPED,
                        child_id=assignment.child_id,
                        mission_id=assignment.mission_id,
                        occurred_at=occurred,
                        source="backfill",
                        idempotency_key=f"backfill:mission-skipped:{assignment.id}",
                        payload={
                            "assignment_id": assignment.id,
                            "context": str(getattr(assignment, "context", "") or ""),
                        },
                    ),
                )
            elif status_value == "expired":
                occurred = _to_utc_datetime(assignment.expires_at) or created_at
                await write_analytics_event(
                    db,
                    AnalyticsEventInput(
                        event_type=AnalyticsEventType.MISSION_EXPIRED,
                        child_id=assignment.child_id,
                        mission_id=assignment.mission_id,
                        occurred_at=occurred,
                        source="backfill",
                        idempotency_key=f"backfill:mission-expired:{assignment.id}",
                        payload={
                            "assignment_id": assignment.id,
                            "context": str(getattr(assignment, "context", "") or ""),
                        },
                    ),
                )

    print("[backfill] completed")


if __name__ == "__main__":
    asyncio.run(backfill())