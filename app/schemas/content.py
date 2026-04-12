"""
Pydantic schemas for content domains still exposed by the API.
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


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
    title: str
    description: str
    context: MissionContext = MissionContext.GENERAL
    is_offline: bool = False


class MissionCreate(MissionBase):
    target_words: List[str]
    conversation_prompts: List[str]


class MissionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_words: Optional[List[str]] = None
    conversation_prompts: Optional[List[str]] = None


class MissionResponse(MissionBase):
    id: str
    target_words: List[str]
    conversation_prompts: List[str]
    is_active: bool
    created_at: datetime
    
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
