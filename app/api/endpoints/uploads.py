"""
File upload endpoints for mobile app integration
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import uuid
import aiofiles
import os
from typing import Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()

# Configure upload directory
UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename"""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload an image file from mobile app.
    
    This endpoint allows mobile apps to upload images directly (e.g., photos from camera)
    instead of providing image URLs. The uploaded image is saved to the server and
    a URL is returned that can be used with other endpoints.
    
    **Use Case:**
    1. Mobile app captures photo with camera
    2. Mobile app uploads file to this endpoint
    3. Endpoint returns image URL
    4. Mobile app uses URL with `/vocabulary/word-learned` endpoint
    
    **Request:**
    - Multipart form data with file upload
    - File field name: `file`
    - Supported formats: JPG, JPEG, PNG, GIF, WEBP
    - Max size: 10MB
    
    **Response:**
    ```json
    {
      "success": true,
      "image_url": "http://localhost:8000/uploads/images/abc123.jpg",
      "filename": "abc123.jpg",
      "size": 123456,
      "content_type": "image/jpeg"
    }
    ```
    
    **Authentication:**
    Requires Bearer token in Authorization header.
    """
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided"
        )
    
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Supported formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size (read in chunks to avoid loading entire file into memory)
    file_size = 0
    chunk_size = 1024 * 1024  # 1MB chunks
    
    # Generate unique filename
    file_extension = get_file_extension(file.filename)
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = UPLOAD_DIR / unique_filename
    
    try:
        # Save file in chunks
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file.read(chunk_size):
                file_size += len(chunk)
                
                # Check size limit
                if file_size > MAX_FILE_SIZE:
                    # Clean up partially written file
                    await f.close()
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024):.0f}MB"
                    )
                
                await f.write(chunk)
        
        # Generate URL (adjust based on your domain/deployment)
        # In production, you might want to use environment variable for base URL
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        image_url = f"{base_url}/uploads/images/{unique_filename}"
        
        return {
            "success": True,
            "image_url": image_url,
            "filename": unique_filename,
            "size": file_size,
            "content_type": file.content_type
        }
    
    except HTTPException:
        raise
    except Exception as e:
        # Clean up file if it exists
        if file_path.exists():
            os.remove(file_path)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )
