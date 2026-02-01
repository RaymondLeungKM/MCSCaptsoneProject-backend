"""
Parent Analytics Schemas
Request/response models for parent dashboard and analytics
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import date, datetime


# Daily Learning Stats Schemas
class DailyLearningStatsResponse(BaseModel):
    """Daily learning statistics"""
    id: str
    child_id: str
    date: date
    words_learned: int = 0
    words_reviewed: int = 0
    new_words_mastered: int = 0
    total_learning_time: int = 0  # minutes
    active_learning_time: int = 0  # minutes
    session_count: int = 0
    categories_studied: Dict[str, int] = {}
    games_played: int = 0
    games_completed: int = 0
    stories_read: int = 0
    bedtime_stories_generated: int = 0
    xp_earned: int = 0
    average_accuracy: float = 0.0

    class Config:
        from_attributes = True


# Learning Insight Schemas
class LearningInsightResponse(BaseModel):
    """AI-generated learning insight"""
    id: str
    child_id: str
    insight_type: str  # 'strength', 'weakness', 'recommendation', 'milestone'
    priority: str = "medium"  # 'high', 'medium', 'low'
    category: Optional[str] = None
    title: str
    description: str
    action_items: List[str] = []
    data: Dict = {}
    is_read: bool = False
    is_dismissed: bool = False
    generated_at: str
    valid_until: Optional[str] = None

    class Config:
        from_attributes = True


class LearningInsightCreateRequest(BaseModel):
    """Request to create a learning insight"""
    child_id: str
    insight_type: str
    priority: str = "medium"
    category: Optional[str] = None
    title: str
    description: str
    action_items: List[str] = []
    data: Dict = {}
    valid_until: Optional[str] = None


class LearningInsightUpdateRequest(BaseModel):
    """Update insight status"""
    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None


# Weekly Report Schemas
class WeeklyReportResponse(BaseModel):
    """Weekly summary report"""
    id: str
    child_id: str
    week_start_date: date
    week_end_date: date
    total_words_learned: int = 0
    total_learning_time: int = 0  # minutes
    total_sessions: int = 0
    days_active: int = 0
    milestones_reached: List[str] = []
    new_badges_earned: List[str] = []
    top_categories: List[Dict] = []
    strengths: List[str] = []
    areas_to_improve: List[str] = []
    recommendations: List[str] = []
    growth_percentage: float = 0.0
    is_sent: bool = False
    sent_at: Optional[str] = None

    class Config:
        from_attributes = True


# Parental Control Schemas
class ParentalControlResponse(BaseModel):
    """Parental control settings"""
    id: str
    child_id: str
    
    # Content filtering
    enabled_categories: List[str] = []
    disabled_categories: List[str] = []
    max_difficulty: str = "hard"
    min_difficulty: str = "easy"
    
    # Screen time
    daily_screen_time_limit: Optional[int] = None
    screen_time_warning_threshold: int = 20
    
    # Learning preferences
    tts_voice: str = "default"
    tts_speech_rate: float = 0.8
    enable_bilingual_mode: bool = False
    show_jyutping: bool = True
    
    # Game settings
    game_difficulty_multiplier: float = 1.0
    enable_time_limits: bool = False
    
    # Safety
    safe_mode_enabled: bool = False
    require_parent_unlock: bool = False
    
    # Notifications
    daily_reminder_enabled: bool = True
    daily_reminder_time: str = "18:00"
    bedtime_story_reminder: bool = True
    weekly_report_enabled: bool = True
    achievement_notifications: bool = True

    class Config:
        from_attributes = True


class ParentalControlUpdateRequest(BaseModel):
    """Update parental control settings"""
    enabled_categories: Optional[List[str]] = None
    disabled_categories: Optional[List[str]] = None
    max_difficulty: Optional[str] = None
    min_difficulty: Optional[str] = None
    daily_screen_time_limit: Optional[int] = None
    screen_time_warning_threshold: Optional[int] = None
    tts_voice: Optional[str] = None
    tts_speech_rate: Optional[float] = None
    enable_bilingual_mode: Optional[bool] = None
    show_jyutping: Optional[bool] = None
    game_difficulty_multiplier: Optional[float] = None
    enable_time_limits: Optional[bool] = None
    safe_mode_enabled: Optional[bool] = None
    require_parent_unlock: Optional[bool] = None
    daily_reminder_enabled: Optional[bool] = None
    daily_reminder_time: Optional[str] = None
    bedtime_story_reminder: Optional[bool] = None
    weekly_report_enabled: Optional[bool] = None
    achievement_notifications: Optional[bool] = None


# Dashboard Summary Schemas
class CategoryProgress(BaseModel):
    """Progress in a specific category"""
    category_id: str
    category_name: str
    category_name_cantonese: str
    words_learned: int
    total_words: int
    progress_percentage: float
    recent_activity: int  # Words learned in last 7 days


class DashboardSummaryResponse(BaseModel):
    """Comprehensive dashboard summary"""
    child_id: str
    child_name: str
    
    # Overview metrics
    total_words_learned: int
    current_streak: int
    level: int
    xp: int
    
    # Time period stats (last 7 days)
    weekly_learning_time: int  # minutes
    weekly_sessions: int
    weekly_words_learned: int
    weekly_xp_earned: int
    
    # Category breakdown
    category_progress: List[CategoryProgress]
    
    # Recent insights
    recent_insights: List[LearningInsightResponse]
    
    # Latest weekly report
    latest_report: Optional[WeeklyReportResponse] = None
    
    # Parental controls
    parental_control: Optional[ParentalControlResponse] = None


class LearningTimeSeriesData(BaseModel):
    """Time series data for charts"""
    dates: List[str]  # ISO date strings
    words_learned: List[int]
    learning_time: List[int]  # minutes
    xp_earned: List[int]
    accuracy: List[float]


class AnalyticsChartsResponse(BaseModel):
    """Data for analytics charts"""
    child_id: str
    period: str  # 'week', 'month', 'all'
    time_series: LearningTimeSeriesData
    category_breakdown: Dict[str, int]  # category_name: word_count
    learning_style_distribution: Dict[str, int]  # activity_type: count
    best_time_of_day: str
    average_session_length: int  # minutes
