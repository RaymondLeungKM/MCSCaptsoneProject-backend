"""
Check consistency between raw tables and P0 aggregate tables.

Usage:
  python check_analytics_aggregate_consistency.py
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select

from app.db.session import AsyncSessionLocal
from app.models.analytics import LearningSession
from app.models.analytics_foundation import ChildDayAnalytics
from app.models.content import MissionAssignment
from app.models.daily_words import DailyWordTracking


def _as_local_day(value) -> date | None:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date()
    if isinstance(value, date):
        return value
    return None


async def run_check(days: int = 7, tolerance: int = 2) -> int:
    start_day = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    mismatches = 0

    async with AsyncSessionLocal() as db:
        aggregate_result = await db.execute(
            select(ChildDayAnalytics).where(ChildDayAnalytics.activity_day >= start_day)
        )
        aggregate_rows = aggregate_result.scalars().all()

        for row in aggregate_rows:
            day_start = datetime.combine(row.activity_day, datetime.min.time(), tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)

            tracking_result = await db.execute(
                select(
                    func.count(DailyWordTracking.id),
                    func.coalesce(
                        func.sum(
                            case(
                                (DailyWordTracking.used_actively.is_(True), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(
                    and_(
                        DailyWordTracking.child_id == row.child_id,
                        DailyWordTracking.date >= day_start,
                        DailyWordTracking.date < day_end,
                    )
                )
            )
            tracked_words, tracked_mastered = tracking_result.one()

            mission_result = await db.execute(
                select(func.count(MissionAssignment.id)).where(
                    and_(
                        MissionAssignment.child_id == row.child_id,
                        MissionAssignment.assignment_date == row.activity_day,
                    )
                )
            )
            mission_assigned = mission_result.scalar_one() or 0

            session_result = await db.execute(
                select(func.coalesce(func.sum(LearningSession.duration_minutes), 0)).where(
                    and_(
                        LearningSession.child_id == row.child_id,
                        LearningSession.start_time >= day_start,
                        LearningSession.start_time < day_end,
                    )
                )
            )
            session_minutes = session_result.scalar_one() or 0

            deltas = {
                "words_encountered": abs((row.words_encountered or 0) - int(tracked_words or 0)),
                "words_mastered": abs((row.words_mastered or 0) - int(tracked_mastered or 0)),
                "mission_assigned_count": abs((row.mission_assigned_count or 0) - int(mission_assigned)),
                "session_minutes_total": abs((row.session_minutes_total or 0) - int(session_minutes)),
            }

            row_mismatch = any(delta > tolerance for delta in deltas.values())
            if row_mismatch:
                mismatches += 1
                print(
                    f"[mismatch] child={row.child_id} day={row.activity_day} deltas={deltas}"
                )

    if mismatches == 0:
        print("[ok] aggregate consistency check passed")
    else:
        print(f"[fail] aggregate consistency mismatches={mismatches}")

    return mismatches


if __name__ == "__main__":
    result = asyncio.run(run_check())
    raise SystemExit(1 if result > 0 else 0)