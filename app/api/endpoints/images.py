"""
Image generation + retrieval endpoints.

GET /api/v1/images/generate?word=&word_cantonese=&category=&word_id=
    Generate (or fetch cached) a cartoon image for vocabulary flashcards.

GET /api/v1/images/by-key/{cache_key}
    Stream the bytes for an already-generated image stored in Postgres
    `word_images`. Used by `words.image_url = /api/v1/images/by-key/{key}`
    so every backend instance serves images from the shared DB.
"""
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.image_generation_service import generate_word_image

router = APIRouter()


@router.get("/generate")
async def generate_image(
    word: str = Query(default="object"),
    word_cantonese: str = Query(default=""),
    category: str = Query(default=""),
    word_id: str = Query(default=""),
):
    """Generate a cartoon flashcard image for a vocabulary word."""
    image_bytes, content_type = await generate_word_image(
        word=word,
        word_cantonese=word_cantonese,
        category=category,
        word_id=word_id or word,
    )

    if image_bytes:
        return Response(
            content=image_bytes,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=604800, immutable",
                "X-Image-Source": "backend-generated",
            },
        )

    # All providers failed — tell the frontend so it shows its emoji SVG
    return JSONResponse(
        status_code=503,
        content={"detail": "Image generation unavailable, use emoji fallback"},
    )


@router.get("/by-key/{cache_key}")
async def get_image_by_key(
    cache_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream an image stored in Postgres `word_images` by its cache_key.

    Returns 404 if the key doesn't exist. The image_url column on `words`
    points here so every backend instance serves the same bytes from the
    shared database — no local disk dependency.
    """
    # Reject obvious garbage early; cache_key is an md5 hex string.
    if not cache_key or len(cache_key) > 128 or not all(
        c in "0123456789abcdefABCDEF" for c in cache_key
    ):
        print(f"[ImageServe] by-key REJECT bad cache_key={cache_key!r}")
        return JSONResponse(status_code=400, content={"detail": "bad cache_key"})

    row = (await db.execute(
        text("SELECT image_data, content_type FROM word_images WHERE cache_key = :k"),
        {"k": cache_key},
    )).first()
    if row is None or row[0] is None:
        print(f"[ImageServe] by-key MISS  cache_key={cache_key} (not in word_images)")
        return JSONResponse(status_code=404, content={"detail": "image not found"})

    size = len(bytes(row[0]))
    ctype = row[1] or "image/jpeg"
    print(f"[ImageServe] by-key HIT   cache_key={cache_key} bytes={size} type={ctype} source=postgres")
    return Response(
        content=bytes(row[0]),
        media_type=ctype,
        headers={
            "Cache-Control": "public, max-age=604800, immutable",
            "X-Image-Source": "postgres-word-images",
        },
    )
