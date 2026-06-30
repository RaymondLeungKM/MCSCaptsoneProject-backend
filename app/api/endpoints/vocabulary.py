"""
Vocabulary word endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict
import uuid
from datetime import datetime
from pathlib import Path
import aiofiles
import os
import json
import re

from app.db.session import get_db, AsyncSessionLocal
from app.schemas.vocabulary import (
    AdminWordResponse,
    WordCreate, 
    WordUpdate, 
    WordResponse, 
    WordWithProgress,
    WordProgressResponse,
    WordProgressUpdate,
    ActiveVocabularyApprovalRequestResponse,
    ExternalWordLearning,
    ExternalWordLearningResponse
)
from app.models.vocabulary import Word, WordProgress, Category
from app.models.daily_words import DailyWordTracking
from app.models.generated_sentences import GeneratedSentence as GeneratedSentenceModel
from app.models.user import User, Child
from app.core.security import get_current_active_user, get_current_admin_user
from app.core.category_colors import get_category_color
from app.core.config import settings
from app.services.sentence_generator import get_sentence_generator, SentenceGenerationResult
from app.services.word_enhancement_service import (
    RelatedWordSuggestion,
    get_word_enhancement_service,
)
from app.services.word_embedding_service import get_word_embedding_service
from app.services.word_graph_service import add_relationship
from app.models.word_personalization import RelationshipType

router = APIRouter()

ACTIVE_VOCAB_REQUEST_MIN_EXPOSURES = 6

UNSAFE_CHILD_VOCAB_TOKENS = {
    "knife",
    "scissors",
    "fork",
    "wok",
    "oven",
    "cuttingboard",
    "candle",
    "weapon",
    "gun",
    "sword",
    "bomb",
    "grenade",
    "axe",
    "刀",
    "剪刀",
    "叉",
    "鑊",
    "焗爐",
    "砧板",
    "蠟燭",
    "武器",
    "槍",
    "劍",
    "炸彈",
    "手榴彈",
    "斧頭",
}


def _normalize_vocab_token(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(
        ch for ch in value.strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
    )


def _is_child_safe_word_fields(
    word: Optional[str],
    word_cantonese: Optional[str],
) -> bool:
    return (
        _normalize_vocab_token(word) not in UNSAFE_CHILD_VOCAB_TOKENS
        and _normalize_vocab_token(word_cantonese) not in UNSAFE_CHILD_VOCAB_TOKENS
    )


def _is_child_safe_word_record(word: Word) -> bool:
    return _is_child_safe_word_fields(word.word, word.word_cantonese)


def _is_child_safe_word_payload(payload: dict) -> bool:
    return _is_child_safe_word_fields(
        payload.get("word"),
        payload.get("word_cantonese"),
    )


def _humanize_learning_source(source: str) -> str:
    normalized = (source or "external_learning").strip().replace("_", " ")
    return normalized or "external learning"


def _build_external_placeholder_content(word: str, source: str) -> dict[str, Optional[str]]:
    normalized_word = (word or "").strip()
    display_word = normalized_word.capitalize() if normalized_word else "Word"
    source_label = _humanize_learning_source(source)
    example_word = normalized_word.lower() if normalized_word else "word"

    return {
        "word": display_word,
        "word_cantonese": None,
        "jyutping": None,
        "definition": f"A word learned from {source_label}",
        "definition_cantonese": f"透過{source_label}學識嘅詞語",
        "example": f"I learned {example_word} from {source_label}.",
        "example_cantonese": f"我透過{source_label}學識咗{display_word}。",
    }


def _normalize_relationship_lookup_value(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(
        ch for ch in value.strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
    )


def _extract_relationship_tokens(*values: Optional[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue

        text = str(value).strip().lower()
        normalized = _normalize_relationship_lookup_value(text)
        if normalized:
            tokens.add(normalized)

        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text):
            if len(token) >= 2 or any("\u4e00" <= ch <= "\u9fff" for ch in token):
                tokens.add(token)

    return tokens


def _extract_relationship_contexts(word: Word) -> set[str]:
    contexts = getattr(word, "contexts", None) or []
    if not isinstance(contexts, list):
        return set()
    return {
        _normalize_relationship_lookup_value(context)
        for context in contexts
        if _normalize_relationship_lookup_value(context)
    }


def _rank_relationship_candidates(
    *,
    current_word: Word,
    catalog_words: List[Word],
    limit: int = 30,
) -> list[Word]:
    current_contexts = _extract_relationship_contexts(current_word)
    current_tokens = _extract_relationship_tokens(
        current_word.word,
        current_word.word_cantonese,
        getattr(current_word, "definition", None),
        getattr(current_word, "definition_cantonese", None),
        getattr(current_word, "physical_action", None),
        *list(getattr(current_word, "contexts", None) or []),
    )
    current_related_ids = set(getattr(current_word, "related_words", None) or [])

    ranked: list[tuple[float, int, float, str, Word]] = []
    for candidate in catalog_words:
        if candidate.id == current_word.id or not candidate.word:
            continue

        score = 0.0
        if candidate.category == current_word.category:
            score += 6.0

        candidate_contexts = _extract_relationship_contexts(candidate)
        shared_contexts = current_contexts & candidate_contexts
        score += min(len(shared_contexts), 3) * 1.5

        candidate_tokens = _extract_relationship_tokens(
            candidate.word,
            candidate.word_cantonese,
            getattr(candidate, "definition", None),
            getattr(candidate, "definition_cantonese", None),
            getattr(candidate, "physical_action", None),
            *list(getattr(candidate, "contexts", None) or []),
        )
        shared_tokens = current_tokens & candidate_tokens
        score += min(len(shared_tokens), 4) * 0.75

        candidate_related_ids = set(getattr(candidate, "related_words", None) or [])
        if candidate.id in current_related_ids or current_word.id in candidate_related_ids:
            score += 2.0

        if getattr(candidate, "created_by_child_id", None) is None:
            score += 0.25

        exposure_score = min(float(getattr(candidate, "total_exposures", 0) or 0.0), 20.0) / 20.0
        score += exposure_score

        ranked.append(
            (
                score,
                1 if getattr(candidate, "created_by_child_id", None) is not None else 0,
                exposure_score,
                candidate.word.lower(),
                candidate,
            )
        )

    ranked.sort(key=lambda item: (-item[0], item[1], -item[2], item[3]))
    return [candidate for _, _, _, _, candidate in ranked[:limit]]


def _build_relationship_candidate_payload(words: List[Word], limit: int = 30) -> list[dict[str, str]]:
    return [
        {
            "word": candidate.word,
            "word_cantonese": candidate.word_cantonese or "",
            "category": candidate.category or "",
            "contexts": ", ".join(
                str(context).strip()
                for context in (candidate.contexts or [])[:3]
                if str(context).strip()
            ),
        }
        for candidate in words[:limit]
        if candidate.word
    ]


def _resolve_related_word_matches(
    *,
    current_word: Word,
    catalog_words: List[Word],
    suggestions: List[RelatedWordSuggestion],
) -> list[tuple[Word, str, float]]:
    lookup: dict[str, Word] = {}
    for candidate in catalog_words:
        if candidate.id == current_word.id:
            continue

        english_key = _normalize_relationship_lookup_value(candidate.word)
        cantonese_key = _normalize_relationship_lookup_value(candidate.word_cantonese)
        if english_key and english_key not in lookup:
            lookup[english_key] = candidate
        if cantonese_key and cantonese_key not in lookup:
            lookup[cantonese_key] = candidate

    resolved: list[tuple[Word, str, float]] = []
    seen_word_ids: set[str] = set()
    for suggestion in suggestions:
        lookup_key = _normalize_relationship_lookup_value(suggestion.word)
        if not lookup_key:
            continue

        candidate = lookup.get(lookup_key)
        if not candidate or candidate.id in seen_word_ids:
            continue

        resolved.append(
            (
                candidate,
                suggestion.relationship_type,
                max(0.0, min(1.0, suggestion.strength)),
            )
        )
        seen_word_ids.add(candidate.id)

    return resolved


async def _attach_ai_relationship_suggestions(
    *,
    db: AsyncSession,
    word: Word,
    enhancement_service=None,
) -> int:
    enhancement_service = enhancement_service or get_word_enhancement_service()
    embedding_service = get_word_embedding_service()

    candidate_result = await db.execute(
        select(Word).where(
            Word.is_active == True,
            Word.id != word.id,
        )
    )
    catalog_words = candidate_result.scalars().all()
    if not catalog_words:
        return 0

    try:
        candidate_pool = await embedding_service.find_similar_words(
            db,
            current_word=word,
            catalog_words=catalog_words,
            limit=30,
        )
    except Exception as exc:
        print(f"[WordEmbedding] Semantic retrieval failed for {word.word}: {exc}")
        candidate_pool = []

    if not candidate_pool:
        candidate_pool = _rank_relationship_candidates(
            current_word=word,
            catalog_words=catalog_words,
            limit=30,
        )
    if not candidate_pool:
        return 0

    suggestions = await enhancement_service.suggest_related_words(
        word=word.word,
        word_cantonese=word.word_cantonese,
        category=word.category,
        candidate_words=_build_relationship_candidate_payload(candidate_pool, limit=30),
    )
    resolved_matches = _resolve_related_word_matches(
        current_word=word,
        catalog_words=candidate_pool,
        suggestions=suggestions,
    )
    if not resolved_matches:
        return 0

    existing_related_ids = list(word.related_words or [])
    related_ids = list(existing_related_ids)

    for matched_word, relationship_type, strength in resolved_matches:
        await add_relationship(
            db,
            word.id,
            matched_word.id,
            RelationshipType(relationship_type),
            strength=strength,
            source="ai_generated",
            bidirectional=True,
        )
        if matched_word.id not in related_ids:
            related_ids.append(matched_word.id)

    if related_ids != existing_related_ids:
        word.related_words = related_ids
        await db.commit()

    return len(resolved_matches)


def _build_captured_word_response(
    word: Word,
    captured_at: Optional[datetime] = None,
) -> dict:
    word_dict = WordResponse.model_validate(word).model_dump()
    word_dict["category_name"] = word.category_rel.name if word.category_rel else None
    word_dict["category_name_cantonese"] = word.category_rel.name_cantonese if word.category_rel else None
    if captured_at is not None:
        word_dict["created_at"] = captured_at
    return word_dict


def _merge_captured_word_payloads(
    tracked_words: List[dict],
    owned_words: List[dict],
    limit: int,
) -> List[dict]:
    combined: dict[str, dict] = {}

    for payload in tracked_words + owned_words:
        combined.setdefault(str(payload["id"]), payload)

    return sorted(
        combined.values(),
        key=lambda payload: payload["created_at"],
        reverse=True,
    )[:limit]


async def _get_category_or_404(category_id: str, db: AsyncSession) -> Category:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return category


async def _ensure_admin_editable_word(word_id: str, db: AsyncSession) -> Word:
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()

    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )

    if word.created_by_child_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Words from "My Collection" cannot be edited in the admin panel',
        )

    return word


async def _recount_category_word_count(category_id: str, db: AsyncSession) -> None:
    count_result = await db.execute(
        select(func.count())
        .select_from(Word)
        .where(Word.category == category_id, Word.is_active == True)
    )
    category = await _get_category_or_404(category_id, db)
    category.word_count = count_result.scalar_one()


def _mongo_to_word_response(doc: dict, child_id: str) -> dict:
    """Convert MongoDB camera-capture document into WordResponse-compatible payload."""
    word = (doc.get("word") or doc.get("label") or doc.get("detected_word") or "Object").strip()
    word_cantonese = (doc.get("word_cantonese") or doc.get("label_cantonese") or doc.get("word_zh") or None)
    image_url = doc.get("image_url") or doc.get("imageUrl") or doc.get("image_path")
    source = doc.get("source") or "object_detection"
    category = doc.get("category") or "general"
    created_at = doc.get("timestamp") or doc.get("created_at") or datetime.utcnow()

    # Ensure created_at is datetime
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = datetime.utcnow()

    return {
        "id": f"mongo-{str(doc.get('_id', uuid.uuid4()))}",
        "word": word,
        "word_cantonese": word_cantonese,
        "jyutping": doc.get("jyutping"),
        "category": category,
        "category_name": category,
        "category_name_cantonese": doc.get("category_cantonese"),
        "pronunciation": doc.get("pronunciation"),
        "definition": doc.get("definition") or f"Word captured from camera ({source})",
        "definition_cantonese": doc.get("definition_cantonese"),
        "example": doc.get("example") or f"I saw a {word.lower()}.",
        "example_cantonese": doc.get("example_cantonese"),
        "difficulty": (doc.get("difficulty") or "easy").lower(),
        "physical_action": doc.get("physical_action"),
        "image_url": image_url,
        "audio_url": doc.get("audio_url"),
        "audio_url_english": doc.get("audio_url_english"),
        "contexts": doc.get("contexts") or [source],
        "related_words": doc.get("related_words") or [],
        "total_exposures": int(doc.get("total_exposures") or doc.get("exposure_count") or 1),
        "success_rate": float(doc.get("success_rate") or 1.0),
        "is_active": bool(doc.get("is_active", True)),
        "created_at": created_at,
        "created_by_child_id": child_id,
    }


async def _fetch_mongo_captured_words(child_id: str, limit: int) -> List[dict]:
    """Fetch camera-captured words from MongoDB when configured."""
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        return []

    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        # pymongo not installed - return gracefully
        return []

    docs: List[dict] = []
    client = None
    try:
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
        collection = client[settings.MONGODB_DATABASE][settings.MONGODB_CAMERA_COLLECTION]

        cursor = (
            collection.find({"child_id": child_id})
            .sort("timestamp", -1)
            .limit(limit)
        )
        docs = list(cursor)
    except Exception as e:
        print(f"[Mongo Capture] Failed to read MongoDB captures: {e}")
        docs = []
    finally:
        if client:
            client.close()

    return [_mongo_to_word_response(doc, child_id) for doc in docs]


@router.get("/external/captured/{child_id}", response_model=List[WordResponse])
async def get_external_captured_words(
    child_id: str,
    limit: int = Query(50, ge=1, le=200),
    include_mongodb: bool = Query(False, description="Merge camera captures from MongoDB if configured"),
    db: AsyncSession = Depends(get_db),
):
    """Get camera-captured/user-uploaded words for a child (PostgreSQL + optional MongoDB)."""
    # Verify child exists
    child_result = await db.execute(select(Child).where(Child.id == child_id))
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Child not found: {child_id}",
        )

    tracked_subquery = (
        select(
            DailyWordTracking.word_id.label("word_id"),
            func.max(DailyWordTracking.date).label("captured_at"),
        )
        .where(
            DailyWordTracking.child_id == child_id,
            DailyWordTracking.learned_context.contains({"source": "external_word_learning"}),
        )
        .group_by(DailyWordTracking.word_id)
        .subquery()
    )

    tracked_query = (
        select(Word, tracked_subquery.c.captured_at)
        .options(selectinload(Word.category_rel))
        .join(tracked_subquery, tracked_subquery.c.word_id == Word.id)
        .where(Word.is_active == True)
        .order_by(tracked_subquery.c.captured_at.desc())
        .limit(limit)
    )
    tracked_result = await db.execute(tracked_query)
    tracked_words = [
        _build_captured_word_response(word, captured_at)
        for word, captured_at in tracked_result.all()
    ]

    owned_query = (
        select(Word)
        .options(selectinload(Word.category_rel))
        .where(Word.is_active == True, Word.created_by_child_id == child_id)
        .order_by(Word.created_at.desc())
        .limit(limit)
    )
    owned_result = await db.execute(owned_query)
    owned_words = [
        _build_captured_word_response(word)
        for word in owned_result.scalars().all()
    ]

    response_words = _merge_captured_word_payloads(tracked_words, owned_words, limit)

    if include_mongodb:
        mongo_words = await _fetch_mongo_captured_words(child_id=child_id, limit=limit)

        # Dedupe by normalized word text + image URL; keep SQL rows first
        seen = {
            f"{(w.get('word') or '').strip().lower()}|{w.get('image_url') or ''}"
            for w in response_words
        }
        for mw in mongo_words:
            key = f"{(mw.get('word') or '').strip().lower()}|{mw.get('image_url') or ''}"
            if key not in seen:
                response_words.append(mw)
                seen.add(key)

    return response_words[:limit]


@router.get("/community", response_model=List[WordResponse])
async def get_community_words(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return recent camera-captured words from children with community sharing enabled.
    
    child_id is intentionally omitted from the response to protect child privacy.
    """
    # Join Word → Child; filter on community_sharing_enabled
    query = (
        select(Word)
        .join(Child, Word.created_by_child_id == Child.id)
        .options(selectinload(Word.category_rel))
        .where(
            Word.is_active == True,
            Word.created_by_child_id.isnot(None),
            Child.community_sharing_enabled == True,
        )
        .order_by(Word.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    words = [word for word in result.scalars().all() if _is_child_safe_word_record(word)]

    response = []
    for word in words:
        word_dict = WordResponse.model_validate(word).model_dump()
        word_dict["category_name"] = word.category_rel.name if word.category_rel else None
        word_dict["category_name_cantonese"] = word.category_rel.name_cantonese if word.category_rel else None
        # Anonymise — do not expose which child captured this word
        word_dict["created_by_child_id"] = None
        response.append(word_dict)

    return response


# Background task for sentence generation
async def generate_sentences_background(word_id: str, word_text: str):
    """
    Background task to generate AI sentences for a word without blocking the API response.
    This runs asynchronously after the API returns success to the user.
    """
    try:
        print(f"[Background Task] Starting sentence generation for word: {word_text} (ID: {word_id})")
        
        # Create a new database session for the background task
        async with AsyncSessionLocal() as db:
            # Fetch the word with category relationship
            result = await db.execute(
                select(Word).options(selectinload(Word.category_rel)).where(Word.id == word_id)
            )
            word = result.scalar_one_or_none()
            
            if not word:
                print(f"[Background Task] ERROR: Word not found: {word_id}")
                return
            
            # Generate sentences
            generator = get_sentence_generator()
            await generator.generate_sentences(
                word=word,
                num_sentences=3,
                contexts=["home", "school"],
                db=db,
                save_to_db=True
            )
            
            print(f"[Background Task] ✓ Successfully generated and saved sentences for: {word_text}")
            
    except Exception as e:
        print(f"[Background Task] ERROR generating sentences for {word_text}: {e}")
        import traceback
        traceback.print_exc()


async def enhance_word_and_generate_sentences_background(
    word_id: str,
    word_text: str,
    source: str,
    image_url: Optional[str],
):
    """
    Background task that fills in AI-enhanced bilingual content for a placeholder word
    and only then generates example sentences.
    """
    try:
        print(f"[Background Task] Starting AI enhancement for word: {word_text} (ID: {word_id})")

        enhancement_service = get_word_enhancement_service()
        enhanced_content = await enhancement_service.enhance_word(
            word=word_text,
            source=source,
            image_url=image_url,
        )

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Word).where(Word.id == word_id))
            word = result.scalar_one_or_none()

            if not word:
                print(f"[Background Task] ERROR: Word not found for enhancement: {word_id}")
                return

            word.word = enhanced_content.word_english.capitalize()
            word.word_cantonese = enhanced_content.word_cantonese
            word.definition = enhanced_content.definition_english
            word.definition_cantonese = enhanced_content.definition_cantonese
            word.example = enhanced_content.example_english
            word.example_cantonese = enhanced_content.example_cantonese
            word.difficulty = enhanced_content.difficulty

            if image_url and not word.image_url:
                word.image_url = image_url

            await db.commit()
            linked_count = await _attach_ai_relationship_suggestions(
                db=db,
                word=word,
                enhancement_service=enhancement_service,
            )
            if linked_count:
                print(
                    f"[Background Task] ✓ Added {linked_count} AI graph relationships for: {word.word}"
                )

        print(f"[Background Task] ✓ AI enhancement completed for: {word_text}")

    except Exception as e:
        print(f"[Background Task] ERROR enhancing word {word_text}: {e}")
        import traceback
        traceback.print_exc()

    await generate_sentences_background(word_id=word_id, word_text=word_text)


