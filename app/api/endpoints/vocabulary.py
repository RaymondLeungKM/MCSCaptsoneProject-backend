"""
Vocabulary word endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid

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
from app.models.user import User, Child
from app.core.security import get_current_active_user

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
    update_data = progress_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(progress, field, value)
    
    # Calculate success rate
    if progress.total_attempts is not None and progress.total_attempts > 0:
        if progress.correct_attempts is not None:
            progress.success_rate = progress.correct_attempts / progress.total_attempts
        else:
            progress.success_rate = 0.0
    
    # Update child's aggregate stats
    if is_new_word or (progress.exposure_count == 1):
        # First time encountering this word
        child.words_learned = (child.words_learned or 0) + 1
        child.today_progress = (child.today_progress or 0) + 1
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
    learning_event: ExternalWordLearning,
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
    
    **Use Cases:**
    - Mobile app with object detection identifies a word from a photo
    - Physical activity sensors detect kinesthetic learning
    - External educational tools integrate with the platform
    
    **Request Body:**
    - `word`: The word text (will be created if it doesn't exist)
    - `child_id`: UUID of the child
    - `timestamp`: ISO 8601 timestamp of when the word was learned
    - `source`: Source identifier (e.g., "object_detection", "physical_activity")
    - `word_id`: (Optional) If you already know the word ID
    - `confidence`: (Optional) Confidence score for ML-based detection (0.0-1.0)
    - `image_url`: (Optional) URL of the image used for detection
    - `metadata`: (Optional) Additional custom data
    """
    try:
        print(f"[External Word Learning] Received request: word={learning_event.word}, child_id={learning_event.child_id}, source={learning_event.source}")
        
        # Verify child exists
        result = await db.execute(
            select(Child).where(Child.id == learning_event.child_id)
        )
        child = result.scalar_one_or_none()
        if not child:
            print(f"[External Word Learning] ERROR: Child not found: {learning_event.child_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Child not found: {learning_event.child_id}"
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
    if learning_event.word_id:
        result = await db.execute(
            select(Word).where(Word.id == learning_event.word_id)
        )
        word = result.scalar_one_or_none()
    else:
        # Try to find word by text (case-insensitive)
        result = await db.execute(
            select(Word).where(Word.word.ilike(learning_event.word))
        )
        word = result.scalar_one_or_none()
    
    if not word:
        # Create new word from object detection
        print(f"[External Word Learning] Creating new word: '{learning_event.word}'")
        word_created = True
        
        # Ensure "general" category exists
        result = await db.execute(
            select(Category).where(Category.name == "general")
        )
        general_category = result.scalar_one_or_none()
        if not general_category:
            print(f"[External Word Learning] Creating 'general' category")
            general_category = Category(
                id=str(uuid.uuid4()),
                name="general",
                description="Words learned from external sources",
                icon="📝",
                color="bg-gray",
                sort_order=99
            )
            db.add(general_category)
            await db.flush()  # Ensure category is created before creating word
        
        word = Word(
            id=str(uuid.uuid4()),
            word=learning_event.word.capitalize(),
            category=general_category.id,  # Use category ID, not name
            difficulty="easy",  # Use valid enum value: easy, medium, or hard
            definition=f"A word learned from {learning_event.source}",
            example=f"I saw a {learning_event.word.lower()}.",
            pronunciation=None,
            physical_action=None,
            image_url=None,
            audio_url=None,
            contexts=[learning_event.source],
            related_words=[]
        )
        db.add(word)
        
        # Increment category word count
        general_category.word_count = (general_category.word_count or 0) + 1
        print(f"[External Word Learning] Updated category word count: {general_category.word_count}")
        print(f"[External Word Learning] New word created: {word.word} (ID: {word.id})")
    
    # Get or create progress
    result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == learning_event.child_id,
            WordProgress.word_id == word.id
        )
    )
    progress = result.scalar_one_or_none()
    
    is_new_word = False
    if not progress:
        is_new_word = True
        progress = WordProgress(
            child_id=learning_event.child_id,
            word_id=word.id,
            exposure_count=0,
            total_attempts=0,
            correct_attempts=0
        )
        db.add(progress)
    
    # Increment exposure count
    progress.exposure_count += 1
    progress.last_practiced = learning_event.timestamp
    
    # Track learning modality based on source
    if learning_event.source == 'object_detection':
        progress.visual_exposures = (progress.visual_exposures or 0) + 1
    elif learning_event.source == 'physical_activity':
        progress.kinesthetic_exposures = (progress.kinesthetic_exposures or 0) + 1
    
    # Mark as correct attempt (external sources are considered successful)
    progress.total_attempts = (progress.total_attempts or 0) + 1
    progress.correct_attempts = (progress.correct_attempts or 0) + 1
    progress.success_rate = progress.correct_attempts / progress.total_attempts
    
    # Update child's aggregate stats (only for first exposure)
    if is_new_word or progress.exposure_count == 1:
        child.words_learned = (child.words_learned or 0) + 1
        child.today_progress = (child.today_progress or 0) + 1
        child.xp = (child.xp or 0) + 10  # Award XP for learning new word
        
        # Level up logic (100 XP per level)
        if child.xp >= child.level * 100:
            child.level += 1
    
    await db.commit()
    await db.refresh(progress)
    await db.refresh(child)
    await db.refresh(word)
    
    # Get category name for response
    result = await db.execute(
        select(Category).where(Category.id == word.category)
    )
    word_category = result.scalar_one_or_none()
    category_name = word_category.name if word_category else None
    
    print(f"[External Word Learning] SUCCESS: {word.word} learned by child {child.id}, XP awarded: {10 if (is_new_word or progress.exposure_count == 1) else 0}, Word created: {word_created}")
    
    # Prepare word response data for frontend
    word_data = {
        "id": word.id,
        "word": word.word,
        "category": word.category,
        "category_name": category_name,
        "pronunciation": word.pronunciation,
        "definition": word.definition,
        "example": word.example,
        "difficulty": word.difficulty,
        "physical_action": word.physical_action,
        "image_url": word.image_url,
        "audio_url": word.audio_url,
        "contexts": word.contexts or [],
        "related_words": word.related_words or [],
        "total_exposures": word.total_exposures,
        "success_rate": word.success_rate,
        "is_active": word.is_active,
        "created_at": word.created_at
    }
    
    return {
        "success": True,
        "word": word.word,
        "word_id": word.id,
        "word_data": word_data,
        "word_created": word_created,
        "child_id": child.id,
        "exposure_count": progress.exposure_count,
        "xp_awarded": 10 if (is_new_word or progress.exposure_count == 1) else 0,
        "total_xp": child.xp,
        "level": child.level,
        "words_learned": child.words_learned,
        "source": learning_event.source,
        "timestamp": learning_event.timestamp
    }
