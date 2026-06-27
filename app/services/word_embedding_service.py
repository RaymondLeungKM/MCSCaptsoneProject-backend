"""Word embedding retrieval service for semantic graph candidate selection."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.word_personalization import WordEmbedding
from app.models.vocabulary import Word
from app.services.llm_service import LLMProvider, get_llm_service


def build_word_embedding_text(word: Word) -> str:
    contexts = ", ".join(
        str(context).strip()
        for context in (getattr(word, "contexts", None) or [])
        if str(context).strip()
    )
    parts = [
        f"english: {word.word}",
        f"cantonese: {word.word_cantonese or '-'}",
        f"category: {word.category or '-'}",
        f"definition_en: {getattr(word, 'definition', None) or '-'}",
        f"definition_yue: {getattr(word, 'definition_cantonese', None) or '-'}",
        f"physical_action: {getattr(word, 'physical_action', None) or '-'}",
        f"contexts: {contexts or '-'}",
    ]
    return " | ".join(parts)


def build_word_embedding_text_hash(word: Word) -> str:
    return sha256(build_word_embedding_text(word).encode("utf-8")).hexdigest()


def embedding_record_is_fresh(
    *,
    record: Optional[WordEmbedding],
    word: Word,
    provider: str,
    model: str,
) -> bool:
    if record is None or not record.embedding:
        return False

    return (
        record.provider == provider
        and record.model == model
        and record.source_text_hash == build_word_embedding_text_hash(word)
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _normalize_contexts(word: Word) -> set[str]:
    return {
        str(context).strip().lower()
        for context in (getattr(word, "contexts", None) or [])
        if str(context).strip()
    }


@dataclass(frozen=True)
class SimilarWordCandidate:
    word: Word
    semantic_similarity: float
    hybrid_score: float


def rank_words_by_embedding_similarity(
    *,
    current_word: Word,
    current_embedding: Sequence[float],
    candidate_embeddings: Iterable[tuple[Word, Sequence[float]]],
    limit: int = 30,
) -> list[SimilarWordCandidate]:
    current_contexts = _normalize_contexts(current_word)
    current_related_ids = set(getattr(current_word, "related_words", None) or [])
    ranked: list[SimilarWordCandidate] = []

    for candidate, embedding in candidate_embeddings:
        similarity = cosine_similarity(current_embedding, embedding)
        if similarity <= 0.0:
            continue

        score = similarity
        if candidate.category == current_word.category:
            score += 0.12

        shared_contexts = current_contexts & _normalize_contexts(candidate)
        score += min(len(shared_contexts), 3) * 0.04

        candidate_related_ids = set(getattr(candidate, "related_words", None) or [])
        if candidate.id in current_related_ids or current_word.id in candidate_related_ids:
            score += 0.06

        if getattr(candidate, "created_by_child_id", None) is None:
            score += 0.01

        exposure_boost = min(float(getattr(candidate, "total_exposures", 0) or 0.0), 20.0) / 400.0
        score += exposure_boost

        ranked.append(
            SimilarWordCandidate(
                word=candidate,
                semantic_similarity=round(similarity, 6),
                hybrid_score=round(score, 6),
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.hybrid_score,
            -item.semantic_similarity,
            item.word.word.lower() if item.word.word else "",
        )
    )
    return ranked[:limit]


class WordEmbeddingService:
    def __init__(self, provider: LLMProvider = LLMProvider.OPENROUTER):
        self.provider = provider
        self.model = settings.OPENROUTER_EMBEDDING_MODEL
        self.llm = get_llm_service(provider)

    @staticmethod
    def _hash_text(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def _upsert_record(
        self,
        *,
        record: Optional[WordEmbedding],
        word: Word,
        text: str,
        text_hash: str,
        vector: Sequence[float],
    ) -> WordEmbedding:
        serialized_vector = [float(value) for value in vector]
        if record is None:
            record = WordEmbedding(
                word_id=word.id,
                provider=self.provider.value,
                model=self.model,
                embedding=serialized_vector,
                dimensions=len(serialized_vector),
                source_text=text,
                source_text_hash=text_hash,
            )
        else:
            record.provider = self.provider.value
            record.model = self.model
            record.embedding = serialized_vector
            record.dimensions = len(serialized_vector)
            record.source_text = text
            record.source_text_hash = text_hash
        return record

    async def ensure_word_embedding(
        self,
        db: AsyncSession,
        *,
        word: Word,
        force_refresh: bool = False,
    ) -> Optional[WordEmbedding]:
        text = build_word_embedding_text(word)
        text_hash = self._hash_text(text)

        result = await db.execute(
            select(WordEmbedding).where(WordEmbedding.word_id == word.id)
        )
        record = result.scalar_one_or_none()

        if (
            not force_refresh
            and embedding_record_is_fresh(
                record=record,
                word=word,
                provider=self.provider.value,
                model=self.model,
            )
        ):
            return record

        embeddings = await self.llm.embed_texts([text], model=self.model)
        if not embeddings:
            return record

        record = self._upsert_record(
            record=record,
            word=word,
            text=text,
            text_hash=text_hash,
            vector=embeddings[0],
        )
        db.add(record)
        await db.flush()
        return record

    async def ensure_embeddings_for_words(
        self,
        db: AsyncSession,
        *,
        words: Sequence[Word],
        max_missing: int = 120,
        force_refresh: bool = False,
    ) -> dict[str, WordEmbedding]:
        if not words:
            return {}

        word_ids = [word.id for word in words]
        result = await db.execute(
            select(WordEmbedding).where(WordEmbedding.word_id.in_(word_ids))
        )
        existing = {record.word_id: record for record in result.scalars().all()}

        stale_batch: list[tuple[Word, Optional[WordEmbedding], str, str]] = []
        for word in words:
            record = existing.get(word.id)
            text = build_word_embedding_text(word)
            text_hash = self._hash_text(text)
            if (
                force_refresh
                or not embedding_record_is_fresh(
                    record=record,
                    word=word,
                    provider=self.provider.value,
                    model=self.model,
                )
            ):
                stale_batch.append((word, record, text, text_hash))

        batch = stale_batch[:max_missing]
        if batch:
            embeddings = await self.llm.embed_texts(
                [text for _, _, text, _ in batch],
                model=self.model,
            )
            for (word, record, text, text_hash), vector in zip(batch, embeddings):
                updated_record = self._upsert_record(
                    record=record,
                    word=word,
                    text=text,
                    text_hash=text_hash,
                    vector=vector,
                )
                db.add(updated_record)
                existing[word.id] = updated_record
            await db.flush()

        return {
            word_id: record
            for word_id, record in existing.items()
            if record.embedding
        }

    async def find_similar_words(
        self,
        db: AsyncSession,
        *,
        current_word: Word,
        catalog_words: Sequence[Word],
        limit: int = 30,
    ) -> list[Word]:
        if not catalog_words:
            return []

        current_record = await self.ensure_word_embedding(db, word=current_word)
        if current_record is None or not current_record.embedding:
            return []

        catalog_records = await self.ensure_embeddings_for_words(
            db,
            words=list(catalog_words),
        )
        candidate_embeddings = [
            (candidate, catalog_records[candidate.id].embedding)
            for candidate in catalog_words
            if candidate.id in catalog_records
        ]
        if not candidate_embeddings:
            return []

        ranked = rank_words_by_embedding_similarity(
            current_word=current_word,
            current_embedding=current_record.embedding,
            candidate_embeddings=candidate_embeddings,
            limit=limit,
        )
        await db.commit()
        return [candidate.word for candidate in ranked]

    async def backfill_embeddings(
        self,
        db: AsyncSession,
        *,
        words: Sequence[Word],
        batch_size: int = 100,
        force_refresh: bool = False,
        dry_run: bool = False,
    ) -> dict[str, int]:
        total_scanned = len(words)
        total_stale = 0
        total_written = 0
        batches = 0

        for start in range(0, total_scanned, max(batch_size, 1)):
            batch = list(words[start : start + max(batch_size, 1)])
            if not batch:
                continue
            batches += 1

            result = await db.execute(
                select(WordEmbedding).where(WordEmbedding.word_id.in_([word.id for word in batch]))
            )
            existing = {record.word_id: record for record in result.scalars().all()}
            stale_words = [
                word
                for word in batch
                if force_refresh
                or not embedding_record_is_fresh(
                    record=existing.get(word.id),
                    word=word,
                    provider=self.provider.value,
                    model=self.model,
                )
            ]
            stale_count = len(stale_words)
            total_stale += stale_count

            if dry_run or stale_count == 0:
                continue

            await self.ensure_embeddings_for_words(
                db,
                words=stale_words,
                max_missing=stale_count,
                force_refresh=force_refresh,
            )
            await db.commit()
            total_written += stale_count

        if dry_run:
            await db.rollback()

        return {
            "total_scanned": total_scanned,
            "total_stale": total_stale,
            "total_written": total_written,
            "batches": batches,
        }


_embedding_service: Optional[WordEmbeddingService] = None


def get_word_embedding_service() -> WordEmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = WordEmbeddingService()
    return _embedding_service