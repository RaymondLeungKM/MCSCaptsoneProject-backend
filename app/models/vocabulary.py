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
    name_cantonese = Column(String)  # Traditional Chinese name
    icon = Column(String, default="📚")
    color = Column(String, default="bg-slate-400")  # Will be auto-assigned on creation
    description = Column(Text)
    description_cantonese = Column(Text)  # Traditional Chinese description
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
    word = Column(String, nullable=False, index=True)  # English word (for reference)
    word_cantonese = Column(String, index=True)  # Traditional Chinese
    category = Column(String, ForeignKey("categories.id"), nullable=False)
    
    # Content
    pronunciation = Column(String)  # English pronunciation
    jyutping = Column(String)  # Cantonese romanization
    definition = Column(Text, nullable=False)  # English definition
    definition_cantonese = Column(Text)  # Traditional Chinese definition
    example = Column(Text, nullable=False)  # English example
    example_cantonese = Column(Text)  # Traditional Chinese example
    
    # Media
    image_url = Column(String)
    audio_url = Column(String)  # Cantonese audio URL
    audio_url_english = Column(String)  # English audio URL (optional)
    
    # Learning metadata
    difficulty = Column(SQLEnum(Difficulty), default=Difficulty.EASY)
    physical_action = Column(Text)  # Kinesthetic learning action
    contexts = Column(JSONB)  # List of contexts where word appears
    related_words = Column(JSONB)  # Related vocabulary IDs
    
    # Analytics
    total_exposures = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    
    # Ownership - for user-uploaded words (NULL means system/shared word)
    created_by_child_id = Column(String, ForeignKey("children.id"), nullable=True, index=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    category_rel = relationship("Category", back_populates="words")
    progress = relationship("WordProgress", back_populates="word")
    generated_sentences = relationship("GeneratedSentence", back_populates="word", cascade="all, delete-orphan")


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
