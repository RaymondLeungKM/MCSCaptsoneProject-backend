"""
Adaptive learning recommendation endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.session import get_db
from app.schemas.analytics import AdaptiveLearningRecommendation, WordOfTheDayResponse
from app.models.user import User, Child
from app.models.vocabulary import Word, WordProgress
from app.core.security import get_current_active_user

router = APIRouter()


def calculate_word_priority(word: Word, progress: WordProgress, child: Child) -> int:
    """Calculate priority score for a word"""
    priority = 0
    
    # Factor 1: Exposure count (needs repetition)
    if not progress:
        priority += 10  # Never seen
    elif progress.exposure_count < 6:
        priority += 10
    elif progress.exposure_count < 12:
        priority += 5
    
    # Factor 2: Not yet mastered
    if not progress or not progress.mastered:
        priority += 7
    
    # Factor 3: Interest alignment (simplified - would need to check child's interests)
    priority += 3
    
    # Factor 4: Low success rate
    if progress and progress.success_rate < 0.7:
        priority += 8
    
    return priority


@router.get("/{child_id}/recommendations", response_model=AdaptiveLearningRecommendation)
async def get_recommendations(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get personalized learning recommendations for a child"""
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
    
    # Get all words
    result = await db.execute(select(Word).where(Word.is_active == True))
    all_words = result.scalars().all()
    
    # Get child's progress on all words
    result = await db.execute(
        select(WordProgress).where(WordProgress.child_id == child_id)
    )
    progress_dict = {p.word_id: p for p in result.scalars().all()}
    
    # Score and rank words
    scored_words = []
    for word in all_words:
        progress = progress_dict.get(word.id)
        score = calculate_word_priority(word, progress, child)
        scored_words.append((word, score))
    
    # Sort by score (highest first)
    scored_words.sort(key=lambda x: x[1], reverse=True)
    
    # Select top 5 words
    next_words = [word.id for word, _ in scored_words[:5]]
    
    # Determine recommended activity based on learning style
    if child.learning_style == "kinesthetic":
        recommended_activity = "game"
        reason = "Kinesthetic learner - games with physical activity recommended"
    elif child.learning_style == "visual":
        recommended_activity = "story"
        reason = "Visual learner - interactive stories recommended"
    else:
        recommended_activity = "mixed"
        reason = "Mixed approach for comprehensive learning"
    
    return {
        "next_words": next_words,
        "recommended_activity": recommended_activity,
        "difficulty": "easy" if child.level < 3 else "medium",
        "reason": reason,
        "estimated_duration": child.attention_span
    }


@router.get("/{child_id}/word-of-the-day", response_model=WordOfTheDayResponse)
async def get_word_of_the_day(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the recommended word of the day for a child"""
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
    
    # Get all words
    result = await db.execute(select(Word).where(Word.is_active == True))
    all_words = result.scalars().all()
    
    # Get child's progress
    result = await db.execute(
        select(WordProgress).where(WordProgress.child_id == child_id)
    )
    progress_dict = {p.word_id: p for p in result.scalars().all()}
    
    # Find highest priority word
    best_word = None
    best_score = -1
    
    for word in all_words:
        progress = progress_dict.get(word.id)
        score = calculate_word_priority(word, progress, child)
        if score > best_score:
            best_score = score
            best_word = word
    
    if not best_word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No suitable word found"
        )
    
    # Generate reason
    progress = progress_dict.get(best_word.id)
    if not progress:
        reason = "New word to learn!"
    elif progress.exposure_count < 6:
        reason = "Needs more practice for retention"
    elif not progress.mastered:
        reason = "Almost mastered - one more push!"
    else:
        reason = "Review time!"
    
    return {
        "word_id": best_word.id,
        "word": best_word.word,
        "reason": reason,
        "priority_score": best_score
    }


@router.get("/{child_id}/next-activity")
async def get_next_activity(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the next recommended activity type for a child"""
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
    
    # Simple recommendation based on learning style
    activity_map = {
        "visual": "story",
        "auditory": "story",
        "kinesthetic": "game",
        "mixed": "game"
    }
    
    recommended = activity_map.get(child.learning_style, "story")
    
    return {
        "recommended_activity": recommended,
        "learning_style": child.learning_style,
        "attention_span": child.attention_span,
        "reason": f"Based on {child.learning_style} learning style"
    }
