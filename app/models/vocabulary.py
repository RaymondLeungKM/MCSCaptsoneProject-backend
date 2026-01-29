"""
Vocabulary models - Words, Categories, Progress tracking
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Text, Enum as SQLEnum, Float, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa
import enum

from app.db.base import Base


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Category(Base):
    """Word category"""
    __tablename__ = "categories"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    icon = Column(String, default="📚")
    color = Column(String, default="bg-sky")
    description = Column(Text)
    word_count = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    words = relationship("Word", back_populates="category_rel")


class Word(Base):
    """Vocabulary word"""
    __tablename__ = "words"
    
    id = Column(String, primary_key=True, index=True)
    word = Column(String, nullable=False, index=True)
    category = Column(String, ForeignKey("categories.id"), nullable=False)
    
    # Content
    pronunciation = Column(String)
    definition = Column(Text, nullable=False)
    example = Column(Text, nullable=False)
    
    # Media
    image_url = Column(String)
    audio_url = Column(String)
    
    # Learning metadata
    difficulty = Column(SQLEnum(Difficulty), default=Difficulty.EASY)
    physical_action = Column(Text)  # Kinesthetic learning action
    contexts = Column(JSONB)  # List of contexts where word appears
    related_words = Column(JSONB)  # Related vocabulary IDs
    
    # Analytics
    total_exposures = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    category_rel = relationship("Category", back_populates="words")
    progress = relationship("WordProgress", back_populates="word")


class WordProgress(Base):
    """Child's progress on individual words"""
    __tablename__ = "word_progress"
    __table_args__ = (
        sa.UniqueConstraint('child_id', 'word_id', name='uq_word_progress_child_word'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    word_id = Column(String, ForeignKey("words.id"), nullable=False)
    
    # Progress tracking
    exposure_count = Column(Integer, default=0)
    mastered = Column(Boolean, default=False)
    mastered_at = Column(DateTime(timezone=True))
    last_practiced = Column(DateTime(timezone=True))
    
    # Performance metrics
    correct_attempts = Column(Integer, default=0)
    total_attempts = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    
    # Learning modes used
    visual_exposures = Column(Integer, default=0)
    auditory_exposures = Column(Integer, default=0)
    kinesthetic_exposures = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    child = relationship("Child", back_populates="word_progress")
    word = relationship("Word", back_populates="progress")
