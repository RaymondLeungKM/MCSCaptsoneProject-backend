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
# ── Noun-phrase helper ───────────────────────────────────────────────────────

async def _get_noun_phrase(english_word: str) -> str:
    """
    Return the correct English noun phrase with article/quantifier for image prompts.

    Strategy:
    1. Check a small lookup for words that grammatically require a quantifier
       (e.g. "toilet paper" → "a roll of toilet paper").  These are the only
       words where "a <word>" would be wrong — roughly 20 common cases.
    2. Ask Ollama as a dynamic fallback (useful if you add new categories later).
    3. Fall back to "a/an <word>" which is correct for the vast majority of nouns.
    """
    word_lower = english_word.strip().lower()

    # Words that need a specific quantifier — only cases where "a X" is wrong.
    # Animals and most objects are fine with "a/an" so they don't appear here.
    _QUANTIFIERS = {
        "toilet paper":  "a roll of toilet paper",
        "paper towel":   "a roll of paper towel",
        "tape":          "a roll of tape",
        "ribbon":        "a roll of ribbon",
        "scissors":      "a pair of scissors",
        "glasses":       "a pair of glasses",
        "sunglasses":    "a pair of sunglasses",
        "shoes":         "a pair of shoes",
        "socks":         "a pair of socks",
        "pants":         "a pair of pants",
        "trousers":      "a pair of trousers",
        "chopsticks":    "a pair of chopsticks",
        "gloves":        "a pair of gloves",
        "grapes":        "a bunch of grapes",
        "bananas":       "a bunch of bananas",
        "flowers":       "a bunch of flowers",
        "bread":         "a loaf of bread",
        "water":         "a glass of water",
        "juice":         "a glass of juice",
        "milk":          "a glass of milk",
        "soap":          "a bar of soap",
        "toothpaste":    "a tube of toothpaste",
        "rice":          "a bowl of rice",
        "noodles":       "a bowl of noodles",
        "cereal":        "a bowl of cereal",
    }

    if word_lower in _QUANTIFIERS:
        return _QUANTIFIERS[word_lower]

    # Ollama: useful for edge cases not in the table above.
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [{"role": "user", "content": (
            "Return ONLY the correct English noun phrase with article for this word.\n"
            "Use quantifiers only when grammatically required (e.g. 'a pair of scissors').\n"
            "For most words just add 'a' or 'an'.\n"
            f"Word: {english_word}"
        )}],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 20},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                result = (
                    data.get("message", {}).get("content", "")
                    or data.get("response", "")
                ).strip().strip('"').strip("'").lower()
                if result and len(result) < 60 and _is_english(result) and word_lower in result:
                    return result
    except Exception:
        pass

    # Final fallback: correct a/an + word
    article = "an" if word_lower and word_lower[0] in "aeiou" else "a"
    return f"{article} {word_lower}"

# ── Prompt builders ───────────────────────────────────────────────────────────

# Categories whose subjects naturally have faces (animals, living creatures).
# Everything else (food, objects, places, etc.) should NOT have a face.
# We rely on the DB category rather than a manual per-word list because:
#  - Kolors/SDXL are diffusion models, not instruction-following LLMs.
#  - They can't evaluate "if X then Y" in a prompt reliably.
#  - Face suppression works via the negative prompt, which must be a static
#    list — so we decide here in Python which version to use.
_FACE_CATEGORIES = {
    "animals", "animal", "pets", "pet",
    "people", "person", "family", "characters",
}


def _naturally_has_face(english_word: str, category: str = "") -> bool:
    """Return True if the subject naturally has a face (animal, person).

    Decision is driven by the DB category so we don't maintain a manual
    word list.  The english_word argument is kept for potential future use
    (e.g. words with no category).
    """
    return category.strip().lower() in _FACE_CATEGORIES


def build_cartoon_prompt(noun_phrase: str, has_face: bool = False) -> str:
    # noun_phrase already has article/quantifier: "a roll of toilet paper"
    # Strip the leading article to get the bare noun for mid-sentence references.
    phrase = (noun_phrase or "an object").strip()
    bare = phrase
    for prefix in ("a bunch of ", "a pair of ", "a roll of ", "a loaf of ",
                   "a glass of ", "a piece of ", "a slice of ", "a set of ",
                   "a bar of ", "a tube of ", "a bag of ", "a box of ",
                   "an ", "a "):
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    if has_face:
        return (
            f"A high-quality cute cartoon watercolor illustration of {phrase} "
            f"for a children's vocabulary flashcard. "
            f"Soft watercolor tones in warm pastels with gentle ink outlines. "
            f"The {bare} is centered, filling about 70% of the frame, "
            f"on a plain cream paper background with a soft shadow beneath. "
            f"No text, no labels, no watermarks."
        )
    return (
        f"A high-quality cartoon watercolor illustration of {phrase} "
        f"for a children's vocabulary flashcard. "
        f"The {bare} is a plain inanimate object with no face, no eyes, no mouth, "
        f"no expression, and no anthropomorphic features whatsoever. "
        f"Soft watercolor tones in warm pastels with gentle ink outlines. "
        f"The {bare} is centered, filling about 70% of the frame, "
        f"on a plain cream paper background with a soft shadow beneath. "
        f"No text, no labels, no watermarks. Just the object."
    )


def build_negative_prompt(has_face: bool = False) -> str:
    base = (
        "photo, photograph, realistic, 3D render, scary, violent, gore, "
        "text, letters, labels, watermark, blurry, signature, "
        "dark background, busy background, "
        "multiple objects, adult, mature, deformed, ugly, low quality"
    )
    if has_face:
        return base
    # For inanimate objects, strongly suppress any facial features
    return (
        "face, eyes, mouth, smile, expression, kawaii face, cute face, anthropomorphic, cartoon face, "
        "googly eyes, eye, eyeball, emoji face, emoticon, character face, "
        + base
    )

# ── Silicon Flow API ──────────────────────────────────────────────────────────

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/images/generations"

# Rate-limit: Silicon Flow free tier allows 2 images per minute (IPM 2).
# On 429 we wait and retry up to MAX_RETRIES_429 times.
MAX_RETRIES_429 = 3
RETRY_WAIT_SECS = 35  # >30s to ensure the per-minute window resets

async def _generate_kolors(english_word: str, category: str = "", retries_on_429: int = MAX_RETRIES_429) -> Optional[bytes]:
    """Kwai-Kolors/Kolors via Silicon Flow, with automatic 429 retry."""
    api_key = settings.SILICONFLOW_API_KEY
    if not api_key:
        print("[ImageGen] SILICONFLOW_API_KEY not set")
        return None
    has_face = _naturally_has_face(english_word, category)
    noun_phrase = await _get_noun_phrase(english_word)
    print(f"[ImageGen] Noun phrase: '{noun_phrase}' (has_face={has_face})")
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": build_cartoon_prompt(noun_phrase, has_face=has_face),
        "negative_prompt": build_negative_prompt(has_face=has_face),
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
    image_bytes = await _generate_kolors(english_word, category=category)

    if image_bytes:
        content_type = "image/jpeg"
        _save_cache(cache_key, image_bytes, content_type)
        _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
        return image_bytes, content_type

    return None, ""
