"""
Word Knowledge Graph Service  (Epic 8.1)

Manages word-relationship edges stored in PostgreSQL and provides
graph-based vocabulary recommendation queries.

Design notes
------------
* We store edges in both directions so that queries can use a single
  WHERE clause on ``word_id`` rather than an OR across two columns.
* Auto-seeding: on first call for a word the service inspects the
  word's ``related_words`` JSONB field and ``category`` to create
  initial edges, avoiding a cold-start on a fresh database.
"""
from __future__ import annotations

import uuid
from typing import List, Optional, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase8 import WordRelationship, RelationshipType
from app.models.vocabulary import Word, WordProgress
from app.schemas.phase8 import (
    WordNode, WordEdge, WordGraphResponse, GraphRecommendationResponse
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_node(word: Word, progress: Optional[WordProgress]) -> WordNode:
    return WordNode(
        word_id=word.id,
        word=word.word,
        word_cantonese=word.word_cantonese,
        jyutping=word.jyutping,
        category=word.category,
        difficulty=word.difficulty.value if word.difficulty else "easy",
        mastered=progress.mastered if progress else False,
        exposure_count=progress.exposure_count if progress else 0,
    )


# ---------------------------------------------------------------------------
# Core service functions
# ---------------------------------------------------------------------------

async def get_word_graph(
    db: AsyncSession,
    centre_word_id: str,
    child_id: str,
    depth: int = 1,
) -> WordGraphResponse:
    """
    Return a subgraph centred on *centre_word_id*.

    ``depth=1``  → direct neighbours only (default)
    ``depth=2``  → neighbours-of-neighbours (can be large, use with care)
    """
    visited_ids: Set[str] = {centre_word_id}
    queue: List[str] = [centre_word_id]
    all_edges: List[WordEdge] = []

    for _ in range(depth):
        if not queue:
            break
        # Fetch all outgoing edges for the current frontier
        result = await db.execute(
            select(WordRelationship).where(WordRelationship.word_id.in_(queue))
        )
        rels = result.scalars().all()

        next_queue: List[str] = []
        for rel in rels:
            all_edges.append(WordEdge(
                source_id=rel.word_id,
                target_id=rel.related_word_id,
                relationship_type=rel.relationship_type,
                strength=rel.strength,
            ))
            if rel.related_word_id not in visited_ids:
                visited_ids.add(rel.related_word_id)
                next_queue.append(rel.related_word_id)

        queue = next_queue

    # If this word has no relationships yet, auto-seed from JSONB field
    if not all_edges:
        await auto_seed_relationships(db, centre_word_id)
        # Retry once
        result = await db.execute(
            select(WordRelationship).where(WordRelationship.word_id == centre_word_id)
        )
        rels = result.scalars().all()
        for rel in rels:
            visited_ids.add(rel.related_word_id)
            all_edges.append(WordEdge(
                source_id=rel.word_id,
                target_id=rel.related_word_id,
                relationship_type=rel.relationship_type,
                strength=rel.strength,
            ))

    # Fetch all word records in visited set
    words_result = await db.execute(
        select(Word).where(Word.id.in_(list(visited_ids)))
    )
    words = {w.id: w for w in words_result.scalars().all()}

    # Fetch child progress
    progress_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id.in_(list(visited_ids)),
        )
    )
    progress_map = {p.word_id: p for p in progress_result.scalars().all()}

    nodes = [
        _to_node(words[wid], progress_map.get(wid))
        for wid in visited_ids
        if wid in words
    ]

    return WordGraphResponse(
        centre_word_id=centre_word_id,
        nodes=nodes,
        edges=all_edges,
    )


