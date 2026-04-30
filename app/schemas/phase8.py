"""
Pydantic schemas for Phase 8 – Advanced AI & Personalization
  - Word Knowledge Graph (Epic 8.1)
  - Spaced Repetition / SM-2 (Epic 8.2)
  - AI Tutor Chat (Epic 8.2.4)
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RelationshipType(str, Enum):
    SEMANTIC   = "semantic"
    CATEGORY   = "category"
    PHONETIC   = "phonetic"
    CONTEXTUAL = "contextual"
    OPPOSITE   = "opposite"


# ---------------------------------------------------------------------------
# Epic 8.1 – Word Knowledge Graph
# ---------------------------------------------------------------------------

class WordRelationshipCreate(BaseModel):
    word_id:           str
    related_word_id:   str
    relationship_type: RelationshipType = RelationshipType.SEMANTIC
    strength:          float            = Field(default=0.7, ge=0.0, le=1.0)
    source:            str              = "system"


class WordRelationshipResponse(BaseModel):
    id:                int
    word_id:           str
    related_word_id:   str
    relationship_type: RelationshipType
    strength:          float
    source:            str
    created_at:        datetime

    class Config:
        from_attributes = True


class WordNode(BaseModel):
    """A node in the vocabulary knowledge graph (returned to the client)."""
    word_id:         str
    word:            str
    word_cantonese:  Optional[str] = None
    jyutping:        Optional[str] = None
    category:        str
    difficulty:      str
    mastered:        bool = False
    exposure_count:  int  = 0


class WordEdge(BaseModel):
    """An edge in the vocabulary knowledge graph."""
    source_id:         str
    target_id:         str
    relationship_type: RelationshipType
    strength:          float


class WordGraphResponse(BaseModel):
    """Subgraph centred on a given word."""
    centre_word_id: str
    nodes:          List[WordNode]
    edges:          List[WordEdge]


class GraphRecommendationResponse(BaseModel):
    """Vocabulary recommendations derived from the knowledge graph."""
    recommended_words: List[WordNode]
    reason:            str
    bridge_concepts:   List[str]   # intermediate concept labels used as bridges


# ---------------------------------------------------------------------------
# Epic 8.2 – Spaced Repetition (SM-2)
# ---------------------------------------------------------------------------

class SpacedRepetitionCardResponse(BaseModel):
    id:              int
    child_id:        str
    word_id:         str
    easiness_factor: float
    interval:        int
    repetitions:     int
    last_quality:    Optional[int] = None
    next_review:     datetime
    last_reviewed:   Optional[datetime] = None
    is_new:          bool
    is_graduated:    bool

    # Convenience: include word surface form
    word:            Optional[str] = None
    word_cantonese:  Optional[str] = None
    jyutping:        Optional[str] = None
    image_url:       Optional[str] = None
    audio_url:       Optional[str] = None
    definition_cantonese: Optional[str] = None

    class Config:
        from_attributes = True


class ReviewQueueResponse(BaseModel):
    """Cards due for review right now."""
    cards:          List[SpacedRepetitionCardResponse]
    total_due:      int
    new_cards_today: int


class ReviewResultRequest(BaseModel):
    """Result of a single card review – quality rating 0-5 (SM-2 convention)."""
    word_id: str
    quality: int = Field(..., ge=0, le=5,
                         description="0=complete blackout … 5=perfect recall")


class ReviewResultResponse(BaseModel):
    word_id:         str
    new_interval:    int
    easiness_factor: float
    next_review:     datetime
    is_graduated:    bool
    message:         str


# ---------------------------------------------------------------------------
# Epic 8.2.3 – Learning Style Detection
# ---------------------------------------------------------------------------

class LearningStyleAssessment(BaseModel):
    """
    Payload sent by the frontend after observing N sessions.
    The backend uses this to update child.learning_style.
    """
    child_id:              str
    kinesthetic_score:     float = Field(default=0.0, ge=0.0, le=1.0)
    visual_score:          float = Field(default=0.0, ge=0.0, le=1.0)
    auditory_score:        float = Field(default=0.0, ge=0.0, le=1.0)
    sessions_analysed:     int   = 1


class LearningStyleResponse(BaseModel):
    child_id:       str
    learning_style: str
    confidence:     float
    explanation:    str


# ---------------------------------------------------------------------------
# Epic 8.2.4 – AI Tutor Chat
# ---------------------------------------------------------------------------

class TutorChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class TutorChatRequest(BaseModel):
    child_id:  str
    question:  str
    word_id:   Optional[str] = None   # optional context word
    history:   List[TutorChatMessage] = []


class TutorChatResponse(BaseModel):
    answer:          str
    referenced_words: List[str] = []   # word IDs mentioned in the reply
    safe_mode:       bool = True
