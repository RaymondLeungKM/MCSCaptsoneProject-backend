"""
Image generation endpoint.
GET /api/v1/images/generate?word=&word_cantonese=&category=&word_id=

Returns a cartoon image for vocabulary flashcards.
Falls back to a JSON error so the frontend can show its emoji SVG.
"""
from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

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
