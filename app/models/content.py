"""
Content models - Stories, Games, Missions
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum

from app.db.base import Base


class PromptType(str, enum.Enum):
    OPEN_ENDED = "open-ended"
    RECALL = "recall"
    PREDICTION = "prediction"
    CONNECTION = "connection"


class GameType(str, enum.Enum):
    MATCHING = "matching"
    ISPY = "ispy"
    SPELLING = "spelling"
    PRONUNCIATION = "pronunciation"
    CHARADES = "charades"
    ACTIONS = "actions"
    SCAVENGER = "scavenger"


class MissionContext(str, enum.Enum):
    MEALTIME = "mealtime"
    BEDTIME = "bedtime"
    PLAYTIME = "playtime"
    OUTDOOR = "outdoor"
    SHOPPING = "shopping"
    GENERAL = "general"


class Story(Base):
    """Interactive story"""
    __tablename__ = "stories"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    cover_image_url = Column(String)
    duration = Column(String)  # e.g., "5 min"
    description = Column(Text)
    
    # Story content stored as JSONB
    pages = Column(JSONB)  # Array of page objects
    target_words = Column(JSONB)  # Array of word IDs
    comprehension_questions = Column(JSONB)  # Array of question objects
    
    difficulty = Column(String, default="easy")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    progress = relationship("StoryProgress", back_populates="story")


class StoryProgress(Base):
    """Child's progress on stories"""
    __tablename__ = "story_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    story_id = Column(String, ForeignKey("stories.id"), nullable=False)
    
    completed = Column(Boolean, default=False)
    repeat_count = Column(Integer, default=0)
    last_read = Column(DateTime(timezone=True))
    pages_completed = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="progress")


class Game(Base):
    """Learning game"""
    __tablename__ = "games"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    icon = Column(String, default="🎮")
    color = Column(String, default="bg-sky")
    
    game_type = Column(SQLEnum(GameType), nullable=False)
    
    # Game characteristics
    physical_activity = Column(Boolean, default=False)
    multi_sensory = Column(Boolean, default=False)
    parent_participation = Column(Boolean, default=False)
    
    # Game configuration
    min_words = Column(Integer, default=3)
    max_words = Column(Integer, default=10)
    difficulty = Column(String, default="easy")
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Mission(Base):
    """Daily or offline mission"""
    __tablename__ = "missions"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
    context = Column(SQLEnum(MissionContext), default=MissionContext.GENERAL)
    target_words = Column(JSONB)  # Array of word IDs
    conversation_prompts = Column(JSONB)  # Array of prompt strings
    
    is_offline = Column(Boolean, default=False)  # True for offline missions
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MissionProgress(Base):
    """Child's mission completion"""
    __tablename__ = "mission_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False)
    
    completed = Column(Boolean, default=False)
    completed_date = Column(DateTime(timezone=True))
    parent_notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
