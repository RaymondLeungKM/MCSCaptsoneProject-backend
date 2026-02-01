"""
Daily word tracking for bedtime story generation
"""
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class DailyWordTracking(Base):
    """Track words encountered/learned each day for story generation"""
    __tablename__ = "daily_word_tracking"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    word_id = Column(String, ForeignKey("words.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Tracking metrics
    exposure_count = Column(Integer, default=1)  # How many times seen today
    used_actively = Column(Boolean, default=False)  # Spoken/acted out
    mastery_confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    
    # Context of learning
    learned_context = Column(JSONB)  # {"activity": "game", "game_type": "matching"}
    
    # For story generation prioritization
    include_in_story = Column(Boolean, default=True)
    story_priority = Column(Integer, default=5)  # 1-10, higher = more priority
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    child = relationship("Child")
    word = relationship("Word")


class GeneratedStory(Base):
    """AI-generated bedtime stories"""
    __tablename__ = "generated_stories"
    
    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    
    # Story metadata
    title = Column(String, nullable=False)
    title_english = Column(String)
    theme = Column(String)  # e.g., "adventure", "family", "animals"
    generation_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Story content
    content_cantonese = Column(String, nullable=False)  # Full story in Traditional Chinese
    content_english = Column(String)  # English translation
    jyutping = Column(String)  # Romanization for difficult words
    
    # Featured words
    featured_words = Column(JSONB)  # Array of word IDs used in story
    word_usage = Column(JSONB)  # Dict mapping word_id to usage context in story
    
    # Audio
    audio_url = Column(String)  # TTS narration
    audio_duration_seconds = Column(Integer)
    
    # Metadata
    reading_time_minutes = Column(Integer, default=5)
    word_count = Column(Integer)
    difficulty_level = Column(String, default="easy")
    
    # Cultural elements
    cultural_references = Column(JSONB)  # Hong Kong landmarks, festivals, etc.
    
    # Engagement
    read_count = Column(Integer, default=0)
    is_favorite = Column(Boolean, default=False)
    parent_approved = Column(Boolean, default=True)
    
    # AI generation metadata
    ai_model = Column(String)  # e.g., "gpt-4", "claude-3"
    generation_prompt = Column(String)  # For debugging/improvement
    generation_time_seconds = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    child = relationship("Child")
