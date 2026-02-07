"""
FastAPI Backend for Preschool Vocabulary Platform
Main application entry point
"""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
