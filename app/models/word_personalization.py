"""
Word personalization models.

Contains the advanced AI and personalization tables used for:
  - word relationships / knowledge graph edges
  - spaced repetition cards
  - cached word embeddings for semantic retrieval
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base


class RelationshipType(str, enum.Enum):
    SEMANTIC = "semantic"
    CATEGORY = "category"
    PHONETIC = "phonetic"
    CONTEXTUAL = "contextual"
    OPPOSITE = "opposite"


class LearningStyleEnum(str, enum.Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class WordRelationship(Base):
    __tablename__ = "word_relationships"
    __table_args__ = (
        UniqueConstraint("word_id", "related_word_id", "relationship_type", name="uq_word_relationship"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    related_word_id = Column(String, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(
        SQLEnum(RelationshipType, name="relationshiptype", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=RelationshipType.SEMANTIC,
    )
    strength = Column(Float, nullable=False, default=0.7)
    source = Column(String, nullable=False, default="system")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    word = relationship("Word", foreign_keys=[word_id], backref="outgoing_relationships")
    related_word = relationship("Word", foreign_keys=[related_word_id], backref="incoming_relationships")


class SpacedRepetitionCard(Base):
    __tablename__ = "spaced_repetition_cards"
    __table_args__ = (
        UniqueConstraint("child_id", "word_id", name="uq_sr_card_child_word"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    easiness_factor = Column(Float, nullable=False, default=2.5)
    interval = Column(Integer, nullable=False, default=1)
    repetitions = Column(Integer, nullable=False, default=0)
    last_quality = Column(Integer, nullable=True)
    next_review = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_reviewed = Column(DateTime(timezone=True), nullable=True)
    is_new = Column(Boolean, nullable=False, default=True)
    is_graduated = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    child = relationship("Child", backref="sr_cards")
    word = relationship("Word", backref="sr_cards")


class WordEmbedding(Base):
    __tablename__ = "word_embeddings"
    __table_args__ = (
        UniqueConstraint("word_id", name="uq_word_embedding_word_id"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False, default="openrouter")
    model = Column(String, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    dimensions = Column(Integer, nullable=False)
    source_text = Column(Text, nullable=False)
    source_text_hash = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    word = relationship("Word")