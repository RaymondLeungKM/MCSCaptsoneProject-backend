"""
Pydantic schemas for Vocabulary
"""
from pydantic import BaseModel, Field, field_validator, computed_field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Category schemas
class CategoryBase(BaseModel):
    name: str
    name_cantonese: Optional[str] = None
    icon: str = "📚"
    color: Optional[str] = None  # Auto-assigned if not provided
    description: Optional[str] = None
    description_cantonese: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    name_cantonese: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    description_cantonese: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: str
    word_count: int
    is_active: bool
    
    class Config:
        from_attributes = True


# Word schemas
class WordBase(BaseModel):
    word: str  # English word (for reference)
    word_cantonese: Optional[str] = None  # Traditional Chinese
    category: str
    pronunciation: Optional[str] = None  # English pronunciation
    jyutping: Optional[str] = None  # Cantonese romanization
    definition: str  # English definition
    definition_cantonese: Optional[str] = None  # Traditional Chinese definition
    example: str  # English example
    example_cantonese: Optional[str] = None  # Traditional Chinese example
    difficulty: Difficulty = Difficulty.EASY
    physical_action: Optional[str] = None


class WordCreate(WordBase):
    image_url: Optional[str] = None
    audio_url: Optional[str] = None  # Cantonese audio
    audio_url_english: Optional[str] = None  # English audio
    contexts: Optional[List[str]] = []
    related_words: Optional[List[str]] = []


class WordUpdate(BaseModel):
    word: Optional[str] = None
    word_cantonese: Optional[str] = None
    category: Optional[str] = None
    pronunciation: Optional[str] = None
    jyutping: Optional[str] = None
    definition: Optional[str] = None
    definition_cantonese: Optional[str] = None
    example: Optional[str] = None
    example_cantonese: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    physical_action: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_url_english: Optional[str] = None
    contexts: Optional[List[str]] = None
    related_words: Optional[List[str]] = None


class WordResponse(WordBase):
    id: str
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_url_english: Optional[str] = None
    contexts: List[str] = []
    related_words: List[str] = []
    total_exposures: int
    success_rate: float
    is_active: bool
    created_at: datetime
    created_by_child_id: Optional[str] = None
    category_name: Optional[str] = None
    category_name_cantonese: Optional[str] = None
    
    @field_validator('contexts', 'related_words', mode='before')
    @classmethod
    def convert_none_to_list(cls, v):
        return v if v is not None else []
    
    class Config:
        from_attributes = True


# Word Progress schemas
class WordProgressBase(BaseModel):
    word_id: str


class WordProgressResponse(BaseModel):
    id: int
    child_id: str
    word_id: str
    exposure_count: int
    mastered: bool
    mastered_at: Optional[datetime] = None
    last_practiced: Optional[datetime] = None
    correct_attempts: int
    total_attempts: int
    success_rate: float
    visual_exposures: int
    auditory_exposures: int
    kinesthetic_exposures: int
    
    class Config:
        from_attributes = True


class WordProgressUpdate(BaseModel):
    exposure_count: Optional[int] = None
    mastered: Optional[bool] = None
    correct_attempts: Optional[int] = None
    total_attempts: Optional[int] = None


class ExternalWordLearning(BaseModel):
    """Schema for word learning events from external sources (mobile app)"""
    word: str = Field(..., description="The word that was learned")
    word_id: Optional[str] = Field(None, description="Optional word ID if known")
    child_id: str = Field(..., description="ID of the child who learned the word")
    timestamp: datetime = Field(..., description="When the word was learned")
    source: str = Field(..., description="Source of learning event (e.g., 'object_detection', 'physical_activity')")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score for object detection")
    image_url: Optional[str] = Field(None, description="URL of the image used for object detection")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ExternalWordLearningResponse(BaseModel):
    """Response schema for external word learning endpoint"""
    success: bool = Field(..., description="Whether the operation was successful")
    word: str = Field(..., description="The word that was learned")
    word_id: str = Field(..., description="ID of the word in the vocabulary")
    word_data: WordResponse = Field(..., description="Complete word data including definition, example, etc.")
    word_created: bool = Field(..., description="Whether the word was newly created")
    child_id: str = Field(..., description="ID of the child")
    exposure_count: int = Field(..., description="Number of times child has been exposed to this word")
    xp_awarded: int = Field(..., description="XP points awarded (10 for first exposure, 0 for subsequent)")
    total_xp: int = Field(..., description="Child's total XP after this learning event")
    level: int = Field(..., description="Child's current level")
    words_learned: int = Field(..., description="Total number of words the child has learned")
    source: str = Field(..., description="Source of the learning event")
    timestamp: datetime = Field(..., description="When the word was learned")


class WordWithProgress(WordResponse):
    """Word with child's progress data"""
    progress: Optional[WordProgressResponse] = None


# Sentence generation schemas
class GeneratedSentence(BaseModel):
    """A generated example sentence"""
    sentence: str = Field(..., description="Cantonese Traditional Chinese sentence")
    sentence_english: Optional[str] = Field(None, description="English translation")
    jyutping: Optional[str] = Field(None, description="Jyutping romanization")
    context: str = Field(..., description="Context/scenario (e.g., 'home', 'school', 'park')")
    difficulty: str = Field(default="easy", description="Difficulty level: easy, medium, hard")


class SentenceGenerationResult(BaseModel):
    """Result of sentence generation for a word"""
    word: str = Field(..., description="English word")
    word_cantonese: str = Field(..., description="Cantonese word (Traditional Chinese)")
    sentences: List[GeneratedSentence] = Field(..., description="List of generated example sentences")
    total_generated: int = Field(..., description="Number of sentences generated")

