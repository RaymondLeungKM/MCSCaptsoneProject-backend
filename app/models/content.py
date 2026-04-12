"""
Content models - Games and Missions
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum

from app.db.base import Base


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
