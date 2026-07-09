"""
Image Generation Service
Generates cartoon-style vocabulary flashcard images using Silicon Flow API (Kolors model)
with MongoDB + disk caching.
Translation from Cantonese to English uses Ollama (local, free) with Google Translate fallback.
"""
import asyncio
import re
import hashlib
import base64
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


# ── Postgres cache (shared word_images table) ────────────────────────────────
# Mirrors the Mongo cache so every backend instance pointing at the shared DB
# sees newly-generated images immediately — no Mongo / no per-host disk needed.

def _get_from_pg(cache_key: str) -> Optional[tuple[bytes, str]]:
    """Fetch image bytes from Postgres `word_images`. Synchronous + best-effort."""
    try:
        import urllib.parse as _up
        from sqlalchemy import create_engine, text
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT image_data, content_type FROM word_images WHERE cache_key = :k"),
                {"k": cache_key},
            ).first()
        if row and row[0]:
            return bytes(row[0]), (row[1] or "image/jpeg")
    except Exception as exc:
        print(f"[ImageGen] Postgres read error: {exc}")
    return None


def _save_to_pg(cache_key: str, word: str, word_cantonese: str,
                data: bytes, content_type: str) -> None:
    """Upsert image bytes into Postgres `word_images`. Best-effort, never raises."""
    try:
        from sqlalchemy import create_engine, text
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO word_images(cache_key, word, word_cantonese, content_type, image_data) "
                "VALUES (:k, :w, :wc, :ct, :d) "
                "ON CONFLICT (cache_key) DO UPDATE SET "
                "  word=EXCLUDED.word, word_cantonese=EXCLUDED.word_cantonese, "
                "  content_type=EXCLUDED.content_type, image_data=EXCLUDED.image_data, "
                "  updated_at=now()"
            ), {"k": cache_key, "w": word, "wc": word_cantonese,
                "ct": content_type, "d": data})
    except Exception as exc:
        # Table may not exist on older deployments; that's OK — Mongo / disk
        # still cover the case. Logged for visibility, never raised.
        print(f"[ImageGen] Postgres write error: {exc}")

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

# Resolve a category UUID -> name once, cached, so the live endpoint (which
# sends category as a UUID) gets the same has_face decision as the
# pre-generation script (which sends the category name).
_CATEGORY_NAME_CACHE: dict[str, str] = {}
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _resolve_category_name(category: str) -> str:
    """If `category` is a UUID, look up its human name; otherwise return as-is."""
    cat = (category or "").strip()
    if not cat or not _UUID_RE.match(cat):
        return cat
    if cat in _CATEGORY_NAME_CACHE:
        return _CATEGORY_NAME_CACHE[cat]
    try:
        from sqlalchemy import create_engine, text
        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT name FROM categories WHERE id = :id"), {"id": cat}
            ).first()
        name = row[0] if row else ""
        _CATEGORY_NAME_CACHE[cat] = name
        return name
    except Exception as exc:
        print(f"[ImageGen] category name lookup failed for {cat}: {exc}")
        return cat


def _naturally_has_face(english_word: str, category: str = "") -> bool:
    """Return True if the subject naturally has a face (animal, person).

    Decision is driven by the DB category so we don't maintain a manual
    word list.  Accepts either a category name or a category UUID (the live
    endpoint passes a UUID; the pre-generation script passes the name).
    """
    name = _resolve_category_name(category)
    return name.strip().lower() in _FACE_CATEGORIES


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

# ── FLUX.2 Klein 9B watercolor prompt (exact template) ─────────────────────────

# Words whose plain English form the image model misreads (word-sense
# collisions). Map them to an unambiguous descriptive phrase so FLUX draws the
# intended object. e.g. "toast" -> drinking toast/cheers instead of bread.
_WORD_DISAMBIGUATION: dict[str, str] = {
    "toast": "a slice of toasted bread",
    "scooter": "a child's kick scooter with a tall handlebar and a standing footboard, push scooter, not a motorcycle",
    "pot": "a metal cooking pot with two handles, a saucepan for cooking on a stove",
    "paper": "a single blank white sheet of paper",
    "glue": "a bottle of white school glue with a cap",
    "marker": "a colorful felt-tip marker pen with its cap, a coloring pen",
    "tape": "a roll of clear adhesive sticky tape",
    "rice": "a bowl of cooked white rice, steamed rice served in a round bowl",
    "broom": "a cleaning broom with a long handle and bristles for sweeping the floor",
    "bag": "a child's school backpack with straps",
}


