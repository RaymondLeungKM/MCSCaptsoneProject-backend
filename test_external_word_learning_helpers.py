import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.endpoints.vocabulary import (
    _build_captured_word_response,
    _build_external_placeholder_content,
    _merge_captured_word_payloads,
)


def make_word(
    *,
    word_id: str,
    word: str,
    created_at: datetime,
    created_by_child_id: str | None = None,
):
    return SimpleNamespace(
        id=word_id,
        word=word,
        word_cantonese=None,
        category="general",
        pronunciation=None,
        jyutping=None,
        definition=f"Definition for {word}",
        definition_cantonese=None,
        example=f"Example for {word}",
        example_cantonese=None,
        difficulty="easy",
        physical_action=None,
        image_url=None,
        audio_url=None,
        audio_url_english=None,
        contexts=[],
        related_words=[],
        total_exposures=0,
        success_rate=0.0,
        is_active=True,
        created_at=created_at,
        created_by_child_id=created_by_child_id,
        category_rel=SimpleNamespace(name="general", name_cantonese="一般"),
    )


class ExternalWordLearningHelperTests(unittest.TestCase):
    def test_builds_fast_placeholder_content_without_ai_fields(self):
        payload = _build_external_placeholder_content("apple", "object_detection")

        self.assertEqual(payload["word"], "Apple")
        self.assertEqual(payload["word_cantonese"], None)
        self.assertEqual(payload["jyutping"], None)
        self.assertIn("object detection", payload["definition"])
        self.assertIn("Apple", payload["example_cantonese"])

    def test_captured_word_response_uses_tracking_timestamp_when_present(self):
        created_at = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
        tracked_at = created_at + timedelta(hours=3)
        word = make_word(word_id="word-1", word="Apple", created_at=created_at)

        response = _build_captured_word_response(word, tracked_at)

        self.assertEqual(response["created_at"], tracked_at)
        self.assertEqual(response["category_name"], "general")
        self.assertEqual(response["category_name_cantonese"], "一般")

    def test_merge_prefers_tracked_entries_and_keeps_recent_order(self):
        base_time = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
        tracked_word = make_word(word_id="word-1", word="Apple", created_at=base_time)
        owned_word = make_word(
            word_id="word-1",
            word="Apple",
            created_at=base_time - timedelta(days=1),
            created_by_child_id="child-1",
        )
        second_word = make_word(
            word_id="word-2",
            word="Banana",
            created_at=base_time - timedelta(hours=1),
            created_by_child_id="child-1",
        )

        tracked_payload = _build_captured_word_response(
            tracked_word,
            captured_at=base_time + timedelta(hours=2),
        )
        owned_payload = _build_captured_word_response(owned_word)
        second_payload = _build_captured_word_response(second_word)

        merged = _merge_captured_word_payloads(
            [tracked_payload],
            [owned_payload, second_payload],
            limit=10,
        )

        self.assertEqual([item["id"] for item in merged], ["word-1", "word-2"])
        self.assertEqual(merged[0]["created_at"], base_time + timedelta(hours=2))


if __name__ == "__main__":
    unittest.main()