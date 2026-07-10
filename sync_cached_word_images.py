"""
Sync vocabulary image_url fields to the cached generated images on disk.

This script is idempotent. It only updates words whose current image_url is
still a placeholder and where a cached file already exists in
uploads/images/words.

Usage:
  ./venv/bin/python sync_cached_word_images.py
  ./venv/bin/python sync_cached_word_images.py --category Stationery
  ./venv/bin/python sync_cached_word_images.py --dry-run
"""

import argparse
import asyncio
from typing import Optional

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, LearningSession  # noqa: F401
from app.models.community import CommunityPost, ModerationStatus, PostReaction  # noqa: F401
from app.models.content import Game, Mission, Story  # noqa: F401
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.services.curated_word_images import get_curated_word_image_url
from app.models.user import Child, User  # noqa: F401
from app.models.vocabulary import Category, Word, WordProgress  # noqa: F401
from app.services.image_generation_service import _cache_key, _cached_image_path


def _is_real_image_url(value: Optional[str]) -> bool:
    return bool(
        value and (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("/")
        )
    )


def _resolve_cached_image_url(word: Word) -> Optional[str]:
    curated_image_url = get_curated_word_image_url(word.word)
    if curated_image_url:
        return curated_image_url

    if _is_real_image_url(word.image_url):
        return word.image_url

    cached_path = _cached_image_path(_cache_key(word.word, word.word_cantonese or ""))
    if not cached_path:
        return None
    return f"/uploads/images/words/{cached_path.name}"


async def sync_cached_word_images(category: Optional[str] = None, dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        query = select(Word).where(Word.is_active == True).order_by(Word.word.asc())

        if category:
            query = query.join(Category, Word.category == Category.id).where(
                func.lower(Category.name) == category.strip().lower()
            )

        result = await db.execute(query)
        words = list(result.scalars().all())

        already_real = 0
        no_cache = 0
        updated: list[tuple[str, str, str]] = []

        for word in words:
            cached_image_url = _resolve_cached_image_url(word)
            if not cached_image_url:
                no_cache += 1
                continue

            if cached_image_url == word.image_url:
                already_real += 1
                continue

            updated.append((word.word, word.word_cantonese or "", cached_image_url))
            if not dry_run:
                word.image_url = cached_image_url

        if not dry_run:
            await db.commit()

        print("Synced cached word images")
        print(f"  Words scanned: {len(words)}")
        print(f"  Already had real image URLs: {already_real}")
        print(f"  Updated from cache: {len(updated)}")
        print(f"  No cached image found: {no_cache}")

        if updated:
            print("  Sample updates:")
            for word, word_cantonese, image_url in updated[:12]:
                label = f"{word} / {word_cantonese}" if word_cantonese else word
                print(f"    - {label} -> {image_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync cached generated images into vocabulary.image_url")
    parser.add_argument("--category", type=str, default=None, help="Only sync one category, e.g. Stationery")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing to the database")
    args = parser.parse_args()

    asyncio.run(sync_cached_word_images(category=args.category, dry_run=args.dry_run))


if __name__ == "__main__":
    main()