"""
Community & Social Sharing models - Phase 10

Epic 10.1: Kid-Friendly Community Feeds
Epic 10.2: Parent Social Networking
"""
from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, DateTime,
    Text, Enum as SQLEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ModerationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FriendshipStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class ChallengeStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Epic 10.1 – Community Feed Models
# ---------------------------------------------------------------------------

class CommunityPost(Base):
    """
    A child's photo check-in that can be shared with the community feed.
    All posts require parental approval (ModerationStatus.APPROVED) before
    appearing in the public feed.  No PII is stored or exposed.
    """
    __tablename__ = "community_posts"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(
        String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id = Column(
        String, ForeignKey("words.id", ondelete="SET NULL"), nullable=True
    )

    # Content
    image_url = Column(String, nullable=False)
    # De-normalised word label (survives word deletion)
    word_text = Column(String)
    word_text_cantonese = Column(String)
    caption = Column(String, nullable=True)  # Short optional caption

    # Privacy – posts never expose real names or locations
    is_anonymous = Column(Boolean, default=True, nullable=False)

    # Moderation – parent (or admin) must approve before the post is visible
    moderation_status = Column(
        SQLEnum(ModerationStatus, name="moderationstatus",
                values_callable=lambda obj: [e.value for e in obj]),
        default=ModerationStatus.PENDING,
        nullable=False,
        index=True,
    )
    moderated_by = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    moderated_at = Column(DateTime(timezone=True), nullable=True)
    moderation_note = Column(String, nullable=True)  # Reason if rejected

    # Cached reaction count (updated on each reaction add/remove)
    reaction_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    child = relationship("Child", foreign_keys=[child_id])
    word = relationship("Word", foreign_keys=[word_id])
    reactions = relationship(
        "PostReaction", back_populates="post", cascade="all, delete-orphan"
    )


class PostReaction(Base):
    """
    A child's anonymous like / star on a community post.
    Each child can react once per post (enforced by unique constraint).
    """
    __tablename__ = "post_reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(
        String, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    child_id = Column(
        String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    reaction_type = Column(String, default="star", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("post_id", "child_id", name="uq_reaction_post_child"),
    )

    # Relationships
    post = relationship("CommunityPost", back_populates="reactions")


# ---------------------------------------------------------------------------
# Epic 10.2 – Parent Social Networking Models
# ---------------------------------------------------------------------------

class ParentFriendship(Base):
    """
    A directional friendship request between two parent accounts.
    The pair (requester_id, addressee_id) is unique; the reverse direction
    should not exist simultaneously (enforced at the service layer).
    """
    __tablename__ = "parent_friendships"

    id = Column(String, primary_key=True, index=True)
    requester_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    addressee_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(
        SQLEnum(FriendshipStatus, name="friendshipstatus",
                values_callable=lambda obj: [e.value for e in obj]),
        default=FriendshipStatus.PENDING,
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
    )

    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    addressee = relationship("User", foreign_keys=[addressee_id])


class CommunityChallenge(Base):
    """
    A weekly (or ad-hoc) challenge visible to all community members.
    E.g. "Find 5 red things this week!"
    """
    __tablename__ = "community_challenges"

    id = Column(String, primary_key=True, index=True)

    # Bilingual title & description
    title = Column(String, nullable=False)
    title_zh = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    description_zh = Column(Text, nullable=True)

    # Challenge parameters
    target_count = Column(Integer, default=5, nullable=False)
    category = Column(String, nullable=True)  # Optional category filter
    emoji = Column(String, default="🏆")

    status = Column(
        SQLEnum(ChallengeStatus, name="challengestatus",
                values_callable=lambda obj: [e.value for e in obj]),
        default=ChallengeStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    participations = relationship(
        "ChallengeParticipation", back_populates="challenge", cascade="all, delete-orphan"
    )


class ChallengeParticipation(Base):
    """
    Tracks a single child's progress towards completing a CommunityChallenge.
    Created automatically when a child's first qualifying event fires.
    """
    __tablename__ = "challenge_participations"

    id = Column(String, primary_key=True, index=True)
    challenge_id = Column(
        String, ForeignKey("community_challenges.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    child_id = Column(
        String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )

    progress = Column(Integer, default=0, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "challenge_id", "child_id", name="uq_participation_challenge_child"
        ),
    )

    # Relationships
    challenge = relationship("CommunityChallenge", back_populates="participations")
    child = relationship("Child", foreign_keys=[child_id])
