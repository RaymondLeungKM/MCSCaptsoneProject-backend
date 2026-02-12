"""
Schemas for TTS audio generation endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


LanguageCode = Literal["cantonese", "english", "mandarin"]


class GenerateWordAudioRequest(BaseModel):
    word_id: Optional[str] = None
    text: Optional[str] = None
    language: LanguageCode = "cantonese"
    voice_name: Optional[str] = None
    speech_rate: float = Field(default=0.9, ge=0.5, le=2.0)
    update_word_record: bool = True


class GenerateSentenceAudioRequest(BaseModel):
    text: str
    language: LanguageCode = "cantonese"
    voice_name: Optional[str] = None
    speech_rate: float = Field(default=0.9, ge=0.5, le=2.0)


class GenerateStoryAudioRequest(BaseModel):
    story_id: Optional[str] = None
    child_id: Optional[str] = None
    text: Optional[str] = None
    use_ssml: bool = True
    language: LanguageCode = "cantonese"
    voice_name: Optional[str] = None
    speech_rate: float = Field(default=0.85, ge=0.5, le=2.0)
    update_story_record: bool = True


class AudioGenerationResponse(BaseModel):
    audio_url: str
    audio_filename: str
    audio_duration_seconds: int
    audio_generate_provider: str
    audio_generate_voice_name: Optional[str] = None
    message: str = "Audio generated successfully"
