"""
Pydantic schemas for Analytics and Learning Sessions
"""
from pydantic import BaseModel, field_validator
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from enum import Enum


class EngagementLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Game Session schemas
class GameSessionCreate(BaseModel):
    """Body sent by the frontend when a mini-game ends"""
    child_id: str
    score: int = 0
    max_score: int = 0
    duration_seconds: int = 0
    words_seen: List[str] = []
    words_correct: List[str] = []
    stars: int = 1


class GameSessionResponse(BaseModel):
    id: int
    child_id: str
    game_id: str
    score: int
    max_score: int
    duration_seconds: int
    words_seen: List[str] = []
    words_correct: List[str] = []
    stars: int
    xp_earned: int
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('words_seen', 'words_correct', mode='before')
    @classmethod
    def coerce_game_lists(cls, value):
        return value if value is not None else []


# Learning Session schemas
class ActivityCompleted(BaseModel):
    type: str  # "story", "game", "mission"
    id: str
    duration_minutes: int


class LearningSessionCreate(BaseModel):
    child_id: str
    start_time: datetime
    words_encountered: List[str] = []
    activities_completed: List[ActivityCompleted] = []


class LearningSessionUpdate(BaseModel):
    end_time: datetime
    words_encountered: List[str]
    words_used_actively: List[str] = []
    activities_completed: List[ActivityCompleted]
    engagement_level: EngagementLevel = EngagementLevel.MEDIUM
    interactions_count: int = 0


class LearningSessionResponse(BaseModel):
    id: str
    child_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    words_encountered: List[str] = []
    words_used_actively: List[str] = []
    activities_completed: List[ActivityCompleted] = []
    engagement_level: EngagementLevel
    interactions_count: int
    xp_earned: int
    created_at: datetime
    
    class Config:
        from_attributes = True

    @field_validator('words_encountered', 'words_used_actively', 'activities_completed', mode='before')
    @classmethod
    def coerce_none_to_list(cls, v):
        return v if v is not None else []


# Daily Stats schemas
class DailyStatsResponse(BaseModel):
    date: date
    total_minutes: int
    words_encountered: int
    words_mastered: int
    activities_completed: int
    xp_earned: int
    session_count: int
    average_engagement: float
    daily_goal_progress: int
    goal_achieved: bool
    
    class Config:
        from_attributes = True


# Progress Stats schemas
class CategoryProgress(BaseModel):
    category: str
    progress: int  # percentage
    mastered: int
    total: int


class ProgressStatsResponse(BaseModel):
    total_words: int
    mastered_words: int
    active_vocabulary: int  # Words used in output
    passive_vocabulary: int  # Words only recognized
    weekly_progress: List[int]  # Last 7 days
    streak_days: int
    category_progress: List[CategoryProgress]
    average_exposures_per_word: float
    multi_sensory_engagement: float  # Percentage


class LearningControlStatusResponse(BaseModel):
    child_id: str
    local_date: date
    today_minutes: int
    active_session_minutes: int
    session_count: int
    has_activity_today: bool
    daily_screen_time_limit: Optional[int] = None
    screen_time_warning_threshold: int = 20
    enable_time_limits: bool = False
    remaining_minutes: Optional[int] = None
    warning_reached: bool = False
    limit_reached: bool = False
    daily_reminder_enabled: bool = True
    daily_reminder_time: str = "18:00"


# Achievement schemas
class AchievementCriteria(BaseModel):
    type: str  # "words_mastered", "streak", "xp_total", etc.
    threshold: int


class AchievementBase(BaseModel):
    name: str
    description: str
    icon: str = "🏆"
    xp_reward: int = 0


class AchievementCreate(AchievementBase):
    criteria: AchievementCriteria


class AchievementResponse(AchievementBase):
    id: str
    criteria: AchievementCriteria
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChildAchievementResponse(BaseModel):
    achievement_id: str
    achievement_name: str
    achievement_icon: str
    earned_at: datetime
    viewed: bool
    
    class Config:
        from_attributes = True


# Adaptive Learning schemas
class AdaptiveLearningRecommendation(BaseModel):
    next_words: List[str]  # Word IDs
    recommended_activity: str  # "story", "game", "mission"
    difficulty: str
    reason: str
    estimated_duration: int  # minutes


class WordOfTheDayResponse(BaseModel):
    word_id: str
    word: str
    word_cantonese: Optional[str] = None
    reason: str
    priority_score: int
