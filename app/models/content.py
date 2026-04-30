"""
Content models - Stories, Games, Missions
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Date, DateTime, Text, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
import enum

from app.db.base import Base


class PromptType(str, enum.Enum):
    OPEN_ENDED = "open-ended"
    RECALL = "recall"
    PREDICTION = "prediction"
    CONNECTION = "connection"


class GameType(str, enum.Enum):
    MATCHING = "matching"
    ISPY = "ispy"
    SPELLING = "spelling"
    PRONUNCIATION = "pronunciation"
    CHARADES = "charades"
    ACTIONS = "actions"
    SCAVENGER = "scavenger"


class MissionContext(str, enum.Enum):
    MEALTIME = "mealtime"
    BEDTIME = "bedtime"
    PLAYTIME = "playtime"
    OUTDOOR = "outdoor"
    SHOPPING = "shopping"
    GENERAL = "general"


class MissionStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MissionSurface(str, enum.Enum):
    CHILD = "child"
    PARENT = "parent"
    BOTH = "both"


class MissionAssignmentSource(str, enum.Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    PARENT = "parent"
    SEED = "seed"


class MissionAssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class Story(Base):
    """Interactive story"""
    __tablename__ = "stories"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    cover_image_url = Column(String)
    duration = Column(String)  # e.g., "5 min"
    description = Column(Text)
    
    # Story content stored as JSONB
    pages = Column(JSONB)  # Array of page objects
    target_words = Column(JSONB)  # Array of word IDs
    comprehension_questions = Column(JSONB)  # Array of question objects
    
    difficulty = Column(String, default="easy")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    progress = relationship("StoryProgress", back_populates="story")


class StoryProgress(Base):
    """Child's progress on stories"""
    __tablename__ = "story_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    story_id = Column(String, ForeignKey("stories.id"), nullable=False)
    
    completed = Column(Boolean, default=False)
    repeat_count = Column(Integer, default=0)
    last_read = Column(DateTime(timezone=True))
    pages_completed = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    story = relationship("Story", back_populates="progress")


class Game(Base):
    """Learning game"""
    __tablename__ = "games"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    icon = Column(String, default="🎮")
    color = Column(String, default="bg-sky")
    
    game_type = Column(SQLEnum(GameType), nullable=False)
    
    # Game characteristics
    physical_activity = Column(Boolean, default=False)
    multi_sensory = Column(Boolean, default=False)
    parent_participation = Column(Boolean, default=False)
    
    # Game configuration
    min_words = Column(Integer, default=3)
    max_words = Column(Integer, default=10)
    difficulty = Column(String, default="easy")
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Mission(Base):
    """Daily or offline mission"""
    __tablename__ = "missions"
    
    id = Column(String, primary_key=True, index=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
    context = Column(SQLEnum(MissionContext, name="missioncontext"), default=MissionContext.GENERAL)
    target_words = Column(JSONB)  # Array of word IDs
    conversation_prompts = Column(JSONB, nullable=False, default=list)  # Array of prompt strings
    selection_tags = Column(JSONB, nullable=False, default=list)
    
    is_offline = Column(Boolean, default=False)  # True for offline missions
    status = Column(SQLEnum(MissionStatus, name="missionstatus"), nullable=False, default=MissionStatus.DRAFT)
    locale = Column(String, nullable=False, default="zh-HK")
    age_min = Column(Integer)
    age_max = Column(Integer)
    difficulty = Column(String)
    surface = Column(SQLEnum(MissionSurface, name="missionsurface"), nullable=False, default=MissionSurface.PARENT)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    catalog_metadata = Column("metadata", JSONB)
    published_at = Column(DateTime(timezone=True))
    archived_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MissionAssignment(Base):
    """Mission assigned to a child on a given date"""
    __tablename__ = "mission_assignments"

    id = Column(String, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False, index=True)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False, index=True)
    assignment_date = Column(Date, nullable=False, index=True)

    source = Column(
        SQLEnum(MissionAssignmentSource, name="missionassignmentsource"),
        nullable=False,
        default=MissionAssignmentSource.SYSTEM,
    )
    status = Column(
        SQLEnum(MissionAssignmentStatus, name="missionassignmentstatus"),
        nullable=False,
        default=MissionAssignmentStatus.ASSIGNED,
    )
    surface = Column(
        SQLEnum(MissionSurface, name="missionsurface"),
        nullable=False,
        default=MissionSurface.PARENT,
    )
    priority = Column(Integer, nullable=False, default=100)
    selection_reason = Column(Text)
    selection_metadata = Column(JSONB)
    available_from = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    skipped_at = Column(DateTime(timezone=True))
    completion_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "child_id",
            "mission_id",
            "assignment_date",
            name="uq_mission_assignment_child_mission_date",
        ),
    )


class MissionProgress(Base):
    """Child's mission completion"""
    __tablename__ = "mission_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(String, ForeignKey("children.id"), nullable=False)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False)
    
    completed = Column(Boolean, default=False)
    completed_date = Column(DateTime(timezone=True))
    parent_notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
