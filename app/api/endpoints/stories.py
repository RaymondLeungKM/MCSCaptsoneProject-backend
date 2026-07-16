"""
Curated story management endpoints.
"""

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin_user
from app.db.session import get_db
from app.models.daily_words import GeneratedStory
from app.models.user import User
from app.schemas.stories import GeneratedStoryCreate, GeneratedStoryResponse
from app.services.story_audio_metadata import build_story_payload

router = APIRouter()


def _default_story_ssml(story_text: str) -> str:
    return f"<speak>{story_text}</speak>"


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
        generated_at=story_data.generated_at or datetime.utcnow(),
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

    story.child_id = story_data.child_id
    story.story_type = "curated"
    story.title = story_data.title
    story.title_english = story_data.title_english
    story.theme = story_data.theme
    story.generated_at = story_data.generated_at or story.generated_at
    story.generated_by = story_data.generated_by or story.generated_by
    story.content_cantonese = story_data.content_cantonese
    story.content_english = story_data.content_english
    story.jyutping = story_data.jyutping
    story.vocab_used = story_data.vocab_used
    story.story_text = story_text
    story.story_text_ssml = story_ssml
    story.story_generate_provdier = story_data.story_generate_provdier
    story.story_generate_model = story_data.story_generate_model
    story.featured_words = story_data.featured_words
    story.word_usage = story_data.word_usage
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
    story.ai_model = story_data.ai_model
    story.generation_prompt = story_data.generation_prompt
    story.generation_time_seconds = story_data.generation_time_seconds
    story.is_active = story_data.is_active
    story.sort_order = story_data.sort_order

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
