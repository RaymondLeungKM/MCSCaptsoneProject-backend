"""add friend challenge tables

Revision ID: c8d9e0f1a2b3
Revises: c9d0e1f2a3b4
Create Date: 2026-05-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c8d9e0f1a2b3"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE friendchallengemetric AS ENUM (
                'practice_days',
                'new_words',
                'active_words'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE friendchallengeinvitestatus AS ENUM (
                'pending',
                'accepted',
                'declined'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    metric_enum = postgresql.ENUM(
        name="friendchallengemetric",
        create_type=False,
    )
    invite_enum = postgresql.ENUM(
        name="friendchallengeinvitestatus",
        create_type=False,
    )

    if "friend_challenges" not in tables:
        op.create_table(
            "friend_challenges",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "creator_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("title_zh", sa.String(), nullable=False),
            sa.Column("metric_type", metric_enum, nullable=False),
            sa.Column("target_count", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("duration_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("emoji", sa.String(), nullable=False, server_default="🤝"),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )
    friend_challenges_indexes = {
        index["name"] for index in inspector.get_indexes("friend_challenges")
    }
    if "ix_friend_challenges_id" not in friend_challenges_indexes:
        op.create_index("ix_friend_challenges_id", "friend_challenges", ["id"], unique=False)
    if "ix_friend_challenges_creator_id" not in friend_challenges_indexes:
        op.create_index(
            "ix_friend_challenges_creator_id",
            "friend_challenges",
            ["creator_id"],
            unique=False,
        )
    if "ix_friend_challenges_metric_type" not in friend_challenges_indexes:
        op.create_index(
            "ix_friend_challenges_metric_type",
            "friend_challenges",
            ["metric_type"],
            unique=False,
        )

    if "friend_challenge_participants" not in tables:
        op.create_table(
            "friend_challenge_participants",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "challenge_id",
                sa.String(),
                sa.ForeignKey("friend_challenges.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "child_id",
                sa.String(),
                sa.ForeignKey("children.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "invite_status",
                invite_enum,
                nullable=False,
                server_default="pending",
            ),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "challenge_id",
                "parent_id",
                name="uq_friend_challenge_participant",
            ),
        )
    participant_indexes = {
        index["name"]
        for index in inspector.get_indexes("friend_challenge_participants")
    }
    if "ix_friend_challenge_participants_id" not in participant_indexes:
        op.create_index(
            "ix_friend_challenge_participants_id",
            "friend_challenge_participants",
            ["id"],
            unique=False,
        )
    if "ix_friend_challenge_participants_challenge_id" not in participant_indexes:
        op.create_index(
            "ix_friend_challenge_participants_challenge_id",
            "friend_challenge_participants",
            ["challenge_id"],
            unique=False,
        )
    if "ix_friend_challenge_participants_parent_id" not in participant_indexes:
        op.create_index(
            "ix_friend_challenge_participants_parent_id",
            "friend_challenge_participants",
            ["parent_id"],
            unique=False,
        )
    if "ix_friend_challenge_participants_child_id" not in participant_indexes:
        op.create_index(
            "ix_friend_challenge_participants_child_id",
            "friend_challenge_participants",
            ["child_id"],
            unique=False,
        )
    if "ix_friend_challenge_participants_invite_status" not in participant_indexes:
        op.create_index(
            "ix_friend_challenge_participants_invite_status",
            "friend_challenge_participants",
            ["invite_status"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("friend_challenge_participants")
    op.drop_table("friend_challenges")

    sa.Enum(name="friendchallengeinvitestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="friendchallengemetric").drop(op.get_bind(), checkfirst=True)