def _disambiguate_word(word: str) -> str:
    return _WORD_DISAMBIGUATION.get(word.strip().lower(), word)


def build_flux_prompt(english_word: str, has_face: bool = False) -> str:
    """Watercolor flashcard prompt template, {word} -> English word.

    has_face=True (animals, people): the subject keeps its natural face, eyes
    and body, shown front-facing so children can recognise it.
    has_face=False (inanimate objects): no face/eyes/limbs/anthropomorphic
    features.
    """
    word = _disambiguate_word((english_word or "object").strip().lower())
    if has_face:
        return (
            f"a high-quality clean soft watercolor illustration of a single {word} "
            f"for children's Cantonese vocabulary flashcard, "
            f"facing forward showing its natural face and friendly eyes, "
            f"full body, calm and gentle expression, "
            f"soft warm pastel tones, gentle ink outlines, smooth shading, centered composition, "
            f"plain cream paper background with subtle texture and soft shadow, "
            f"child-friendly, educational, no text, no labels"
        )
    return (
        f"a high-quality clean soft watercolor illustration of a single {word} "
        f"for children's Cantonese vocabulary flashcard, simple plain inanimate object, "
        f"no face no eyes no mouth no limbs no anthropomorphic features, "
        f"soft warm pastel tones, gentle ink outlines, smooth shading, centered composition, "
        f"plain cream paper background with subtle texture and soft shadow, "
        f"child-friendly, educational, no text, no labels"
    )


# Shared negative terms for every flashcard, regardless of subject.
_FLUX_NEG_BASE = (
    "photo, photograph, realistic, 3D render, clay, pixel art, "
    "multiple objects, busy background, cluttered background, decorative background, "
    "foliage, leaves, plants, flowers, branches, splashes, paint splatter, "
    "scenery, pattern, border, frame, dark background, "
    "text, letters, labels, watermark, blurry, low quality, oversaturated"
)

# Inanimate objects must additionally suppress any face/anthropomorphism.
FLUX_NEGATIVE_PROMPT = (
    "face, eyes, mouth, smile, kawaii face, cartoon face, anthropomorphic, "
    "limbs, arms, legs, hands, " + _FLUX_NEG_BASE
)

# Animals/people keep their face — only suppress human-like anthropomorphism
# (standing upright, clothes, human hands) and back/rear views.
FLUX_NEGATIVE_PROMPT_FACE = (
    "anthropomorphic, humanoid, standing upright like a human, wearing clothes, "
    "human hands, back view, rear view, headless, faceless, " + _FLUX_NEG_BASE
)


def build_flux_negative_prompt(has_face: bool = False) -> str:
    return FLUX_NEGATIVE_PROMPT_FACE if has_face else FLUX_NEGATIVE_PROMPT


# ── Cloudflare Workers AI — FLUX.2 Klein 9B ─────────────────────────────────────

FLUX_MODEL_ID = "@cf/black-forest-labs/flux-2-klein-9b"
# FLUX.2 models require multipart form data (not JSON).
FLUX_MAX_RETRIES = 3
FLUX_RETRY_WAIT_SECS = 5

