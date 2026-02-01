"""
Parent Analytics Models
Comprehensive analytics and insights for parent dashboard
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from app.db.base import Base


class DailyLearningStats(Base):
    """
    Daily learning statistics aggregation
    Tracks daily learning activity for progress charts
    """
    __tablename__ = "daily_learning_stats"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # Learning metrics
    words_learned = Column(Integer, default=0)
    words_reviewed = Column(Integer, default=0)
    new_words_mastered = Column(Integer, default=0)
    
    # Time tracking (minutes)
    total_learning_time = Column(Integer, default=0)
    active_learning_time = Column(Integer, default=0)
    
    # Session counts
    session_count = Column(Integer, default=0)
    
    # Category breakdown (JSONB)
    categories_studied = Column(JSON, default=dict)  # {category_id: word_count}
    
    # Game engagement
    games_played = Column(Integer, default=0)
    games_completed = Column(Integer, default=0)
    
    # Story engagement
    stories_read = Column(Integer, default=0)
    bedtime_stories_generated = Column(Integer, default=0)
    
    # XP earned
    xp_earned = Column(Integer, default=0)
    
    # Accuracy metrics
    average_accuracy = Column(Float, default=0.0)  # 0-100%
    
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

    # Relationship
    child = relationship("Child", back_populates="daily_stats")

    def __repr__(self):
        return f"<DailyLearningStats(child_id={self.child_id}, date={self.date}, words={self.words_learned})>"


class LearningInsight(Base):
    """
    AI-generated learning insights and recommendations
    """
    __tablename__ = "learning_insights"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Insight metadata
    insight_type = Column(String, nullable=False)  # 'strength', 'weakness', 'recommendation', 'milestone'
    priority = Column(String, default="medium")  # 'high', 'medium', 'low'
    category = Column(String, nullable=True)  # Related category if applicable
    
    # Content
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
    # Actionable recommendations
    action_items = Column(JSON, default=list)  # ["Suggestion 1", "Suggestion 2"]
    
    # Supporting data
    data = Column(JSON, default=dict)  # {metric: value, chart_data: [...]}
    
    # Status
    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)
    
    # Timestamps
    generated_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    valid_until = Column(String, nullable=True)  # Insights can expire
    
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    # Relationship
    child = relationship("Child", back_populates="insights")

    def __repr__(self):
        return f"<LearningInsight(child_id={self.child_id}, type={self.insight_type}, title={self.title})>"


class WeeklyReport(Base):
    """
    Weekly summary reports for parents
    """
    __tablename__ = "weekly_reports"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Report period
    week_start_date = Column(Date, nullable=False, index=True)
    week_end_date = Column(Date, nullable=False)
    
    # Summary metrics
    total_words_learned = Column(Integer, default=0)
    total_learning_time = Column(Integer, default=0)  # minutes
    total_sessions = Column(Integer, default=0)
    days_active = Column(Integer, default=0)
    
    # Achievements
    milestones_reached = Column(JSON, default=list)
    new_badges_earned = Column(JSON, default=list)
    
    # Top categories
    top_categories = Column(JSON, default=list)  # [{category: name, words: count}]
    
    # Strengths and areas for improvement
    strengths = Column(JSON, default=list)
    areas_to_improve = Column(JSON, default=list)
    
    # Recommendations
    recommendations = Column(JSON, default=list)
    
    # Comparison to previous week
    growth_percentage = Column(Float, default=0.0)
    
    # Status
    is_sent = Column(Boolean, default=False)
    sent_at = Column(String, nullable=True)
    
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    # Relationship
    child = relationship("Child", back_populates="weekly_reports")

    def __repr__(self):
        return f"<WeeklyReport(child_id={self.child_id}, week={self.week_start_date})>"


class ParentalControl(Base):
    """
    Parental control settings per child
    """
    __tablename__ = "parental_controls"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Content filtering
    enabled_categories = Column(JSON, default=list)  # Empty = all enabled
    disabled_categories = Column(JSON, default=list)
    max_difficulty = Column(String, default="hard")  # 'easy', 'medium', 'hard'
    min_difficulty = Column(String, default="easy")
    
    # Screen time limits (minutes per day)
    daily_screen_time_limit = Column(Integer, nullable=True)  # null = no limit
    screen_time_warning_threshold = Column(Integer, default=20)  # Warn at X minutes
    
    # Learning preferences
    tts_voice = Column(String, default="default")  # Voice preference ID
    tts_speech_rate = Column(Float, default=0.8)  # 0.5-2.0
    enable_bilingual_mode = Column(Boolean, default=False)
    show_jyutping = Column(Boolean, default=True)
    
    # Game settings
    game_difficulty_multiplier = Column(Float, default=1.0)  # 0.5-2.0
    enable_time_limits = Column(Boolean, default=False)
    
    # Safety settings
    safe_mode_enabled = Column(Boolean, default=False)  # Simplified UI for younger children
    require_parent_unlock = Column(Boolean, default=False)  # Parent PIN to unlock certain features
    
    # Notification preferences
    daily_reminder_enabled = Column(Boolean, default=True)
    daily_reminder_time = Column(String, default="18:00")  # HH:MM
    bedtime_story_reminder = Column(Boolean, default=True)
    weekly_report_enabled = Column(Boolean, default=True)
    achievement_notifications = Column(Boolean, default=True)
    
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

    # Relationship
    child = relationship("Child", back_populates="parental_control", uselist=False)

    def __repr__(self):
        return f"<ParentalControl(child_id={self.child_id})>"
