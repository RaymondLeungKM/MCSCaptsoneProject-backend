"""
Image Generation Service
Generates cartoon-style vocabulary flashcard images using Silicon Flow API (Kolors model)
with MongoDB + disk caching.
Translation from Cantonese to English uses Ollama (local, free) with Google Translate fallback.
"""
import asyncio
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from app.core.config import settings

# ── Cache ────────────────────────────────────────────────────────────────────
CACHE_DIR = Path("uploads/images/words")

def _cache_key(word: str, word_cantonese: str) -> str:
    raw = (word_cantonese or word or "object").strip()
    return hashlib.md5(raw.encode()).hexdigest()

def _cached_image_path(cache_key: str) -> Optional[Path]:
    for ext in ("jpg", "png", "webp"):
        p = CACHE_DIR / f"{cache_key}.{ext}"
        if p.exists():
            return p
    return None

def _save_cache(cache_key: str, data: bytes, content_type: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"
    path = CACHE_DIR / f"{cache_key}.{ext}"
    path.write_bytes(data)
    return path

# ── MongoDB cache ────────────────────────────────────────────────────────────

def _get_from_mongo(cache_key: str) -> Optional[tuple[bytes, str]]:
    """Fetch a pre-generated image from MongoDB. Returns (bytes, content_type) or None."""
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        return None
    try:
        from app.db.mongodb import get_image_collection
        col = get_image_collection()
        doc = col.find_one({"cache_key": cache_key}, {"image_data": 1, "content_type": 1})
        if doc and doc.get("image_data"):
            return bytes(doc["image_data"]), doc.get("content_type", "image/jpeg")
    except Exception as exc:
        print(f"[ImageGen] MongoDB read error: {exc}")
    return None


def _save_to_mongo(cache_key: str, word: str, word_cantonese: str,
                   data: bytes, content_type: str) -> None:
    """Store a generated image in MongoDB for future instant retrieval."""
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        return
    try:
        from app.db.mongodb import get_image_collection
        from bson import Binary
        col = get_image_collection()
        col.update_one(
            {"cache_key": cache_key},
            {"$set": {
                "cache_key": cache_key,
                "word": word,
                "word_cantonese": word_cantonese,
                "image_data": Binary(data),
                "content_type": content_type,
                "updated_at": datetime.now(timezone.utc),
            },
             "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    except Exception as exc:
        print(f"[ImageGen] MongoDB write error: {exc}")

# ── Cantonese → English translation ─────────────────────────────────────────

_ENGLISH_RE = re.compile(r'^[A-Za-z0-9 \-_]+$')

def _is_english(text: str) -> bool:
    return bool(_ENGLISH_RE.match(text.strip()))

async def _translate_via_ollama(word_cantonese: str) -> Optional[str]:
    """Ask local Ollama to translate Cantonese → simple English noun."""
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Translate this Cantonese word to a simple English noun suitable for "
                    "an image search. Return ONLY the English word or short phrase, nothing else.\n"
                    f"Cantonese word: {word_cantonese}"
                ),
            }
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 20},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                translated = (
                    data.get("message", {}).get("content", "")
                    or data.get("response", "")
                ).strip().strip('"').strip("'").lower()
                # Reject if looks like the model echoed something long or non-English
                if translated and len(translated) < 50 and _is_english(translated):
                    return translated
    except Exception:
        pass
    return None

async def _translate_via_google(word: str) -> Optional[str]:
    """Fallback: Google Translate free endpoint."""
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=en&dt=t&q={word}"
    )
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and isinstance(data[0], list):
                    parts = [
                        seg[0] for seg in data[0]
                        if isinstance(seg, list) and seg[0]
                    ]
                    result = " ".join(parts).strip().lower()
                    if result:
                        return result
    except Exception:
        pass
    return None

async def translate_to_english(word: str, word_cantonese: str) -> str:
    """Return the best English translation for an image search prompt."""
    source = (word_cantonese or word or "object").strip()

    if _is_english(source):
        return source.lower()

    # Try Ollama first (local, fast)
    result = await _translate_via_ollama(source)
    if result:
        return result

    # Fallback to Google Translate
    result = await _translate_via_google(source)
    if result and _is_english(result):
        return result

    # Last resort: use the raw string (Pollinations accepts some Unicode)
    return source

# ── Prompt builders ───────────────────────────────────────────────────────────

