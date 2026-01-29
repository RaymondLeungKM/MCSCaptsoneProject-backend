"""
Analytics and Learning Session models
"""
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Float, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum

from app.db.base import Base


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


class DailyStats(Base):
    """Daily aggregated statistics per child"""
    __tablename__ = "daily_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Daily metrics
    total_minutes = Column(Integer, default=0)
    words_encountered = Column(Integer, default=0)
    words_mastered = Column(Integer, default=0)
    activities_completed = Column(Integer, default=0)
    xp_earned = Column(Integer, default=0)
    
    # Engagement
    session_count = Column(Integer, default=0)
    average_engagement = Column(Float, default=0.0)
    
    # Progress towards daily goal
    daily_goal_progress = Column(Integer, default=0)
    goal_achieved = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


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
