"""
Story content endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.db.session import get_db
from app.schemas.stories import GeneratedStoryCreate, GeneratedStoryResponse
from app.models.daily_words import GeneratedStory
from app.models.user import User
from app.core.security import get_current_admin_user

router = APIRouter()


def _build_story_payload(story: GeneratedStory) -> GeneratedStoryResponse:
    return GeneratedStoryResponse.model_validate(story)


async def _get_story_or_404(db: AsyncSession, story_id: str) -> GeneratedStory:
    result = await db.execute(select(GeneratedStory).where(GeneratedStory.id == story_id))
    story = result.scalar_one_or_none()

    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found",
        )

    return story


@router.get("/", response_model=List[GeneratedStoryResponse])
async def get_stories(
    db: AsyncSession = Depends(get_db)
):
    """Get all active curated stories."""
    result = await db.execute(
        select(GeneratedStory)
        .where(
            GeneratedStory.is_active == True,
            GeneratedStory.story_type == "curated",
        )
        .order_by(GeneratedStory.sort_order, GeneratedStory.created_at)
    )
    stories = result.scalars().all()
    return stories


@router.get("/admin/all", response_model=List[GeneratedStoryResponse])
async def get_admin_stories(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all curated stories, including inactive ones, for admin management."""
    result = await db.execute(
        select(GeneratedStory)
        .where(GeneratedStory.story_type == "curated")
        .order_by(GeneratedStory.sort_order, GeneratedStory.created_at)
    )
    stories = result.scalars().all()
    return stories


@router.post("/admin", response_model=GeneratedStoryResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_story(
    story_data: GeneratedStoryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a curated story in the generated stories table."""
    story = GeneratedStory(
        id=str(uuid.uuid4()),
        child_id=None,
        story_type="curated",
        title=story_data.title,
        title_english=story_data.title_english,
        theme=story_data.theme,
        generated_at=story_data.generated_at or None,
        generated_by=story_data.generated_by or "admin",
        content_cantonese=story_data.content_cantonese,
        content_english=story_data.content_english,
        jyutping=story_data.jyutping,
        vocab_used=story_data.vocab_used,
        story_text=story_data.story_text or story_data.content_cantonese,
        story_text_ssml=story_data.story_text_ssml or f"<speak>{story_data.content_cantonese}</speak>",
        story_generate_provdier=story_data.story_generate_provdier,
        story_generate_model=story_data.story_generate_model,
        featured_words=story_data.featured_words,
        word_usage=story_data.word_usage,
        audio_url=story_data.audio_url,
        audio_duration_seconds=story_data.audio_duration_seconds,
        audio_filename=story_data.audio_filename or "curated-story.mp3",
        audio_generate_provider=story_data.audio_generate_provider,
        audio_generate_voice_name=story_data.audio_generate_voice_name,
        reading_time_minutes=story_data.reading_time_minutes,
        word_count=story_data.word_count,
        difficulty_level=story_data.difficulty_level,
        cultural_references=story_data.cultural_references,
        read_count=0,
        is_favorite=False,
        parent_approved=True,
        is_active=story_data.is_active,
        sort_order=story_data.sort_order,
        ai_model=story_data.ai_model,
        generation_prompt=story_data.generation_prompt,
        generation_time_seconds=story_data.generation_time_seconds,
    )

    db.add(story)
    await db.commit()
    await db.refresh(story)
    return _build_story_payload(story)


@router.patch("/admin/{story_id}", response_model=GeneratedStoryResponse)
async def update_admin_story(
    story_id: str,
    story_data: GeneratedStoryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing curated story."""
    story = await _get_story_or_404(db, story_id)

    story.title = story_data.title
    story.title_english = story_data.title_english
    story.theme = story_data.theme
    story.generated_by = story_data.generated_by or story.generated_by
    story.content_cantonese = story_data.content_cantonese
    story.content_english = story_data.content_english
    story.jyutping = story_data.jyutping
    story.vocab_used = story_data.vocab_used
    story.story_text = story_data.story_text or story_data.content_cantonese
    story.story_text_ssml = story_data.story_text_ssml or f"<speak>{story_data.content_cantonese}</speak>"
    story.story_generate_provdier = story_data.story_generate_provdier
    story.story_generate_model = story_data.story_generate_model
    story.featured_words = story_data.featured_words
    story.word_usage = story_data.word_usage
    story.audio_url = story_data.audio_url
    story.audio_duration_seconds = story_data.audio_duration_seconds
    story.audio_filename = story_data.audio_filename or story.audio_filename
    story.audio_generate_provider = story_data.audio_generate_provider
    story.audio_generate_voice_name = story_data.audio_generate_voice_name
    story.reading_time_minutes = story_data.reading_time_minutes
    story.word_count = story_data.word_count
    story.difficulty_level = story_data.difficulty_level
    story.cultural_references = story_data.cultural_references
    story.is_active = story_data.is_active
    story.sort_order = story_data.sort_order
    story.ai_model = story_data.ai_model
    story.generation_prompt = story_data.generation_prompt
    story.generation_time_seconds = story_data.generation_time_seconds

    await db.commit()
    await db.refresh(story)
    return _build_story_payload(story)


@router.delete("/admin/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_story(
    story_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide a curated story from the public catalog without removing its history."""
    story = await _get_story_or_404(db, story_id)

    story.is_active = False
    await db.commit()


@router.get("/{story_id}", response_model=GeneratedStoryResponse)
async def get_story(
    story_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get specific curated story."""
    story = await _get_story_or_404(db, story_id)
    return story
