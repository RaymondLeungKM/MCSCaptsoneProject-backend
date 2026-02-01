"""
Schemas for daily word tracking and story generation
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class DailyWordTrackingCreate(BaseModel):
    child_id: str
    word_id: str
    date: datetime
    exposure_count: int = 1
    used_actively: bool = False
    mastery_confidence: float = 0.0
    learned_context: Optional[Dict[str, Any]] = None
    include_in_story: bool = True
    story_priority: int = 5


class DailyWordTrackingResponse(BaseModel):
    id: int
    child_id: str
    word_id: str
    date: datetime
    exposure_count: int
    used_actively: bool
    mastery_confidence: float
    learned_context: Optional[Dict[str, Any]]
    include_in_story: bool
    story_priority: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DailyWordSummary(BaseModel):
    """Word summary for story generation"""
    word_id: str
    word: str
    word_cantonese: str
    jyutping: str
    definition_cantonese: str
    example_cantonese: str
    category: str
    exposure_count: int
    used_actively: bool
    mastery_confidence: float
    story_priority: int


class GeneratedStoryCreate(BaseModel):
    child_id: str
    title: str
    title_english: Optional[str] = None
    theme: Optional[str] = None
    content_cantonese: str
    content_english: Optional[str] = None
    jyutping: Optional[str] = None
    featured_words: List[str] = Field(default_factory=list)  # List of word IDs
    word_usage: Optional[Dict[str, Any]] = None
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    reading_time_minutes: int = 5
    word_count: Optional[int] = None
    difficulty_level: str = "easy"
    cultural_references: Optional[List[str]] = None
    ai_model: Optional[str] = None
    generation_prompt: Optional[str] = None
    generation_time_seconds: Optional[float] = None


class GeneratedStoryResponse(BaseModel):
    id: str
    child_id: str
    title: str
    title_english: Optional[str]
    theme: Optional[str]
    generation_date: datetime
    content_cantonese: str
    content_english: Optional[str]
    jyutping: Optional[str]
    featured_words: List[str]
    word_usage: Optional[Dict[str, Any]]
    audio_url: Optional[str]
    audio_duration_seconds: Optional[int]
    reading_time_minutes: int
    word_count: Optional[int]
    difficulty_level: str
    cultural_references: Optional[List[str]]
    read_count: int
    is_favorite: bool
    parent_approved: bool
    ai_model: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class StoryGenerationRequest(BaseModel):
    """Request to generate a bedtime story"""
    child_id: str
    theme: Optional[str] = None  # e.g., "adventure", "family", "animals"
    date: Optional[datetime] = None  # Default to today
    word_count_target: int = Field(default=400, ge=200, le=800)
    reading_time_minutes: int = Field(default=5, ge=3, le=10)
    include_english: bool = False
    include_jyutping: bool = True


class StoryGenerationResponse(BaseModel):
    """Response after generating a story"""
    story: GeneratedStoryResponse
    words_used: List[DailyWordSummary]
    generation_time_seconds: float
    success: bool
    message: Optional[str] = None
