"""
Progress tracking endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid
from datetime import datetime

from app.db.session import get_db
from app.schemas.analytics import (
    LearningSessionCreate,
    LearningSessionUpdate,
    LearningSessionResponse,
    ProgressStatsResponse
)
from app.models.analytics import LearningSession
from app.models.user import User, Child
from app.models.vocabulary import WordProgress
from app.core.security import get_current_active_user

router = APIRouter()


@router.post("/session", response_model=LearningSessionResponse)
async def start_learning_session(
    session_data: LearningSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Start a new learning session"""
    # Verify child belongs to user
    result = await db.execute(
        select(Child).where(
            Child.id == session_data.child_id,
            Child.parent_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )
    
    session = LearningSession(
        id=str(uuid.uuid4()),
        child_id=session_data.child_id,
        start_time=session_data.start_time,
        words_encountered=session_data.words_encountered,
        activities_completed=[act.dict() for act in session_data.activities_completed],
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    return session


@router.patch("/session/{session_id}", response_model=LearningSessionResponse)
async def end_learning_session(
    session_id: str,
    session_data: LearningSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """End a learning session and record results"""
    result = await db.execute(
        select(LearningSession).where(LearningSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Update session
    session.end_time = session_data.end_time
    session.words_encountered = session_data.words_encountered
    session.words_used_actively = session_data.words_used_actively
    session.activities_completed = [act.dict() for act in session_data.activities_completed]
    session.engagement_level = session_data.engagement_level
    session.interactions_count = session_data.interactions_count
    
    # Calculate duration
    if session.end_time and session.start_time:
        duration = (session.end_time - session.start_time).total_seconds() / 60
        session.duration_minutes = int(duration)
    
    # Calculate XP earned
    session.xp_earned = len(session.words_encountered) * 10 + session.interactions_count * 5
    
    await db.commit()
    await db.refresh(session)
    
    return session


@router.get("/{child_id}/stats", response_model=ProgressStatsResponse)
async def get_progress_stats(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get overall progress statistics for a child"""
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
    
    # Get word progress stats
    result = await db.execute(
        select(WordProgress).where(WordProgress.child_id == child_id)
    )
    all_progress = result.scalars().all()
    
    mastered_words = sum(1 for p in all_progress if p.mastered)
    total_words = len(all_progress)
    
    # Calculate active vs passive vocabulary
    active_vocab = sum(1 for p in all_progress if p.kinesthetic_exposures > 0)
    passive_vocab = total_words - active_vocab
    
    # TODO: Implement full statistics calculation
    # This is a simplified version
    
    return {
        "total_words": total_words,
        "mastered_words": mastered_words,
        "active_vocabulary": active_vocab,
        "passive_vocabulary": passive_vocab,
        "weekly_progress": [0, 0, 0, 0, 0, 0, 0],  # Placeholder
        "streak_days": child.current_streak,
        "category_progress": [],  # Placeholder
        "average_exposures_per_word": sum(p.exposure_count for p in all_progress) / max(total_words, 1),
        "multi_sensory_engagement": 0.0  # Placeholder
    }
