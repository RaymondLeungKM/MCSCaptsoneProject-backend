import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.endpoints.adaptive_learning import get_sr_review_queue
from app.schemas.word_personalization import (
    ReviewQueueFeatures,
    ReviewQueueResponse,
    SpacedRepetitionCardResponse,
)


class _ExecuteResult:
    def __init__(self, has_child: bool):
        self._has_child = has_child

    def scalar_one_or_none(self):
        return object() if self._has_child else None


class _FakeDB:
    def __init__(self, has_child: bool):
        self.has_child = has_child

    async def execute(self, _query):
        return _ExecuteResult(self.has_child)


class AdaptiveReviewQueueEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_queue_endpoint_returns_service_payload(self):
        fake_db = _FakeDB(has_child=True)
        user = SimpleNamespace(id="parent-1")
        expected = ReviewQueueResponse(
            cards=[
                SpacedRepetitionCardResponse(
                    id=1,
                    child_id="child-1",
                    word_id="word-1",
                    easiness_factor=2.5,
                    interval=3,
                    repetitions=2,
                    next_review="2026-06-27T00:00:00Z",
                    is_new=False,
                    is_graduated=False,
                    word_cantonese="蘋果",
                    queue_reason="bridge",
                    queue_features=ReviewQueueFeatures(
                        due_score=0.8,
                        graph_score=0.72,
                        bridge_score=0.9,
                        centrality_score=0.5,
                        weak_link_boost=0.2,
                        diversity_penalty=0.0,
                        final_score=0.71,
                    ),
                )
            ],
            total_due=3,
            new_cards_today=1,
        )

        with patch(
            "app.api.endpoints.adaptive_learning.get_review_queue",
            new=AsyncMock(return_value=expected),
        ) as queue_mock:
            result = await get_sr_review_queue(
                "child-1",
                max_cards=15,
                max_new=4,
                current_user=user,
                db=fake_db,
            )

        self.assertEqual(result.total_due, 3)
        self.assertEqual(result.new_cards_today, 1)
        self.assertEqual(result.cards[0].queue_reason, "bridge")
        self.assertAlmostEqual(result.cards[0].queue_features.bridge_score, 0.9)
        self.assertAlmostEqual(result.cards[0].queue_features.final_score, 0.71)
        queue_mock.assert_awaited_once()

    async def test_review_queue_endpoint_raises_not_found(self):
        fake_db = _FakeDB(has_child=False)
        user = SimpleNamespace(id="parent-1")

        with self.assertRaises(HTTPException) as context:
            await get_sr_review_queue(
                "missing-child",
                current_user=user,
                db=fake_db,
            )

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
