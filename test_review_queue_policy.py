import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.spaced_repetition_service import (
    _QueueCandidate,
    _compute_quick_win_score,
    _compute_weak_link_ratio,
    _resolve_primary_reason,
    _select_ranked_candidates,
)


def make_card(word_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        word_id=word_id,
        next_review=datetime.now(timezone.utc) - timedelta(days=1),
    )


class ReviewQueuePolicyTests(unittest.TestCase):
    def test_resolve_primary_reason_favors_weak_link_then_bridge_then_due(self):
        self.assertEqual(
            _resolve_primary_reason(
                due_score=0.9,
                bridge_score=0.8,
                weak_link_ratio=0.7,
                quick_win_score=0.9,
            ),
            "weak_link",
        )

        self.assertEqual(
            _resolve_primary_reason(
                due_score=0.4,
                bridge_score=0.7,
                weak_link_ratio=0.2,
                quick_win_score=0.9,
            ),
            "bridge",
        )

        self.assertEqual(
            _resolve_primary_reason(
                due_score=0.8,
                bridge_score=0.3,
                weak_link_ratio=0.2,
                quick_win_score=0.9,
            ),
            "due",
        )

        self.assertEqual(
            _resolve_primary_reason(
                due_score=0.2,
                bridge_score=0.2,
                weak_link_ratio=0.2,
                quick_win_score=0.8,
            ),
            "quick_win",
        )

        self.assertEqual(
            _resolve_primary_reason(
                due_score=0.2,
                bridge_score=0.2,
                weak_link_ratio=0.2,
                quick_win_score=0.2,
            ),
            "balance",
        )

    def test_low_success_progress_gets_high_weak_link_ratio(self):
        progress = SimpleNamespace(
            total_attempts=6,
            success_rate=0.2,
            exposure_count=9,
            mastered=False,
        )

        self.assertGreaterEqual(_compute_weak_link_ratio(progress), 0.85)

    def test_quick_win_score_rewards_easy_high_success_review_cards(self):
        card = SimpleNamespace(is_new=False, repetitions=5, easiness_factor=2.9)
        progress = SimpleNamespace(total_attempts=8, success_rate=0.95)

        self.assertGreaterEqual(_compute_quick_win_score(card, progress), 0.8)

    def test_selection_balances_categories_and_reason_caps(self):
        candidates = [
            _QueueCandidate(
                card=make_card("w1"),
                word=None,
                reason="due",
                due_score=1.0,
                graph_score=0.1,
                bridge_score=0.1,
                centrality_score=0.1,
                weak_link_boost=0.1,
                quick_win_score=0.1,
                base_score=1.0,
                category="animals",
            ),
            _QueueCandidate(
                card=make_card("w2"),
                word=None,
                reason="due",
                due_score=0.95,
                graph_score=0.1,
                bridge_score=0.1,
                centrality_score=0.1,
                weak_link_boost=0.1,
                quick_win_score=0.1,
                base_score=0.99,
                category="animals",
            ),
            _QueueCandidate(
                card=make_card("w3"),
                word=None,
                reason="due",
                due_score=0.9,
                graph_score=0.1,
                bridge_score=0.1,
                centrality_score=0.1,
                weak_link_boost=0.1,
                quick_win_score=0.1,
                base_score=0.98,
                category="animals",
            ),
            _QueueCandidate(
                card=make_card("w4"),
                word=None,
                reason="bridge",
                due_score=0.5,
                graph_score=0.8,
                bridge_score=0.8,
                centrality_score=0.6,
                weak_link_boost=0.2,
                quick_win_score=0.2,
                base_score=0.97,
                category="food",
            ),
        ]

        ranked = _select_ranked_candidates(candidates, max_cards=4)

        self.assertEqual(len(ranked), 4)
        self.assertEqual(ranked[0].card.word_id, "w1")
        self.assertEqual(ranked[1].card.word_id, "w4")
        self.assertEqual(ranked[2].card.word_id, "w2")
        self.assertNotEqual(ranked[1].category, ranked[0].category)


if __name__ == "__main__":
    unittest.main()
