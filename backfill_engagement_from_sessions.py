"""Backfill derived engagement metrics from historical learning sessions.

Usage:
  python backfill_engagement_from_sessions.py
  python backfill_engagement_from_sessions.py --days 180
  python backfill_engagement_from_sessions.py --days 180 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.api.endpoints.progress import _derive_engagement_level, _engagement_to_score
from app.db.session import AsyncSessionLocal
from app.models.analytics import LearningSession
from app.models.analytics_foundation import AnalyticsEventLog, ChildDayAnalytics
from app.models.user import Child
from app.services.analytics_foundation import AnalyticsEventType, resolve_age_band


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _duration_minutes(start_time: datetime, end_time: datetime) -> int:
    seconds = max((end_time - start_time).total_seconds(), 0)
    if seconds <= 0:
        return 0
    return max(1, int((seconds + 59) // 60))


async def backfill(days: int, dry_run: bool) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        sessions_result = await db.execute(
            select(LearningSession).where(
                or_(
                    LearningSession.end_time >= cutoff,
                    and_(
                        LearningSession.end_time.is_(None),
                        LearningSession.start_time >= cutoff,
                    ),
                )
            )
        )
        sessions = sessions_result.scalars().all()

        event_rows_result = await db.execute(
            select(AnalyticsEventLog).where(
                AnalyticsEventLog.event_type == AnalyticsEventType.SESSION_ENDED.value,
                AnalyticsEventLog.occurred_at >= cutoff,
                AnalyticsEventLog.idempotency_key.like("session-ended:%"),
            )
        )
        event_rows = event_rows_result.scalars().all()
        event_by_key = {
            row.idempotency_key: row
            for row in event_rows
            if row.idempotency_key
        }

        child_ids = {session.child_id for session in sessions if session.child_id}
        children_result = await db.execute(select(Child).where(Child.id.in_(child_ids)))
        children = {child.id: child for child in children_result.scalars().all()}

        session_updates = 0
        event_updates = 0
        day_rollups: dict[tuple[str, date], dict[str, float]] = {}

        for session in sessions:
            start_at = _ensure_utc(session.start_time)
            end_at = _ensure_utc(session.end_time) or start_at
            if start_at is None or end_at is None:
                continue

            duration_minutes = int(session.duration_minutes or 0)
            if duration_minutes <= 0:
                duration_minutes = _duration_minutes(start_at, end_at)

            words_encountered_count = len(session.words_encountered or [])
            words_used_actively_count = len(session.words_used_actively or [])
            activities_count = len(session.activities_completed or [])
            interactions_count = int(session.interactions_count or 0)

            derived_level = _derive_engagement_level(
                duration_minutes=duration_minutes,
                interactions_count=interactions_count,
                activities_count=activities_count,
                words_used_actively_count=words_used_actively_count,
                words_encountered_count=words_encountered_count,
            )

            current_level = str(
                getattr(session.engagement_level, "value", session.engagement_level)
            ).lower()
            if current_level != derived_level:
                session.engagement_level = derived_level
                session_updates += 1

            score = _engagement_to_score(derived_level)
            activity_day = end_at.date()
            day_key = (session.child_id, activity_day)
            rollup = day_rollups.setdefault(day_key, {"sum": 0.0, "count": 0.0})
            rollup["sum"] += score
            rollup["count"] += 1

            event_key = f"session-ended:{session.id}"
            event_row = event_by_key.get(event_key)
            if event_row is not None:
                payload = dict(event_row.payload or {})
                payload["duration_minutes"] = duration_minutes
                payload["engagement_score"] = score
                payload["engagement_level_derived"] = derived_level
                payload.setdefault("engagement_level_reported", current_level)
                payload["words_encountered_count"] = words_encountered_count
                payload["words_used_actively_count"] = words_used_actively_count
                payload["activities_count"] = activities_count
                payload["interactions_count"] = interactions_count
                event_row.payload = payload
                event_updates += 1

        child_day_updates = 0
        child_day_creates = 0
        for (child_id, activity_day), values in day_rollups.items():
            result = await db.execute(
                select(ChildDayAnalytics).where(
                    ChildDayAnalytics.child_id == child_id,
                    ChildDayAnalytics.activity_day == activity_day,
                )
            )
            row = result.scalar_one_or_none()

            if row is None:
                child = children.get(child_id)
                row = ChildDayAnalytics(
                    child_id=child_id,
                    activity_day=activity_day,
                    age_band=resolve_age_band(child.age) if child else "unknown",
                )
                db.add(row)
                child_day_creates += 1

            count = int(values["count"])
            total = float(values["sum"])
            row.engagement_events_count = count
            row.engagement_score_sum = round(total, 4)
            row.engagement_score_avg = round(total / max(count, 1), 4)
            child_day_updates += 1

        if dry_run:
            await db.rollback()
            print("[backfill-engagement] dry-run completed (no changes committed)")
        else:
            await db.commit()
            print("[backfill-engagement] committed")

        print(f"[backfill-engagement] sessions_scanned={len(sessions)}")
        print(f"[backfill-engagement] session_level_updates={session_updates}")
        print(f"[backfill-engagement] event_payload_updates={event_updates}")
        print(f"[backfill-engagement] child_day_updates={child_day_updates}")
        print(f"[backfill-engagement] child_day_creates={child_day_creates}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill derived engagement from sessions")
    parser.add_argument("--days", type=int, default=90, help="Lookback days")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(backfill(days=max(args.days, 1), dry_run=args.dry_run))
