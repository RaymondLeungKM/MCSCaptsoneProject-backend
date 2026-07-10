"""
Analytics and Learning Session models
"""
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Float, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum

from app.db.base import Base


class GameSession(Base):
    """Individual mini-game play session"""
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String, nullable=False)           # "quiz" | "matching" | "speaking"
    score = Column(Integer, default=0)                 # correct answers / pairs found
    max_score = Column(Integer, default=0)             # total rounds / pairs
    duration_seconds = Column(Integer, default=0)
    words_seen = Column(JSONB, default=list)           # word IDs shown to child
    words_correct = Column(JSONB, default=list)        # word IDs answered correctly
    stars = Column(Integer, default=1)                 # 1–3 stars
    xp_earned = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    child = relationship("Child")


class EngagementLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LearningSession(Base):
    """Individual learning session tracking"""
    __tablename__ = "learning_sessions"
    
    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    
    # Session details
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration_minutes = Column(Integer)
    
    # Activity tracking
    words_encountered = Column(JSONB)  # Array of word IDs
    words_used_actively = Column(JSONB)  # Words child spoke/acted out
    activities_completed = Column(JSONB)  # Array of activity objects
    
    # Engagement metrics
    engagement_level = Column(SQLEnum(EngagementLevel), default=EngagementLevel.MEDIUM)
    interactions_count = Column(Integer, default=0)
    
    # XP earned in this session
    xp_earned = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    child = relationship("Child", back_populates="learning_sessions")


class Achievement(Base):
    """Achievement/badge definitions"""
    __tablename__ = "achievements"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    icon = Column(String, default="🏆")
    
    # Unlock criteria (stored as JSON)
    criteria = Column(JSONB)
    
    # Reward
    xp_reward = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChildAchievement(Base):
    """Child's earned achievements"""
    __tablename__ = "child_achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    achievement_id = Column(String, ForeignKey("achievements.id"), nullable=False)
    
    earned_at = Column(DateTime(timezone=True), server_default=func.now())
    viewed = Column(Boolean, default=False)
