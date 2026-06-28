import json
import unittest
from types import SimpleNamespace

from app.api.endpoints.vocabulary import (
    _rank_relationship_candidates,
    _resolve_related_word_matches,
)
from app.services.word_enhancement_service import (
    RelatedWordSuggestion,
    WordEnhancementService,
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


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    async def generate(self, **kwargs):
        return json.dumps(self.payload)


class WordRelationshipEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_suggest_related_words_parses_and_normalizes_response(self):
        service = object.__new__(WordEnhancementService)
        service.llm = _FakeLLM(
            {
                "related_terms": [
                    {
                        "word": "Cat",
                        "relationship_type": "semantic",
                        "strength": 0.9,
                    },
                    {
                        "word": "Dog",
                        "relationship_type": "unknown_type",
                        "strength": 0.55,
                    },
                ]
            }
        )

        suggestions = await service.suggest_related_words(
            word="Tiger",
            word_cantonese="老虎",
            category="animals",
            candidate_words=[
                {"word": "Cat", "word_cantonese": "貓", "category": "animals"},
                {"word": "Dog", "word_cantonese": "狗", "category": "animals"},
            ],
        )

        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0].word, "Cat")
        self.assertEqual(suggestions[0].relationship_type, "semantic")
        self.assertEqual(suggestions[1].relationship_type, "semantic")

    def test_resolve_related_word_matches_supports_english_and_cantonese(self):
        current_word = make_word(word_id="word-0", word="Tiger", word_cantonese="老虎")
        catalog_words = [
            make_word(word_id="word-1", word="Cat", word_cantonese="貓", category="animals"),
            make_word(word_id="word-2", word="Dog", word_cantonese="狗", category="animals"),
            make_word(word_id="word-3", word="Park", word_cantonese="公園", category="places"),
        ]

        resolved = _resolve_related_word_matches(
            current_word=current_word,
            catalog_words=catalog_words,
            suggestions=[
                RelatedWordSuggestion(
                    word="貓",
                    relationship_type="semantic",
                    strength=0.88,
                ),
                RelatedWordSuggestion(
                    word="Dog",
                    relationship_type="contextual",
                    strength=0.67,
                ),
                RelatedWordSuggestion(
                    word="Dog",
                    relationship_type="semantic",
                    strength=0.91,
                ),
            ],
        )

        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0][0].id, "word-1")
        self.assertEqual(resolved[0][1], "semantic")
        self.assertAlmostEqual(resolved[0][2], 0.88)
        self.assertEqual(resolved[1][0].id, "word-2")
        self.assertEqual(resolved[1][1], "contextual")

    def test_rank_relationship_candidates_uses_broader_catalog_before_ai_shortlist(self):
        current_word = make_word(
            word_id="word-0",
            word="Tiger",
            word_cantonese="老虎",
            category="animals",
            contexts=["zoo", "story_time"],
            definition="A big striped animal",
            definition_cantonese="一種有條紋嘅大動物",
        )
        filler_words = [
            make_word(
                word_id=f"filler-{index}",
                word=f"Object {index}",
                word_cantonese=f"物件{index}",
                category="objects",
                contexts=["classroom"],
                definition="A classroom object",
            )
            for index in range(90)
        ]
        late_strong_match = make_word(
            word_id="word-91",
            word="Cat",
            word_cantonese="貓",
            category="animals",
            contexts=["zoo", "story_time"],
            definition="A small animal with stripes sometimes",
            definition_cantonese="一種細小嘅動物",
            total_exposures=12,
        )
        catalog_words = filler_words + [late_strong_match]

        ranked = _rank_relationship_candidates(
            current_word=current_word,
            catalog_words=catalog_words,
            limit=5,
        )

        self.assertEqual(ranked[0].id, "word-91")
        self.assertIn("word-91", [candidate.id for candidate in ranked])


if __name__ == "__main__":
    unittest.main()