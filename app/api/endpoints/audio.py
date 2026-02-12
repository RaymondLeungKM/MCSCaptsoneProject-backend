"""
Audio generation endpoints (Phase 3 - TTS).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User, Child
from app.models.vocabulary import Word
from app.models.daily_words import GeneratedStory
from app.schemas.audio import (
    GenerateWordAudioRequest,
    GenerateSentenceAudioRequest,
    GenerateStoryAudioRequest,
    AudioGenerationResponse,
)
from app.services.tts_service import tts_service

router = APIRouter()


@router.post("/generate-word-audio", response_model=AudioGenerationResponse)
async def generate_word_audio(
    request: GenerateWordAudioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate TTS audio for a single vocabulary word and optionally persist URL to word record."""

    text_to_speak = request.text
    word: Word | None = None

    if request.word_id:
        result = await db.execute(select(Word).where(Word.id == request.word_id))
        word = result.scalar_one_or_none()
        if not word:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word not found")

        if not text_to_speak:
            text_to_speak = (
                word.word_cantonese if request.language == "cantonese" else word.word
            )

    if not text_to_speak:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide word_id or text to generate audio",
        )

    generated = tts_service.generate_audio(
        text_to_speak,
        language=request.language,
        voice_name=request.voice_name,
        speech_rate=request.speech_rate,
        filename_prefix="word",
    )

    if word and request.update_word_record:
        if request.language == "english":
            word.audio_url_english = generated["audio_url"]
        else:
            word.audio_url = generated["audio_url"]

        await db.commit()

    return AudioGenerationResponse(**generated)


@router.post("/generate-sentence-audio", response_model=AudioGenerationResponse)
async def generate_sentence_audio(
    request: GenerateSentenceAudioRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate TTS audio for an arbitrary sentence."""

    generated = tts_service.generate_audio(
        request.text,
        language=request.language,
        voice_name=request.voice_name,
        speech_rate=request.speech_rate,
        filename_prefix="sentence",
    )
    return AudioGenerationResponse(**generated)


@router.post("/generate-story-audio", response_model=AudioGenerationResponse)
async def generate_story_audio(
    request: GenerateStoryAudioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate TTS audio for a story and optionally persist URL to generated story record."""

    story: GeneratedStory | None = None
    text_to_speak = request.text

    if request.story_id:
        query = select(GeneratedStory).where(GeneratedStory.id == request.story_id)
        if request.child_id:
            query = query.where(GeneratedStory.child_id == request.child_id)

        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")

        if request.child_id:
            child_query = select(Child).where(
                and_(Child.id == request.child_id, Child.parent_id == current_user.id)
            )
            child_result = await db.execute(child_query)
            child = child_result.scalar_one_or_none()
            if not child:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this child story",
                )

        if not text_to_speak:
            text_to_speak = story.story_text_ssml if request.use_ssml else story.story_text

    if not text_to_speak:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide story_id or text to generate story audio",
        )

    generated = tts_service.generate_audio(
        text_to_speak,
        language=request.language,
        voice_name=request.voice_name,
        speech_rate=request.speech_rate,
        filename_prefix="story",
    )

    if story and request.update_story_record:
        story.audio_url = generated["audio_url"]
        story.audio_duration_seconds = generated["audio_duration_seconds"]
        story.audio_filename = generated["audio_filename"]
        story.audio_generate_provider = generated["audio_generate_provider"]
        story.audio_generate_voice_name = generated["audio_generate_voice_name"]
        await db.commit()

    return AudioGenerationResponse(**generated)
