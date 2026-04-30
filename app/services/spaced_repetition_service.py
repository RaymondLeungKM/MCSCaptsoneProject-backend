"""
Spaced Repetition Service – SM-2 Algorithm  (Epic 8.2)

The SuperMemo SM-2 algorithm determines the optimal next review date for
each vocabulary card so that children revise words *just before* they would
forget them, maximising long-term retention with minimal study time.

Quality ratings (q) passed in from the frontend:
  5 – perfect response, instant recall
  4 – correct response, slight hesitation
  3 – correct response, with serious difficulty
  2 – incorrect; but upon seeing the answer it felt obvious  (reset)
  1 – incorrect; the answer was hard to recall even after seeing it (reset)
  0 – complete blackout                                               (reset)

Reference: https://www.supermemo.com/en/archives1990-2015/english/ol/sm2
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase8 import SpacedRepetitionCard
from app.models.vocabulary import Word
from app.schemas.phase8 import (
    SpacedRepetitionCardResponse,
    ReviewQueueResponse,
    ReviewResultResponse,
)


# ---------------------------------------------------------------------------
# Pure SM-2 maths (no DB dependency)
# ---------------------------------------------------------------------------

def sm2_next(
    quality: int,
    repetitions: int,
    easiness_factor: float,
    interval: int,
) -> tuple[int, float, int]:
    """
    Compute the next SM-2 state.

    Returns (new_interval_days, new_easiness_factor, new_repetitions).
    """
    # Cap quality to valid range
    quality = max(0, min(5, quality))

    if quality < 3:
        # Incorrect – reset streak
        new_repetitions = 0
        new_interval    = 1
    else:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * easiness_factor)
        new_repetitions = repetitions + 1

    # Update easiness factor
    new_ef = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)   # floor at 1.3

    return new_interval, round(new_ef, 4), new_repetitions


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _enrich(card: SpacedRepetitionCard, word: Word) -> SpacedRepetitionCardResponse:
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


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def get_review_queue(
    db: AsyncSession,
    child_id: str,
    max_cards: int = 20,
    max_new: int = 5,
) -> ReviewQueueResponse:
    """
    Return cards that are due for review (``next_review <= now``).
    Also inject up to ``max_new`` brand-new cards to introduce fresh
    vocabulary.
    """
    now = datetime.now(timezone.utc)

    # Due cards
    due_result = await db.execute(
        select(SpacedRepetitionCard).where(
            SpacedRepetitionCard.child_id == child_id,
            SpacedRepetitionCard.next_review <= now,
            SpacedRepetitionCard.is_new == False,
        ).order_by(SpacedRepetitionCard.next_review).limit(max_cards)
    )
    due_cards = due_result.scalars().all()

    # New cards – words the child has been exposed to but not yet in SR
    from app.models.vocabulary import WordProgress
    exposure_result = await db.execute(
        select(WordProgress.word_id).where(
            WordProgress.child_id == child_id,
            WordProgress.exposure_count > 0,
        )
    )
    exposed_word_ids = [row[0] for row in exposure_result.all()]

    existing_sr_result = await db.execute(
        select(SpacedRepetitionCard.word_id).where(
            SpacedRepetitionCard.child_id == child_id
        )
    )
    existing_sr_ids = {row[0] for row in existing_sr_result.all()}

    new_word_ids = [wid for wid in exposed_word_ids if wid not in existing_sr_ids][:max_new]

    # Create SR cards for new words
    new_cards: List[SpacedRepetitionCard] = []
    for wid in new_word_ids:
        card = await _get_or_create_card(db, child_id, wid)
        new_cards.append(card)
    await db.commit()

    all_cards = list(due_cards) + new_cards
    all_word_ids = [c.word_id for c in all_cards]

    # Fetch words in one query
    words_result = await db.execute(
        select(Word).where(Word.id.in_(all_word_ids))
    )
    word_map = {w.id: w for w in words_result.scalars().all()}

    enriched = [_enrich(c, word_map.get(c.word_id)) for c in all_cards]

    return ReviewQueueResponse(
        cards=enriched,
        total_due=len(due_cards),
        new_cards_today=len(new_cards),
    )


async def process_review(
    db: AsyncSession,
    child_id: str,
    word_id: str,
    quality: int,
) -> ReviewResultResponse:
    """
    Apply SM-2 to the card and persist the new state.
    """
    card = await _get_or_create_card(db, child_id, word_id)

    new_interval, new_ef, new_reps = sm2_next(
        quality, card.repetitions, card.easiness_factor, card.interval
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
