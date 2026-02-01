"""
User models - Parent and Child profiles
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.db.base import Base


class UserRole(str, enum.Enum):
    PARENT = "parent"
    ADMIN = "admin"


class LearningStyle(str, enum.Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class TimeOfDay(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class LanguagePreference(str, enum.Enum):
    CANTONESE = "cantonese"  # Traditional Chinese only
    ENGLISH = "english"  # English only
    BILINGUAL = "bilingual"  # Both languages displayed


class User(Base):
    """Parent/Guardian user account"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.PARENT)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    children = relationship("Child", back_populates="parent", cascade="all, delete-orphan")


class Child(Base):
    """Child profile"""
    __tablename__ = "children"
    
    id = Column(String, primary_key=True, index=True)
    parent_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    avatar = Column(String, default="👧")
    age = Column(Integer, nullable=False)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    words_learned = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    daily_goal = Column(Integer, default=5)
    today_progress = Column(Integer, default=0)
    
    # Learning preferences
    learning_style = Column(SQLEnum(LearningStyle), default=LearningStyle.MIXED)
    language_preference = Column(SQLEnum(LanguagePreference), default=LanguagePreference.CANTONESE)
    attention_span = Column(Integer, default=15)  # minutes
    preferred_time_of_day = Column(SQLEnum(TimeOfDay), default=TimeOfDay.MORNING)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_active = Column(DateTime(timezone=True))
    
    # Relationships
    parent = relationship("User", back_populates="children")
    interests = relationship("ChildInterest", back_populates="child", cascade="all, delete-orphan")
    learning_sessions = relationship("LearningSession", back_populates="child", cascade="all, delete-orphan")
    word_progress = relationship("WordProgress", back_populates="child", cascade="all, delete-orphan")
    daily_stats = relationship("DailyLearningStats", back_populates="child", cascade="all, delete-orphan")
    insights = relationship("LearningInsight", back_populates="child", cascade="all, delete-orphan")
    weekly_reports = relationship("WeeklyReport", back_populates="child", cascade="all, delete-orphan")
    parental_control = relationship("ParentalControl", back_populates="child", cascade="all, delete-orphan", uselist=False)


class ChildInterest(Base):
    """Child's learning interests/preferences"""
    __tablename__ = "child_interests"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    
    child = relationship("Child", back_populates="interests")
    category = relationship("Category")
