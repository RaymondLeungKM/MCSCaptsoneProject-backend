import unittest
from types import SimpleNamespace

from app.services.word_graph_service import (
    build_relationship_maps,
    compute_graph_queue_score,
)


class WordGraphQueueScoringTests(unittest.TestCase):
    def test_build_relationship_maps_and_score_are_deterministic(self):
        relationships = [
            SimpleNamespace(word_id="w1", related_word_id="k1", strength=0.9),
            SimpleNamespace(word_id="w1", related_word_id="x1", strength=0.5),
            SimpleNamespace(word_id="x1", related_word_id="w1", strength=0.4),
        ]

        outgoing_map, incoming_degree = build_relationship_maps(relationships)
        score = compute_graph_queue_score(
            "w1",
            outgoing_map=outgoing_map,
            incoming_degree=incoming_degree,
            known_word_ids={"k1"},
            weak_link_ratio=0.8,
        )

        self.assertEqual(score.connection_count, 1)
        self.assertEqual(score.centrality_degree, 3)
        self.assertAlmostEqual(score.bridge_score, 0.45)
        self.assertAlmostEqual(score.centrality_score, 0.5)
        self.assertAlmostEqual(score.weak_link_boost, 0.8)
        self.assertAlmostEqual(score.graph_score, 0.52)

    def test_sparse_graph_candidate_has_zero_bridge_and_centrality(self):
        outgoing_map, incoming_degree = build_relationship_maps([])

        score = compute_graph_queue_score(
            "isolated",
            outgoing_map=outgoing_map,
            incoming_degree=incoming_degree,
            known_word_ids=set(),
            weak_link_ratio=0.0,
        )

        self.assertEqual(score.connection_count, 0)
        self.assertEqual(score.centrality_degree, 0)
        self.assertEqual(score.bridge_score, 0.0)
        self.assertEqual(score.centrality_score, 0.0)
        self.assertEqual(score.graph_score, 0.0)

    def test_dense_graph_candidate_caps_centrality_and_bridge_scores(self):
        relationships = [
            SimpleNamespace(word_id="hub", related_word_id=f"k{index}", strength=0.9)
            for index in range(1, 8)
        ] + [
            SimpleNamespace(word_id=f"x{index}", related_word_id="hub", strength=0.4)
            for index in range(1, 5)
        ]

        outgoing_map, incoming_degree = build_relationship_maps(relationships)
        score = compute_graph_queue_score(
            "hub",
            outgoing_map=outgoing_map,
            incoming_degree=incoming_degree,
            known_word_ids={f"k{index}" for index in range(1, 8)},
            weak_link_ratio=1.0,
        )

        self.assertEqual(score.connection_count, 7)
        self.assertEqual(score.centrality_degree, 11)
        self.assertEqual(score.bridge_score, 1.0)
        self.assertEqual(score.centrality_score, 1.0)
        self.assertEqual(score.weak_link_boost, 1.0)
        self.assertEqual(score.graph_score, 1.0)


if __name__ == "__main__":
    unittest.main()
