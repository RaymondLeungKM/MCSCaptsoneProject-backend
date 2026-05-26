"""
Tests for the image pre-generation pipeline.

Verifies:
  1. MongoDB lookup works (pre-generated images are found)
  2. The /api/v1/images/generate endpoint returns a real image (not 503)
  3. The image content-type is valid (image/jpeg, not image/jpg)
  4. No word with an emoji image_url is incorrectly skipped by pregenerate
  5. End-to-end: Scarf / 圍巾 image is served correctly

Run:
  python test_image_pipeline.py
  python test_image_pipeline.py --word "圍巾"   # test a specific word
"""

import argparse
import asyncio
import hashlib
import sys

import httpx

BACKEND_BASE = "http://localhost:8000"
GENERATE_URL = f"{BACKEND_BASE}/api/v1/images/generate"
VALID_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _cache_key(word: str, word_cantonese: str) -> str:
    raw = (word_cantonese or word or "object").strip()
    return hashlib.md5(raw.encode()).hexdigest()


def _get_collection():
    from app.core.config import settings
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        print("⚠️  MongoDB not enabled — skipping MongoDB tests")
        return None
    from app.db.mongodb import get_image_collection
    return get_image_collection()


# ── Test helpers ──────────────────────────────────────────────────────────────

def check(label: str, condition: bool, detail: str = ""):
    status = "✅ PASS" if condition else "❌ FAIL"
    msg = f"  {status}  {label}"
    if detail:
        msg += f"\n         {detail}"
    print(msg)
    return condition


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_mongo_image_exists(word: str, word_cantonese: str) -> bool:
    """Verify the word has a pre-generated image in MongoDB."""
    col = _get_collection()
    if col is None:
        return True  # skip
    ck = _cache_key(word, word_cantonese)
    doc = col.find_one({"cache_key": ck}, {"image_data": 1, "content_type": 1, "cache_key": 1})
    exists = doc is not None and bool(doc.get("image_data"))
    return check(
        f"MongoDB: image exists for '{word_cantonese}' / '{word}'",
        exists,
        f"cache_key={ck}" if not exists else f"cache_key={ck} ✓",
    )


def test_mongo_content_type(word: str, word_cantonese: str) -> bool:
    """Verify content_type is a valid MIME type (not 'image/jpg')."""
    col = _get_collection()
    if col is None:
        return True
    ck = _cache_key(word, word_cantonese)
    doc = col.find_one({"cache_key": ck}, {"content_type": 1})
    if not doc:
        return check(f"MongoDB: content_type valid for '{word}'", False, "document not found")
    ct = doc.get("content_type", "")
    valid = ct in VALID_CONTENT_TYPES
    return check(
        f"MongoDB: content_type is valid for '{word}'",
        valid,
        f"got '{ct}', expected one of {VALID_CONTENT_TYPES}",
    )


async def test_api_endpoint_returns_image(word: str, word_cantonese: str) -> bool:
    """Call /api/v1/images/generate and verify it returns image bytes."""
    params = {"word": word, "word_cantonese": word_cantonese, "category": "test", "word_id": word}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(GENERATE_URL, params=params)
    except httpx.ConnectError:
        return check(
            f"API: /images/generate returns image for '{word}'",
            False,
            f"Cannot connect to {BACKEND_BASE} — is the backend running?",
        )

    ok = resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/")
    return check(
        f"API: /images/generate returns image for '{word}'",
        ok,
        f"status={resp.status_code} content-type={resp.headers.get('content-type')} size={len(resp.content)}B",
    )


async def test_api_content_type_is_valid(word: str, word_cantonese: str) -> bool:
    """Verify the API response content-type is a proper MIME type."""
    params = {"word": word, "word_cantonese": word_cantonese, "category": "test", "word_id": word}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(GENERATE_URL, params=params)
    except httpx.ConnectError:
        return check(f"API: content-type valid for '{word}'", False, "backend not reachable")

    ct = resp.headers.get("content-type", "")
    valid = any(ct.startswith(t) for t in VALID_CONTENT_TYPES)
    return check(
        f"API: content-type is valid for '{word}'",
        valid,
        f"got '{ct}'",
    )


async def test_api_image_size_reasonable(word: str, word_cantonese: str) -> bool:
    """Verify returned image is a real image (>5KB), not a tiny placeholder."""
    params = {"word": word, "word_cantonese": word_cantonese, "category": "test", "word_id": word}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(GENERATE_URL, params=params)
    except httpx.ConnectError:
        return check(f"API: image size reasonable for '{word}'", False, "backend not reachable")

    size = len(resp.content)
    ok = resp.status_code == 200 and size > 5_000
    return check(
        f"API: image size > 5KB for '{word}'",
        ok,
        f"size={size}B ({size//1024}KB)",
    )


async def test_pregenerate_skips_emoji_image_url() -> bool:
    """Verify pregenerate does NOT skip words whose image_url is an emoji."""
    import logging
    logging.disable(logging.CRITICAL)
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        r = await session.execute(
            text("SELECT word, word_cantonese, image_url FROM words WHERE image_url IS NOT NULL AND is_active = TRUE LIMIT 50")
        )
        rows = r.fetchall()

    emoji_url_words = [
        (row.word, row.word_cantonese, row.image_url)
        for row in rows
        if row.image_url
        and not row.image_url.startswith("http://")
        and not row.image_url.startswith("https://")
        and not row.image_url.startswith("/")
    ]
    col = _get_collection()

    all_pass = True
    if not emoji_url_words:
        check("No words with emoji image_url found — pregenerate logic fine", True)
        return True

    for word, cantonese, emoji_url in emoji_url_words[:5]:  # check first 5
        ck = _cache_key(word, cantonese or "")
        in_mongo = False
        if col is not None:
            doc = col.find_one({"cache_key": ck}, {"_id": 1})
            in_mongo = doc is not None
        ok = check(
            f"Emoji image_url word '{word}' ({cantonese}) has MongoDB entry",
            in_mongo,
            f"image_url={emoji_url!r} — run pregenerate_images.py to generate",
        )
        all_pass = all_pass and ok

    if emoji_url_words:
        print(f"  ℹ️   {len(emoji_url_words)} words have emoji image_url and need MongoDB pre-generation")

    return all_pass


async def run_tests(word: str = "Scarf", word_cantonese: str = "圍巾"):
    print(f"\n{'='*60}")
    print(f"Image Pipeline Tests — word='{word}' / cantonese='{word_cantonese}'")
    print(f"{'='*60}\n")

    results = []

    # MongoDB tests (synchronous)
    print("── MongoDB ──────────────────────────────────────────────")
    results.append(test_mongo_image_exists(word, word_cantonese))
    results.append(test_mongo_content_type(word, word_cantonese))

    # API endpoint tests (async)
    print("\n── API Endpoint ─────────────────────────────────────────")
    results.append(await test_api_endpoint_returns_image(word, word_cantonese))
    results.append(await test_api_content_type_is_valid(word, word_cantonese))
    results.append(await test_api_image_size_reasonable(word, word_cantonese))

    # Pregenerate logic test
    print("\n── Pregenerate Logic ────────────────────────────────────")
    results.append(await test_pregenerate_skips_emoji_image_url())

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        print("Run 'python pregenerate_images.py' to generate missing images.")
    print(f"{'='*60}\n")

    return passed == total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--word", default="Scarf", help="English word to test (default: Scarf)")
    parser.add_argument("--cantonese", default="圍巾", help="Cantonese word to test (default: 圍巾)")
    args = parser.parse_args()

    success = asyncio.run(run_tests(args.word, args.cantonese))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
