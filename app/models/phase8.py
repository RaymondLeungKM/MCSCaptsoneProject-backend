"""
Phase 8 – Advanced AI & Personalization models

Adds:
  word_relationships        – knowledge-graph edges between vocabulary words (Epic 8.1)
  spaced_repetition_cards   – per-child SM-2 spaced-repetition state (Epic 8.2)
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Enum as SQLEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RelationshipType(str, enum.Enum):
    SEMANTIC   = "semantic"    # same conceptual domain (e.g. cat → dog)
    CATEGORY   = "category"    # same grammatical / thematic category
    PHONETIC   = "phonetic"    # similar Jyutping sound
    CONTEXTUAL = "contextual"  # appear together in real-world contexts
    OPPOSITE   = "opposite"    # antonym relationship


class LearningStyleEnum(str, enum.Enum):
    VISUAL      = "visual"
    AUDITORY    = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED       = "mixed"


# ---------------------------------------------------------------------------
# Epic 8.1 – Word Knowledge Graph
# ---------------------------------------------------------------------------

class WordRelationship(Base):
    """
    Directed (but typically symmetric) edge in the vocabulary knowledge graph.

    Both directions are stored as separate rows so that queries can go in
    either direction efficiently.
    """
    __tablename__ = "word_relationships"
    __table_args__ = (
        UniqueConstraint("word_id", "related_word_id", "relationship_type",
                         name="uq_word_relationship"),
    )

    id                = Column(Integer, primary_key=True, index=True, autoincrement=True)
    word_id           = Column(String, ForeignKey("words.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    related_word_id   = Column(String, ForeignKey("words.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    relationship_type = Column(SQLEnum(RelationshipType, name="relationshiptype",
                               values_callable=lambda obj: [e.value for e in obj]),
                               nullable=False,
                               default=RelationshipType.SEMANTIC)
    # Weighted strength 0.0 – 1.0 (higher = stronger connection)
    strength          = Column(Float, nullable=False, default=0.7)
    # Who created this edge: "system" | "ai_generated" | user-id
    source            = Column(String, nullable=False, default="system")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # back-references
    word         = relationship("Word", foreign_keys=[word_id],
                                backref="outgoing_relationships")
    related_word = relationship("Word", foreign_keys=[related_word_id],
                                backref="incoming_relationships")


# ---------------------------------------------------------------------------
# Epic 8.2 – SM-2 Spaced Repetition
# ---------------------------------------------------------------------------

class SpacedRepetitionCard(Base):
    """
    Tracks the SM-2 spaced-repetition state for one word per child.

    SM-2 parameters
    ---------------
    * ``easiness_factor`` (EF) – starts at 2.5; rises/falls based on quality
    * ``interval``        – days until next review (starts at 1, then 6, …)
    * ``repetitions``     – number of times rated ≥ 3 in a row
    * ``next_review``     – datetime after which the card is due
    """
    __tablename__ = "spaced_repetition_cards"
    __table_args__ = (
        UniqueConstraint("child_id", "word_id", name="uq_sr_card_child_word"),
    )

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)
    child_id        = Column(String, ForeignKey("children.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    word_id         = Column(String, ForeignKey("words.id",    ondelete="CASCADE"),
                             nullable=False, index=True)

    # SM-2 state
    easiness_factor = Column(Float,   nullable=False, default=2.5)
    interval        = Column(Integer, nullable=False, default=1)     # days
    repetitions     = Column(Integer, nullable=False, default=0)
    last_quality    = Column(Integer, nullable=True)                  # 0-5 rating

    # Scheduling
    next_review     = Column(DateTime(timezone=True), nullable=False,
                             server_default=func.now())
    last_reviewed   = Column(DateTime(timezone=True), nullable=True)

    # Convenience flags
    is_new          = Column(Boolean, nullable=False, default=True)
    is_graduated    = Column(Boolean, nullable=False, default=False)  # interval > 21 days

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    child = relationship("Child", backref="sr_cards")
    word  = relationship("Word",  backref="sr_cards")
