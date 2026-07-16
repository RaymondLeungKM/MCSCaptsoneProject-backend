"""
Curated story management endpoints.
"""

from datetime import datetime, timezone
import logging
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_admin_user
from app.db.session import get_db
from app.models.daily_words import GeneratedStory
from app.models.user import User
from app.schemas.stories import GeneratedStoryCreate, GeneratedStoryResponse
from app.services.external_story_program_service import (
    ExternalStoryProgramError,
    external_story_program_service,
)
from app.services.story_audio_metadata import build_story_payload, resolve_story_audio_duration_seconds

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _to_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_story_ssml(story_text: str) -> str:
    return f"<speak>{story_text}</speak>"


def _configured_story_provider() -> str:
    return (settings.LLM_PROVIDER or "unknown").strip().lower()


def _configured_story_model() -> str:
    provider = _configured_story_provider()
    if provider == "openrouter":
        model = (settings.OPENROUTER_MODEL or "").strip()
    elif provider == "ollama":
        model = (settings.OLLAMA_MODEL or "").strip()
    elif provider == "openai":
        model = (getattr(settings, "OPENAI_MODEL", "") or "").strip()
    elif provider == "anthropic":
        model = (getattr(settings, "ANTHROPIC_MODEL", "") or "").strip()
    else:
        model = ""

    return model or "unknown"


def _split_keywords(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    return [
        token.strip()
        for token in re.split(r"[,，、;；\n]+", raw_value)
        if token and token.strip()
    ]


def _extract_story_keywords(story: GeneratedStory) -> list[str]:
    keywords: list[str] = []

    for entry in story.featured_words or []:
        if isinstance(entry, str):
            keywords.extend(_split_keywords(entry))

    keywords.extend(_split_keywords(story.vocab_used))

    deduped: list[str] = []
    for keyword in keywords:
        if keyword not in deduped:
            deduped.append(keyword)

    return deduped


def _build_generation_prompt(story: GeneratedStory) -> str:
    gen_source = _to_aware_utc(story.generation_date) or _to_aware_utc(story.generated_at) or datetime.now(timezone.utc)
    gen_date = gen_source.strftime("%Y-%m-%d")
    story_cat = (story.theme or "curated").strip() or "curated"
    vocab_words = _extract_story_keywords(story)
    vocab_display = ", ".join(vocab_words) if vocab_words else "N/A"
    child_display = story.child_id or "unknown"
    return (
        f"Admin curated story generation for child={child_display}, "
        f"gen_date={gen_date}, story_cat={story_cat}, vocab={vocab_display}"
    )


def _should_autogenerate_story_audio(story_data: GeneratedStoryCreate, story_text: str) -> bool:
    incoming_audio_filename = (story_data.audio_filename or "").strip().lower()
    incoming_ssml = (story_data.story_text_ssml or "").strip()
    expected_default_ssml = _default_story_ssml(story_text).strip()

    return (
        not incoming_audio_filename
        or incoming_audio_filename == "curated-story.mp3"
        or not incoming_ssml
        or incoming_ssml == expected_default_ssml
    )


def _apply_generated_audio_fields(story: GeneratedStory, generated_audio_result) -> None:
    story.story_text_ssml = generated_audio_result.story_text_ssml or _default_story_ssml(story.story_text)
    story.audio_url = generated_audio_result.audio_url
    story.audio_filename = generated_audio_result.audio_filename
    story.page_audio_segments = generated_audio_result.page_audio_segments or None
    story.audio_generate_provider = generated_audio_result.tts_provider
    story.audio_generate_voice_name = generated_audio_result.voice_name


def _apply_generated_story_enrichment(
    story: GeneratedStory,
    generated_audio_result,
    generation_time_seconds: float,
) -> None:
    _apply_generated_audio_fields(story, generated_audio_result)

    generated_at = generated_audio_result.generated_at or datetime.now(timezone.utc)
    story.generated_at = _to_naive_utc(generated_at)
    story.generation_date = _to_aware_utc(generated_at)

    resolved_model = (generated_audio_result.llm_model or "").strip() or _configured_story_model()
    story.story_generate_provdier = _configured_story_provider()
    story.story_generate_model = resolved_model
    story.ai_model = resolved_model

    normalized_text = (story.story_text or "").strip()
    story.word_count = len(normalized_text) if normalized_text else story.word_count
    story.generation_time_seconds = generation_time_seconds
    story.generation_prompt = _build_generation_prompt(story)

    story.audio_duration_seconds = resolve_story_audio_duration_seconds(
        GeneratedStory(
            audio_url=story.audio_url,
            audio_filename=story.audio_filename,
            audio_duration_seconds=story.audio_duration_seconds,
            reading_time_minutes=story.reading_time_minutes,
            content_cantonese=story.content_cantonese,
            story_text=story.story_text,
        )
    )

    if story.read_count is None:
        story.read_count = 0
    if story.is_favorite is None:
        story.is_favorite = False
    if story.parent_approved is None:
        story.parent_approved = True


def _build_default_word_usage(story: GeneratedStory) -> dict[str, str] | None:
    keywords = _extract_story_keywords(story)
    if not keywords:
        return None

    return {
        word: "在故事中自然地出現。"
        for word in keywords
    }


def _normalize_curated_story_fields(story: GeneratedStory) -> None:
    normalized_text = (story.story_text or "").strip()
    if normalized_text:
        story.word_count = len(normalized_text)

    if not story.title_english:
        story.title_english = story.title

    story.story_generate_provdier = _configured_story_provider()

    if not story.story_generate_model or story.story_generate_model == "external_story_program":
        story.story_generate_model = _configured_story_model()

    if not story.ai_model or story.ai_model == "external_story_program":
        story.ai_model = story.story_generate_model or _configured_story_model()

    if not story.generation_prompt:
        story.generation_prompt = _build_generation_prompt(story)

    if not story.vocab_used:
        keywords = _extract_story_keywords(story)
        if keywords:
            story.vocab_used = ", ".join(keywords)

    if not story.word_usage:
        story.word_usage = _build_default_word_usage(story)

    story.audio_duration_seconds = resolve_story_audio_duration_seconds(story)

    story.generated_at = _to_naive_utc(story.generated_at) or datetime.utcnow()
    story.generation_date = _to_aware_utc(story.generation_date) or datetime.now(timezone.utc)


async def _get_story_or_404(db: AsyncSession, story_id: str) -> GeneratedStory:
    result = await db.execute(select(GeneratedStory).where(GeneratedStory.id == story_id))
    story = result.scalar_one_or_none()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found",
        )

    return story


