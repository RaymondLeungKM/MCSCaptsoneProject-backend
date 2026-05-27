"""repair missing community social schema

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-05-27 23:40:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _refresh(bind):
    inspector = sa.inspect(bind)
    return inspector, set(inspector.get_table_names())


def _ensure_index(bind, table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE moderationstatus AS ENUM ('pending', 'approved', 'rejected');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE friendshipstatus AS ENUM ('pending', 'accepted', 'blocked');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE challengestatus AS ENUM ('active', 'completed', 'expired');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )

    moderationstatus = postgresql.ENUM(name="moderationstatus", create_type=False)
    friendshipstatus = postgresql.ENUM(name="friendshipstatus", create_type=False)
    challengestatus = postgresql.ENUM(name="challengestatus", create_type=False)

    inspector, tables = _refresh(bind)

    if "community_posts" not in tables:
        op.create_table(
            "community_posts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "child_id",
                sa.String(),
                sa.ForeignKey("children.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "word_id",
                sa.String(),
                sa.ForeignKey("words.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("image_url", sa.String(), nullable=False),
            sa.Column("word_text", sa.String(), nullable=True),
            sa.Column("word_text_cantonese", sa.String(), nullable=True),
            sa.Column("caption", sa.String(), nullable=True),
            sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "moderation_status",
                moderationstatus,
                nullable=False,
                server_default="pending",
            ),
            sa.Column(
                "moderated_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("moderation_note", sa.String(), nullable=True),
            sa.Column("reaction_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    _ensure_index(bind, "community_posts", "ix_community_posts_id", ["id"])
    _ensure_index(bind, "community_posts", "ix_community_posts_child_id", ["child_id"])
    _ensure_index(bind, "community_posts", "ix_community_posts_word_id", ["word_id"])
    _ensure_index(
        bind,
        "community_posts",
        "ix_community_posts_moderation_status",
        ["moderation_status"],
    )

    inspector, tables = _refresh(bind)
    if "post_reactions" not in tables:
        op.create_table(
            "post_reactions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "post_id",
                sa.String(),
                sa.ForeignKey("community_posts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "child_id",
                sa.String(),
                sa.ForeignKey("children.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("reaction_type", sa.String(), nullable=False, server_default="star"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.UniqueConstraint("post_id", "child_id", name="uq_reaction_post_child"),
        )

    _ensure_index(bind, "post_reactions", "ix_post_reactions_post_id", ["post_id"])
    _ensure_index(bind, "post_reactions", "ix_post_reactions_child_id", ["child_id"])

    inspector, tables = _refresh(bind)
    if "parent_friendships" not in tables:
        op.create_table(
            "parent_friendships",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "requester_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "addressee_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "status",
                friendshipstatus,
                nullable=False,
                server_default="pending",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
        )

    _ensure_index(bind, "parent_friendships", "ix_parent_friendships_id", ["id"])
    _ensure_index(
        bind,
        "parent_friendships",
        "ix_parent_friendships_requester_id",
        ["requester_id"],
    )
    _ensure_index(
        bind,
        "parent_friendships",
        "ix_parent_friendships_addressee_id",
        ["addressee_id"],
    )

    inspector, tables = _refresh(bind)
    if "community_challenges" not in tables:
        op.create_table(
            "community_challenges",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("title_zh", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("description_zh", sa.Text(), nullable=True),
            sa.Column("target_count", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("emoji", sa.String(), nullable=False, server_default="🏆"),
            sa.Column(
                "status",
                challengestatus,
                nullable=False,
                server_default="active",
            ),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )

    _ensure_index(bind, "community_challenges", "ix_community_challenges_id", ["id"])
    _ensure_index(
        bind,
        "community_challenges",
        "ix_community_challenges_status",
        ["status"],
    )

    inspector, tables = _refresh(bind)
    if "challenge_participations" not in tables:
        op.create_table(
            "challenge_participations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "challenge_id",
                sa.String(),
                sa.ForeignKey("community_challenges.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "child_id",
                sa.String(),
                sa.ForeignKey("children.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "challenge_id",
                "child_id",
                name="uq_participation_challenge_child",
            ),
        )

    _ensure_index(
        bind,
        "challenge_participations",
        "ix_challenge_participations_id",
        ["id"],
    )
    _ensure_index(
        bind,
        "challenge_participations",
        "ix_challenge_participations_challenge_id",
        ["challenge_id"],
    )
    _ensure_index(
        bind,
        "challenge_participations",
        "ix_challenge_participations_child_id",
        ["child_id"],
    )


def downgrade() -> None:
    # This migration only repairs missing schema on already-upgraded databases.
    # Downgrading it should not drop tables that may already be in active use.
    pass