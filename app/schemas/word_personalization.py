"""
Pydantic schemas for Word Personalization features.
  - Word Knowledge Graph (Epic 8.1)
  - Spaced Repetition / SM-2 (Epic 8.2)
  - AI Tutor Chat (Epic 8.2.4)
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class RelationshipType(str, Enum):
    SEMANTIC = "semantic"
    CATEGORY = "category"
    PHONETIC = "phonetic"
    CONTEXTUAL = "contextual"
    OPPOSITE = "opposite"


class WordRelationshipCreate(BaseModel):
    word_id: str
    related_word_id: str
    relationship_type: RelationshipType = RelationshipType.SEMANTIC
    strength: float = Field(default=0.7, ge=0.0, le=1.0)
    source: str = "system"


class WordRelationshipResponse(BaseModel):
    id: int
    word_id: str
    related_word_id: str
    relationship_type: RelationshipType
    strength: float
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class WordRelationshipReviewItem(BaseModel):
    id: int
    word_id: str
    word: Optional[str] = None
    word_cantonese: Optional[str] = None
    related_word_id: str
    related_word: Optional[str] = None
    related_word_cantonese: Optional[str] = None
    relationship_type: RelationshipType
    strength: float
    source: str
    created_at: datetime


class WordRelationshipReviewListResponse(BaseModel):
    items: List[WordRelationshipReviewItem]
    total_pending: int
    limit: int


class WordRelationshipReviewActionResponse(BaseModel):
    id: int
    action: str
    success: bool = True


class WordNode(BaseModel):
    word_id: str
    word: str
    word_cantonese: Optional[str] = None
    jyutping: Optional[str] = None
    category: str
    difficulty: str
    mastered: bool = False
    exposure_count: int = 0


class WordEdge(BaseModel):
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    strength: float


class WordGraphResponse(BaseModel):
    centre_word_id: str
    nodes: List[WordNode]
    edges: List[WordEdge]


class GraphRecommendationResponse(BaseModel):
    recommended_words: List[WordNode]
    reason: str
    bridge_concepts: List[str]


class ReviewQueueFeatures(BaseModel):
    due_score: float = 0.0
    graph_score: float = 0.0
    bridge_score: float = 0.0
    centrality_score: float = 0.0
    weak_link_boost: float = 0.0
    diversity_penalty: float = 0.0
    final_score: float = 0.0


class SpacedRepetitionCardResponse(BaseModel):
    id: int
    child_id: str
    word_id: str
    easiness_factor: float
    interval: int
    repetitions: int
    last_quality: Optional[int] = None
    next_review: datetime
    last_reviewed: Optional[datetime] = None
    is_new: bool
    is_graduated: bool
    word: Optional[str] = None
    word_cantonese: Optional[str] = None
    jyutping: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    definition_cantonese: Optional[str] = None
    queue_reason: Optional[str] = None
    queue_features: Optional[ReviewQueueFeatures] = None

    class Config:
        from_attributes = True


class ReviewQueueResponse(BaseModel):
    cards: List[SpacedRepetitionCardResponse]
    total_due: int
    new_cards_today: int


class ReviewResultRequest(BaseModel):
    word_id: str
    quality: int = Field(..., ge=0, le=5, description="0=complete blackout … 5=perfect recall")


class ReviewResultResponse(BaseModel):
    word_id: str
    new_interval: int
    easiness_factor: float
    next_review: datetime
    is_graduated: bool
    message: str


class LearningStyleAssessment(BaseModel):
    child_id: str
    kinesthetic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    visual_score: float = Field(default=0.0, ge=0.0, le=1.0)
    auditory_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sessions_analysed: int = 1


class LearningStyleResponse(BaseModel):
    child_id: str
    learning_style: str
    confidence: float
    explanation: str


class TutorChatMessage(BaseModel):
    role: str
    content: str


class TutorChatRequest(BaseModel):
    child_id: str
    question: str
    word_id: Optional[str] = None
    history: List[TutorChatMessage] = []


class TutorChatResponse(BaseModel):
    answer: str
    referenced_words: List[str] = []
    safe_mode: bool = True