async def _generate_flux(english_word: str, category: str = "", retries: int = FLUX_MAX_RETRIES) -> Optional[bytes]:
    """Generate a watercolor flashcard image via Cloudflare Workers AI FLUX.2 Klein 9B."""
    account_id = settings.CLOUDFLARE_ACCOUNT_ID or settings.CF_ACCOUNT_ID
    api_token = settings.CLOUDFLARE_AI_API_TOKEN
    if not account_id or not api_token:
        print("[ImageGen] CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_AI_API_TOKEN not set")
        return None

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{FLUX_MODEL_ID}"
    headers = {"Authorization": f"Bearer {api_token}"}
    has_face = _naturally_has_face(english_word, category)
    prompt = build_flux_prompt(english_word, has_face=has_face)
    print(f"[ImageGen] FLUX prompt (has_face={has_face}): '{prompt[:80]}...'")
    form_data = {
        "prompt": prompt,
        "negative_prompt": build_flux_negative_prompt(has_face=has_face),
        "width": "768",
        "height": "768",
        "guidance": "7.5",
        "num_steps": "4",
    }

    for attempt in range(1 + retries):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, data=form_data, headers=headers)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "image/" in content_type:
                        image_bytes = resp.content
                    else:
                        # JSON response with base64 image
                        try:
                            data = resp.json()
                            b64 = data.get("result", {}).get("image", "")
                            if not b64:
                                print("[ImageGen] FLUX 200 but no result.image in JSON")
                                return None
                            image_bytes = base64.b64decode(b64)
                        except Exception as exc:
                            print(f"[ImageGen] FLUX JSON parse error: {exc}")
                            return None
                    if len(image_bytes) > 2000:
                        print("[ImageGen] FLUX image generated successfully")
                        return image_bytes
                    print(f"[ImageGen] FLUX image too small ({len(image_bytes)} bytes)")
                    return None
                elif resp.status_code in (429, 500, 502, 503):
                    if attempt < retries:
                        print(f"[ImageGen] FLUX transient {resp.status_code}, waiting {FLUX_RETRY_WAIT_SECS}s (retry {attempt+1}/{retries})...")
                        await asyncio.sleep(FLUX_RETRY_WAIT_SECS)
                        continue
                    print(f"[ImageGen] FLUX {resp.status_code}, retries exhausted: {resp.text[:200]}")
                    return None
                else:
                    print(f"[ImageGen] FLUX error {resp.status_code}: {resp.text[:200]}")
                    return None
        except Exception as exc:
            if attempt < retries:
                print(f"[ImageGen] FLUX error: {exc} — retry {attempt+1}/{retries}")
                await asyncio.sleep(FLUX_RETRY_WAIT_SECS)
                continue
            print(f"[ImageGen] FLUX error (exhausted): {exc}")
            return None
    return None


def detect_image_content_type(data: bytes) -> str:
    """Detect content type from image magic bytes (FLUX may return JPEG or PNG)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"

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

    Lookup order: Postgres word_images → MongoDB → disk cache → on-demand
    generation. Anything generated or recovered is written back to all three
    so subsequent reads from any backend instance hit the shared Postgres
    table first.
    """
    cache_key = _cache_key(word, word_cantonese)
    label = word_cantonese or word
    print(f"[ImageGen] request word={word!r} canto={word_cantonese!r} category={category!r} cache_key={cache_key}")

    # 1. Postgres `word_images` (shared cache across all backend instances).
    pg_result = _get_from_pg(cache_key)
    if pg_result:
        print(f"[ImageGen] SOURCE=postgres HIT '{label}' bytes={len(pg_result[0])} type={pg_result[1]}")
        return pg_result

    # 2. MongoDB (legacy / local cache).
    mongo_result = _get_from_mongo(cache_key)
    if mongo_result:
        print(f"[ImageGen] SOURCE=mongodb HIT '{label}' bytes={len(mongo_result[0])} type={mongo_result[1]} (backfilling to postgres)")
        # Backfill into shared Postgres so other instances can see it too.
        _save_to_pg(cache_key, word, word_cantonese, mongo_result[0], mongo_result[1])
        return mongo_result

    # 3. Disk cache (legacy / local fallback).
    cached = _cached_image_path(cache_key)
    if cached:
        data = cached.read_bytes()
        suffix = cached.suffix.lstrip(".")
        content_type = f"image/{suffix}"
        print(f"[ImageGen] SOURCE=disk HIT '{label}' path={cached} bytes={len(data)} (backfilling to postgres+mongo)")
        # Backfill to shared Postgres + Mongo so future lookups are faster
        # and other instances can find the image.
        _save_to_pg(cache_key, word, word_cantonese, data, content_type)
        _save_to_mongo(cache_key, word, word_cantonese, data, content_type)
        return data, content_type

    # 4. Translate
    english_word = await translate_to_english(word, word_cantonese)
    print(f"[ImageGen] CACHE MISS '{label}' → generating via FLUX for english={english_word!r}")

    # 5. FLUX.2 Klein 9B (Cloudflare Workers AI)
    image_bytes = await _generate_flux(english_word, category=category)

    if image_bytes:
        content_type = detect_image_content_type(image_bytes)
        print(f"[ImageGen] SOURCE=flux GENERATED '{label}' bytes={len(image_bytes)} type={content_type} (saving to disk+postgres+mongo)")
        _save_cache(cache_key, image_bytes, content_type)
        _save_to_pg(cache_key, word, word_cantonese, image_bytes, content_type)
        _save_to_mongo(cache_key, word, word_cantonese, image_bytes, content_type)
        return image_bytes, content_type

    print(f"[ImageGen] SOURCE=none FAILED '{label}' — all providers failed, frontend will use emoji fallback")
    return None, ""
