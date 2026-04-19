"""
Pre-generate images for all vocabulary words and store them in MongoDB.

Fetches all words from PostgreSQL, generates cartoon images via Silicon Flow,
and stores the image binary data in MongoDB's word_images collection.
Words that already have an image in MongoDB are skipped.

Usage:
  python pregenerate_images.py              # Generate for words missing images
  python pregenerate_images.py --force      # Re-generate all images
  python pregenerate_images.py --limit 10   # Only generate for 10 words
"""
import argparse
import asyncio
import sys
import time

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
# Import all models to ensure relationships are configured
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement
from app.models.parent_analytics import DailyLearningStats, LearningInsight, WeeklyReport, ParentalControl
from app.models.generated_sentences import GeneratedSentence
from app.models.daily_words import DailyWordTracking
from app.services.image_generation_service import (
    _cache_key,
    _generate_kolors,
    _save_cache,
    _save_to_mongo,
    _get_from_mongo,
    translate_to_english,
)


async def pregenerate_all(force: bool = False, limit: int | None = None):
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        print("❌ MongoDB is not enabled. Set MONGODB_ENABLED=true and MONGODB_URI in .env")
        sys.exit(1)

    # Fetch all active words from PostgreSQL
    async with AsyncSessionLocal() as session:
        query = select(Word).where(Word.is_active == True).order_by(Word.word)
        if limit:
            query = query.limit(limit)
        result = await session.execute(query)
        words = result.scalars().all()

    total = len(words)
    print(f"📋 Found {total} active words")

    generated = 0
    skipped = 0
    failed = 0

    for i, w in enumerate(words, 1):
        word = w.word
        word_cantonese = w.word_cantonese or ""
        cache_key = _cache_key(word, word_cantonese)

        # Skip if already in MongoDB (unless --force)
        if not force:
            existing = _get_from_mongo(cache_key)
            if existing:
                skipped += 1
                print(f"  [{i}/{total}] ⏭️  {word} ({word_cantonese}) — already in MongoDB")
                continue

        # Translate to English
        english_word = await translate_to_english(word, word_cantonese)
        print(f"  [{i}/{total}] 🎨 {word} ({word_cantonese}) → '{english_word}' ... ", end="", flush=True)

        # Generate image
        start = time.time()
        image_bytes = await _generate_kolors(english_word)
        elapsed = time.time() - start

        if image_bytes:
            content_type = "image/jpeg"
            # Save to both MongoDB and disk
            _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
            _save_cache(cache_key, image_bytes, content_type)
            generated += 1
            print(f"✅ ({elapsed:.1f}s, {len(image_bytes)//1024}KB)")
            # Respect 2 IPM limit: wait 31s before next request (unless last word)
            if i < total:
                time.sleep(31)
        else:
            failed += 1
            print(f"❌ failed ({elapsed:.1f}s)")



    print(f"\n{'='*50}")
    print(f"✅ Generated: {generated}")
    print(f"⏭️  Skipped (already in MongoDB): {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {total}")


def main():
    parser = argparse.ArgumentParser(description="Pre-generate word images into MongoDB")
    parser.add_argument("--force", action="store_true", help="Re-generate all images (even if they exist)")
    parser.add_argument("--limit", type=int, default=None, help="Only process N words")
    args = parser.parse_args()

    asyncio.run(pregenerate_all(force=args.force, limit=args.limit))


if __name__ == "__main__":
    main()
