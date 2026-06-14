"""
Endpoints for AI-generated bedtime stories
"""
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.exc import SQLAlchemyError
from typing import List
from datetime import datetime, date

from app.db.session import get_db, engine
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
    StoryGenerationResponse,
    ExternalStoryInvokeRequest,
    ExternalStoryInvokeResponse,
)
from app.services.story_generator import story_generator
from app.services.external_story_program_service import (
    ExternalStoryProgramError,
    external_story_program_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

THEME_VOCAB_HINTS = {
    "adventure": "冒險",
    "family": "家庭",
    "animals": "動物",
    "nature": "大自然",
    "friendship": "友誼",
    "bedtime": "睡前",
}

THEME_TITLE_LABELS = {
    "adventure": ("冒險", "Adventure"),
    "family": ("家庭", "Family"),
    "animals": ("動物", "Animals"),
    "nature": ("大自然", "Nature"),
    "friendship": ("友誼", "Friendship"),
    "bedtime": ("睡前", "Bedtime"),
}


def _word_label(word: DailyWordSummary) -> str:
    return (word.word_cantonese or word.word or word.word_id).strip()


def _build_external_vocab_words(
    theme: str | None,
    words: List[DailyWordSummary],
) -> List[str]:
    theme_hint = THEME_VOCAB_HINTS.get(theme or "")
    ordered_words = [theme_hint] + [_word_label(word) for word in words]
    return list(dict.fromkeys([word for word in ordered_words if word]))[:30]


def _build_external_title(
    child_name: str,
    theme: str | None,
) -> tuple[str, str]:
    zh_theme, en_theme = THEME_TITLE_LABELS.get(theme or "bedtime", ("睡前", "Bedtime"))
    return f"{child_name}的{zh_theme}故事", f"{child_name}'s {en_theme} Story"


def _build_external_word_usage(words: List[DailyWordSummary]) -> dict[str, str]:
    return {
        _word_label(word): (
            word.definition_cantonese
            or word.example_cantonese
            or "在故事中自然地出現。"
        )
        for word in words
    }


async def _insert_generated_story_log_audit(
    story_id: str,
    audit_values: dict[str, object],
) -> None:
    """Best-effort audit row for legacy generated_stories_log consumers."""
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO generated_stories_log (
                        vocab_used,
                        story_text,
                        story_text_ssml,
                        story_generate_provdier,
                        story_generate_model,
                        audio_filename,
                        audio_generate_provider,
                        audio_generate_voice_name,
                        generated_at,
                        generated_by
                    ) VALUES (
                        :vocab_used,
                        :story_text,
                        :story_text_ssml,
                        :story_generate_provdier,
                        :story_generate_model,
                        :audio_filename,
                        :audio_generate_provider,
                        :audio_generate_voice_name,
                        :generated_at,
                        :generated_by
                    )
                    """
                ),
                audit_values,
            )
    except SQLAlchemyError as error:
        logger.warning(
            "Failed to insert generated_stories_log audit row for generated story %s: %s",
            story_id,
            error,
        )


async def _generate_story_with_internal_generator(
    request: ExternalStoryInvokeRequest,
    db: AsyncSession,
    words_used: List[DailyWordSummary],
    message: str = "Story generated successfully",
) -> StoryGenerationResponse:
    try:
        story_request = StoryGenerationRequest(**request.model_dump())
        story, _, generation_time = await story_generator.generate_story(db, story_request)
    except ValueError as error:
        error_msg = str(error)

        if "No words learned today" in error_msg:
            detail = "No words learned today to include in story. Please complete some learning activities first."
        elif "Failed to parse AI response" in error_msg:
            detail = f"The AI generated an invalid story format. Error: {error_msg}"
        else:
            detail = error_msg

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate story: {error}",
        ) from error

    return StoryGenerationResponse(
        story=GeneratedStoryResponse.model_validate(story),
        words_used=words_used,
        generation_time_seconds=generation_time,
        success=True,
        message=message,
    )


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
        error_msg = str(e)
        print(f"[API] ValueError during story generation: {error_msg}")
        
        # Provide more user-friendly error messages
        if "No words learned today" in error_msg:
            detail = "No words learned today to include in story. Please complete some learning activities first."
        elif "Failed to parse AI response" in error_msg:
            # Include more details for debugging
            detail = f"The AI generated an invalid story format. Error: {error_msg}"
        else:
            detail = error_msg
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        print(f"[API] Error generating story: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate story: {str(e)}"
        )


@router.post("/external/invoke", response_model=StoryGenerationResponse)
async def invoke_external_story_program(
    request: ExternalStoryInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invoke the external story-generation-program and persist into generated_stories."""
    child_query = select(Child).where(
        and_(Child.id == request.child_id, Child.parent_id == current_user.id)
    )
    result = await db.execute(child_query)
    child = result.scalar_one_or_none()

    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found",
        )

    words_used = await story_generator.get_daily_words(db, request.child_id, request.date)
    if not words_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No words learned today to include in story. Please complete some learning activities first.",
        )

    vocab_words = _build_external_vocab_words(request.theme, words_used)
    generation_started = time.perf_counter()

    external_program_error = external_story_program_service.availability_error()
    if external_program_error:
        return await _generate_story_with_internal_generator(
            request,
            db,
            words_used,
            message=(
                "Story generated successfully using the built-in generator because "
                "the external story program is unavailable."
            ),
        )

    try:
        result = await run_in_threadpool(
            external_story_program_service.invoke,
            vocab_words,
        )

        persisted_at = datetime.utcnow()
        title, title_english = _build_external_title(child.name, request.theme)
        story = GeneratedStory(
            id=str(uuid.uuid4()),
            child_id=request.child_id,
            title=title,
            title_english=title_english,
            theme=request.theme,
            generation_date=persisted_at,
            generated_at=persisted_at,
            generated_by="external_story_program",
            content_cantonese=result.story_text,
            content_english=None,
            jyutping=None,
            vocab_used=result.vocab_used[:500],
            story_text=result.story_text,
            story_text_ssml=story_generator._build_story_ssml(result.story_text),
            story_generate_provdier="OpenRouter",
            story_generate_model=result.llm_model,
            featured_words=[_word_label(word) for word in words_used],
            word_usage=_build_external_word_usage(words_used),
            audio_url=result.audio_url,
            audio_duration_seconds=None,
            audio_filename=result.audio_filename,
            audio_generate_provider=result.tts_provider,
            audio_generate_voice_name=None,
            reading_time_minutes=request.reading_time_minutes,
            word_count=len(result.story_text),
            difficulty_level="easy",
            cultural_references=None,
            read_count=0,
            is_favorite=False,
            parent_approved=True,
            ai_model=result.llm_model,
            generation_prompt=(
                f"External story program invoked for child={request.child_id}, "
                f"theme={request.theme or 'bedtime'}, vocab={result.vocab_used}"
            ),
            generation_time_seconds=time.perf_counter() - generation_started,
        )

        db.add(story)
        await db.commit()
        await db.refresh(story)
        story_response = GeneratedStoryResponse.model_validate(story)
        await _insert_generated_story_log_audit(
            story.id,
            {
                "vocab_used": story.vocab_used,
                "story_text": story.story_text,
                "story_text_ssml": story.story_text_ssml,
                "story_generate_provdier": story.story_generate_provdier,
                "story_generate_model": story.story_generate_model,
                "audio_filename": story.audio_filename,
                "audio_generate_provider": story.audio_generate_provider,
                "audio_generate_voice_name": story.audio_generate_voice_name,
                "generated_at": story.generated_at,
                "generated_by": "external_story_program_backend_api",
            },
        )

        return StoryGenerationResponse(
            story=story_response,
            words_used=words_used,
            generation_time_seconds=story.generation_time_seconds or 0.0,
            success=True,
            message="Story generated successfully",
        )
    except ExternalStoryProgramError as error:
        return await _generate_story_with_internal_generator(
            request,
            db,
            words_used,
            message=(
                "Story generated successfully using the built-in generator because "
                f"the external story program failed: {error}"
            ),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invoke external story program: {error}",
        ) from error


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
