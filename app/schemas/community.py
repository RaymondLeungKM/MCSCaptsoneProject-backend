"""
Pydantic schemas for Community & Social Sharing features (Phase 10)
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Shared Enumerations
# ---------------------------------------------------------------------------

class ModerationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FriendshipStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class ChallengeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Community Post schemas (Epic 10.1)
# ---------------------------------------------------------------------------

class CommunityPostCreate(BaseModel):
    """Submitted by a child (via parent-controlled session)"""
    word_id: Optional[str] = None
    word_text: Optional[str] = None
    word_text_cantonese: Optional[str] = None
    caption: Optional[str] = Field(None, max_length=120)
    # image_url is filled in by the upload service


class CommunityPostResponse(BaseModel):
    id: str
    child_id: str
    word_id: Optional[str]
    word_text: Optional[str]
    word_text_cantonese: Optional[str]
    caption: Optional[str]
    image_url: str
    is_anonymous: bool
    moderation_status: ModerationStatus
    reaction_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ModerationAction(BaseModel):
    """Payload for a parent approving or rejecting a post"""
    status: ModerationStatus  # APPROVED or REJECTED
    note: Optional[str] = Field(None, max_length=255)


class PostReactionCreate(BaseModel):
    reaction_type: str = "star"


class PostReactionResponse(BaseModel):
    id: int
    post_id: str
    child_id: str
    reaction_type: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Parent Friendship schemas (Epic 10.2)
# ---------------------------------------------------------------------------

class FriendRequestCreate(BaseModel):
    """Identify the target parent by email"""
    addressee_email: str


class FriendshipResponse(BaseModel):
    id: str
    requester_id: str
    addressee_id: str
    status: FriendshipStatus
    created_at: datetime
    updated_at: Optional[datetime]

    # Denormalised display info
    requester_name: Optional[str] = None
    addressee_name: Optional[str] = None

    class Config:
        from_attributes = True


class FriendshipStatusUpdate(BaseModel):
    status: FriendshipStatus  # ACCEPTED or BLOCKED


class FriendChildStats(BaseModel):
    """Aggregate stats for a friend's child (only opt-in data is shown)"""
    child_name: str
    avatar: str
    age: int
    words_learned: int
    current_streak: int
    level: int
    # Top words learned this week (titles only – no PII)
    recent_words: List[str] = []


class FriendProgressResponse(BaseModel):
    """What a parent can see about a connected friend's learning activity"""
    friend_id: str
    friend_name: str
    children_stats: List[FriendChildStats] = []


# ---------------------------------------------------------------------------
# Community Challenge schemas (Epic 10.2)
# ---------------------------------------------------------------------------

class CommunityChallengeCreate(BaseModel):
    title: str
    title_zh: Optional[str] = None
    description: Optional[str] = None
    description_zh: Optional[str] = None
    target_count: int = 5
    category: Optional[str] = None
    emoji: str = "🏆"
    starts_at: datetime
    ends_at: datetime


class CommunityChallengeResponse(BaseModel):
    id: str
    title: str
    title_zh: Optional[str]
    description: Optional[str]
    description_zh: Optional[str]
    target_count: int
    category: Optional[str]
    emoji: str
    status: ChallengeStatus
    starts_at: datetime
    ends_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ChallengeParticipationResponse(BaseModel):
    id: str
    challenge_id: str
    child_id: str
    progress: int
    is_completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    # Joined challenge info
    challenge_title: Optional[str] = None
    challenge_title_zh: Optional[str] = None
    challenge_target: Optional[int] = None
    challenge_emoji: Optional[str] = None

    class Config:
        from_attributes = True


class ChallengeProgressUpdate(BaseModel):
    """Increment a child's participation progress"""
    increment: int = Field(1, ge=1, le=100)
