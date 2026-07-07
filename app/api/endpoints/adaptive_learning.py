"""
Adaptive learning recommendation endpoints
Phase 8 extensions: knowledge-graph recommendations, spaced repetition,
learning-style assessment, and learning-speed profiling.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import aliased, selectinload
from typing import List

from app.db.session import get_db
from app.schemas.analytics import AdaptiveLearningRecommendation, WordOfTheDayResponse
from app.schemas.word_personalization import (
    WordRelationshipCreate, WordRelationshipResponse,
    WordRelationshipReviewItem, WordRelationshipReviewListResponse,
    WordRelationshipReviewActionResponse,
    WordGraphResponse, GraphRecommendationResponse,
    ReviewQueueResponse, ReviewResultRequest, ReviewResultResponse,
    LearningStyleAssessment, LearningStyleResponse,
)
from app.models.user import User, Child, ChildInterest
from app.models.vocabulary import Word, WordProgress
from app.models.word_personalization import WordRelationship, RelationshipType
from app.core.security import get_current_active_user, get_current_admin_user
from app.services.word_graph_service import (
    get_word_graph, get_graph_recommendations, add_relationship
)
from app.services.spaced_repetition_service import (
    get_review_queue, process_review, get_learning_speed_profile,
    AnkiSRSettings,
)
from app.models.parent_analytics import ParentalControl as ParentalControlModel

router = APIRouter()


def _is_pending_ai_relationship(source: str | None) -> bool:
    normalized = (source or "").strip().lower()
    if not normalized.startswith("ai_"):
        return False
    return "approved" not in normalized and "rejected" not in normalized


def _normalize_learning_style(value: str | None) -> str:
    return value or "mixed"


def _normalize_interest_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _extract_child_interest_keys(child: Child) -> set[str]:
    keys: set[str] = set()

    for interest in child.interests:
        category_id = _normalize_interest_key(interest.category_id)
        if category_id:
            keys.add(category_id)

        category = getattr(interest, "category", None)
        category_name = _normalize_interest_key(
            getattr(category, "name", None) if category is not None else None
        )
        if category_name:
            keys.add(category_name)

        category_name_cantonese = _normalize_interest_key(
            getattr(category, "name_cantonese", None) if category is not None else None
        )
        if category_name_cantonese:
            keys.add(category_name_cantonese)

    return keys


def _style_activity_templates(style: str) -> List[str]:
    return {
        "kinesthetic": [
            "做動作猜謎",
            "實物尋寶",
            "角色扮演",
            "肢體動作遊戲",
        ],
        "visual": [
            "圖像配對遊戲",
            "彩色閃卡",
            "繪本閱讀",
            "繪畫與填色",
        ],
        "auditory": [
            "朗讀故事",
            "兒歌與韻律",
            "聲音配對",
            "口語重複練習",
        ],
        "mixed": [
            "綜合活動",
            "講故事",
            "互動遊戲",
            "美勞創作",
        ],
    }.get(style, ["綜合活動", "講故事", "互動遊戲", "美勞創作"])


def _build_style_explanation(
    child: Child,
    priority_words: List[Word],
    progress_dict: dict[str, WordProgress],
) -> str:
    style = _normalize_learning_style(child.learning_style)
    needs_repetition = 0
    almost_mastered = 0

    for word in priority_words:
        progress = progress_dict.get(word.id)
        if not progress or progress.exposure_count < 6:
            needs_repetition += 1
        elif not progress.mastered:
            almost_mastered += 1

    if style == "kinesthetic":
        return (
            f"{child.name} 目前有 {needs_repetition} 個重點詞彙仍在建立記憶，"
            "配合動作、實物和走動式練習，通常會比單純看卡片更投入。"
        )

    if style == "visual":
        return (
            f"{child.name} 這一輪聚焦的 {len(priority_words)} 個詞彙中，"
            f"有 {needs_repetition} 個適合用圖片、顏色提示和視覺配對去加深印象。"
        )

    if style == "auditory":
        return (
            f"{child.name} 現在的重點詞彙較適合透過聽故事、跟讀和節奏重複來鞏固，"
            f"當中有 {almost_mastered or needs_repetition} 個詞語適合多聽幾次。"
        )

    return (
        f"{child.name} 目前的重點詞彙同時包含新詞和待鞏固詞彙，"
        "交替使用故事、互動遊戲和動手創作，會比單一方式更容易記住。"
    )


def _build_recommendation_reason(
    child: Child,
    priority_words: List[Word],
    progress_dict: dict[str, WordProgress],
    recommended_activity: str,
) -> str:
    needs_repetition = sum(
        1
        for word in priority_words
        if (progress := progress_dict.get(word.id)) is None or progress.exposure_count < 6
    )
    almost_mastered = sum(
        1
        for word in priority_words
        if (progress := progress_dict.get(word.id)) is not None
        and progress.exposure_count >= 6
        and not progress.mastered
    )

    if recommended_activity == "game":
        return (
            f"這次挑出的 {len(priority_words)} 個重點詞彙中，有 {needs_repetition} 個仍需要加強練習，"
            f"先用互動遊戲帶 {child.name} 重複接觸，通常更容易維持投入感。"
        )

    if recommended_activity == "story":
        return (
            f"這次的重點詞彙裡有 {almost_mastered or needs_repetition} 個很適合放進故事情境中重溫，"
            f"讓 {child.name} 先透過圖片和語境理解，再進一步開口使用。"
        )

    return (
        f"目前有 {needs_repetition} 個詞彙需要更多重複接觸，"
        "交替使用多種學習方式可以同時照顧理解、記憶和主動輸出。"
    )


def _build_suggested_activities(
    child: Child,
    priority_words: List[Word],
    progress_dict: dict[str, WordProgress],
) -> List[str]:
    style = _normalize_learning_style(child.learning_style)
    suggestions = list(_style_activity_templates(style))

    needs_repetition = sum(
        1
        for word in priority_words
        if (progress := progress_dict.get(word.id)) is None or progress.exposure_count < 6
    )
    has_physical_action = any(word.physical_action for word in priority_words)
    has_almost_mastered = any(
        (progress := progress_dict.get(word.id)) is not None
        and progress.exposure_count >= 6
        and not progress.mastered
        for word in priority_words
    )

    if needs_repetition >= 3:
        if style == "visual":
            suggestions.insert(0, "圖片配對重複練習")
        elif style == "auditory":
            suggestions.insert(0, "慢速跟讀與節奏複誦")
        elif style == "kinesthetic":
            suggestions.insert(0, "走動式重複練習")
        else:
            suggestions.insert(0, "綜合主題小任務")

    if has_physical_action:
        suggestions.insert(1, "做動作猜謎")

    if has_almost_mastered:
        suggestions.append("生活情境對話")

    unique_suggestions: List[str] = []
    for suggestion in suggestions:
        if suggestion not in unique_suggestions:
            unique_suggestions.append(suggestion)

    return unique_suggestions[:4]


def _build_next_activity_reason(child: Child) -> str:
    style = _normalize_learning_style(child.learning_style)
    if style == "visual":
        return "根據目前的視覺學習偏好，先用故事和圖片進入主題會更容易吸收。"
    if style == "auditory":
        return "根據目前的聽覺學習偏好，先聽故事和跟讀會更自然。"
    if style == "kinesthetic":
        return "根據目前的動作學習偏好，先玩互動遊戲會更投入。"
    return "根據目前的混合學習偏好，先從互動練習開始，再切換故事或創作會更合適。"


def calculate_word_priority(
    word: Word,
    progress: WordProgress,
    child: Child,
    interest_keys: set[str],
) -> int:
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
    
    # Factor 3: Interest alignment
    word_category_key = _normalize_interest_key(word.category)
    if interest_keys and word_category_key in interest_keys:
        priority += 8
    
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
        select(Child)
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
        .where(Child.id == child_id, Child.parent_id == current_user.id)
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
    interest_keys = _extract_child_interest_keys(child)
    
    # Score and rank words
    scored_words = []
    for word in all_words:
        progress = progress_dict.get(word.id)
        score = calculate_word_priority(word, progress, child, interest_keys)
        scored_words.append((word, score))
    
    # Sort by score (highest first)
    scored_words.sort(key=lambda x: x[1], reverse=True)
    
    # Select top 5 words
    priority_words = [word for word, _ in scored_words[:5]]
    next_words = [word.id for word in priority_words]
    
    # Determine recommended activity based on learning style
    learning_style = _normalize_learning_style(child.learning_style)

    if learning_style == "kinesthetic":
        recommended_activity = "game"
    elif learning_style == "visual":
        recommended_activity = "story"
    elif learning_style == "auditory":
        recommended_activity = "story"
    else:
        recommended_activity = "mixed"

    reason = _build_recommendation_reason(
        child,
        priority_words,
        progress_dict,
        recommended_activity,
    )
    style_explanation = _build_style_explanation(
        child,
        priority_words,
        progress_dict,
    )
    suggested_activities = _build_suggested_activities(
        child,
        priority_words,
        progress_dict,
    )
    
    return {
        "next_words": next_words,
        "recommended_activity": recommended_activity,
        "difficulty": "easy" if child.level < 3 else "medium",
        "reason": reason,
        "estimated_duration": child.attention_span,
        "learning_style": learning_style,
        "style_explanation": style_explanation,
        "suggested_activities": suggested_activities,
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
        select(Child)
        .options(selectinload(Child.interests).selectinload(ChildInterest.category))
        .where(Child.id == child_id, Child.parent_id == current_user.id)
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
    interest_keys = _extract_child_interest_keys(child)
    
    # Find highest priority word
    best_word = None
    best_score = -1
    
    for word in all_words:
        progress = progress_dict.get(word.id)
        score = calculate_word_priority(word, progress, child, interest_keys)
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
        reason = "這是今天很適合開始學的新詞語。"
    elif progress.exposure_count < 6:
        reason = "這個詞語還需要多練習幾次，會更容易記住。"
    elif not progress.mastered:
        reason = "差一點就完全掌握了，再努力一次。"
    else:
        reason = "現在很適合重溫這個詞語。"
    
    return {
        "word_id": best_word.id,
        "word": best_word.word,
        "word_cantonese": best_word.word_cantonese,
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
        "reason": _build_next_activity_reason(child)
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


@router.get(
    "/admin/word-relationships/pending",
    response_model=WordRelationshipReviewListResponse,
    summary="List pending AI-generated word relationships for admin review",
)
async def list_pending_word_relationship_reviews(
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user  # authentication is enforced by dependency

    max_limit = max(1, min(limit, 300))
    source_filters = [
        WordRelationship.source.ilike("ai_%"),
    ]
    exclusion_filters = [
        WordRelationship.source.ilike("%approved%"),
        WordRelationship.source.ilike("%rejected%"),
    ]

    total_result = await db.execute(
        select(func.count())
        .select_from(WordRelationship)
        .where(or_(*source_filters))
        .where(~or_(*exclusion_filters))
    )
    total_pending = int(total_result.scalar() or 0)

    source_word = aliased(Word)
    related_word = aliased(Word)

    rows_result = await db.execute(
        select(
            WordRelationship,
            source_word.word,
            source_word.word_cantonese,
            related_word.word,
            related_word.word_cantonese,
        )
        .join(source_word, source_word.id == WordRelationship.word_id)
        .join(related_word, related_word.id == WordRelationship.related_word_id)
        .where(or_(*source_filters))
        .where(~or_(*exclusion_filters))
        .order_by(WordRelationship.created_at.desc(), WordRelationship.id.desc())
        .limit(max_limit)
    )

    items: list[WordRelationshipReviewItem] = []
    for rel, word, word_cantonese, related, related_cantonese in rows_result.all():
        if not _is_pending_ai_relationship(rel.source):
            continue
        items.append(
            WordRelationshipReviewItem(
                id=rel.id,
                word_id=rel.word_id,
                word=word,
                word_cantonese=word_cantonese,
                related_word_id=rel.related_word_id,
                related_word=related,
                related_word_cantonese=related_cantonese,
                relationship_type=rel.relationship_type,
                strength=rel.strength,
                source=rel.source,
                created_at=rel.created_at,
            )
        )

    return WordRelationshipReviewListResponse(
        items=items,
        total_pending=total_pending,
        limit=max_limit,
    )


@router.post(
    "/admin/word-relationships/{relationship_id}/approve",
    response_model=WordRelationshipReviewActionResponse,
    summary="Approve an AI-generated relationship",
)
async def approve_pending_word_relationship(
    relationship_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WordRelationship).where(WordRelationship.id == relationship_id)
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    if not _is_pending_ai_relationship(rel.source):
        raise HTTPException(
            status_code=400,
            detail="This relationship is not pending AI review",
        )

    rel.source = f"ai_approved:{current_user.id}"
    await db.commit()

    return WordRelationshipReviewActionResponse(
        id=relationship_id,
        action="approved",
        success=True,
    )


@router.post(
    "/admin/word-relationships/{relationship_id}/reject",
    response_model=WordRelationshipReviewActionResponse,
    summary="Reject an AI-generated relationship",
)
async def reject_pending_word_relationship(
    relationship_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user  # authentication is enforced by dependency

    result = await db.execute(
        select(WordRelationship).where(WordRelationship.id == relationship_id)
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    if not _is_pending_ai_relationship(rel.source):
        raise HTTPException(
            status_code=400,
            detail="This relationship is not pending AI review",
        )

    reverse_result = await db.execute(
        select(WordRelationship).where(
            WordRelationship.word_id == rel.related_word_id,
            WordRelationship.related_word_id == rel.word_id,
            WordRelationship.relationship_type == rel.relationship_type,
        )
    )
    reverse = reverse_result.scalar_one_or_none()

    await db.delete(rel)
    if reverse and _is_pending_ai_relationship(reverse.source):
        await db.delete(reverse)
    await db.commit()

    return WordRelationshipReviewActionResponse(
        id=relationship_id,
        action="rejected",
        success=True,
    )


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

    # Load parent-configured Anki SM-2 settings (falls back to defaults if not set).
    ctrl_result = await db.execute(
        select(ParentalControlModel).where(ParentalControlModel.child_id == child_id)
    )
    ctrl = ctrl_result.scalar_one_or_none()
    sr_settings = AnkiSRSettings(
        easy_bonus          = getattr(ctrl, 'sr_easy_bonus',          1.3)    if ctrl else 1.3,
        interval_modifier   = getattr(ctrl, 'sr_interval_modifier',   1.0)    if ctrl else 1.0,
        max_interval_days   = getattr(ctrl, 'sr_max_interval_days',   36500)  if ctrl else 36500,
        graduating_interval = getattr(ctrl, 'sr_graduating_interval', 1)      if ctrl else 1,
        easy_interval       = getattr(ctrl, 'sr_easy_interval',       4)      if ctrl else 4,
        lapse_interval_pct  = getattr(ctrl, 'sr_lapse_interval_pct',  0.0)    if ctrl else 0.0,
    )

    return await process_review(db, child_id, payload.word_id, payload.quality, sr_settings)


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
