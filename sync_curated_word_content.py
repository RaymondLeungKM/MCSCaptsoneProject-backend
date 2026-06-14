"""Sync curated Cantonese labels/jyutping and curated image URLs into words.

Usage:
  ./venv/bin/python sync_curated_word_content.py
  ./venv/bin/python sync_curated_word_content.py --word Puzzle --word Ruler
  ./venv/bin/python sync_curated_word_content.py --dry-run
"""

import argparse
import asyncio

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.analytics import Achievement, DailyStats, LearningSession  # noqa: F401
from app.models.community import CommunityPost, ModerationStatus, PostReaction  # noqa: F401
from app.models.content import Game, Mission, Story  # noqa: F401
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    DailyLearningStats,
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.user import Child, User  # noqa: F401
from app.models.vocabulary import Category, Word, WordProgress  # noqa: F401
from app.services.curated_cantonese_vocabulary import CURATED_CANTONESE_WORDS
from app.services.curated_word_images import get_curated_word_image_url


async def sync_curated_word_content(
    words: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    async with AsyncSessionLocal() as db:
        query = select(Word).where(Word.is_active == True).order_by(Word.word.asc())

        if words:
            normalized = [word.strip().lower() for word in words if word.strip()]
            query = query.where(func.lower(Word.word).in_(normalized))

        result = await db.execute(query)
        records = list(result.scalars().all())

        updated: list[tuple[str, str, str, str | None]] = []

        for record in records:
            original = (
                record.word_cantonese or "",
                record.jyutping or "",
                record.image_url,
            )

            curated = CURATED_CANTONESE_WORDS.get(record.word)
            if curated:
                record.word_cantonese = curated["word_cantonese"]
                record.jyutping = curated["jyutping"]

            curated_image_url = get_curated_word_image_url(record.word)
            if curated_image_url:
                record.image_url = curated_image_url

            current = (
                record.word_cantonese or "",
                record.jyutping or "",
                record.image_url,
            )
            if current != original:
                updated.append(
                    (
                        record.word,
                        record.word_cantonese or "",
                        record.jyutping or "",
                        record.image_url,
                    )
                )

        if not dry_run:
            await db.commit()

        print("Synced curated word content")
        print(f"  Words scanned: {len(records)}")
        print(f"  Updated rows: {len(updated)}")
        if updated:
            print("  Updated entries:")
            for word, word_cantonese, jyutping, image_url in updated:
                print(f"    - {word} | {word_cantonese} | {jyutping} | {image_url}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync curated Cantonese word labels and image URLs into vocabulary records",
    )
    parser.add_argument(
        "--word",
        action="append",
        default=[],
        help="Limit sync to one English word. Repeat for multiple words.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview updates without writing changes.",
    )
    args = parser.parse_args()

    asyncio.run(sync_curated_word_content(words=args.word, dry_run=args.dry_run))


if __name__ == "__main__":
    main()