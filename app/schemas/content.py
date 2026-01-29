"""
Pydantic schemas for Content (Stories, Games, Missions)
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
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


# Story schemas
class DialogicPrompt(BaseModel):
    id: str
    type: PromptType
    question: str
    target_words: List[str]
    acceptable_responses: Optional[List[str]] = None


class StoryPage(BaseModel):
    id: str
    text: str
    highlighted_words: List[str]
    emoji: str
    dialogic_prompts: Optional[List[DialogicPrompt]] = None
    physical_action: Optional[str] = None


class StoryBase(BaseModel):
    title: str
    cover_image_url: Optional[str] = None
    duration: str = "5 min"
    description: Optional[str] = None
    difficulty: str = "easy"


class StoryCreate(StoryBase):
    pages: List[StoryPage]
    target_words: List[str]
    comprehension_questions: Optional[List[DialogicPrompt]] = None


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    cover_image_url: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None
    pages: Optional[List[StoryPage]] = None
    target_words: Optional[List[str]] = None


class StoryResponse(StoryBase):
    id: str
    pages: List[StoryPage]
    target_words: List[str]
    comprehension_questions: Optional[List[DialogicPrompt]] = None
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class StoryProgressResponse(BaseModel):
    story_id: str
    completed: bool
    repeat_count: int
    last_read: Optional[datetime] = None
    pages_completed: int
    
    class Config:
        from_attributes = True


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
