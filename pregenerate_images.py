"""
Pre-generate images for all vocabulary words and store them in MongoDB.

Fetches all words from PostgreSQL, generates cartoon images via Silicon Flow,
and stores the image binary data in MongoDB's word_images collection.

Resume behaviour (default):
  Words that already have image_url set in PostgreSQL, or already have an image
  in MongoDB, are skipped automatically — so you can re-run this script the next
  day and it will continue from where it left off.

Early-exit on quota exhaustion:
  If the Silicon Flow API fails N times in a row (--max-failures, default 3),
  the script assumes the daily quota has been hit and exits gracefully. Run it
  again tomorrow to continue.

Usage:
  python pregenerate_images.py                        # Continue from last run
  python pregenerate_images.py --status               # Show progress, don't generate
  python pregenerate_images.py --word "圍巾"           # Generate one word (Cantonese)
  python pregenerate_images.py --word "Scarf"         # Generate one word (English)
  python pregenerate_images.py --category "Animals"   # Only regenerate Animals category
  python pregenerate_images.py --force                # Re-generate all images
  python pregenerate_images.py --limit 10             # Only generate for 10 words
  python pregenerate_images.py --max-failures 5       # Stop after 5 consecutive failures
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
from sqlalchemy.orm import selectinload
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


async def pregenerate_all(force: bool = False, limit: int | None = None, max_failures: int = 3, status_only: bool = False, word_filter: str | None = None, category_filter: str | None = None):
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        print("❌ MongoDB is not enabled. Set MONGODB_ENABLED=true and MONGODB_URI in .env")
        sys.exit(1)

    # Fetch words from PostgreSQL
    async with AsyncSessionLocal() as session:
        query = select(Word).options(selectinload(Word.category_rel)).where(Word.is_active == True).order_by(Word.word)
        if word_filter:
            # Match on English word OR Cantonese word (case-insensitive)
            from sqlalchemy import or_, func
            query = query.where(
                or_(
                    func.lower(Word.word) == word_filter.lower(),
                    Word.word_cantonese == word_filter,
                )
            )
        if category_filter:
            # Join with categories table and filter by name (case-insensitive)
            from sqlalchemy import func
            query = query.join(Word.category_rel).where(
                func.lower(Category.name) == category_filter.strip().lower()
            )
        if limit:
            query = query.limit(limit)
        result = await session.execute(query)
        words = result.scalars().all()

    total = len(words)
    category_label = f" in category '{category_filter}'" if category_filter else ""
    print(f"📋 Found {total} active words{category_label}")

    # ── Status / progress report ──────────────────────────────────────────
    if status_only or True:  # always print a summary before generating
        has_pg_image = sum(
            1 for w in words
            if w.image_url and (
                w.image_url.startswith("http://")
                or w.image_url.startswith("https://")
                or w.image_url.startswith("/")
            )
        )
        has_mongo = 0
        for w in words:
            if not w.image_url:
                ck = _cache_key(w.word, w.word_cantonese or "")
                if _get_from_mongo(ck):
                    has_mongo += 1
        needs_gen = total - has_pg_image - has_mongo
        print(f"  ✅ PostgreSQL image_url set : {has_pg_image}")
        print(f"  ✅ Pre-generated in MongoDB : {has_mongo}")
        print(f"  🎨 Still needs generation   : {needs_gen}")
        if status_only:
            return

    generated = 0
    skipped = 0
    failed = 0
    consecutive_failures = 0  # track consecutive failures to detect quota exhaustion

    for i, w in enumerate(words, 1):
        word = w.word
        word_cantonese = w.word_cantonese or ""
        cache_key = _cache_key(word, word_cantonese)

        # Skip if already in MongoDB or PostgreSQL image_url (unless --force)
        if not force:
            # Only skip if image_url is a real URL — emoji values like "🧣" are
            # stored as placeholders and must still be generated into MongoDB.
            if w.image_url and (
                w.image_url.startswith("http://")
                or w.image_url.startswith("https://")
                or w.image_url.startswith("/")
            ):
                skipped += 1
                print(f"  [{i}/{total}] ⏭️  {word} ({word_cantonese}) — image_url already in PostgreSQL")
                continue

            existing = _get_from_mongo(cache_key)
            if existing:
                skipped += 1
                print(f"  [{i}/{total}] ⏭️  {word} ({word_cantonese}) — already in MongoDB")
                continue

        # Translate to English
        category_name = w.category_rel.name if w.category_rel else ""
        english_word = await translate_to_english(word, word_cantonese)
        print(f"  [{i}/{total}] 🎨 {word} ({word_cantonese}) [{category_name}] → '{english_word}' ... ", end="", flush=True)

        # Generate image
        start = time.time()
        image_bytes = await _generate_kolors(english_word, category=category_name)
        elapsed = time.time() - start

        if image_bytes:
            content_type = "image/jpeg"
            # Save to both MongoDB and disk
            _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
            _save_cache(cache_key, image_bytes, content_type)
            generated += 1
            consecutive_failures = 0  # reset on success
            print(f"✅ ({elapsed:.1f}s, {len(image_bytes)//1024}KB)")
            # Respect 2 IPM limit: wait 31s before next request (unless last word)
            if i < total:
                time.sleep(31)
        else:
            failed += 1
            consecutive_failures += 1
            print(f"❌ failed ({elapsed:.1f}s)")

            # If N consecutive failures, assume daily quota exhausted — stop early
            # so we don't waste time on words that will all fail too.
            # Run the script again tomorrow; it will resume from this point.
            if consecutive_failures >= max_failures:
                remaining = total - i
                print(f"\n⚠️  {consecutive_failures} consecutive failures — daily API quota likely exhausted.")
                print(f"   {remaining} words remaining. Run the script again tomorrow to continue.")
                break



    print(f"\n{'='*50}")
    print(f"✅ Generated: {generated}")
    print(f"⏭️  Skipped (already in MongoDB): {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {total}")


def main():
    parser = argparse.ArgumentParser(description="Pre-generate word images into MongoDB")
    parser.add_argument("--force", action="store_true", help="Re-generate all images (even if they exist)")
    parser.add_argument("--limit", type=int, default=None, help="Only process N words")
    parser.add_argument("--max-failures", type=int, default=3,
                        help="Stop after N consecutive failures (assumes daily quota exhausted). Default: 3")
    parser.add_argument("--status", action="store_true",
                        help="Show generation progress/status only, do not generate any images")
    parser.add_argument("--word", type=str, default=None,
                        help="Generate image for a single word only (English or Cantonese). Implies --force.")
    parser.add_argument("--category", type=str, default=None,
                        help="Only process words in this category (e.g. 'Animals'). Use with --force to re-generate.")
    args = parser.parse_args()

    asyncio.run(pregenerate_all(
        force=args.force or bool(args.word),  # single-word mode always regenerates
        limit=args.limit,
        max_failures=args.max_failures,
        status_only=args.status,
        word_filter=args.word,
        category_filter=args.category,
    ))


if __name__ == "__main__":
    main()
