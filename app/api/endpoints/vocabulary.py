"""
Vocabulary word endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict
import uuid
from datetime import datetime
from pathlib import Path
import aiofiles
import os
import json

from app.db.session import get_db
from app.schemas.vocabulary import (
    WordCreate, 
    WordUpdate, 
    WordResponse, 
    WordWithProgress,
    WordProgressUpdate,
    ExternalWordLearning,
    ExternalWordLearningResponse
)
from app.models.vocabulary import Word, WordProgress, Category
from app.models.generated_sentences import GeneratedSentence as GeneratedSentenceModel
from app.models.user import User, Child
from app.core.security import get_current_active_user
from app.core.category_colors import get_category_color
from app.services.sentence_generator import get_sentence_generator, SentenceGenerationResult
from app.services.word_enhancement_service import get_word_enhancement_service

router = APIRouter()


@router.get("/", response_model=List[WordResponse])
async def get_words(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Get list of words with optional filters"""
    query = select(Word).options(selectinload(Word.category_rel)).where(Word.is_active == True)
    
    if category:
        query = query.where(Word.category == category)
    if difficulty:
        query = query.where(Word.difficulty == difficulty)
    
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    words = result.scalars().all()
    
    # Add category name to each word
    response_words = []
    for word in words:
        word_dict = WordResponse.model_validate(word).model_dump()
        word_dict['category_name'] = word.category_rel.name if word.category_rel else None
        word_dict['category_name_cantonese'] = word.category_rel.name_cantonese if word.category_rel else None
        response_words.append(word_dict)
    
    return response_words


