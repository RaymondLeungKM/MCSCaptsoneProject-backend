import math
import time
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.endpoints.adaptive_learning import get_sr_review_queue
from app.api.endpoints.admin_analytics import (
    get_content_performance,
    get_engagement_trends,
    get_mission_funnel,
    get_participation_trends,
)


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, rows=None, scalar=None, scalar_items=None):
        self._rows = rows or []
        self._scalar = scalar
        self._scalar_items = scalar_items or []

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

    def scalars(self):
        return FakeScalars(self._scalar_items)

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


class CountingFakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.execute_calls = 0

    async def execute(self, _query):
        self.execute_calls += 1
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)


def _p95_ms(samples_ms: list[float]) -> float:
    sorted_samples = sorted(samples_ms)
    if not sorted_samples:
        return 0.0
    rank = max(math.ceil(0.95 * len(sorted_samples)) - 1, 0)
    return sorted_samples[rank]


class P5PerformanceGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_analytics_endpoint_query_budgets(self):
        admin_user = SimpleNamespace(id="admin-1", role="admin", consent_analytics=True)

        participation_session = CountingFakeSession(
            [
                FakeResult(
                    rows=[
                        (date(2026, 6, 1), "child-1", 2),
                        (date(2026, 6, 2), "child-1", 3),
                    ]
                )
            ]
        )
        await get_participation_trends(
            from_day=date(2026, 6, 1),
            to_day=date(2026, 6, 2),
            age_band=None,
            current_user=admin_user,
            db=participation_session,
        )
        self.assertLessEqual(participation_session.execute_calls, 1)

        funnel_session = CountingFakeSession(
            [
                FakeResult(
                    rows=[
                        ("assigned", "playtime", "system", "5-6", 10),
                        ("started", "playtime", "system", "5-6", 6),
                        ("completed", "playtime", "system", "5-6", 4),
                    ]
                )
            ]
        )
        await get_mission_funnel(
            from_day=date(2026, 6, 1),
            to_day=date(2026, 6, 7),
            age_band=None,
            context=None,
            source=None,
            current_user=admin_user,
            db=funnel_session,
        )
        self.assertLessEqual(funnel_session.execute_calls, 1)

        engagement_session = CountingFakeSession(
            [
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            activity_day=date(2026, 6, 1),
                            avg_session_minutes=11.0,
                            avg_engagement_score=0.6,
                            active_children=3,
                        )
                    ]
                ),
                FakeResult(scalar_items=[0.2, 0.5, 0.9]),
                FakeResult(scalar=7.0),
            ]
        )
        await get_engagement_trends(
            from_day=date(2026, 6, 1),
            to_day=date(2026, 6, 7),
            age_band=None,
            current_user=admin_user,
            db=engagement_session,
        )
        self.assertLessEqual(engagement_session.execute_calls, 3)

        content_session = CountingFakeSession(
            [
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            content_type="word",
                            content_id="apple",
                            category_id="food",
                            exposure_count=20,
                            completion_count=16,
                            success_count=10,
                            avg_mastery_delta=0.3,
                            avg_retention_proxy_score=0.7,
                        )
                    ]
                )
            ]
        )
        await get_content_performance(
            from_day=date(2026, 6, 1),
            to_day=date(2026, 6, 30),
            age_band=None,
            category=None,
            content_type=None,
            top_n=5,
            current_user=admin_user,
            db=content_session,
        )
        self.assertLessEqual(content_session.execute_calls, 1)

    async def test_queue_generation_and_admin_endpoints_p95_latency(self):
        parent_user = SimpleNamespace(id="parent-1")
        admin_user = SimpleNamespace(id="admin-1", role="admin", consent_analytics=True)

        queue_samples_ms = []
        for _ in range(15):
            session = CountingFakeSession([FakeResult(scalar=SimpleNamespace(id="child-1"))])
            with patch(
                "app.api.endpoints.adaptive_learning.get_review_queue",
                new=AsyncMock(
                    return_value=SimpleNamespace(cards=[], total_due=0, new_cards_today=0)
                ),
            ):
                started = time.perf_counter()
                await get_sr_review_queue(
                    "child-1",
                    max_cards=20,
                    max_new=5,
                    current_user=parent_user,
                    db=session,
                )
                queue_samples_ms.append((time.perf_counter() - started) * 1000)
            self.assertLessEqual(session.execute_calls, 1)

        analytics_samples_ms = []
        for _ in range(15):
            session = CountingFakeSession(
                [
                    FakeResult(
                        rows=[
                            (date(2026, 6, 1), "child-1", 2),
                            (date(2026, 6, 2), "child-1", 3),
                            (date(2026, 6, 2), "child-2", 2),
                        ]
                    )
                ]
            )
            started = time.perf_counter()
            await get_participation_trends(
                from_day=date(2026, 6, 1),
                to_day=date(2026, 6, 2),
                age_band="5-6",
                current_user=admin_user,
                db=session,
            )
            analytics_samples_ms.append((time.perf_counter() - started) * 1000)
            self.assertLessEqual(session.execute_calls, 1)

        self.assertLess(_p95_ms(queue_samples_ms), 50.0)
        self.assertLess(_p95_ms(analytics_samples_ms), 50.0)


if __name__ == "__main__":
    unittest.main()
