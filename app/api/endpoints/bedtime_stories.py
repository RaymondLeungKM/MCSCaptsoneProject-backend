"""
Endpoints for AI-generated bedtime stories
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List
from datetime import datetime, date

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User, Child
from app.models.daily_words import DailyWordTracking, GeneratedStory
from app.models.vocabulary import Word
from app.schemas.stories import (
    DailyWordTrackingCreate,
    DailyWordTrackingResponse,
    DailyWordSummary,
    GeneratedStoryCreate,
    GeneratedStoryResponse,
    StoryGenerationRequest,
    StoryGenerationResponse
)
from app.services.story_generator import story_generator

router = APIRouter()


@router.get("/daily-words/{child_id}", response_model=List[DailyWordSummary])
async def get_daily_words(
    child_id: str,
    date: datetime = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get words learned today for a child"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get daily words
    words = await story_generator.get_daily_words(db, child_id, date)
    return words


@router.post("/track-word", response_model=DailyWordTrackingResponse)
async def track_daily_word(
    tracking: DailyWordTrackingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Track a word learned today"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == tracking.child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Check if already tracked today
    start_of_day = tracking.date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = tracking.date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    existing_query = select(DailyWordTracking).where(
        and_(
            DailyWordTracking.child_id == tracking.child_id,
            DailyWordTracking.word_id == tracking.word_id,
            DailyWordTracking.date >= start_of_day,
            DailyWordTracking.date <= end_of_day
        )
    )
    result = await db.execute(existing_query)
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update existing record
        existing.exposure_count += tracking.exposure_count
        existing.used_actively = existing.used_actively or tracking.used_actively
        existing.mastery_confidence = max(existing.mastery_confidence, tracking.mastery_confidence)
        if tracking.learned_context:
            existing.learned_context = tracking.learned_context
        await db.commit()
        await db.refresh(existing)
        return existing
    
    # Create new tracking record
    new_tracking = DailyWordTracking(**tracking.model_dump())
    db.add(new_tracking)
    await db.commit()
    await db.refresh(new_tracking)
    return new_tracking


@router.post("/generate", response_model=StoryGenerationResponse)
async def generate_bedtime_story(
    request: StoryGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate an AI-powered bedtime story using today's learned words"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == request.child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    try:
        # Generate story
        story, words_used, generation_time = await story_generator.generate_story(db, request)
        
        # Convert to response
        story_response = GeneratedStoryResponse.model_validate(story)
        
        return StoryGenerationResponse(
            story=story_response,
            words_used=words_used,
            generation_time_seconds=generation_time,
            success=True,
            message="Story generated successfully"
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"[API] Error generating story: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate story"
        )


@router.get("/list/{child_id}", response_model=List[GeneratedStoryResponse])
async def get_child_stories(
    child_id: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all stories generated for a child"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get stories
    stories_query = (
        select(GeneratedStory)
        .where(GeneratedStory.child_id == child_id)
        .order_by(GeneratedStory.generation_date.desc())
        .limit(limit)
    )
    result = await db.execute(stories_query)
    stories = result.scalars().all()
    
    return [GeneratedStoryResponse.model_validate(s) for s in stories]


@router.get("/{child_id}/{story_id}", response_model=GeneratedStoryResponse)
async def get_story(
    child_id: str,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific generated story"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get story
    story_query = select(GeneratedStory).where(
        and_(
            GeneratedStory.id == story_id,
            GeneratedStory.child_id == child_id
        )
    )
    result = await db.execute(story_query)
    story = result.scalar_one_or_none()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Increment read count
    story.read_count += 1
    await db.commit()
    await db.refresh(story)
    
    return GeneratedStoryResponse.model_validate(story)


@router.patch("/{child_id}/{story_id}/favorite")
async def toggle_favorite(
    child_id: str,
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle favorite status for a story"""
    
    # Verify child belongs to user
    child_query = select(Child).where(
        and_(Child.id == child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get story
    story_query = select(GeneratedStory).where(
        and_(
            GeneratedStory.id == story_id,
            GeneratedStory.child_id == child_id
        )
    )
    result = await db.execute(story_query)
    story = result.scalar_one_or_none()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Toggle favorite
    story.is_favorite = not story.is_favorite
    await db.commit()
    await db.refresh(story)
    
    return {"is_favorite": story.is_favorite}
