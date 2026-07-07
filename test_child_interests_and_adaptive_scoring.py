import unittest
from types import SimpleNamespace

from app.api.endpoints.adaptive_learning import (
    _extract_child_interest_keys,
    calculate_word_priority,
)
from app.api.endpoints.children import (
    _replace_child_interests,
    _resolve_interest_category_ids,
)


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, scalar_items):
        self._scalar_items = scalar_items

    def scalars(self):
        return _FakeScalars(self._scalar_items)


class _FakeDB:
    def __init__(self, categories):
        self._categories = categories

    async def execute(self, _query):
        return _FakeResult(self._categories)


class ChildInterestPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_interest_category_ids_by_name_and_id(self):
        categories = [
            SimpleNamespace(id="cat-animals", name="Animals"),
            SimpleNamespace(id="cat-food", name="Food"),
        ]
        db = _FakeDB(categories)

        resolved = await _resolve_interest_category_ids(
            db,
            ["animals", "CAT-FOOD", "unknown", "Animals"],
        )

        self.assertEqual(resolved, ["cat-animals", "cat-food"])

    async def test_replace_child_interests_overwrites_existing_rows(self):
        categories = [
            SimpleNamespace(id="cat-animals", name="Animals"),
            SimpleNamespace(id="cat-food", name="Food"),
        ]
        db = _FakeDB(categories)
        child = SimpleNamespace(interests=[SimpleNamespace(category_id="old")])

        await _replace_child_interests(db, child, ["Food", "animals"])

        self.assertEqual(len(child.interests), 2)
        self.assertEqual(child.interests[0].category_id, "cat-food")
        self.assertEqual(child.interests[1].category_id, "cat-animals")


class AdaptiveInterestScoringTests(unittest.TestCase):
    def test_extract_child_interest_keys_includes_id_and_names(self):
        child = SimpleNamespace(
            interests=[
                SimpleNamespace(
                    category_id="cat-animals",
                    category=SimpleNamespace(name="Animals", name_cantonese="動物"),
                )
            ]
        )

        keys = _extract_child_interest_keys(child)

        self.assertIn("cat-animals", keys)
        self.assertIn("animals", keys)
        self.assertIn("動物", keys)

    def test_calculate_word_priority_boosts_interest_aligned_words(self):
        word = SimpleNamespace(category="Animals")
        child = SimpleNamespace(interests=[])
        progress = SimpleNamespace(exposure_count=8, mastered=False, success_rate=0.9)

        baseline = calculate_word_priority(word, progress, child, set())
        boosted = calculate_word_priority(word, progress, child, {"animals"})

        self.assertEqual(boosted - baseline, 8)


if __name__ == "__main__":
    unittest.main()
