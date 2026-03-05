"""
Adaptive learning recommendation endpoints
Phase 8 extensions: knowledge-graph recommendations, spaced repetition,
learning-style assessment, and learning-speed profiling.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.session import get_db
from app.schemas.analytics import AdaptiveLearningRecommendation, WordOfTheDayResponse
from app.schemas.phase8 import (
    WordRelationshipCreate, WordRelationshipResponse,
    WordGraphResponse, GraphRecommendationResponse,
    ReviewQueueResponse, ReviewResultRequest, ReviewResultResponse,
    LearningStyleAssessment, LearningStyleResponse,
)
from app.models.user import User, Child
from app.models.vocabulary import Word, WordProgress
from app.models.phase8 import WordRelationship, RelationshipType
from app.core.security import get_current_active_user
from app.services.word_graph_service import (
    get_word_graph, get_graph_recommendations, add_relationship
)
from app.services.spaced_repetition_service import (
    get_review_queue, process_review, get_learning_speed_profile
)

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


# ---------------------------------------------------------------------------
# Phase 8 – Epic 8.1: Knowledge Graph endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{child_id}/word-graph/{word_id}",
    response_model=WordGraphResponse,
    summary="Get word knowledge sub-graph",
)
async def get_word_knowledge_graph(
    child_id: str,
    word_id: str,
    depth: int = 1,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the neighbourhood of *word_id* in the vocabulary knowledge graph.
    ``depth=1`` returns direct neighbours; ``depth=2`` extends one hop further.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    return await get_word_graph(db, word_id, child_id, depth=max(1, min(depth, 2)))


@router.get(
    "/{child_id}/graph-recommendations",
    response_model=GraphRecommendationResponse,
    summary="Get graph-based vocabulary recommendations",
)
async def get_vocabulary_graph_recommendations(
    child_id: str,
    limit: int = 5,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Walk the knowledge graph from the child's current vocabulary and recommend
    highly-connected unmastered words.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    return await get_graph_recommendations(db, child_id, limit=limit)


@router.post(
    "/word-relationships",
    response_model=WordRelationshipResponse,
    status_code=201,
    summary="Add a word relationship (admin / AI pipeline use)",
)
async def create_word_relationship(
    payload: WordRelationshipCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Insert a directed edge into the vocabulary knowledge graph.
    A reverse edge is automatically inserted for symmetric relationships.
    """
    await add_relationship(
        db,
        payload.word_id,
        payload.related_word_id,
        RelationshipType(payload.relationship_type),
        payload.strength,
        source=str(current_user.id),
        bidirectional=True,
    )
    # Return the newly created (or existing) edge
    result = await db.execute(
        select(WordRelationship).where(
            WordRelationship.word_id == payload.word_id,
            WordRelationship.related_word_id == payload.related_word_id,
        )
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=500, detail="Failed to create relationship")
    return rel


# ---------------------------------------------------------------------------
# Phase 8 – Epic 8.2: Spaced Repetition endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{child_id}/review-queue",
    response_model=ReviewQueueResponse,
    summary="Get spaced-repetition review queue",
)
async def get_sr_review_queue(
    child_id: str,
    max_cards: int = 20,
    max_new: int = 5,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all vocabulary cards due for SM-2 review today, plus up to
    *max_new* newly-introduced cards.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    return await get_review_queue(db, child_id, max_cards=max_cards, max_new=max_new)


@router.post(
    "/{child_id}/review",
    response_model=ReviewResultResponse,
    summary="Submit a spaced-repetition review result",
)
async def submit_review_result(
    child_id: str,
    payload: ReviewResultRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply the SM-2 algorithm to a reviewed card.
    The client submits a quality rating (0-5) and receives the new schedule.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    return await process_review(db, child_id, payload.word_id, payload.quality)


@router.get(
    "/{child_id}/learning-speed",
    summary="Get child's learning speed profile",
)
async def get_child_learning_speed(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a summary of the child's SM-2 statistics: average EF, average
    interval, graduation rate, and a plain-language assessment.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    return await get_learning_speed_profile(db, child_id)


# ---------------------------------------------------------------------------
# Phase 8 – Epic 8.2.3: Learning Style Detection endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/{child_id}/learning-style",
    response_model=LearningStyleResponse,
    summary="Update child learning style from observed session data",
)
async def update_learning_style(
    child_id: str,
    payload: LearningStyleAssessment,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    The frontend sends aggregated engagement scores per style dimension.
    The highest score wins; the child record is updated and the new style
    is returned with a confidence measure.
    """
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    scores = {
        "kinesthetic": payload.kinesthetic_score,
        "visual":      payload.visual_score,
        "auditory":    payload.auditory_score,
    }
    best_style     = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score     = scores[best_style]
    second_best    = sorted(scores.values(), reverse=True)[1]
    confidence     = best_score - second_best  # rough margin

    # Update child record
    child.learning_style = best_style  # type: ignore[assignment]
    await db.commit()

    explanations = {
        "visual":      "透過視覺（圖片、卡片、配對遊戲）學習效果最佳",
        "auditory":    "透過聆聽（故事、發音、音樂）學習效果最佳",
        "kinesthetic": "透過活動（肢體動作、遊戲、尋寶）學習效果最佳",
    }

    return LearningStyleResponse(
        child_id=child_id,
        learning_style=best_style,
        confidence=round(confidence, 3),
        explanation=explanations.get(best_style, "混合學習方式"),
    )