@router.get("/", response_model=list[GeneratedStoryResponse])
async def list_public_curated_stories(db: AsyncSession = Depends(get_db)):
    """List active curated stories for child/public UI."""
    result = await db.execute(
        select(GeneratedStory)
        .where(
            GeneratedStory.is_active.is_(True),
            GeneratedStory.story_type == "curated",
        )
        .order_by(GeneratedStory.sort_order.asc(), GeneratedStory.created_at.desc())
    )
    stories = result.scalars().all()
    return [build_story_payload(story) for story in stories]


@router.get("/admin/all", response_model=list[GeneratedStoryResponse])
async def list_admin_curated_stories(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all curated stories for admin management."""
    del current_user
    result = await db.execute(
        select(GeneratedStory)
        .where(GeneratedStory.story_type == "curated")
        .order_by(GeneratedStory.sort_order.asc(), GeneratedStory.created_at.desc())
    )
    stories = result.scalars().all()
    return [build_story_payload(story) for story in stories]


@router.post("/admin", response_model=GeneratedStoryResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_story(
    story_data: GeneratedStoryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a curated story record."""
    del current_user
    story_text = (story_data.story_text or story_data.content_cantonese).strip()
    story_ssml = (story_data.story_text_ssml or _default_story_ssml(story_text)).strip()

    story = GeneratedStory(
        id=str(uuid.uuid4()),
        child_id=story_data.child_id,
        story_type="curated",
        title=story_data.title,
        title_english=story_data.title_english,
        theme=story_data.theme,
        generated_at=_to_naive_utc(story_data.generated_at) or datetime.utcnow(),
        generated_by=story_data.generated_by or "admin",
        content_cantonese=story_data.content_cantonese,
        content_english=story_data.content_english,
        jyutping=story_data.jyutping,
        vocab_used=story_data.vocab_used,
        story_text=story_text,
        story_text_ssml=story_ssml,
        story_generate_provdier=story_data.story_generate_provdier,
        story_generate_model=story_data.story_generate_model,
        featured_words=story_data.featured_words,
        word_usage=story_data.word_usage,
        audio_url=story_data.audio_url,
        audio_duration_seconds=story_data.audio_duration_seconds,
        audio_filename=story_data.audio_filename or "curated-story.mp3",
        page_audio_segments=(
            [segment.model_dump() for segment in story_data.page_audio_segments]
            if story_data.page_audio_segments is not None
            else None
        ),
        audio_generate_provider=story_data.audio_generate_provider,
        audio_generate_voice_name=story_data.audio_generate_voice_name,
        reading_time_minutes=story_data.reading_time_minutes,
        word_count=story_data.word_count,
        difficulty_level=story_data.difficulty_level,
        cultural_references=story_data.cultural_references,
        ai_model=story_data.ai_model,
        generation_prompt=story_data.generation_prompt,
        generation_time_seconds=story_data.generation_time_seconds,
        is_active=story_data.is_active,
        sort_order=story_data.sort_order,
    )

    should_autogenerate = _should_autogenerate_story_audio(story_data, story_text)
    if should_autogenerate:
        try:
            generation_started = time.perf_counter()
            generated_audio_result = external_story_program_service.invoke_from_story_text(story_text)
            _apply_generated_story_enrichment(
                story,
                generated_audio_result,
                generation_time_seconds=time.perf_counter() - generation_started,
            )
        except ExternalStoryProgramError as error:
            logger.warning(
                "Admin story save skipped external audio generation for story %s: %s",
                story.id,
                error,
            )

    _normalize_curated_story_fields(story)

    db.add(story)
    await db.commit()
    await db.refresh(story)
    return build_story_payload(story)


@router.patch("/admin/{story_id}", response_model=GeneratedStoryResponse)
async def update_admin_story(
    story_id: str,
    story_data: GeneratedStoryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a curated story record."""
    del current_user
    story = await _get_story_or_404(db, story_id)

    story_text = (story_data.story_text or story_data.content_cantonese).strip()
    story_ssml = (story_data.story_text_ssml or _default_story_ssml(story_text)).strip()

    story.child_id = story_data.child_id or story.child_id
    story.story_type = "curated"
    story.title = story_data.title
    story.title_english = story_data.title_english or story.title_english
    story.theme = story_data.theme
    story.generated_at = story_data.generated_at or story.generated_at
    story.generated_at = _to_naive_utc(story.generated_at)
    story.generated_by = story_data.generated_by or story.generated_by
    story.content_cantonese = story_data.content_cantonese
    story.content_english = story_data.content_english
    story.jyutping = story_data.jyutping
    story.vocab_used = story_data.vocab_used or story.vocab_used
    story.story_text = story_text
    story.story_text_ssml = story_ssml
    story.story_generate_provdier = story_data.story_generate_provdier or story.story_generate_provdier
    story.story_generate_model = story_data.story_generate_model or story.story_generate_model
    story.featured_words = story_data.featured_words
    story.word_usage = story_data.word_usage or story.word_usage
    story.audio_url = story_data.audio_url
    story.audio_duration_seconds = story_data.audio_duration_seconds
    story.audio_filename = story_data.audio_filename or story.audio_filename
    story.page_audio_segments = (
        [segment.model_dump() for segment in story_data.page_audio_segments]
        if story_data.page_audio_segments is not None
        else None
    )
    story.audio_generate_provider = story_data.audio_generate_provider
    story.audio_generate_voice_name = story_data.audio_generate_voice_name
    story.reading_time_minutes = story_data.reading_time_minutes
    story.word_count = story_data.word_count
    story.difficulty_level = story_data.difficulty_level
    story.cultural_references = story_data.cultural_references
    story.ai_model = story_data.ai_model or story.ai_model
    story.generation_prompt = story_data.generation_prompt or story.generation_prompt
    story.generation_time_seconds = story_data.generation_time_seconds
    story.is_active = story_data.is_active
    story.sort_order = story_data.sort_order

    should_autogenerate = _should_autogenerate_story_audio(story_data, story_text)
    if should_autogenerate:
        try:
            generation_started = time.perf_counter()
            generated_audio_result = external_story_program_service.invoke_from_story_text(story_text)
            _apply_generated_story_enrichment(
                story,
                generated_audio_result,
                generation_time_seconds=time.perf_counter() - generation_started,
            )
        except ExternalStoryProgramError as error:
            logger.warning(
                "Admin story update skipped external audio generation for story %s: %s",
                story.id,
                error,
            )

    _normalize_curated_story_fields(story)

    await db.commit()
    await db.refresh(story)
    return build_story_payload(story)


@router.delete("/admin/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_story(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a curated story by marking it inactive."""
    del current_user
    story = await _get_story_or_404(db, story_id)
    story.is_active = False
    await db.commit()
    return None
