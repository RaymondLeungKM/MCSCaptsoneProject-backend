"""
Story content endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.db.session import get_db
from app.schemas.content import StoryCreate, StoryResponse, StoryProgressResponse
from app.models.content import Story, StoryProgress
from app.models.user import User, Child
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/", response_model=List[StoryResponse])
async def get_stories(
    db: AsyncSession = Depends(get_db)
):
    """Get all active stories"""
    result = await db.execute(
        select(Story).where(Story.is_active == True).order_by(Story.sort_order)
    )
    stories = result.scalars().all()
    return stories


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific story with all pages"""
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    return story


@router.get("/child/{child_id}/progress", response_model=List[StoryProgressResponse])
async def get_child_story_progress(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get child's progress on all stories"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    result = await db.execute(
        select(StoryProgress).where(StoryProgress.child_id == child_id)
    )
    progress_list = result.scalars().all()
    
    return progress_list


@router.post("/{story_id}/progress/{child_id}")
async def update_story_progress(
    story_id: str,
    child_id: str,
    pages_completed: int,
    completed: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update child's progress on a story"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    # Get or create progress
    result = await db.execute(
        select(StoryProgress).where(
            StoryProgress.child_id == child_id,
            StoryProgress.story_id == story_id
        )
    )
    progress = result.scalar_one_or_none()
    
    from datetime import datetime
    
    if not progress:
        progress = StoryProgress(
            child_id=child_id,
            story_id=story_id,
            pages_completed=pages_completed,
            completed=completed,
            last_read=datetime.utcnow(),
            repeat_count=1
        )
        db.add(progress)
    else:
        progress.pages_completed = pages_completed
        progress.last_read = datetime.utcnow()
        if completed and not progress.completed:
            progress.completed = True
        if completed:
            progress.repeat_count += 1
    
    await db.commit()
    await db.refresh(progress)
    
    return progress
