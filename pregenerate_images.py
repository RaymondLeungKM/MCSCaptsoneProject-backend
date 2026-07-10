"""
Pre-generate images for all vocabulary words and store them in MongoDB.

Fetches all words from PostgreSQL plus the minigame dictionary
(app/services/minigame_vocabulary.py), generates soft-watercolor flashcard
images via FLUX.2 Klein 9B (Cloudflare Workers AI), and stores the image binary
data in MongoDB's word_images collection (and on disk).

Resume behaviour (default):
  Words that already have image_url set in PostgreSQL, or already have an image
  in MongoDB, are skipped automatically — so you can re-run this script and it
  will continue from where it left off.

Usage:
  python pregenerate_images.py                        # Continue from last run
  python pregenerate_images.py --status               # Show progress, don't generate
  python pregenerate_images.py --word "圍巾"           # Generate one word (Cantonese)
  python pregenerate_images.py --word "Scarf"         # Generate one word (English)
  python pregenerate_images.py --category "Animals"   # Only regenerate Animals category
  python pregenerate_images.py --force                # Re-generate all images
  python pregenerate_images.py --limit 10             # Only generate for 10 words
"""
from __future__ import annotations

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
from app.models.analytics import LearningSession, Achievement
from app.models.parent_analytics import LearningInsight, WeeklyReport, ParentalControl
from app.models.generated_sentences import GeneratedSentence
from app.models.daily_words import DailyWordTracking
from app.services.image_generation_service import (
    _cache_key,
    _generate_flux,
    _save_cache,
    _save_to_mongo,
    _get_from_mongo,
    translate_to_english,
    detect_image_content_type,
    _is_english,
)
from app.services.minigame_vocabulary import MINIGAME_CANTONESE_TO_ENGLISH


async def pregenerate_all(force: bool = False, limit: int | None = None, status_only: bool = False, word_filter: str | None = None, category_filter: str | None = None):
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

    # Normalize DB rows into a uniform item shape:
    #   {word, word_cantonese, category, image_url}
    items: list[dict] = []
    seen_cache_keys: set[str] = set()
    for w in words:
        ck = _cache_key(w.word, w.word_cantonese or "")
        seen_cache_keys.add(ck)
        # DB words store their English term in `word` (e.g. "Ball"). Prefer it
        # directly when it's already English so we don't mistranslate the
        # Cantonese (e.g. 波 → "wave"). Otherwise translate from Cantonese.
        db_english = w.word if _is_english(w.word or "") else None
        items.append({
            "word": w.word,
            "word_cantonese": w.word_cantonese or "",
            "category": w.category_rel.name if w.category_rel else "",
            "image_url": w.image_url,
            "english_known": db_english,
        })

    # Add minigame dictionary words (learning tab + minigames) that aren't
    # already covered by the DB words. Skipped when a specific --word/--category
    # filter is active, so those modes stay scoped to the database.
    if not word_filter and not category_filter:
        added = 0
        for cantonese, english in MINIGAME_CANTONESE_TO_ENGLISH.items():
            ck = _cache_key(english, cantonese)
            if ck in seen_cache_keys:
                continue
            seen_cache_keys.add(ck)
            items.append({
                "word": english,
                "word_cantonese": cantonese,
                "category": "",
                "image_url": None,
                # Dictionary provides a vetted English term — use it directly so
                # we never mistranslate (e.g. 波 → "wave" instead of "ball").
                "english_known": english,
            })
            added += 1
        if added:
            print(f"➕ Added {added} minigame dictionary words not in the database")

    if limit:
        items = items[:limit]

    total = len(items)
    category_label = f" in category '{category_filter}'" if category_filter else ""
    print(f"📋 Found {total} words to consider{category_label}")

    # ── Status / progress report ──────────────────────────────────────────
    if status_only or True:  # always print a summary before generating
        has_pg_image = sum(
            1 for it in items
            if it["image_url"] and (
                it["image_url"].startswith("http://")
                or it["image_url"].startswith("https://")
                or it["image_url"].startswith("/")
            )
        )
        has_mongo = 0
        for it in items:
            if not it["image_url"]:
                ck = _cache_key(it["word"], it["word_cantonese"])
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

    for i, it in enumerate(items, 1):
        word = it["word"]
        word_cantonese = it["word_cantonese"]
        category_name = it["category"]
        cache_key = _cache_key(word, word_cantonese)

        # Skip if already in MongoDB or PostgreSQL image_url (unless --force)
        if not force:
            # Only skip if image_url is a real URL — emoji values like "🧣" are
            # stored as placeholders and must still be generated into MongoDB.
            if it["image_url"] and (
                it["image_url"].startswith("http://")
                or it["image_url"].startswith("https://")
                or it["image_url"].startswith("/")
            ):
                skipped += 1
                print(f"  [{i}/{total}] ⏭️  {word} ({word_cantonese}) — image_url already in PostgreSQL")
                continue

            existing = _get_from_mongo(cache_key)
            if existing:
                skipped += 1
                print(f"  [{i}/{total}] ⏭️  {word} ({word_cantonese}) — already in MongoDB")
                continue

        # Determine the English term for the FLUX prompt.
        # Dictionary words carry a vetted English term; DB words are translated
        # from Cantonese (Ollama → Google Translate) as before.
        if it["english_known"]:
            english_word = it["english_known"]
        else:
            english_word = await translate_to_english(word, word_cantonese)
        print(f"  [{i}/{total}] 🎨 {word} ({word_cantonese}) [{category_name}] → '{english_word}' ... ", end="", flush=True)

        # Generate image via FLUX.2 Klein 9B (Cloudflare Workers AI)
        start = time.time()
        image_bytes = await _generate_flux(english_word, category=category_name)
        elapsed = time.time() - start

        if image_bytes:
            content_type = detect_image_content_type(image_bytes)
            # Save to both MongoDB and disk
            _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
            _save_cache(cache_key, image_bytes, content_type)
            generated += 1
            print(f"✅ ({elapsed:.1f}s, {len(image_bytes)//1024}KB)")
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
        status_only=args.status,
        word_filter=args.word,
        category_filter=args.category,
    ))


if __name__ == "__main__":
    main()
