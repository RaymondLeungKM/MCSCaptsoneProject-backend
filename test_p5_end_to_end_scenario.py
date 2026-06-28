import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.endpoints.adaptive_learning import get_sr_review_queue
from app.api.endpoints.admin_analytics import get_participation_trends
from app.api.endpoints.missions import _serialize_assigned_mission
from app.api.endpoints.parent_dashboard import get_parent_benchmarks
from app.models.content import MissionAssignmentSource, MissionAssignmentStatus, MissionContext


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

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)


class P5EndToEndScenarioTests(unittest.IsolatedAsyncioTestCase):
    async def test_revision_cluster_benchmark_admin_trend_flow(self):
        parent_user = SimpleNamespace(id="parent-1", consent_analytics=True)
        admin_user = SimpleNamespace(id="admin-1", role="admin", consent_analytics=True)

        review_session = FakeSession([FakeResult(scalar=SimpleNamespace(id="child-1"))])
        mocked_queue = SimpleNamespace(
            cards=[
                SimpleNamespace(
                    word_id="word-1",
                    queue_reason="bridge",
                    queue_features=SimpleNamespace(final_score=0.87),
                )
            ],
            total_due=1,
            new_cards_today=0,
        )

        with patch(
            "app.api.endpoints.adaptive_learning.get_review_queue",
            new=AsyncMock(return_value=mocked_queue),
        ):
            review_response = await get_sr_review_queue(
                "child-1",
                max_cards=10,
                max_new=3,
                current_user=parent_user,
                db=review_session,
            )

        self.assertEqual(review_response.total_due, 1)
        self.assertEqual(review_response.cards[0].queue_reason, "bridge")

        mission = SimpleNamespace(
            id="mission-cluster-1",
            slug="cluster-child-1-20260621-seed1",
            title="Cluster: Food + Action",
            description="Graph-generated mission",
            context=MissionContext.PLAYTIME,
            is_offline=False,
            status="published",
            locale="zh-HK",
            age_min=4,
            age_max=6,
            difficulty="medium",
            surface="child",
            sort_order=0,
            selection_tags=["concept_cluster", "graph_generated"],
            catalog_metadata={
                "cluster_id": "cluster-child-1-20260621-seed1",
                "seed_word_id": "seed-1",
                "cluster_depth": 2,
                "cluster_strategy": "two_hop_bridge",
            },
            published_at=None,
            archived_at=None,
            target_words=["apple", "eat", "happy"],
            conversation_prompts=["Describe your snack"],
            is_active=True,
            created_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            updated_at=None,
        )
        assignment = SimpleNamespace(
            id="assignment-1",
            child_id="child-1",
            mission_id=mission.id,
            assignment_date=date(2026, 6, 21),
            source=MissionAssignmentSource.SYSTEM,
            status=MissionAssignmentStatus.ASSIGNED,
            surface="child",
            priority=1,
            selection_reason="Graph concept cluster mission",
            selection_metadata={
                "is_cluster": True,
                "cluster_id": "cluster-child-1-20260621-seed1",
                "seed_word_id": "seed-1",
                "cluster_depth": 2,
                "cluster_strategy": "two_hop_bridge",
            },
            available_from=None,
            expires_at=None,
            started_at=None,
            completed_at=None,
            skipped_at=None,
            completion_notes=None,
            created_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            updated_at=None,
        )

        serialized_mission = _serialize_assigned_mission(
            mission,
            child_id="child-1",
            assignment_date=date(2026, 6, 21),
            assignment=assignment,
            progress=None,
        )

        self.assertTrue(serialized_mission["assignment"]["selection_metadata"]["is_cluster"])
        self.assertEqual(
            serialized_mission["assignment"]["selection_metadata"]["cluster_strategy"],
            "two_hop_bridge",
        )

        child = SimpleNamespace(id="child-1", parent_id="parent-1", age=5)
        child_rows = [
            SimpleNamespace(
                child_id="child-1",
                activity_day=date(2026, 6, 20),
                words_mastered=4,
                session_minutes_total=10,
            ),
            SimpleNamespace(
                child_id="child-1",
                activity_day=date(2026, 6, 21),
                words_mastered=5,
                session_minutes_total=14,
            ),
        ]
        cohort_rows = child_rows + [
            SimpleNamespace(
                child_id="child-2",
                activity_day=date(2026, 6, 20),
                words_mastered=3,
                session_minutes_total=8,
            ),
            SimpleNamespace(
                child_id="child-2",
                activity_day=date(2026, 6, 21),
                words_mastered=4,
                session_minutes_total=9,
            ),
        ]

        benchmark_session = FakeSession(
            [
                FakeResult(scalar=child),
                FakeResult(scalar_items=child_rows),
                FakeResult(scalar_items=cohort_rows),
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            category="food",
                            total_count=10,
                            mastered_count=6,
                        )
                    ]
                ),
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            category="food",
                            total_count=20,
                            mastered_count=10,
                        )
                    ]
                ),
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            id="food",
                            name_cantonese="食物",
                            name="Food",
                        )
                    ]
                ),
            ]
        )

        benchmark_response = await get_parent_benchmarks(
            child_id="child-1",
            range_days=28,
            minimum_cohort_threshold=2,
            current_user=parent_user,
            db=benchmark_session,
        )

        self.assertFalse(benchmark_response.suppression.is_suppressed)
        self.assertIsNotNone(benchmark_response.pace_benchmark)
        self.assertIsNotNone(benchmark_response.engagement_benchmark)
        self.assertGreaterEqual(len(benchmark_response.category_benchmarks), 1)

        admin_session = FakeSession(
            [
                FakeResult(
                    rows=[
                        (date(2026, 6, 20), "child-1", 2),
                        (date(2026, 6, 21), "child-1", 3),
                    ]
                )
            ]
        )

        admin_response = await get_participation_trends(
            from_day=date(2026, 6, 20),
            to_day=date(2026, 6, 21),
            age_band="5-6",
            current_user=admin_user,
            db=admin_session,
        )

        self.assertEqual(admin_response.summary.total_active_children, 1)
        self.assertEqual(len(admin_response.points), 2)
        self.assertEqual(admin_response.points[-1].dau, 1)


if __name__ == "__main__":
    unittest.main()
