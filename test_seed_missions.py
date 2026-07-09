import unittest
from types import SimpleNamespace

from seed_missions import _resolve_target_words, _word_display


class SeedMissionTargetWordsTests(unittest.TestCase):
    def test_word_display_prefers_cantonese_when_present(self):
        word = SimpleNamespace(word="Apple", word_cantonese="蘋果")
        self.assertEqual(_word_display(word), "蘋果")

    def test_word_display_falls_back_to_english(self):
        word = SimpleNamespace(word="Apple", word_cantonese="")
        self.assertEqual(_word_display(word), "Apple")

    def test_resolve_target_words_uses_lookup_order(self):
        lookup = {
            "Apple": SimpleNamespace(word="Apple", word_cantonese="蘋果"),
            "Book": SimpleNamespace(word="Book", word_cantonese="書"),
        }

        resolved = _resolve_target_words(
            mission_slug="mission-1",
            target_word_keys=["Book", "Apple"],
            word_lookup=lookup,
        )

        self.assertEqual(resolved, ["書", "蘋果"])

    def test_resolve_target_words_raises_for_missing_seed_words(self):
        with self.assertRaises(RuntimeError) as error:
            _resolve_target_words(
                mission_slug="mission-1",
                target_word_keys=["Missing"],
                word_lookup={},
            )

        self.assertIn("Missing seeded words", str(error.exception))


if __name__ == "__main__":
    unittest.main()
