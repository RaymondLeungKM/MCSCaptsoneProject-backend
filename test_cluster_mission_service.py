import unittest
from types import SimpleNamespace

from app.services.cluster_mission_service import (
    _build_cluster_description,
    _build_practical_prompts,
    _display_word,
    _pick_context_from_categories,
    _pick_seed_word,
)


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.execute_calls = 0

    async def execute(self, _query):
        self.execute_calls += 1
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)


class ClusterMissionServiceTests(unittest.TestCase):
    def test_context_prefers_mealtime_for_food(self):
        self.assertEqual(
            _pick_context_from_categories(["Food", "Nature"]),
            "mealtime",
        )

    def test_context_falls_back_to_playtime(self):
        self.assertEqual(
            _pick_context_from_categories(["Unknown"]),
            "playtime",
        )

    def test_display_word_filters_placeholder_and_non_cjk_text(self):
        word = SimpleNamespace(word_cantonese="粵語詞語（繁體中文）", word="Banana")
        self.assertEqual(_display_word(word), "")

    def test_build_practical_prompts_for_mealtime(self):
        prompts = _build_practical_prompts(
            context="mealtime",
            seed_display="香蕉",
            display_words=["香蕉", "草莓"],
        )
        self.assertEqual(len(prompts), 3)
        self.assertIn("開飯前", prompts[0])
        self.assertIn("香蕉", prompts[0])

    def test_cluster_description_uses_word_list_when_cjk_words_are_available(self):
        description = _build_cluster_description(
            seed_display="香蕉",
            display_words=["香蕉", "草莓", "米飯"],
            context="mealtime",
        )

        self.assertIn("香蕉、草莓、米飯", description)
        self.assertIn("用餐情境", description)

    def test_cluster_description_avoids_mixed_language_word_listing(self):
        description = _build_cluster_description(
            seed_display="香蕉",
            display_words=["香蕉", "Egg", "Noodles"],
            context="playtime",
        )

        self.assertNotIn("Egg", description)
        self.assertNotIn("Noodles", description)
        self.assertIn("遊戲情境", description)


class ClusterMissionSeedSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_pick_seed_word_prefers_connected_candidate(self):
        connected_word = SimpleNamespace(id="connected-word")
        session = _FakeSession([_FakeResult((connected_word, SimpleNamespace()))])

        picked = await _pick_seed_word(session, child_id="child-1")

        self.assertIsNotNone(picked)
        self.assertEqual(picked.id, "connected-word")
        self.assertEqual(session.execute_calls, 1)

    async def test_pick_seed_word_falls_back_when_no_connected_candidate(self):
        fallback_word = SimpleNamespace(id="fallback-word")
        session = _FakeSession(
            [
                _FakeResult(None),
                _FakeResult((fallback_word, SimpleNamespace())),
            ]
        )

        picked = await _pick_seed_word(session, child_id="child-1")

        self.assertIsNotNone(picked)
        self.assertEqual(picked.id, "fallback-word")
        self.assertEqual(session.execute_calls, 2)


if __name__ == "__main__":
    unittest.main()
