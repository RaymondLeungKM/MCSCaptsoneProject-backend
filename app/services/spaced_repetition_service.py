"""
Spaced Repetition Service – Anki-modified SM-2 Algorithm  (Epic 8.2)

Anki departs from the original SM-2 paper in several ways that improve
real-world retention:

  1. Quality scale collapsed to four semantic buckets:
       0-1  Again  – failed; card lapses and interval is reduced
       2    Hard   – correct but harder than expected; small penalty
       3    Good   – correct as expected; normal progression
       4-5  Easy   – correct, easier than expected; bonus interval + EF boost

  2. Interval computation:
       Again  →  max(lapse_min, round(old_interval * lapse_pct))   EF −0.20
       Hard   →  max(1, round(old_interval * 1.2 * modifier))      EF −0.15
       Good   →  graduating/easy interval for new cards;            EF unchanged
                  round(old_interval * EF * modifier) for reviews
       Easy   →  easy_interval for new cards;                       EF +0.15
                  round(old_interval * EF * easy_bonus * modifier) for reviews

  3. All intervals are capped at max_interval_days.
  4. EF has a floor of 1.3 (same as original SM-2).

Parent-configurable parameters (stored in parental_controls):
  sr_easy_bonus          float  default 1.3   – multiplier added on Easy reviews
  sr_interval_modifier   float  default 1.0   – global scale on every interval
  sr_max_interval_days   int    default 36500  – ceiling
  sr_graduating_interval int    default 1      – days after first Good on new card
  sr_easy_interval       int    default 4      – days after first Easy on new/graduating card
  sr_lapse_interval_pct  float  default 0.0   – fraction of interval kept after Again
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import exp
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.word_personalization import (
    ReviewQueueDecision,
    SpacedRepetitionCard,
    WordRelationship,
)
from app.core.config import settings
from app.models.vocabulary import Word, WordProgress
from app.schemas.word_personalization import (
    ReviewQueueFeatures,
    SpacedRepetitionCardResponse,
    ReviewQueueResponse,
    ReviewResultResponse,
)
from app.services.word_graph_service import (
    build_relationship_maps,
    compute_graph_queue_score,
)


# ---------------------------------------------------------------------------
# Anki-modified SM-2 maths (no DB dependency)
# ---------------------------------------------------------------------------

class AnkiSRSettings:
    """Value object holding Anki SM-2 tuning knobs."""
    def __init__(
        self,
        easy_bonus: float = 1.3,
        interval_modifier: float = 1.0,
        max_interval_days: int = 36500,
        graduating_interval: int = 1,
        easy_interval: int = 4,
        lapse_interval_pct: float = 0.0,
    ) -> None:
        self.easy_bonus          = max(1.0, easy_bonus)
        self.interval_modifier   = max(0.1, interval_modifier)
        self.max_interval_days   = max(1, max_interval_days)
        self.graduating_interval = max(1, graduating_interval)
        self.easy_interval       = max(1, easy_interval)
        self.lapse_interval_pct  = max(0.0, min(1.0, lapse_interval_pct))


DEFAULT_ANKI_SETTINGS = AnkiSRSettings()


@dataclass(frozen=True)
class ReviewQueuePolicy:
    """Explainable, versioned weights for the graph-informed queue reranker."""

    version: str = "graph_reranker_v2"
    candidate_pool_multiplier: int = 3
    urgency_weight: float = 0.55
    learner_need_weight: float = 0.25
    graph_weight: float = 0.15
    quick_win_weight: float = 0.05
    diversity_lambda: float = 0.18
    critical_urgency_threshold: float = 0.85
    max_candidate_pool: int = 15
    max_graph_candidates: int = 0


DEFAULT_REVIEW_QUEUE_POLICY = ReviewQueuePolicy(
    version=settings.REVIEW_QUEUE_POLICY_VERSION,
    candidate_pool_multiplier=max(1, settings.REVIEW_QUEUE_CANDIDATE_POOL_MULTIPLIER),
    urgency_weight=settings.REVIEW_QUEUE_URGENCY_WEIGHT,
    learner_need_weight=settings.REVIEW_QUEUE_LEARNER_NEED_WEIGHT,
    graph_weight=settings.REVIEW_QUEUE_GRAPH_WEIGHT,
    quick_win_weight=settings.REVIEW_QUEUE_QUICK_WIN_WEIGHT,
    diversity_lambda=max(0.0, settings.REVIEW_QUEUE_DIVERSITY_LAMBDA),
    critical_urgency_threshold=min(1.0, max(0.0, settings.REVIEW_QUEUE_CRITICAL_URGENCY_THRESHOLD)),
    max_candidate_pool=max(1, settings.REVIEW_QUEUE_MAX_CANDIDATE_POOL),
    max_graph_candidates=max(0, settings.REVIEW_QUEUE_MAX_GRAPH_CANDIDATES),
)


def anki_sm2_next(
    quality: int,
    repetitions: int,
    easiness_factor: float,
    interval: int,
    settings: AnkiSRSettings = DEFAULT_ANKI_SETTINGS,
) -> tuple[int, float, int]:
    """
    Compute the next Anki-modified SM-2 state.

    Returns (new_interval_days, new_easiness_factor, new_repetitions).

    Quality buckets (maps the 0-5 frontend scale):
      0-1  → Again   (lapse)
      2    → Hard
      3    → Good
      4-5  → Easy
    """
    quality = max(0, min(5, quality))
    ef = max(1.3, easiness_factor)
    mod = settings.interval_modifier
    cap = settings.max_interval_days

    if quality <= 1:
        # Again / lapse
        new_ef   = max(1.3, ef - 0.20)
        lapse_iv = max(1, round(interval * settings.lapse_interval_pct))
        new_interval  = min(lapse_iv, cap)
        new_reps = 0

    elif quality == 2:
        # Hard – slightly punish EF, interval grows slowly
        new_ef  = max(1.3, ef - 0.15)
        if repetitions == 0:
            # Hard on a brand-new card: stay at graduating interval
            new_interval = min(settings.graduating_interval, cap)
        else:
            new_interval = min(max(1, round(interval * 1.2 * mod)), cap)
        new_reps = repetitions + 1

    elif quality == 3:
        # Good – normal progression, EF unchanged
        new_ef = ef
        if repetitions == 0:
            new_interval = min(settings.graduating_interval, cap)
        elif repetitions == 1:
            new_interval = min(settings.easy_interval, cap)
        else:
            new_interval = min(max(1, round(interval * ef * mod)), cap)
        new_reps = repetitions + 1

    else:
        # Easy (quality 4-5) – bonus interval + EF boost
        new_ef = min(ef + 0.15, 5.0)
        if repetitions <= 1:
            new_interval = min(settings.easy_interval, cap)
        else:
            new_interval = min(
                max(1, round(interval * ef * settings.easy_bonus * mod)), cap
            )
        new_reps = repetitions + 1

    return new_interval, round(new_ef, 4), new_reps


# Keep the old name as an alias so any other callers don't break.
def sm2_next(
    quality: int,
    repetitions: int,
    easiness_factor: float,
    interval: int,
) -> tuple[int, float, int]:
    """Legacy wrapper – delegates to anki_sm2_next with default settings."""
    return anki_sm2_next(quality, repetitions, easiness_factor, interval)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _enrich(
    card: SpacedRepetitionCard,
    word: Word,
    queue_reason: str | None = None,
    queue_features: ReviewQueueFeatures | None = None,
) -> SpacedRepetitionCardResponse:
    return SpacedRepetitionCardResponse(
        id=card.id,
        child_id=card.child_id,
        word_id=card.word_id,
        easiness_factor=card.easiness_factor,
        interval=card.interval,
        repetitions=card.repetitions,
        last_quality=card.last_quality,
        next_review=card.next_review,
        last_reviewed=card.last_reviewed,
        is_new=card.is_new,
        is_graduated=card.is_graduated,
        word=word.word if word else None,
        word_cantonese=word.word_cantonese if word else None,
        jyutping=word.jyutping if word else None,
        image_url=word.image_url if word else None,
        audio_url=word.audio_url if word else None,
        definition_cantonese=word.definition_cantonese if word else None,
        queue_reason=queue_reason,
        queue_features=queue_features,
    )


async def _get_or_create_card(
    db: AsyncSession,
    child_id: str,
    word_id: str,
) -> SpacedRepetitionCard:
    result = await db.execute(
        select(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.word_id  == word_id,
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        card = SpacedRepetitionCard(
            child_id=child_id,
            word_id=word_id,
        )
        db.add(card)
        await db.flush()  # get the id
    return card


@dataclass
class _QueueCandidate:
    card: SpacedRepetitionCard
    word: Word | None
    reason: str
    due_score: float
    graph_score: float
    bridge_score: float
    centrality_score: float
    weak_link_boost: float
    quick_win_score: float
    base_score: float
    category: str
    urgency_score: float = 0.0
    learner_need_score: float = 0.0
    graph_connectivity_score: float = 0.0
    candidate_pool_rank: int = 0
    diversity_penalty: float = 0.0
    final_score: float = 0.0


def _compute_due_score(card: SpacedRepetitionCard, now: datetime) -> float:
    """Legacy alias retained for API clients; v2 urgency is normalized to [0, 1]."""
    return _compute_urgency_score(card, now)


def _compute_urgency_score(card: SpacedRepetitionCard, now: datetime) -> float:
    if card.is_new:
        return 0.05

    overdue_seconds = max((now - card.next_review).total_seconds(), 0.0)
    overdue_days = overdue_seconds / 86400
    return round(1.0 - exp(-overdue_days / 3.0), 4)


def _compute_weak_link_ratio(progress: WordProgress | None) -> float:
    """Legacy alias retained for API clients; v2 names this learner need."""
    return _compute_learner_need_score(progress)


def _compute_learner_need_score(progress: WordProgress | None) -> float:
    if not progress or progress.total_attempts <= 0:
        return 0.0

    # Beta(1, 1) smoothing prevents one early failure from dominating the queue.
    successful_attempts = progress.success_rate * progress.total_attempts
    smoothed_success = (successful_attempts + 1.0) / (progress.total_attempts + 2.0)
    low_success = max(0.0, (0.8 - smoothed_success) / 0.8)
    exposure_pressure = min(1.0, progress.exposure_count / 10.0)
    not_mastered_bonus = 0.2 if not progress.mastered else 0.0

    return round(min(1.0, low_success * 0.7 + exposure_pressure * 0.3 + not_mastered_bonus), 4)


def _compute_quick_win_score(
    card: SpacedRepetitionCard,
    progress: WordProgress | None,
) -> float:
    if card.is_new:
        return 0.0

    success_rate = progress.success_rate if progress and progress.total_attempts > 0 else 0.75
    success_component = max(0.0, min(1.0, success_rate)) * 0.5
    repetition_component = min(1.0, card.repetitions / 6.0) * 0.3
    ef_component = min(1.0, max(card.easiness_factor - 2.0, 0.0) / 1.5) * 0.2

    return round(success_component + repetition_component + ef_component, 4)


def _resolve_primary_reason(
    *,
    due_score: float,
    bridge_score: float,
    weak_link_ratio: float,
    quick_win_score: float,
) -> str:
    if weak_link_ratio >= 0.65:
        return "weak_link"
    if bridge_score >= 0.55:
        return "bridge"
    if due_score >= 0.75:
        return "due"
    if quick_win_score >= 0.7:
        return "quick_win"
    return "balance"


def _resolve_primary_reason_v2(candidate: _QueueCandidate, policy: ReviewQueuePolicy) -> str:
    contributions = {
        "due": candidate.urgency_score * policy.urgency_weight,
        "weak_link": candidate.learner_need_score * policy.learner_need_weight,
        "bridge": candidate.graph_connectivity_score * policy.graph_weight,
        "quick_win": candidate.quick_win_score * policy.quick_win_weight,
    }
    return max(contributions, key=contributions.get) if max(contributions.values()) > 0 else "balance"


def _select_ranked_candidates(
    candidates: list[_QueueCandidate],
    max_cards: int,
    policy: ReviewQueuePolicy = DEFAULT_REVIEW_QUEUE_POLICY,
) -> list[_QueueCandidate]:
    """Greedy MMR reranker with explicit protection for highly overdue cards."""
    selected: list[_QueueCandidate] = []
    remaining = list(candidates)

    while remaining and len(selected) < max_cards:
        best_index = 0
        best_score = float("-inf")

        for index, candidate in enumerate(remaining):
            redundancy = max(
                (_candidate_similarity(candidate, selected_candidate) for selected_candidate in selected),
                default=0.0,
            )
            penalty = 0.0 if candidate.urgency_score >= policy.critical_urgency_threshold else policy.diversity_lambda * redundancy
            adjusted_score = candidate.base_score - penalty
            tie_breaker = (candidate.base_score, -candidate.card.next_review.timestamp(), candidate.card.word_id)
            if (adjusted_score, tie_breaker) > (
                best_score,
                (
                    remaining[best_index].base_score,
                    -remaining[best_index].card.next_review.timestamp(),
                    remaining[best_index].card.word_id,
                ),
            ):
                best_score = adjusted_score
                best_index = index

        picked = remaining.pop(best_index)

        picked.diversity_penalty = round(max(0.0, picked.base_score - best_score), 4)
        picked.final_score = round(best_score, 4)
        selected.append(picked)

    return selected


def _candidate_similarity(left: _QueueCandidate, right: _QueueCandidate) -> float:
    """A simple, explainable redundancy proxy for MMR reranking."""
    if left.category == right.category and left.category != "unknown":
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def get_review_queue(
    db: AsyncSession,
    child_id: str,
    max_cards: int = 20,
    max_new: int = 5,
    policy: ReviewQueuePolicy = DEFAULT_REVIEW_QUEUE_POLICY,
) -> ReviewQueueResponse:
    """
    Return cards that are due for review (``next_review <= now``).
    Also inject up to ``max_new`` brand-new cards to introduce fresh
    vocabulary.
    """
    now = datetime.now(timezone.utc)

    max_cards = max(1, max_cards)
    max_new = max(0, max_new)
    due_pool_limit = min(
        max_cards * policy.candidate_pool_multiplier,
        policy.max_candidate_pool,
    )

    total_due_result = await db.execute(
        select(func.count()).select_from(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.next_review <= now,
            SpacedRepetitionCard.is_new == False,
        )
    )
    total_due = total_due_result.scalar_one()

    # Retrieve a broader urgency-ranked set before graph-informed reranking.
    due_result = await db.execute(
        select(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.next_review <= now,
            SpacedRepetitionCard.is_new == False,
        ).order_by(SpacedRepetitionCard.next_review, SpacedRepetitionCard.word_id).limit(due_pool_limit)
    )
    due_cards = due_result.scalars().all()

    # Existing new cards that were created earlier but not yet reviewed.
    # Without this, is_new cards can disappear after reload because they are
    # excluded from due-cards and also excluded from fresh-card creation.
    existing_new_result = await db.execute(
        select(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.is_new == True,
        ).order_by(SpacedRepetitionCard.created_at.desc()).limit(max_new)
    )
    existing_new_cards = existing_new_result.scalars().all()

    # New cards – words the child has been exposed to but not yet in SR
    from app.models.vocabulary import WordProgress
    exposure_result = await db.execute(
        select(WordProgress.word_id).join(Word, Word.id == WordProgress.word_id).where(
            WordProgress.child_id == child_id,
            WordProgress.exposure_count > 0,
            Word.is_active == True,
        ).order_by(WordProgress.created_at.desc(), WordProgress.word_id)
    )
    exposed_word_ids = [row[0] for row in exposure_result.all()]

    existing_sr_result = await db.execute(
        select(SpacedRepetitionCard.word_id).where(
            SpacedRepetitionCard.child_id == child_id
        )
    )
    existing_sr_ids = {row[0] for row in existing_sr_result.all()}

    remaining_new_slots = max(max_new - len(existing_new_cards), 0)
    new_word_ids = [
        wid for wid in exposed_word_ids
        if wid not in existing_sr_ids
    ][:remaining_new_slots]

    # Create SR cards for new words
    new_cards: List[SpacedRepetitionCard] = []
    for wid in new_word_ids:
        card = await _get_or_create_card(db, child_id, wid)
        new_cards.append(card)
    await db.commit()

    pending_new_cards = (existing_new_cards + new_cards)[:max_new]
    all_cards = list(due_cards) + pending_new_cards
    all_word_ids = [c.word_id for c in all_cards]

    # Early review of graph neighbours is opt-in and disabled by default.
    if policy.max_graph_candidates and exposed_word_ids:
        graph_candidate_ids_result = await db.execute(
            select(WordRelationship.related_word_id)
            .where(
                WordRelationship.word_id.in_(exposed_word_ids),
                WordRelationship.strength >= 0.45,
            )
            .order_by(WordRelationship.strength.desc(), WordRelationship.related_word_id)
            .limit(policy.max_graph_candidates * 3)
        )
        graph_candidate_ids = [
            row[0]
            for row in graph_candidate_ids_result.all()
            if row[0] not in set(all_word_ids)
        ][:policy.max_graph_candidates]

        if graph_candidate_ids:
            graph_cards_result = await db.execute(
                select(SpacedRepetitionCard)
                .join(Word, Word.id == SpacedRepetitionCard.word_id)
                .where(
                    SpacedRepetitionCard.child_id == child_id,
                    SpacedRepetitionCard.word_id.in_(graph_candidate_ids),
                    SpacedRepetitionCard.is_new == False,
                    SpacedRepetitionCard.next_review > now,
                    Word.is_active == True,
                )
            )
            graph_cards_by_word_id = {
                card.word_id: card for card in graph_cards_result.scalars().all()
            }
            all_cards.extend(
                graph_cards_by_word_id[word_id]
                for word_id in graph_candidate_ids
                if word_id in graph_cards_by_word_id
            )
            all_word_ids = [card.word_id for card in all_cards]

    if not all_cards:
        return ReviewQueueResponse(
            cards=[],
            total_due=total_due,
            new_cards_today=0,
            policy_version=policy.version,
        )

    # Fetch words in one query
    words_result = await db.execute(
        select(Word).where(Word.id.in_(all_word_ids))
    )
    word_map = {w.id: w for w in words_result.scalars().all()}

    progress_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id.in_(all_word_ids),
        )
    )
    progress_map = {progress.word_id: progress for progress in progress_result.scalars().all()}

    known_progress_result = await db.execute(
        select(WordProgress.word_id).where(
            WordProgress.child_id == child_id,
            WordProgress.exposure_count > 0,
        )
    )
    known_word_ids = {row[0] for row in known_progress_result.all()}

    graph_scope_word_ids = set(all_word_ids) | known_word_ids
    relationships_result = await db.execute(
        select(WordRelationship).where(
            WordRelationship.word_id.in_(list(graph_scope_word_ids)),
            WordRelationship.related_word_id.in_(list(graph_scope_word_ids)),
        )
    )
    relationships = relationships_result.scalars().all()
    outgoing_map, incoming_degree = build_relationship_maps(relationships)

    candidates: list[_QueueCandidate] = []
    for card in all_cards:
        progress = progress_map.get(card.word_id)
        learner_need_score = _compute_learner_need_score(progress)
        graph_score = compute_graph_queue_score(
            card.word_id,
            outgoing_map=outgoing_map,
            incoming_degree=incoming_degree,
            known_word_ids=known_word_ids,
            weak_link_ratio=learner_need_score,
        )
        urgency_score = _compute_urgency_score(card, now)
        quick_win_score = _compute_quick_win_score(card, progress)
        graph_connectivity_score = round(
            graph_score.bridge_score * 0.65 + graph_score.centrality_score * 0.35,
            4,
        )
        base_score = round(
            urgency_score * policy.urgency_weight
            + learner_need_score * policy.learner_need_weight
            + graph_connectivity_score * policy.graph_weight
            + quick_win_score * policy.quick_win_weight,
            4,
        )

        word = word_map.get(card.word_id)
        category = word.category if word and word.category else "unknown"

        candidates.append(
            _QueueCandidate(
                card=card,
                word=word,
                reason="balance",
                urgency_score=urgency_score,
                learner_need_score=learner_need_score,
                graph_connectivity_score=graph_connectivity_score,
                due_score=urgency_score,
                graph_score=graph_score.graph_score,
                bridge_score=graph_score.bridge_score,
                centrality_score=graph_score.centrality_score,
                weak_link_boost=graph_score.weak_link_boost,
                quick_win_score=quick_win_score,
                base_score=base_score,
                category=category,
            )
        )

    # Deterministic baseline ordering before applying composition and diversity balancing.
    candidates.sort(
        key=lambda candidate: (
            -candidate.base_score,
            candidate.card.next_review,
            candidate.card.word_id,
        )
    )
    for candidate_pool_rank, candidate in enumerate(candidates, start=1):
        candidate.candidate_pool_rank = candidate_pool_rank
        candidate.reason = _resolve_primary_reason_v2(candidate, policy)

    selected_candidates = _select_ranked_candidates(candidates, max_cards, policy)
    selected_ranks = {candidate.card.word_id: rank for rank, candidate in enumerate(selected_candidates, start=1)}

    for candidate in candidates:
        db.add(
            ReviewQueueDecision(
                child_id=child_id,
                word_id=candidate.card.word_id,
                policy_version=policy.version,
                candidate_pool_rank=candidate.candidate_pool_rank,
                final_queue_rank=selected_ranks.get(candidate.card.word_id),
                selected=candidate.card.word_id in selected_ranks,
                queue_reason=candidate.reason,
                feature_snapshot={
                    "urgency_score": candidate.urgency_score,
                    "learner_need_score": candidate.learner_need_score,
                    "graph_connectivity_score": candidate.graph_connectivity_score,
                    "quick_win_score": candidate.quick_win_score,
                    "relevance_score": candidate.base_score,
                    "redundancy_penalty": candidate.diversity_penalty,
                    "final_score": candidate.final_score,
                    "category": candidate.category,
                },
            )
        )
    await db.commit()

    enriched = [
        _enrich(
            candidate.card,
            candidate.word,
            queue_reason=candidate.reason,
            queue_features=ReviewQueueFeatures(
                urgency_score=candidate.urgency_score,
                learner_need_score=candidate.learner_need_score,
                graph_connectivity_score=candidate.graph_connectivity_score,
                quick_win_score=candidate.quick_win_score,
                due_score=candidate.due_score,
                graph_score=candidate.graph_score,
                bridge_score=candidate.bridge_score,
                centrality_score=candidate.centrality_score,
                weak_link_boost=candidate.weak_link_boost,
                diversity_penalty=candidate.diversity_penalty,
                final_score=candidate.final_score,
                candidate_pool_rank=candidate.candidate_pool_rank,
                final_queue_rank=final_queue_rank,
                policy_version=policy.version,
            ),
        )
        for final_queue_rank, candidate in enumerate(selected_candidates, start=1)
    ]

    return ReviewQueueResponse(
        cards=enriched,
        total_due=total_due,
        new_cards_today=len(new_cards),
        policy_version=policy.version,
    )


async def process_review(
    db: AsyncSession,
    child_id: str,
    word_id: str,
    quality: int,
    settings: AnkiSRSettings = DEFAULT_ANKI_SETTINGS,
) -> ReviewResultResponse:
    """
    Apply Anki-modified SM-2 to the card and persist the new state.
    Pass a populated AnkiSRSettings to use parent-configured tuning.
    """
    card = await _get_or_create_card(db, child_id, word_id)

    new_interval, new_ef, new_reps = anki_sm2_next(
        quality, card.repetitions, card.easiness_factor, card.interval, settings
    )

    now = datetime.now(timezone.utc)
    card.easiness_factor = new_ef
    card.interval        = new_interval
    card.repetitions     = new_reps
    card.last_quality    = quality
    card.last_reviewed   = now
    card.next_review     = now + timedelta(days=new_interval)
    card.is_new          = False
    card.is_graduated    = new_interval > 21

    await db.commit()
    await db.refresh(card)

    if quality < 3:
        message = "繼續努力！我們很快再複習這個詞彙。"
    elif quality == 5:
        message = "非常棒！你已經完全掌握了這個詞彙！🌟"
    elif new_interval >= 14:
        message = f"做得好！下次複習在 {new_interval} 天後。"
    else:
        message = f"良好！下次複習在 {new_interval} 天後。"

    return ReviewResultResponse(
        word_id=word_id,
        new_interval=card.interval,
        easiness_factor=card.easiness_factor,
        next_review=card.next_review,
        is_graduated=card.is_graduated,
        message=message,
    )


async def get_learning_speed_profile(
    db: AsyncSession,
    child_id: str,
) -> dict:
    """
    Compute a simple learning-speed profile from the child's SR card history.
    Returns avg EF, avg interval, graduation rate, and a textual assessment.
    """
    result = await db.execute(
        select(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.is_new == False,
        )
    )
    cards = result.scalars().all()

    if not cards:
        return {
            "avg_easiness_factor": 2.5,
            "avg_interval": 1,
            "graduation_rate": 0.0,
            "total_cards": 0,
            "assessment": "尚未有足夠數據，繼續學習吧！",
        }

    avg_ef    = sum(c.easiness_factor for c in cards) / len(cards)
    avg_ivl   = sum(c.interval        for c in cards) / len(cards)
    grad_rate = sum(1 for c in cards if c.is_graduated) / len(cards)

    if avg_ef >= 2.6 and grad_rate >= 0.5:
        assessment = "學習速度很快！記憶力強，保持下去！🚀"
    elif avg_ef >= 2.2:
        assessment = "學習進度穩定，繼續努力！😊"
    else:
        assessment = "需要多些重複練習，別灰心，多練習就能進步！💪"

    return {
        "avg_easiness_factor": round(avg_ef, 3),
        "avg_interval":        round(avg_ivl, 1),
        "graduation_rate":     round(grad_rate, 3),
        "total_cards":         len(cards),
        "assessment":          assessment,
    }
