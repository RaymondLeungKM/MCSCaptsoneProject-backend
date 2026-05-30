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


class FriendChallengeMetric(str, Enum):
    PRACTICE_DAYS = "practice_days"
    NEW_WORDS = "new_words"
    ACTIVE_WORDS = "active_words"


class FriendChallengeInviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class FriendChallengeViewStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    DECLINED = "declined"


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


class CommunityPostFromCollectionCreate(BaseModel):
    """Share an existing word from the child's My Collection (no new file upload)."""
    word_id: str
    caption: Optional[str] = Field(None, max_length=120)


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


class FriendRequestByIdCreate(BaseModel):
    """Identify the target parent by their user ID"""
    addressee_id: str


class UserSearchResult(BaseModel):
    """Safe public profile returned when searching for a user by ID"""
    id: str
    full_name: str

    class Config:
        from_attributes = True


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
    target_count: int = Field(5, ge=1, le=1000)
    category: Optional[str] = None
    emoji: str = "🏆"
    status: ChallengeStatus = ChallengeStatus.ACTIVE
    starts_at: datetime
    ends_at: datetime


class CommunityChallengeUpdate(BaseModel):
    title: Optional[str] = None
    title_zh: Optional[str] = None
    description: Optional[str] = None
    description_zh: Optional[str] = None
    target_count: Optional[int] = Field(None, ge=1, le=1000)
    category: Optional[str] = None
    emoji: Optional[str] = None
    status: Optional[ChallengeStatus] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


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
    child_name: Optional[str] = None
    child_avatar: Optional[str] = None
    parent_name: Optional[str] = None
    participant_code: Optional[str] = None
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

    # Optional leaderboard display info
    parent_name: Optional[str] = None
    child_name: Optional[str] = None
    child_avatar: Optional[str] = None
    participant_code: Optional[str] = None

    class Config:
        from_attributes = True


class ChallengeProgressUpdate(BaseModel):
    """Increment a child's participation progress"""
    increment: int = Field(1, ge=1, le=100)


class FriendChallengeCreate(BaseModel):
    child_id: str
    invited_parent_ids: List[str] = Field(default_factory=list)
    metric_type: FriendChallengeMetric
    target_count: int = Field(..., ge=1, le=50)
    duration_days: int = Field(7, ge=3, le=30)


class FriendChallengeRespond(BaseModel):
    invite_status: FriendChallengeInviteStatus
    child_id: Optional[str] = None


class FriendChallengeParticipantResponse(BaseModel):
    id: str
    parent_id: str
    parent_name: Optional[str] = None
    child_id: Optional[str] = None
    child_name: Optional[str] = None
    child_avatar: Optional[str] = None
    invite_status: FriendChallengeInviteStatus
    progress: int = 0
    is_completed: bool = False


class FriendChallengeResponse(BaseModel):
    id: str
    creator_id: str
    creator_name: Optional[str] = None
    title: str
    title_zh: str
    metric_type: FriendChallengeMetric
    target_count: int
    duration_days: int
    emoji: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    accepted_participant_count: int = 0
    pending_participant_count: int = 0
    my_invite_status: FriendChallengeInviteStatus
    my_child_id: Optional[str] = None
    my_progress: int = 0
    my_completed: bool = False
    view_status: FriendChallengeViewStatus
    participants: List[FriendChallengeParticipantResponse] = Field(
        default_factory=list
    )
