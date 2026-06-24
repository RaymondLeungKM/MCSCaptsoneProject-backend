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

    remaining_card_slots = max(max_cards - len(due_cards), 0)
    pending_new_cards = (existing_new_cards + new_cards)[:remaining_card_slots]
    all_cards = list(due_cards) + pending_new_cards
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