async def enrich_word_relationships_background(word_id: str):
    """Background task to attach AI-suggested graph relationships to an existing word."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Word).where(Word.id == word_id))
            word = result.scalar_one_or_none()
            if not word or not word.is_active:
                return

            linked_count = await _attach_ai_relationship_suggestions(db=db, word=word)
            print(
                f"[Background Task] Relationship enrichment for {word.word}: {linked_count} link(s) added"
            )
    except Exception as e:
        print(f"[Background Task] ERROR enriching graph relationships for {word_id}: {e}")
        import traceback
        traceback.print_exc()


@router.get("/", response_model=List[WordResponse])
async def get_words(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    child_id: Optional[str] = None,
    include_external: bool = Query(True, description="Include child uploaded/captured words when child_id is provided"),
    include_mongodb: bool = Query(False, description="Merge camera captures from MongoDB when child_id is provided"),
    limit: int = Query(50, le=250),
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Get list of words with optional filters"""
    query = select(Word).options(selectinload(Word.category_rel)).where(Word.is_active == True)

    # Only return words that belong to an ACTIVE category, so hidden categories
    # (e.g. deactivated Colors/Family/Places, or the junk 'general') never leak
    # into the learning page or the games.
    query = query.join(Category, Word.category == Category.id).where(Category.is_active == True)

    # By default, keep system words; when child_id provided, optionally include child's external words too.
    if child_id and include_external:
        from sqlalchemy import or_
        query = query.where(
            or_(
                Word.created_by_child_id.is_(None),
                Word.created_by_child_id == child_id,
            )
        )
    else:
        query = query.where(Word.created_by_child_id.is_(None))
    
    if category:
        query = query.where(Word.category == category)
    if difficulty:
        query = query.where(Word.difficulty == difficulty)
    
    # Prefer child-specific words first when child_id is provided.
    if child_id and include_external:
        query = query.order_by(Word.created_by_child_id.desc().nullslast(), Word.created_at.desc())
    else:
        query = query.order_by(Word.created_at.desc())

    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    words = [word for word in result.scalars().all() if _is_child_safe_word_record(word)]
    
    # Add category name to each word
    response_words = []
    for word in words:
        word_dict = WordResponse.model_validate(word).model_dump()
        word_dict['category_name'] = word.category_rel.name if word.category_rel else None
        word_dict['category_name_cantonese'] = word.category_rel.name_cantonese if word.category_rel else None
        response_words.append(word_dict)
    
    if child_id and include_mongodb:
        mongo_words = await _fetch_mongo_captured_words(child_id=child_id, limit=limit)
        seen = {
            f"{(w.get('word') or '').strip().lower()}|{w.get('image_url') or ''}"
            for w in response_words
        }
        for mw in mongo_words:
            if not _is_child_safe_word_payload(mw):
                continue
            key = f"{(mw.get('word') or '').strip().lower()}|{mw.get('image_url') or ''}"
            if key not in seen:
                response_words.append(mw)
                seen.add(key)

    return response_words[:limit]


