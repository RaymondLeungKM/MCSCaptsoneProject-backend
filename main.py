"""
FastAPI Backend for Preschool Vocabulary Platform
Main application entry point
"""
# Load .env into os.environ before any other imports so os.getenv() works
# throughout the app (pydantic_settings alone does not populate os.environ).
from dotenv import load_dotenv
load_dotenv()

import mimetypes
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from app.api import api_router
from app.core.config import settings
from app.db.session import engine
from app.db.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("🚀 Starting Preschool Vocabulary Platform API...")
    
    # Create uploads directory if it doesn't exist
    uploads_dir = Path("uploads/images")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    # Create tables (in production, use Alembic migrations)
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    print("👋 Shutting down API...")


app = FastAPI(
    title="Preschool Vocabulary Platform API",
    description="API for managing vocabulary learning for preschool children",
    version="1.0.0",
    lifespan=lifespan,
)

def custom_openapi() -> dict:
    """Customize OpenAPI schema to ensure file inputs render correctly in Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Fix the /external/word-learned endpoint to properly show file upload in Swagger UI
    # We need to modify the requestBody directly at the path level
    path = "/api/v1/vocabulary/external/word-learned"
    if path in openapi_schema.get("paths", {}):
        post_op = openapi_schema["paths"][path].get("post", {})
        if "requestBody" in post_op:
            # Get the current schema reference or inline schema
            content = post_op["requestBody"].get("content", {})
            multipart = content.get("multipart/form-data", {})
            
            if multipart:
                # Replace with inline schema that Swagger UI understands
                post_op["requestBody"]["content"]["multipart/form-data"] = {
                    "schema": {
                        "type": "object",
                        "required": ["word", "child_id", "source", "timestamp"],
                        "properties": {
                            "word": {
                                "type": "string",
                                "description": "The word that was learned"
                            },
                            "child_id": {
                                "type": "string",
                                "description": "ID of the child who learned the word"
                            },
                            "source": {
                                "type": "string",
                                "description": "Source of learning (e.g., object_detection, physical_activity)"
                            },
                            "timestamp": {
                                "type": "string",
                                "description": "ISO 8601 timestamp when word was learned"
                            },
                            "word_id": {
                                "type": "string",
                                "description": "Optional word ID if known"
                            },
                            "confidence": {
                                "type": "number",
                                "format": "float",
                                "description": "Detection confidence (0.0-1.0)"
                            },
                            "image_url": {
                                "type": "string",
                                "description": "Image URL (if not uploading file)"
                            },
                            "metadata": {
                                "type": "string",
                                "description": "Additional metadata as JSON string"
                            },
                            "image": {
                                "type": "string",
                                "format": "binary",
                                "description": "Optional image file from camera"
                            }
                        }
                    }
                }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve audio with HTTP Range support so the player can seek to a page segment
# on the first (uncached) playback. Starlette's StaticFiles in this version does
# not honour Range requests, which forces the browser to download the whole file
# before it can seek, causing playback to start from 0:00 on a cold load.
_AUDIO_DIR = Path("uploads/audio").resolve()
_FILE_CHUNK_SIZE = 64 * 1024


def _serve_file_with_range(
    file_path: Path,
    request: Request,
    content_type: str,
) -> Response:
    file_size = file_path.stat().st_size
    base_headers = {
        "accept-ranges": "bytes",
        "content-type": content_type,
    }

    range_header = request.headers.get("range")
    range_match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip()) if range_header else None

    if range_match:
        start_token, end_token = range_match.group(1), range_match.group(2)

        if start_token == "":
            suffix_length = int(end_token) if end_token else 0
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_token)
            end = int(end_token) if end_token else file_size - 1

        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            return Response(
                status_code=416,
                headers={
                    "accept-ranges": "bytes",
                    "content-range": f"bytes */{file_size}",
                },
            )

        chunk_length = end - start + 1

        def iter_range():
            with open(file_path, "rb") as audio_file:
                audio_file.seek(start)
                remaining = chunk_length
                while remaining > 0:
                    data = audio_file.read(min(_FILE_CHUNK_SIZE, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers={
                **base_headers,
                "content-range": f"bytes {start}-{end}/{file_size}",
                "content-length": str(chunk_length),
            },
        )

    def iter_full():
        with open(file_path, "rb") as audio_file:
            while True:
                data = audio_file.read(_FILE_CHUNK_SIZE)
                if not data:
                    break
                yield data

    return StreamingResponse(
        iter_full(),
        status_code=200,
        headers={**base_headers, "content-length": str(file_size)},
    )


@app.get("/uploads/audio/{filename}")
def serve_audio_file(filename: str, request: Request) -> Response:
    """Serve generated audio with Range support (defends against path traversal)."""
    candidate = (_AUDIO_DIR / filename).resolve()
    if not str(candidate).startswith(str(_AUDIO_DIR) + "/") or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")

    content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    return _serve_file_with_range(candidate, request, content_type)


# Mount static files for uploaded images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "Preschool Vocabulary Platform API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