@router.get("/{word_id}", response_model=WordResponse)
async def get_word(
    word_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific word details"""
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()
    
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found"
        )
    
    return word


@router.get("/child/{child_id}", response_model=List[WordWithProgress])
async def get_words_with_progress(
    child_id: str,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get words with child's progress data"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get words with progress
    query = select(Word).options(selectinload(Word.category_rel)).where(Word.is_active == True)
    if category:
        query = query.where(Word.category == category)
    
    result = await db.execute(query)
    words = result.scalars().all()
    
    # Get progress for each word
    words_with_progress = []
    for word in words:
        progress_result = await db.execute(
            select(WordProgress).where(
                WordProgress.child_id == child_id,
                WordProgress.word_id == word.id
            )
        )
        progress = progress_result.scalar_one_or_none()
        
        word_dict = {
            **word.__dict__,
            "category_name": word.category_rel.name if word.category_rel else None,
            "category_name_cantonese": word.category_rel.name_cantonese if word.category_rel else None,
            "progress": progress
        }
        words_with_progress.append(word_dict)
    
    return words_with_progress


@router.post("/", response_model=WordResponse, status_code=status.HTTP_201_CREATED)
async def create_word(
    word_data: WordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create new word (admin only)"""
    word = Word(
        id=str(uuid.uuid4()),
        word=word_data.word,
        category=word_data.category,
        pronunciation=word_data.pronunciation,
        definition=word_data.definition,
        example=word_data.example,
        difficulty=word_data.difficulty,
        physical_action=word_data.physical_action,
        image_url=word_data.image_url,
        audio_url=word_data.audio_url,
        contexts=word_data.contexts or [],
        related_words=word_data.related_words or [],
    )
    
    db.add(word)
    await db.commit()
    await db.refresh(word)
    
    return word


@router.patch("/{word_id}", response_model=WordResponse)
async def update_word(
    word_id: str,
    word_data: WordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update word (admin only)"""
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()
    
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found"
        )
    
    update_data = word_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(word, field, value)
    
    await db.commit()
    await db.refresh(word)
    
    return word


@router.post("/{word_id}/progress/{child_id}")
async def update_word_progress(
    word_id: str,
    child_id: str,
    progress_data: WordProgressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update child's progress on a word"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get or create progress
    result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_id
        )
    )
    progress = result.scalar_one_or_none()
    
    is_new_word = False
    if not progress:
        is_new_word = True
        progress = WordProgress(
            child_id=child_id,
            word_id=word_id
        )
        db.add(progress)
    
    # Update progress
    old_exposure_count = progress.exposure_count or 0
    update_data = progress_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(progress, field, value)
    
    # Calculate success rate
    if progress.total_attempts is not None and progress.total_attempts > 0:
        if progress.correct_attempts is not None:
            progress.success_rate = progress.correct_attempts / progress.total_attempts
        else:
            progress.success_rate = 0.0
    
    # Update child's aggregate stats (only for first exposure to a new word)
    if is_new_word and progress.exposure_count == 1:
        # First time encountering this word - increment counters
        child.words_learned = (child.words_learned or 0) + 1
        child.xp = (child.xp or 0) + 10  # Award XP for learning new word
        
        # Level up logic (100 XP per level)
        if child.xp >= child.level * 100:
            child.level += 1
    
    await db.commit()
    await db.refresh(progress)
    
    return progress


@router.post(
    "/external/word-learned",
    response_model=ExternalWordLearningResponse,
    status_code=status.HTTP_200_OK,
    summary="Record external word learning",
    description="Records word learning from external sources like mobile app object detection or physical activities",
    responses={
        200: {
            "description": "Word learning recorded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "word": "Elephant",
                        "word_id": "5a182e71-c7a6-4489-b182-29d3fb4a76a6",
                        "word_data": {
                            "id": "5a182e71-c7a6-4489-b182-29d3fb4a76a6",
                            "word": "Elephant",
                            "category": "animals",
                            "definition": "A large gray animal with a trunk",
                            "example": "The elephant is very big."
                        },
                        "word_created": False,
                        "child_id": "2a2e0b85-dd89-4ae3-90d4-c58ce0d488e0",
                        "exposure_count": 2,
                        "xp_awarded": 0,
                        "total_xp": 100,
                        "level": 2,
                        "words_learned": 10,
                        "source": "object_detection",
                        "timestamp": "2026-01-27T16:43:03.748Z"
                    }
                }
            }
        },
        404: {
            "description": "Child not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Child not found: invalid-child-id"}
                }
            }
        }
    },
    tags=["Mobile Integration"]
)
async def record_external_word_learning(
    word: str = Form(..., description="The word that was learned"),
    child_id: str = Form(..., description="ID of the child who learned the word"),
    source: str = Form(..., description="Source of learning (e.g., object_detection, physical_activity)"),
    timestamp: str = Form(..., description="ISO 8601 timestamp when word was learned"),
    word_id: Optional[str] = Form(None, description="Optional word ID if known"),
    confidence: Optional[float] = Form(None, description="Detection confidence (0.0-1.0)"),
    image_url: Optional[str] = Form(None, description="Image URL (if not uploading file)"),
    metadata: Optional[str] = Form(None, description="Additional metadata as JSON string"),
    image: Optional[UploadFile] = File(None, description="Optional image file from camera"),
    db: AsyncSession = Depends(get_db)
):
    """
    Record word learning from external sources (mobile app object detection, physical activities, etc.)
    
    This endpoint allows the mobile app to notify the backend when a child learns a word
    through activities outside the web platform. It supports:
    
    - **Automatic word creation**: If the word doesn't exist in the vocabulary, it will be created automatically
    - **Progress tracking**: Records exposure count and learning modality (visual/kinesthetic)
    - **XP rewards**: Awards 10 XP for first exposure to a word
    - **Level progression**: Automatically levels up the child (100 XP per level)
    - **Learning sources**: Tracks source (object_detection, physical_activity, etc.)
    - **Direct image upload**: Upload image file directly without separate API call
    
    **Use Cases:**
    - Mobile app with object detection identifies a word from a photo
    - Physical activity sensors detect kinesthetic learning
    - External educational tools integrate with the platform
    
    **Request (multipart/form-data):**
    - `word`: The word text (required)
    - `child_id`: UUID of the child (required)
    - `timestamp`: ISO 8601 timestamp (required)
    - `source`: Source identifier (required)
    - `word_id`: (Optional) If you already know the word ID
    - `confidence`: (Optional) Confidence score for ML-based detection (0.0-1.0)
    - `image_url`: (Optional) URL of the image (use if image is already hosted)
    - `image`: (Optional) Image file upload (JPG, PNG, etc.) - direct from camera
    - `metadata`: (Optional) Additional custom data as JSON string
    
    **Mobile Integration Workflow (Simplified - Single API Call):**
    1. Mobile app captures photo and performs object detection
    2. Mobile calls THIS endpoint with form-data including the image file
    3. Backend saves image, records progress, awards XP, and returns updated stats
    
    **Note:** You can either provide `image` (file upload) OR `image_url` (string), not both.
    If both are provided, the file upload takes precedence.
    """
    # Handle image file upload if provided
    final_image_url = image_url
    if image and image.filename:
        try:
            # Validate file type
            ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
            file_ext = Path(image.filename).suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                )
            
            # Create uploads directory
            UPLOAD_DIR = Path("uploads/images")
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = UPLOAD_DIR / unique_filename
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                content = await image.read()
                await f.write(content)
            
            # Generate URL
            base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
            final_image_url = f"{base_url}/uploads/images/{unique_filename}"
            print(f"[External Word Learning] Image uploaded: {final_image_url}")
        except HTTPException:
            raise
        except Exception as e:
            print(f"[External Word Learning] Image upload failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload image: {str(e)}"
            )
    
    # Parse metadata if provided
    metadata_dict = None
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            print(f"[External Word Learning] Invalid metadata JSON: {metadata}")
    
    # Parse timestamp
    try:
        timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timestamp format. Use ISO 8601 format."
        )
    
    try:
        print(f"[External Word Learning] Received request: word={word}, child_id={child_id}, source={source}")
        
        # Verify child exists
        result = await db.execute(
            select(Child).where(Child.id == child_id)
        )
        child = result.scalar_one_or_none()
        if not child:
            print(f"[External Word Learning] ERROR: Child not found: {child_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Child not found: {child_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[External Word Learning] UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
    
    # Find the word by ID or word text
    word_created = False
    if word_id:
        result = await db.execute(
            select(Word).where(Word.id == word_id)
        )
        word_obj = result.scalar_one_or_none()
    else:
        # Try to find word by text (case-insensitive)
        result = await db.execute(
            select(Word).where(Word.word.ilike(word))
        )
        word_obj = result.scalar_one_or_none()
    
    # If word exists and image_url provided, update it
    if word_obj and final_image_url and not word_obj.image_url:
        word_obj.image_url = final_image_url
        print(f"[External Word Learning] Updated image URL for existing word: {word_obj.word}")
        print(f"[External Word Learning] NOTE: For existing words, we only update image. The word text '{word_obj.word}' remains unchanged.")
    
    if not word_obj:
        # Create new word from object detection with AI-enhanced bilingual content
        print(f"[External Word Learning] Creating new word with AI enhancement: '{word}'")
        word_created = True
        
        # Ensure "general" category exists
        result = await db.execute(
            select(Category).where(Category.name == "general")
        )
        general_category = result.scalar_one_or_none()
        if not general_category:
            print(f"[External Word Learning] Creating 'general' category")
            # Get count for color assignment
            result_count = await db.execute(select(Category))
            existing_count = len(result_count.scalars().all())
            
            general_category = Category(
                id=str(uuid.uuid4()),
                name="general",
                name_cantonese="一般",
                description="Words learned from external sources",
                description_cantonese="從外部來源學習的詞語",
                icon="📝",
                color=get_category_color("general", existing_count),
                sort_order=99
            )
            db.add(general_category)
            await db.flush()  # Ensure category is created before creating word
        
        # Use AI to generate complete bilingual content
        try:
            enhancement_service = get_word_enhancement_service()
            enhanced_content = await enhancement_service.enhance_word(
                word=word,
                source=source,
                image_url=final_image_url
            )
            
            print(f"[External Word Learning] ✓ AI-enhanced content generated")
            print(f"  - Cantonese: {enhanced_content.word_cantonese} ({enhanced_content.jyutping})")
            
            word_obj = Word(
                id=str(uuid.uuid4()),
                word=enhanced_content.word_english.capitalize(),
                word_cantonese=enhanced_content.word_cantonese,
                jyutping=enhanced_content.jyutping,
                category=general_category.id,
                difficulty=enhanced_content.difficulty,
                definition=enhanced_content.definition_english,
                definition_cantonese=enhanced_content.definition_cantonese,
                example=enhanced_content.example_english,
                example_cantonese=enhanced_content.example_cantonese,
                pronunciation=None,
                physical_action=None,
                image_url=final_image_url,
                audio_url=None,
                contexts=[source],
                related_words=[]
            )
        except Exception as e:
            print(f"[External Word Learning] WARNING: AI enhancement failed: {e}")
            print(f"[External Word Learning] Falling back to basic word creation")
            # Fallback to basic word creation
            word_obj = Word(
                id=str(uuid.uuid4()),
                word=word.capitalize(),
                category=general_category.id,
                difficulty="easy",
                definition=f"A word learned from {source}",
                example=f"I saw a {word.lower()}.",
                pronunciation=None,
                physical_action=None,
                image_url=final_image_url,
                audio_url=None,
                contexts=[source],
                related_words=[]
            )
        
        db.add(word_obj)
        
        # Increment category word count
        general_category.word_count = (general_category.word_count or 0) + 1
        print(f"[External Word Learning] Updated category word count: {general_category.word_count}")
        print(f"[External Word Learning] New word created: {word_obj.word} (ID: {word_obj.id})")
    
    # Get or create progress
    result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_obj.id
        )
    )
    progress = result.scalar_one_or_none()
    
    is_new_word = False
    if not progress:
        is_new_word = True
        progress = WordProgress(
            child_id=child_id,
            word_id=word_obj.id,
            exposure_count=0,
            total_attempts=0,
            correct_attempts=0
        )
        db.add(progress)
    
    # Increment exposure count
    progress.exposure_count += 1
    progress.last_practiced = timestamp_dt
    
    # Track learning modality based on source
    if source == 'object_detection':
        progress.visual_exposures = (progress.visual_exposures or 0) + 1
    elif source == 'physical_activity':
        progress.kinesthetic_exposures = (progress.kinesthetic_exposures or 0) + 1
    
    # Mark as correct attempt (external sources are considered successful)
    progress.total_attempts = (progress.total_attempts or 0) + 1
    progress.correct_attempts = (progress.correct_attempts or 0) + 1
    progress.success_rate = progress.correct_attempts / progress.total_attempts
    
    # Update child's aggregate stats (only for first exposure)
    leveled_up = False
    if is_new_word or progress.exposure_count == 1:
        child.words_learned = (child.words_learned or 0) + 1
        child.today_progress = (child.today_progress or 0) + 1
        child.xp = (child.xp or 0) + 10  # Award XP for learning new word
        
        # Level up logic (100 XP per level)
        if child.xp >= child.level * 100:
            child.level += 1
            leveled_up = True
    
    await db.commit()
    await db.refresh(progress)
    await db.refresh(child)
    await db.refresh(word_obj)
    
    # Generate AI sentences for new words (async, in background)
    if word_created or is_new_word:
        try:
            print(f"[External Word Learning] Generating AI sentences for new word: {word_obj.word}")
            generator = get_sentence_generator()
            await generator.generate_sentences(
                word=word_obj,
                num_sentences=3,
                contexts=["home", "school"],
                db=db,
                save_to_db=True
            )
            print(f"[External Word Learning] AI sentences generated and saved for: {word_obj.word}")
        except Exception as e:
            # Don't fail the whole request if sentence generation fails
            print(f"[External Word Learning] WARNING: Failed to generate sentences: {e}")
    
    # Get category name for response
    result = await db.execute(
        select(Category).where(Category.id == word_obj.category)
    )
    word_category = result.scalar_one_or_none()
    category_name = word_category.name if word_category else None
    
    print(f"[External Word Learning] SUCCESS: {word_obj.word} learned by child {child.id}, XP awarded: {10 if (is_new_word or progress.exposure_count == 1) else 0}, Word created: {word_created}")
    
    # Prepare word response data for frontend
    word_data = {
        "id": word_obj.id,
        "word": word_obj.word,
        "category": word_obj.category,
        "category_name": category_name,
        "pronunciation": word_obj.pronunciation,
        "definition": word_obj.definition,
        "example": word_obj.example,
        "difficulty": word_obj.difficulty,
        "physical_action": word_obj.physical_action,
        "image_url": word_obj.image_url,
        "audio_url": word_obj.audio_url,
        "contexts": word_obj.contexts or [],
        "related_words": word_obj.related_words or [],
        "total_exposures": word_obj.total_exposures,
        "success_rate": word_obj.success_rate,
        "is_active": word_obj.is_active,
        "created_at": word_obj.created_at
    }
    
    return {
        "success": True,
        "word": word_obj.word,
        "word_id": word_obj.id,
        "word_data": word_data,
        "word_created": word_created,
        "child_id": child.id,
        "exposure_count": progress.exposure_count,
        "xp_awarded": 10 if (is_new_word or progress.exposure_count == 1) else 0,
        "total_xp": child.xp,
        "level": child.level,
        "words_learned": child.words_learned,
        "source": source,
        "timestamp": timestamp_dt,
        "level_up": leveled_up,
    }


@router.post(
    "/{word_id}/generate-sentences",
    response_model=SentenceGenerationResult,
    summary="Generate example sentences for a word",
    description="""
    Generate age-appropriate Cantonese example sentences for a vocabulary word using AI.
    
    This endpoint uses LLM to create contextual, natural sentences that demonstrate
    how the word is used in everyday situations relevant to Hong Kong preschoolers.
    
    **Features:**
    - 3-5 example sentences per word
    - Multiple contexts (home, school, park, etc.)
    - Includes Jyutping romanization
    - English translations provided
    - Age-appropriate language (3-5 years old)
    - Difficulty levels (easy, medium, hard)
    
    **Use Cases:**
    - Show examples after object detection
    - Enhance word learning with contextual usage
    - Provide variety in teaching materials
    - Help parents understand word usage
    
    **Parameters:**
    - `word_id`: UUID of the word
    - `num_sentences`: Number of sentences to generate (default 3, max 5)
    - `contexts`: Optional list of specific contexts (home, school, park, supermarket, playground, meal_time, bedtime)
    
    **Response:**
    - Generated sentences with Traditional Chinese text
    - Jyutping romanization for pronunciation
    - English translations
    - Context labels (where the word might be used)
    - Difficulty ratings
    
    **Note:** First request may take 5-10 seconds. Results are not cached in this version.
    """,
    tags=["AI Features"]
)
async def generate_word_sentences(
    word_id: str,
    num_sentences: int = Query(default=3, ge=1, le=5, description="Number of sentences to generate"),
    contexts: Optional[List[str]] = Query(default=None, description="Specific contexts (optional)"),
    db: AsyncSession = Depends(get_db)
):
    """Generate example sentences for a word using AI"""
    # Get word with category relationship
    result = await db.execute(
        select(Word).options(selectinload(Word.category_rel)).where(Word.id == word_id)
    )
    word = result.scalar_one_or_none()
    
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Word not found: {word_id}"
        )
    
    # Generate sentences
    try:
        generator = get_sentence_generator()
        result = await generator.generate_sentences(
            word=word,
            num_sentences=num_sentences,
            contexts=contexts,
            db=db,
            save_to_db=True  # Save to database
        )
        return result
    except Exception as e:
        print(f"[GenerateSentences] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate sentences: {str(e)}"
        )


@router.get(
    "/{word_id}/sentences",
    response_model=List[Dict],
    summary="Get saved example sentences for a word",
    description="""
    Retrieve AI-generated example sentences that have been saved to the database.
    
    Returns sentences with:
    - Traditional Chinese text
    - Jyutping romanization
    - English translation
    - Context information (home, school, park, etc.)
    - Difficulty level
    
    If no sentences are saved, returns empty list. Use the /generate-sentences endpoint
    to generate and save new sentences.
    """
)
async def get_word_sentences(
    word_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get saved example sentences for a word"""
    # Verify word exists
    result = await db.execute(
        select(Word).where(Word.id == word_id)
    )
    word = result.scalar_one_or_none()
    
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Word not found: {word_id}"
        )
    
    # Get saved sentences
    result = await db.execute(
        select(GeneratedSentenceModel)
        .where(GeneratedSentenceModel.word_id == word_id)
        .where(GeneratedSentenceModel.is_active == True)
        .order_by(GeneratedSentenceModel.created_at.desc())
    )
    sentences = result.scalars().all()
    
    # Increment view count
    for sent in sentences:
        sent.view_count = (sent.view_count or 0) + 1
    await db.commit()
    
    return [
        {
            "id": sent.id,
            "sentence": sent.sentence,
            "sentence_english": sent.sentence_english,
            "jyutping": sent.jyutping,
            "context": sent.context,
            "difficulty": sent.difficulty,
            "created_at": sent.created_at
        }
        for sent in sentences
    ]


@router.post(
    "/{word_id}/enhance",
    response_model=WordResponse,
    summary="Enhance word with AI-generated bilingual content",
    description="""
    Enhance an existing word with AI-generated bilingual content (Cantonese + English).
    
    This endpoint uses AI to generate:
    - Cantonese word text and Jyutping romanization
    - Age-appropriate definitions in both languages
    - Example sentences in both languages
    - Appropriate difficulty level
    
    **IMPORTANT: Preservation Behavior**
    - Existing word text (English and Cantonese) is NEVER modified
    - Only MISSING bilingual fields are filled in
    - If word already has Cantonese content, it's preserved
    - Only generic definitions ("word learned from...") are updated
    
    **Use Cases:**
    - Add missing Cantonese translations to English-only words
    - Fill in missing definitions/examples
    - Add Jyutping to words that lack it
    
    **What Gets Updated:**
    - ✅ Missing `word_cantonese`, `jyutping`, definitions, examples
    - ✅ Generic definitions that need improvement
    - ❌ Existing word text (English or Cantonese)
    - ❌ Existing manually curated content
    """,
    tags=["AI Features"]
)
async def enhance_word_content(
    word_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Enhance a word with AI-generated bilingual content"""
    # Get word
    result = await db.execute(
        select(Word).where(Word.id == word_id)
    )
    word = result.scalar_one_or_none()
    
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Word not found: {word_id}"
        )
    
    # Store original word to ensure it's never modified
    original_word = word.word
    
    print(f"[EnhanceWord] Enhancing word: {original_word} (ID: {word_id})")
    print(f"[EnhanceWord] Current state:")
    print(f"  - word: {word.word}")
    print(f"  - word_cantonese: {word.word_cantonese}")
    print(f"  - definition: {word.definition[:50] if word.definition else 'None'}...")
    
    # Generate enhanced content
    try:
        enhancement_service = get_word_enhancement_service()
        enhanced = await enhancement_service.enhance_word(
            word=original_word,
            source="enhancement"
        )
        
        # IMPORTANT: Only update MISSING bilingual fields
        # NEVER modify existing word.word (English) or word.word_cantonese (Chinese) text
        
        # Store original Cantonese word to ensure it's never modified
        original_word_cantonese = word.word_cantonese
        
        # Only update if field is missing/empty
        if not word.word_cantonese:
            word.word_cantonese = enhanced.word_cantonese
        else:
            print(f"[EnhanceWord]   Preserving existing Cantonese word: {word.word_cantonese}")
        
        if not word.jyutping:
            word.jyutping = enhanced.jyutping
        else:
            print(f"[EnhanceWord]   Preserving existing jyutping: {word.jyutping}")
        
        if not word.definition_cantonese:
            word.definition_cantonese = enhanced.definition_cantonese
        else:
            print(f"[EnhanceWord]   Preserving existing Cantonese definition")
        
        if not word.example_cantonese:
            word.example_cantonese = enhanced.example_cantonese
        else:
            print(f"[EnhanceWord]   Preserving existing Cantonese example")
        
        # Only update English definition/example if it was generic
        if not word.definition or "word learned from" in word.definition.lower():
            word.definition = enhanced.definition_english
            word.example = enhanced.example_english
        
        # Update difficulty if needed
        if enhanced.difficulty and enhanced.difficulty in ["easy", "medium", "hard"]:
            word.difficulty = enhanced.difficulty
        
        # Explicitly ensure word fields are NOT changed
        if word.word != original_word:
            print(f"[EnhanceWord] ⚠️  WARNING: English word was modified! Reverting.")
            print(f"[EnhanceWord]   Original: {original_word}")
            print(f"[EnhanceWord]   Changed to: {word.word}")
            word.word = original_word
        
        if original_word_cantonese and word.word_cantonese != original_word_cantonese:
            print(f"[EnhanceWord] ⚠️  WARNING: Cantonese word was modified! Reverting.")
            print(f"[EnhanceWord]   Original: {original_word_cantonese}")
            print(f"[EnhanceWord]   Changed to: {word.word_cantonese}")
            word.word_cantonese = original_word_cantonese
        
        await db.commit()
        await db.refresh(word)
        
        # Final verification that word texts weren't changed
        if word.word != original_word:
            print(f"[EnhanceWord] ❌ ERROR: English word was unexpectedly modified after commit!")
            print(f"[EnhanceWord]   Original: {original_word}")
            print(f"[EnhanceWord]   Changed to: {word.word}")
            word.word = original_word
            await db.commit()
        
        if original_word_cantonese and word.word_cantonese != original_word_cantonese:
            print(f"[EnhanceWord] ❌ ERROR: Cantonese word was unexpectedly modified after commit!")
            print(f"[EnhanceWord]   Original: {original_word_cantonese}")
            print(f"[EnhanceWord]   Changed to: {word.word_cantonese}")
            word.word_cantonese = original_word_cantonese
            await db.commit()
        
        print(f"[EnhanceWord] ✓ Successfully enhanced word: {word.word}")
        print(f"[EnhanceWord] Final state:")
        print(f"  - word: {word.word} (unchanged: {word.word == original_word})")
        print(f"  - word_cantonese: {word.word_cantonese} (unchanged: {not original_word_cantonese or word.word_cantonese == original_word_cantonese})")
        print(f"  - definition: {word.definition[:50] if word.definition else 'None'}...")
        
        return word
        
    except Exception as e:
        print(f"[EnhanceWord] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enhance word: {str(e)}"
        )


@router.post(
    "/batch-enhance",
    summary="Batch enhance multiple words with AI",
    description="""
    Enhance multiple words with AI-generated bilingual content.
    
    This endpoint processes words and fills in missing Cantonese translations
    and generates complete bilingual content for them.
    
    **IMPORTANT: Preservation Behavior**
    - Existing word text (English and Cantonese) is NEVER modified
    - Only MISSING bilingual fields are filled in
    - Words with existing Cantonese content are preserved
    - Only generic definitions ("word learned from...") are updated
    
    **Parameters:**
    - `limit`: Maximum number of words to process (default 10, max 50)
    - `category`: Optional category filter
    - `only_missing`: Only enhance words without Cantonese content (default true)
    
    **Response:**
    - Number of words processed
    - Number of successes and failures
    - List of processed word IDs
    
    **Safe to Use:**
    - Won't overwrite manually curated content
    - Preserves existing translations
    - Only fills in gaps in bilingual content
    
    **Note:** This operation can take time. For large batches, consider
    running in multiple smaller batches (10-20 words at a time).
    """,
    tags=["AI Features"]
)
async def batch_enhance_words(
    limit: int = Query(default=10, ge=1, le=50),
    category: Optional[str] = Query(default=None),
    only_missing: bool = Query(default=True),
    db: AsyncSession = Depends(get_db)
):
    """Batch enhance words with AI-generated content"""
    print(f"[BatchEnhance] Starting batch enhancement (limit={limit}, category={category}, only_missing={only_missing})")
    
    # Build query
    query = select(Word).where(Word.is_active == True)
    
    if category:
        query = query.where(Word.category == category)
    
    if only_missing:
        # Only enhance words without Cantonese content
        query = query.where(
            (Word.word_cantonese.is_(None)) | (Word.word_cantonese == "")
        )
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    words = result.scalars().all()
    
    if not words:
        return {
            "message": "No words found matching criteria",
            "total": 0,
            "success": 0,
            "failed": 0,
            "processed_ids": []
        }
    
    print(f"[BatchEnhance] Found {len(words)} words to enhance")
    
    # Process each word
    enhancement_service = get_word_enhancement_service()
    processed_ids = []
    success_count = 0
    failed_count = 0
    
    for word in words:
        try:
            # Store original words to ensure they're never modified
            original_word = word.word
            original_word_cantonese = word.word_cantonese
            
            print(f"[BatchEnhance] Processing: {original_word} (ID: {word.id})")
            
            enhanced = await enhancement_service.enhance_word(
                word=original_word,
                source="batch_enhancement"
            )
            
            # IMPORTANT: Only update MISSING bilingual fields
            # NEVER modify existing word.word (English) or word.word_cantonese (Chinese) text
            
            # Only update if field is missing/empty
            if not word.word_cantonese:
                word.word_cantonese = enhanced.word_cantonese
                print(f"[BatchEnhance]   Added Cantonese: {enhanced.word_cantonese}")
            else:
                print(f"[BatchEnhance]   Preserving existing Cantonese: {word.word_cantonese}")
            
            if not word.jyutping:
                word.jyutping = enhanced.jyutping
            
            if not word.definition_cantonese:
                word.definition_cantonese = enhanced.definition_cantonese
            
            if not word.example_cantonese:
                word.example_cantonese = enhanced.example_cantonese
            
            # Only update English definition/example if it was generic
            if not word.definition or "word learned from" in word.definition.lower():
                word.definition = enhanced.definition_english
                word.example = enhanced.example_english
            
            if enhanced.difficulty and enhanced.difficulty in ["easy", "medium", "hard"]:
                word.difficulty = enhanced.difficulty
            
            # Explicitly ensure word fields are NOT changed
            if word.word != original_word:
                print(f"[BatchEnhance] ⚠️  WARNING: English word was modified! Reverting.")
                print(f"[BatchEnhance]   Original: {original_word}")
                print(f"[BatchEnhance]   Changed to: {word.word}")
                word.word = original_word
            
            if original_word_cantonese and word.word_cantonese != original_word_cantonese:
                print(f"[BatchEnhance] ⚠️  WARNING: Cantonese word was modified! Reverting.")
                print(f"[BatchEnhance]   Original: {original_word_cantonese}")
                print(f"[BatchEnhance]   Changed to: {word.word_cantonese}")
                word.word_cantonese = original_word_cantonese
            
            processed_ids.append(word.id)
            success_count += 1
            final_cantonese = word.word_cantonese or enhanced.word_cantonese
            print(f"[BatchEnhance] ✓ Enhanced: {original_word} -> {final_cantonese} (words unchanged: EN={word.word == original_word}, 粵={not original_word_cantonese or word.word_cantonese == original_word_cantonese})")
            
        except Exception as e:
            failed_count += 1
            print(f"[BatchEnhance] ✗ Failed to enhance {word.word}: {str(e)}")
    
    # Commit all changes
    await db.commit()
    
    result = {
        "message": f"Processed {len(words)} words",
        "total": len(words),
        "success": success_count,
        "failed": failed_count,
        "processed_ids": processed_ids
    }
    
    print(f"[BatchEnhance] Complete: {success_count} success, {failed_count} failed")
    return result
