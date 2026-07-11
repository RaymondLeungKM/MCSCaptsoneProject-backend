"""
Pydantic schemas for Content (Stories, Games, Missions)
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from enum import Enum


class PromptType(str, Enum):
    OPEN_ENDED = "open-ended"
    RECALL = "recall"
    PREDICTION = "prediction"
    CONNECTION = "connection"


class GameType(str, Enum):
    MATCHING = "matching"
    ISPY = "ispy"
    SPELLING = "spelling"
    PRONUNCIATION = "pronunciation"
    CHARADES = "charades"
    ACTIONS = "actions"
    SCAVENGER = "scavenger"


class MissionContext(str, Enum):
    MEALTIME = "mealtime"
    BEDTIME = "bedtime"
    PLAYTIME = "playtime"
    OUTDOOR = "outdoor"
    SHOPPING = "shopping"
    GENERAL = "general"


class MissionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MissionSurface(str, Enum):
    CHILD = "child"
    PARENT = "parent"
    BOTH = "both"


class MissionAssignmentSource(str, Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    PARENT = "parent"
    SEED = "seed"


class MissionAssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


# Game schemas
class GameBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: str = "🎮"
    color: str = "bg-sky"
    game_type: GameType


class GameCreate(GameBase):
    physical_activity: bool = False
    multi_sensory: bool = False
    parent_participation: bool = False
    min_words: int = 3
    max_words: int = 10
    difficulty: str = "easy"


class GameUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    physical_activity: Optional[bool] = None
    multi_sensory: Optional[bool] = None
    parent_participation: Optional[bool] = None


class GameResponse(GameBase):
    id: str
    physical_activity: bool
    multi_sensory: bool
    parent_participation: bool
    min_words: int
    max_words: int
    difficulty: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Mission schemas
class MissionBase(BaseModel):
    slug: str
    title: str
    description: str
    context: MissionContext = MissionContext.GENERAL
    is_offline: bool = False
    status: MissionStatus = MissionStatus.DRAFT
    locale: str = "zh-HK"
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    difficulty: Optional[str] = None
    surface: MissionSurface = MissionSurface.PARENT
    sort_order: int = 0
    assignment_repeat_cooldown_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
    )
    selection_tags: List[str] = Field(default_factory=list)
    catalog_metadata: Optional[Dict[str, Any]] = None
    published_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class MissionCreate(MissionBase):
    target_words: List[str] = Field(default_factory=list)
    conversation_prompts: List[str] = Field(default_factory=list)


class MissionUpdate(BaseModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    context: Optional[MissionContext] = None
    is_offline: Optional[bool] = None
    status: Optional[MissionStatus] = None
    locale: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    difficulty: Optional[str] = None
    surface: Optional[MissionSurface] = None
    sort_order: Optional[int] = None
    assignment_repeat_cooldown_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
    )
    selection_tags: Optional[List[str]] = None
    catalog_metadata: Optional[Dict[str, Any]] = None
    published_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    target_words: Optional[List[str]] = None
    conversation_prompts: Optional[List[str]] = None
    is_active: Optional[bool] = None


class MissionResponse(MissionBase):
    id: str
    target_words: List[str] = Field(default_factory=list)
    conversation_prompts: List[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("selection_tags", "target_words", "conversation_prompts", mode="before")
    @classmethod
    def _normalize_nullable_list_fields(cls, value):
        return [] if value is None else value
    
    class Config:
        from_attributes = True


class MissionProgressResponse(BaseModel):
    mission_id: str
    completed: bool
    completed_date: Optional[datetime] = None
    parent_notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class MissionProgressUpdate(BaseModel):
    completed: bool
    parent_notes: Optional[str] = None


class MissionAssignmentBase(BaseModel):
    child_id: str
    mission_id: str
    assignment_date: date
    source: MissionAssignmentSource = MissionAssignmentSource.SYSTEM
    status: MissionAssignmentStatus = MissionAssignmentStatus.ASSIGNED
    surface: MissionSurface = MissionSurface.PARENT
    priority: int = 100
    selection_reason: Optional[str] = None
    selection_metadata: Optional[Dict[str, Any]] = None
    available_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    skipped_at: Optional[datetime] = None
    completion_notes: Optional[str] = None


class MissionAssignmentCreate(MissionAssignmentBase):
    pass


class MissionAssignmentUpdate(BaseModel):
    source: Optional[MissionAssignmentSource] = None
    status: Optional[MissionAssignmentStatus] = None
    surface: Optional[MissionSurface] = None
    priority: Optional[int] = None
    selection_reason: Optional[str] = None
    selection_metadata: Optional[Dict[str, Any]] = None
    available_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    skipped_at: Optional[datetime] = None
    completion_notes: Optional[str] = None


class MissionAssignmentResponse(MissionAssignmentBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AssignedMissionResponse(MissionResponse):
    assignment: MissionAssignmentResponse


class MissionCompletionHistoryItem(BaseModel):
    mission_id: str
    title: str
    context: MissionContext
    is_offline: bool
    surface: MissionSurface
    assignment_date: date
    completed_at: datetime
    completion_notes: Optional[str] = None
    target_words: List[str] = Field(default_factory=list)
    points_earned: int


class MissionSummaryResponse(BaseModel):
    child_id: str
    local_today: date
    completed_today: int
    completed_this_week: int
    weekly_goal: int
    streak_days: int
    total_completed: int
    family_points: int
    level: int
    level_title: str
    next_level_points: int
    points_to_next_level: int
    next_reward_label: str
    encouragement: str
    recent_completions: List[MissionCompletionHistoryItem] = Field(
        default_factory=list
    )


class ParentMicroMissionCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., min_length=6, max_length=240)
    context: MissionContext = MissionContext.GENERAL
    target_words: List[str] = Field(default_factory=list, max_length=8)
    conversation_prompts: List[str] = Field(default_factory=list, max_length=4)
