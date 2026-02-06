"""
Pydantic schemas for User/Child
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    PARENT = "parent"
    ADMIN = "admin"


class LearningStyle(str, Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class TimeOfDay(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class LanguagePreference(str, Enum):
    CANTONESE = "cantonese"  # Traditional Chinese only
    ENGLISH = "english"  # English only
    BILINGUAL = "bilingual"  # Both languages displayed


# User schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserResponse(UserBase):
    id: str
    role: UserRole
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Child schemas
class ChildBase(BaseModel):
    name: str
    age: int
    avatar: str = "👧"
    daily_goal: int = 5
    learning_style: LearningStyle = LearningStyle.MIXED
    language_preference: LanguagePreference = LanguagePreference.CANTONESE
    attention_span: int = 15
    preferred_time_of_day: TimeOfDay = TimeOfDay.MORNING


class ChildCreate(ChildBase):
    interests: Optional[List[str]] = []


class ChildUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    avatar: Optional[str] = None
    daily_goal: Optional[int] = None
    learning_style: Optional[LearningStyle] = None
    language_preference: Optional[LanguagePreference] = None
    attention_span: Optional[int] = None
    preferred_time_of_day: Optional[TimeOfDay] = None


class ChildResponse(ChildBase):
    id: str
    parent_id: str
    level: int
    xp: int
    words_learned: int
    current_streak: int
    today_progress: int
    created_at: datetime
    last_active: Optional[datetime] = None
    interests: List[str] = []
    
    class Config:
        from_attributes = True


class ChildProfileResponse(ChildResponse):
    """Extended child profile with additional statistics"""
    total_sessions: int = 0
    total_minutes: int = 0
    mastered_words: int = 0
    active_vocabulary: int = 0
    passive_vocabulary: int = 0
    

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class RegisterResponse(Token):
    user: UserResponse


class TokenData(BaseModel):
    user_id: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