def build_cartoon_prompt(english_word: str) -> str:
    w = (english_word or "object").strip()
    return (
        f"A high-quality, cute cartoon watercolor illustration of a single, pristine {w}, suitable for a children's picture book. Soft, blended watercolor tones in warm pastels appropriate for the object are used with gentle, defining ink outlines. This is a clean, lifeless object study; it has absolutely no face, eyes, smile, or limbs (arms, legs, or shoes). The single {w} is centered and clearly oriented, filling approximately 70% of the frame. The setting is a plain textured cream paper background with a soft, diffuse shadow wash beneath the object, similar to image_0.png. Soft, diffused lighting highlights the object's form. There is absolutely no text, letters, labels, or watermarks present."
    )

def build_negative_prompt() -> str:
    return (
        "photo, photograph, realistic, 3D render, scary, violent, gore, "
        "text, letters, labels, watermark, blurry, signature, "
        "dark background, busy background, "
        "multiple objects, adult, mature, deformed, ugly, low quality"
    )

# ── Silicon Flow API ──────────────────────────────────────────────────────────

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/images/generations"

# Rate-limit: Silicon Flow free tier allows 2 images per minute (IPM 2).
# On 429 we wait and retry up to MAX_RETRIES_429 times.
MAX_RETRIES_429 = 3
RETRY_WAIT_SECS = 35  # >30s to ensure the per-minute window resets

async def _generate_kolors(english_word: str, retries_on_429: int = MAX_RETRIES_429) -> Optional[bytes]:
    """Kwai-Kolors/Kolors via Silicon Flow, with automatic 429 retry."""
    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        print("[ImageGen] SILICONFLOW_API_KEY not set")
        return None
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": build_cartoon_prompt(english_word),
        "negative_prompt": build_negative_prompt(),
        "image_size": "1024x1024",
        "batch_size": 1,
        "num_inference_steps": 20,
        "guidance_scale": 7.5,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(1 + retries_on_429):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(SILICONFLOW_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    images = resp.json().get("images", [])
                    if images and images[0].get("url"):
                        img_resp = await client.get(images[0]["url"])
                        if img_resp.status_code == 200 and len(img_resp.content) > 2000:
                            print("[ImageGen] Kolors image generated successfully")
                            return img_resp.content
                    print("[ImageGen] Kolors returned 200 but no usable image URL")
                    return None
                elif resp.status_code == 429:
                    if attempt < retries_on_429:
                        print(f"[ImageGen] Rate limited (429), waiting {RETRY_WAIT_SECS}s (retry {attempt+1}/{retries_on_429})...")
                        await asyncio.sleep(RETRY_WAIT_SECS)
                        continue
                    else:
                        print(f"[ImageGen] Rate limited (429), all {retries_on_429} retries exhausted")
                        return None
                else:
                    print(f"[ImageGen] Kolors error {resp.status_code}: {resp.text[:200]}")
                    return None
        except Exception as exc:
            print(f"[ImageGen] Kolors error: {exc}")
            return None
    return None

# ── Public API ────────────────────────────────────────────────────────────────

async def generate_word_image(
    word: str,
    word_cantonese: str,
    category: str,
    word_id: str,
) -> tuple[Optional[bytes], str]:
    """
    Returns (image_bytes, content_type).
    image_bytes is None if all providers fail — caller should use emoji fallback.

    Lookup order: MongoDB → disk cache → on-demand generation (stored to both).
    """
    cache_key = _cache_key(word, word_cantonese)

    # 1. MongoDB (pre-generated images — instant)
    mongo_result = _get_from_mongo(cache_key)
    if mongo_result:
        print(f"[ImageGen] MongoDB hit for '{word_cantonese or word}'")
        return mongo_result

    # 2. Disk cache (legacy / fallback)
    cached = _cached_image_path(cache_key)
    if cached:
        data = cached.read_bytes()
        suffix = cached.suffix.lstrip(".")
        content_type = f"image/{suffix}"
        # Backfill to MongoDB so future lookups are faster
        _save_to_mongo(cache_key, word, word_cantonese, data, content_type)
        return data, content_type

    # 3. Translate
    english_word = await translate_to_english(word, word_cantonese)
    print(f"[ImageGen] Generating for '{word_cantonese}' → '{english_word}'")

    # 4. Kolors
    image_bytes = await _generate_kolors(english_word)

    if image_bytes:
        content_type = "image/jpeg"
        _save_cache(cache_key, image_bytes, content_type)
        _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
        return image_bytes, content_type

    return None, ""