@router.get("/admin/all", response_model=List[AdminWordResponse])
async def get_admin_words(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    creator_search: Optional[str] = Query(
        None,
        description="Filter My Collection words by creator user ID or email",
    ),
    limit: int = Query(250, ge=1, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get admin vocabulary list, including My Collection words and creator metadata."""
    query = (
        select(
            Word,
            Child.name.label("creator_child_name"),
            User.id.label("creator_user_id"),
            User.email.label("creator_user_email"),
        )
        .outerjoin(Child, Word.created_by_child_id == Child.id)
        .outerjoin(User, Child.parent_id == User.id)
        .options(selectinload(Word.category_rel))
        .where(Word.is_active == True)
    )

    if category:
        query = query.where(Word.category == category)
    if difficulty:
        query = query.where(Word.difficulty == difficulty)
    if creator_search:
        normalized_search = f"%{creator_search.strip()}%"
        query = query.where(
            or_(
                User.id.ilike(normalized_search),
                User.email.ilike(normalized_search),
            )
        )

    query = query.order_by(
        Word.created_by_child_id.is_not(None).desc(),
        Word.created_at.desc(),
    ).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.all()

    response_words = []
    for word, creator_child_name, creator_user_id, creator_user_email in rows:
        word_dict = AdminWordResponse.model_validate(word).model_dump()
        word_dict["category_name"] = word.category_rel.name if word.category_rel else None
        word_dict["category_name_cantonese"] = (
            word.category_rel.name_cantonese if word.category_rel else None
        )
        word_dict["creator_user_id"] = creator_user_id
        word_dict["creator_user_email"] = creator_user_email
        word_dict["creator_child_name"] = creator_child_name
        word_dict["is_user_uploaded"] = word.created_by_child_id is not None
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
    own_only: bool = Query(
        False,
        description="Only return words created by this child",
    ),
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
    
    # Get words with progress.
    # Default: system words + this child's uploaded words.
    # own_only=true: only this child's uploaded words (used for My Collection).
    query = select(Word).options(selectinload(Word.category_rel)).where(
        Word.is_active == True,
    )

    if own_only:
        query = query.where(Word.created_by_child_id == child_id)
    else:
        query = query.where(
            or_(
                Word.created_by_child_id.is_(None),
                Word.created_by_child_id == child_id,
            )
        )

    if category:
        query = query.where(Word.category == category)
    
    result = await db.execute(query)
    words = [word for word in result.scalars().all() if _is_child_safe_word_record(word)]
    
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


@router.get(
    "/child/{child_id}/active-vocab/pending",
    response_model=List[ActiveVocabularyApprovalRequestResponse],
)
async def get_pending_active_vocab_requests(
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List child words that are waiting for parent confirmation before becoming active vocabulary."""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    pending_result = await db.execute(
        select(WordProgress, Word)
        .join(Word, Word.id == WordProgress.word_id)
        .where(
            WordProgress.child_id == child_id,
            WordProgress.pending_active_vocab_approval.is_(True),
            WordProgress.active_vocab_requested_at.is_not(None),
        )
        .order_by(WordProgress.active_vocab_requested_at.desc())
    )

    return [
        {
            "child_id": child_id,
            "word_id": word.id,
            "word": word.word,
            "word_cantonese": word.word_cantonese,
            "image_url": word.image_url,
            "requested_at": progress.active_vocab_requested_at,
            "exposure_count": progress.exposure_count or 0,
            "last_practiced": progress.last_practiced,
        }
        for progress, word in pending_result.all()
    ]


@router.post("/{word_id}/progress/{child_id}/request-active-vocab", response_model=WordProgressResponse)
async def request_active_vocab_approval(
    word_id: str,
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Request parent confirmation before a word is counted as active vocabulary."""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    word_result = await db.execute(select(Word).where(Word.id == word_id))
    word = word_result.scalar_one_or_none()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found"
        )

    progress_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_id,
        )
    )
    progress = progress_result.scalar_one_or_none()

    if not progress:
        progress = WordProgress(child_id=child_id, word_id=word_id)
        db.add(progress)

    if progress.mastered:
        return progress

    exposure_count = progress.exposure_count or 0
    if exposure_count < ACTIVE_VOCAB_REQUEST_MIN_EXPOSURES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collect {ACTIVE_VOCAB_REQUEST_MIN_EXPOSURES} memory stars before requesting parent confirmation"
        )

    progress.pending_active_vocab_approval = True
    progress.active_vocab_requested_at = datetime.utcnow()

    await db.commit()
    await db.refresh(progress)

    return progress


@router.post("/{word_id}/progress/{child_id}/approve-active-vocab", response_model=WordProgressResponse)
async def approve_active_vocab_request(
    word_id: str,
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Approve a pending active-vocabulary request for a child."""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    progress_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word progress not found"
        )

    progress.pending_active_vocab_approval = False
    progress.active_vocab_requested_at = None
    if not progress.mastered:
        progress.mastered = True
        progress.mastered_at = datetime.utcnow()

    now = datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    tracking_result = await db.execute(
        select(DailyWordTracking)
        .where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.word_id == word_id,
                DailyWordTracking.date >= start_of_day,
                DailyWordTracking.date <= end_of_day,
            )
        )
        .order_by(DailyWordTracking.date.desc(), DailyWordTracking.id.desc())
    )
    tracking_rows = tracking_result.scalars().all()
    tracking = tracking_rows[0] if tracking_rows else None

    if tracking:
        tracking.used_actively = True
        tracking.mastery_confidence = max(tracking.mastery_confidence or 0.0, 1.0)
        tracking.learned_context = {
            **(tracking.learned_context or {}),
            "activity": "parent_confirmed_active_vocab",
            "source": "parent_dashboard",
        }
        tracking.story_priority = max(tracking.story_priority or 0, 8)
    else:
        tracking = DailyWordTracking(
            child_id=child_id,
            word_id=word_id,
            date=now,
            exposure_count=0,
            used_actively=True,
            mastery_confidence=1.0,
            learned_context={
                "activity": "parent_confirmed_active_vocab",
                "source": "parent_dashboard",
            },
            include_in_story=True,
            story_priority=8,
        )
        db.add(tracking)

    await db.commit()
    await db.refresh(progress)

    return progress