async def get_graph_recommendations(
    db: AsyncSession,
    child_id: str,
    limit: int = 5,
) -> GraphRecommendationResponse:
    """
    Walk the knowledge graph from all words the child knows and recommend
    the highest-connectivity *unmastered* neighbours.
    """
    # Words the child has been exposed to
    exposed_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.exposure_count > 0,
        )
    )
    exposed = exposed_result.scalars().all()
    mastered_ids = {p.word_id for p in exposed if p.mastered}
    known_ids    = {p.word_id for p in exposed}

    if not known_ids:
        # Cold start: return easy words from any category
        result = await db.execute(
            select(Word).where(Word.difficulty == "easy", Word.is_active == True).limit(limit)
        )
        words = result.scalars().all()
        return GraphRecommendationResponse(
            recommended_words=[_to_node(w, None) for w in words],
            reason="開始學習基礎詞彙！",
            bridge_concepts=[],
        )

    # Find outgoing edges from known words, grouping by target
    result = await db.execute(
        select(
            WordRelationship.related_word_id,
            func.sum(WordRelationship.strength).label("total_strength"),
            func.count(WordRelationship.id).label("connection_count"),
        )
        .where(WordRelationship.word_id.in_(list(known_ids)))
        .group_by(WordRelationship.related_word_id)
        .order_by(func.sum(WordRelationship.strength).desc())
    )
    rows = result.all()

    # Keep only unmastered/unseen words
    candidate_ids = [
        row.related_word_id
        for row in rows
        if row.related_word_id not in mastered_ids
        and row.related_word_id not in known_ids
    ][:limit * 2]  # over-fetch then trim

    if not candidate_ids:
        # Fallback: words in same categories as known words
        known_words_result = await db.execute(
            select(Word).where(Word.id.in_(list(known_ids)))
        )
        known_words = known_words_result.scalars().all()
        categories = list({w.category for w in known_words})

        result = await db.execute(
            select(Word).where(
                Word.category.in_(categories),
                Word.id.notin_(list(known_ids)),
                Word.is_active == True,
            ).limit(limit)
        )
        words = result.scalars().all()
        return GraphRecommendationResponse(
            recommended_words=[_to_node(w, None) for w in words],
            reason="根據你已學習的類別，推薦相關詞彙！",
            bridge_concepts=categories,
        )

    words_result = await db.execute(
        select(Word).where(Word.id.in_(candidate_ids[:limit]))
    )
    words = {w.id: w for w in words_result.scalars().all()}

    recommended = [
        _to_node(words[wid], None)
        for wid in candidate_ids[:limit]
        if wid in words
    ]

    bridge_concepts = list({w.category for w in words.values()})

    return GraphRecommendationResponse(
        recommended_words=recommended,
        reason=f"根據你的知識圖譜，推薦 {len(recommended)} 個相關詞彙！",
        bridge_concepts=bridge_concepts,
    )


async def add_relationship(
    db: AsyncSession,
    word_id: str,
    related_word_id: str,
    relationship_type: RelationshipType = RelationshipType.SEMANTIC,
    strength: float = 0.7,
    source: str = "system",
    bidirectional: bool = True,
) -> None:
    """
    Insert one (or two, if bidirectional) edges, ignoring duplicates.
    """
    for w_a, w_b in [(word_id, related_word_id)] + (
        [(related_word_id, word_id)] if bidirectional else []
    ):
        existing = await db.execute(
            select(WordRelationship).where(
                WordRelationship.word_id == w_a,
                WordRelationship.related_word_id == w_b,
                WordRelationship.relationship_type == relationship_type,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(WordRelationship(
                word_id=w_a,
                related_word_id=w_b,
                relationship_type=relationship_type,
                strength=strength,
                source=source,
            ))
    await db.commit()


async def auto_seed_relationships(
    db: AsyncSession,
    word_id: str,
) -> None:
    """
    Bootstrap relationships for a word from its own ``related_words``
    JSONB field and from other words in the same category.
    Called lazily on first graph query.
    """
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()
    if not word:
        return

    # 1. Explicit related_words list stored on the word record
    if word.related_words:
        related_ids = word.related_words if isinstance(word.related_words, list) else []
        for rid in related_ids:
            await add_relationship(
                db, word_id, rid,
                RelationshipType.SEMANTIC, strength=0.8, source="word_field",
                bidirectional=True,
            )

    # 2. Implicit same-category peers (sample up to 5 peers)
    peers_result = await db.execute(
        select(Word).where(
            Word.category == word.category,
            Word.id != word_id,
            Word.is_active == True,
        ).limit(5)
    )
    peers = peers_result.scalars().all()
    for peer in peers:
        await add_relationship(
            db, word_id, peer.id,
            RelationshipType.CATEGORY, strength=0.6, source="auto_category",
            bidirectional=True,
        )
