import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from app.core.security import get_current_admin_user
from app.db.session import get_db


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


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, query):
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)


class AdminAnalyticsEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _override_admin_and_db(self, fake_session):
        async def override_admin_user():
            return SimpleNamespace(id="admin-1", role="admin", consent_analytics=True)

        async def override_db():
            yield fake_session

        app.dependency_overrides[get_current_admin_user] = override_admin_user
        app.dependency_overrides[get_db] = override_db

    def test_admin_analytics_endpoint_blocks_non_admin(self):
        async def override_forbidden_user():
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[get_current_admin_user] = override_forbidden_user

        response = self.client.get("/api/v1/admin/analytics/participation")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Admin access required", response.text)

    def test_participation_endpoint_returns_trend_points(self):
        fake_session = FakeSession(
            [
                FakeResult(
                    rows=[
                        (date(2026, 6, 1), "child-1", 2),
                        (date(2026, 6, 2), "child-1", 3),
                        (date(2026, 6, 2), "child-2", 1),
                    ]
                )
            ]
        )
        self._override_admin_and_db(fake_session)

        response = self.client.get(
            "/api/v1/admin/analytics/participation?from=2026-06-01&to=2026-06-02"
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["summary"]["window_days"], 2)
        self.assertEqual(payload["summary"]["total_active_children"], 2)
        self.assertEqual(len(payload["points"]), 2)
        self.assertEqual(payload["points"][0]["dau"], 1)
        self.assertEqual(payload["points"][1]["dau"], 2)

    def test_mission_funnel_endpoint_returns_overall_and_segments(self):
        fake_session = FakeSession(
            [
                FakeResult(
                    rows=[
                        ("assigned", "playtime", "system", "5-6", 10),
                        ("started", "playtime", "system", "5-6", 6),
                        ("completed", "playtime", "system", "5-6", 4),
                        ("skipped", "playtime", "system", "5-6", 1),
                        ("expired", "playtime", "system", "5-6", 1),
                    ]
                )
            ]
        )
        self._override_admin_and_db(fake_session)

        response = self.client.get(
            "/api/v1/admin/analytics/missions/funnel?from=2026-06-01&to=2026-06-07"
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["overall"]["assigned"], 10)
        self.assertEqual(payload["overall"]["completed"], 4)
        self.assertEqual(payload["overall"]["completion_rate"], 0.4)
        self.assertGreaterEqual(len(payload["by_context"]), 1)
        self.assertGreaterEqual(len(payload["by_source"]), 1)
        self.assertGreaterEqual(len(payload["by_age_band"]), 1)

    def test_engagement_endpoint_returns_summary_distribution_and_points(self):
        fake_session = FakeSession(
            [
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            activity_day=date(2026, 6, 1),
                            avg_session_minutes=10.0,
                            avg_engagement_score=0.5,
                            active_children=2,
                        ),
                        SimpleNamespace(
                            activity_day=date(2026, 6, 2),
                            avg_session_minutes=12.0,
                            avg_engagement_score=0.7,
                            active_children=3,
                        ),
                    ]
                ),
                FakeResult(scalar_items=[0.2, 0.5, 0.8]),
                FakeResult(scalar=6.0),
            ]
        )
        self._override_admin_and_db(fake_session)

        response = self.client.get(
            "/api/v1/admin/analytics/engagement?from=2026-06-01&to=2026-06-02"
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["summary"]["average_session_minutes"], 11.0)
        self.assertEqual(payload["distribution"]["low"], 1)
        self.assertEqual(payload["distribution"]["medium"], 1)
        self.assertEqual(payload["distribution"]["high"], 1)
        self.assertEqual(len(payload["points"]), 2)

    def test_content_performance_endpoint_returns_ranked_lists(self):
        fake_session = FakeSession(
            [
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            content_type="word",
                            content_id="apple",
                            category_id="food",
                            exposure_count=40,
                            completion_count=30,
                            success_count=20,
                            avg_mastery_delta=0.4,
                            avg_retention_proxy_score=0.7,
                        ),
                        SimpleNamespace(
                            content_type="word",
                            content_id="rare-item",
                            category_id="food",
                            exposure_count=5,
                            completion_count=1,
                            success_count=0,
                            avg_mastery_delta=0.1,
                            avg_retention_proxy_score=0.2,
                        ),
                    ]
                )
            ]
        )
        self._override_admin_and_db(fake_session)

        response = self.client.get(
            "/api/v1/admin/analytics/content-performance?from=2026-06-01&to=2026-06-30"
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["summary"]["evaluated_items"], 2)
        self.assertGreaterEqual(len(payload["top_content"]), 1)
        self.assertGreaterEqual(len(payload["underperforming_content"]), 1)
        self.assertEqual(payload["top_content"][0]["content_id"], "apple")


if __name__ == "__main__":
    unittest.main()