@router.post("/{word_id}/progress/{child_id}/reject-active-vocab", response_model=WordProgressResponse)
async def reject_active_vocab_request(
    word_id: str,
    child_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Reject a pending active-vocabulary request for a child."""
    result = await db.execute(
        select(Child).where(Child.id == child_id, Child.parent_id == current_user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found"
        )

    progress_result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word progress not found"
        )

    progress.pending_active_vocab_approval = False
    progress.active_vocab_requested_at = None

    await db.commit()
    await db.refresh(progress)

    return progress


@router.post("/", response_model=WordResponse, status_code=status.HTTP_201_CREATED)
async def create_word(
    word_data: WordCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create new word (admin only)"""
    await _get_category_or_404(word_data.category, db)

    word = Word(
        id=str(uuid.uuid4()),
        word=word_data.word,
        word_cantonese=word_data.word_cantonese,
        category=word_data.category,
        pronunciation=word_data.pronunciation,
        jyutping=word_data.jyutping,
        definition=word_data.definition,
        definition_cantonese=word_data.definition_cantonese,
        example=word_data.example,
        example_cantonese=word_data.example_cantonese,
        difficulty=word_data.difficulty,
        physical_action=word_data.physical_action,
        image_url=word_data.image_url,
        audio_url=word_data.audio_url,
        audio_url_english=word_data.audio_url_english,
        contexts=word_data.contexts or [],
        related_words=word_data.related_words or [],
    )
    
    db.add(word)
    await _recount_category_word_count(word.category, db)
    await db.commit()
    await db.refresh(word)

    background_tasks.add_task(enrich_word_relationships_background, word.id)
    
    return word


@router.patch("/{word_id}", response_model=WordResponse)
async def update_word(
    word_id: str,
    word_data: WordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update word (admin only)"""
    word = await _ensure_admin_editable_word(word_id, db)
    
    update_data = word_data.dict(exclude_unset=True)

    old_category_id = word.category
    if "category" in update_data:
        await _get_category_or_404(update_data["category"], db)

    for field, value in update_data.items():
        setattr(word, field, value)

    await _recount_category_word_count(word.category, db)
    if old_category_id != word.category:
        await _recount_category_word_count(old_category_id, db)
    
    await db.commit()
    await db.refresh(word)
    
    return word


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word(
    word_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Soft-delete a shared vocabulary word (admin only)."""
    word = await _ensure_admin_editable_word(word_id, db)

    if word.is_active:
        word.is_active = False
        await _recount_category_word_count(word.category, db)
        await db.commit()

    return None


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
    if "mastered" in update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the active vocabulary approval flow to change mastery status"
        )

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
    background_tasks: BackgroundTasks,
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
            
            # Store only the path (nginx will handle serving)
            final_image_url = f"/uploads/images/{unique_filename}"
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
        # Create a lightweight placeholder word immediately and finish AI enhancement
        # in the background so mobile clients do not wait on LLM latency.
        print(f"[External Word Learning] Creating placeholder word for background AI enhancement: '{word}'")
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
        
        placeholder_content = _build_external_placeholder_content(word, source)
        word_obj = Word(
            id=str(uuid.uuid4()),
            word=placeholder_content["word"],
            word_cantonese=placeholder_content["word_cantonese"],
            jyutping=placeholder_content["jyutping"],
            category=general_category.id,
            difficulty="easy",
            definition=placeholder_content["definition"],
            definition_cantonese=placeholder_content["definition_cantonese"],
            example=placeholder_content["example"],
            example_cantonese=placeholder_content["example_cantonese"],
            pronunciation=None,
            physical_action=None,
            image_url=final_image_url,
            audio_url=None,
            contexts=[source],
            related_words=[],
            created_by_child_id=child_id  # Mark as user-uploaded
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

    tracking_start = timestamp_dt.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    tracking_end = timestamp_dt.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999,
    )
    tracking_context: dict[str, object] = {
        "activity": source,
        "source": "external_word_learning",
    }

    if confidence is not None:
        tracking_context["confidence"] = confidence

    if metadata_dict:
        tracking_context["metadata"] = metadata_dict

    tracking_result = await db.execute(
        select(DailyWordTracking).where(
            and_(
                DailyWordTracking.child_id == child_id,
                DailyWordTracking.word_id == word_obj.id,
                DailyWordTracking.date >= tracking_start,
                DailyWordTracking.date <= tracking_end,
            )
        )
    )
    existing_tracking = tracking_result.scalar_one_or_none()

    tracking_mastery_confidence = confidence if confidence is not None else 0.35

    if existing_tracking:
        existing_tracking.exposure_count = (existing_tracking.exposure_count or 0) + 1
        existing_tracking.mastery_confidence = max(
            existing_tracking.mastery_confidence or 0.0,
            tracking_mastery_confidence,
        )

        if isinstance(existing_tracking.learned_context, dict):
            merged_context = dict(existing_tracking.learned_context)
            merged_context.update(tracking_context)
            existing_tracking.learned_context = merged_context
        else:
            existing_tracking.learned_context = tracking_context
    else:
        db.add(
            DailyWordTracking(
                child_id=child_id,
                word_id=word_obj.id,
                date=timestamp_dt,
                exposure_count=1,
                used_actively=False,
                mastery_confidence=tracking_mastery_confidence,
                learned_context=tracking_context,
                include_in_story=True,
                story_priority=5,
            )
        )
    
    await db.commit()
    await db.refresh(progress)
    await db.refresh(child)
    await db.refresh(word_obj)
    
    # Finish AI work after the response so mobile clients do not block on LLM latency.
    if word_created:
        print(f"[External Word Learning] Scheduling background AI enhancement for: {word_obj.word}")
        background_tasks.add_task(
            enhance_word_and_generate_sentences_background,
            word_id=word_obj.id,
            word_text=word_obj.word,
            source=source,
            image_url=final_image_url,
        )
    elif is_new_word:
        print(f"[External Word Learning] Scheduling background sentence generation for: {word_obj.word}")
        background_tasks.add_task(
            generate_sentences_background,
            word_id=word_obj.id,
            word_text=word_obj.word
        )
    
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
        error_str = str(e)
        llm_provider = (settings.LLM_PROVIDER or "ollama").strip().lower()
        provider_error_markers = [
            "Cannot connect to Ollama",
            "Connection refused",
            "API key required",
            "401",
            "403",
            "429",
            "timeout",
            "timed out",
            llm_provider,
            llm_provider.capitalize(),
        ]
        if any(marker in error_str for marker in provider_error_markers):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"AI service unavailable for configured provider '{llm_provider}'. "
                    "Check LLM_PROVIDER and the corresponding provider credentials/configuration."
                )
            )
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
