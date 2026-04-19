"""
Community models – Epic 10.1 (Phase 10)

community_posts: child photo check-ins pending parent/admin moderation
post_reactions:  star reactions from other children
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base


class ModerationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CommunityPost(Base):
    """A photo check-in submitted by a child for community sharing."""
    __tablename__ = "community_posts"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="SET NULL"), nullable=True, index=True)

    # Cached display text (denormalised for speed)
    word_text = Column(String, nullable=True)           # English
    word_text_cantonese = Column(String, nullable=True) # Traditional Chinese

    caption = Column(Text, nullable=True)
    image_url = Column(String, nullable=False)

    is_anonymous = Column(Boolean, default=True, nullable=False)
    moderation_status = Column(
        SQLEnum(ModerationStatus, values_callable=lambda x: [e.value for e in x]),
        default=ModerationStatus.PENDING,
        nullable=False,
        index=True,
    )
    moderation_note = Column(Text, nullable=True)
    moderated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    moderated_at = Column(DateTime(timezone=True), nullable=True)

    reaction_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    reactions = relationship("PostReaction", back_populates="post", cascade="all, delete-orphan")


class PostReaction(Base):
    """Star reaction from a child on a community post."""
    __tablename__ = "post_reactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(String, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    child_id = Column(String, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)
    reaction_type = Column(String, default="star", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    post = relationship("CommunityPost", back_populates="reactions")
