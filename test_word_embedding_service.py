import unittest
from types import SimpleNamespace

from app.services.word_embedding_service import (
    build_word_embedding_text,
    build_word_embedding_text_hash,
    embedding_record_is_fresh,
    rank_words_by_embedding_similarity,
)


def make_word(
    *,
    word_id: str,
    word: str,
    word_cantonese: str | None,
    category: str = "general",
    contexts: list[str] | None = None,
    definition: str | None = None,
    definition_cantonese: str | None = None,
    physical_action: str | None = None,
    related_words: list[str] | None = None,
    total_exposures: int = 0,
    created_by_child_id: str | None = None,
):
    return SimpleNamespace(
        id=word_id,
        word=word,
        word_cantonese=word_cantonese,
        category=category,
        contexts=contexts or [],
        definition=definition,
        definition_cantonese=definition_cantonese,
        physical_action=physical_action,
        related_words=related_words or [],
        total_exposures=total_exposures,
        created_by_child_id=created_by_child_id,
    )


class WordEmbeddingServiceTests(unittest.TestCase):
    def test_build_word_embedding_text_includes_multilingual_context(self):
        word = make_word(
            word_id="word-1",
            word="Apple",
            word_cantonese="蘋果",
            category="fruits",
            contexts=["snack", "home"],
            definition="A sweet round fruit",
            definition_cantonese="一種甜甜哋圓形生果",
            physical_action="pretend to eat",
        )

        text = build_word_embedding_text(word)

        self.assertIn("english: Apple", text)
        self.assertIn("cantonese: 蘋果", text)
        self.assertIn("category: fruits", text)
        self.assertIn("contexts: snack, home", text)

    def test_rank_words_by_embedding_similarity_prefers_semantic_match(self):
        current_word = make_word(
            word_id="word-0",
            word="Apple",
            word_cantonese="蘋果",
            category="fruits",
            contexts=["snack", "home"],
        )
        banana = make_word(
            word_id="word-1",
            word="Banana",
            word_cantonese="香蕉",
            category="fruits",
            contexts=["snack", "school"],
            total_exposures=10,
        )
        car = make_word(
            word_id="word-2",
            word="Car",
            word_cantonese="車",
            category="transport",
            contexts=["road"],
            total_exposures=10,
        )

        ranked = rank_words_by_embedding_similarity(
            current_word=current_word,
            current_embedding=[1.0, 0.0],
            candidate_embeddings=[
                (banana, [0.98, 0.02]),
                (car, [0.0, 1.0]),
            ],
            limit=2,
        )

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].word.id, "word-1")
        self.assertGreater(ranked[0].semantic_similarity, 0.9)

    def test_embedding_record_is_fresh_detects_matching_cache_metadata(self):
        word = make_word(
            word_id="word-1",
            word="Apple",
            word_cantonese="蘋果",
            category="fruits",
            contexts=["snack"],
            definition="A sweet round fruit",
        )
        record = SimpleNamespace(
            provider="openrouter",
            model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
            embedding=[0.1, 0.2],
            source_text_hash=build_word_embedding_text_hash(word),
        )

        self.assertTrue(
            embedding_record_is_fresh(
                record=record,
                word=word,
                provider="openrouter",
                model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
            )
        )

    def test_embedding_record_is_fresh_rejects_stale_source_hash(self):
        word = make_word(
            word_id="word-1",
            word="Apple",
            word_cantonese="蘋果",
            category="fruits",
            contexts=["snack", "home"],
        )
        record = SimpleNamespace(
            provider="openrouter",
            model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
            embedding=[0.1, 0.2],
            source_text_hash="stale-hash",
        )

        self.assertFalse(
            embedding_record_is_fresh(
                record=record,
                word=word,
                provider="openrouter",
                model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
            )
        )


if __name__ == "__main__":
    unittest.main()