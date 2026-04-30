"""add mission catalog fields and mission assignments

Revision ID: ab3c4d5e6f71
Revises: f6a7b8c9d0e1
Create Date: 2026-04-30 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "ab3c4d5e6f71"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


MISSION_STATUS_ENUM = postgresql.ENUM(
    "DRAFT",
    "PUBLISHED",
    "ARCHIVED",
    name="missionstatus",
    create_type=False,
)
MISSION_SURFACE_ENUM = postgresql.ENUM(
    "CHILD",
    "PARENT",
    "BOTH",
    name="missionsurface",
    create_type=False,
)
MISSION_ASSIGNMENT_SOURCE_ENUM = postgresql.ENUM(
    "SYSTEM",
    "ADMIN",
    "PARENT",
    "SEED",
    name="missionassignmentsource",
    create_type=False,
)
MISSION_ASSIGNMENT_STATUS_ENUM = postgresql.ENUM(
    "ASSIGNED",
    "IN_PROGRESS",
    "COMPLETED",
    "SKIPPED",
    "EXPIRED",
    name="missionassignmentstatus",
    create_type=False,
)


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE missionstatus AS ENUM ('DRAFT', 'PUBLISHED', 'ARCHIVED');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE missionsurface AS ENUM ('CHILD', 'PARENT', 'BOTH');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE missionassignmentsource AS ENUM ('SYSTEM', 'ADMIN', 'PARENT', 'SEED');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                CREATE TYPE missionassignmentstatus AS ENUM ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'EXPIRED');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )

    mission_columns = _column_names(inspector, "missions")

    if "slug" not in mission_columns:
        op.add_column("missions", sa.Column("slug", sa.String(), nullable=True))
    if "selection_tags" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column(
                "selection_tags",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if "status" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column(
                "status",
                MISSION_STATUS_ENUM,
                nullable=False,
                server_default=sa.text("'DRAFT'::missionstatus"),
            ),
        )
    if "locale" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column(
                "locale",
                sa.String(),
                nullable=False,
                server_default="zh-HK",
            ),
        )
    if "age_min" not in mission_columns:
        op.add_column("missions", sa.Column("age_min", sa.Integer(), nullable=True))
    if "age_max" not in mission_columns:
        op.add_column("missions", sa.Column("age_max", sa.Integer(), nullable=True))
    if "difficulty" not in mission_columns:
        op.add_column("missions", sa.Column("difficulty", sa.String(), nullable=True))
    if "surface" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column(
                "surface",
                MISSION_SURFACE_ENUM,
                nullable=False,
                server_default=sa.text("'PARENT'::missionsurface"),
            ),
        )
    if "sort_order" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "metadata" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "published_at" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "archived_at" not in mission_columns:
        op.add_column(
            "missions",
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE missions
            SET conversation_prompts = '[]'::jsonb
            WHERE conversation_prompts IS NULL
            """
        )
    )
    op.alter_column(
        "missions",
        "conversation_prompts",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )

    op.execute(
        sa.text(
            """
            UPDATE missions
            SET slug = 'mission-' || SUBSTRING(id FROM 1 FOR 8)
            WHERE slug IS NULL OR BTRIM(slug) = ''
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE missions
            SET status = CASE
                WHEN COALESCE(is_active, true) THEN 'PUBLISHED'::missionstatus
                ELSE 'ARCHIVED'::missionstatus
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE missions
            SET surface = CASE
                WHEN COALESCE(is_offline, false) THEN 'PARENT'::missionsurface
                ELSE 'CHILD'::missionsurface
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE missions
            SET published_at = COALESCE(created_at, NOW())
            WHERE status = 'PUBLISHED'::missionstatus
              AND published_at IS NULL
            """
        )
    )

    op.alter_column("missions", "slug", existing_type=sa.String(), nullable=False)

    inspector = sa.inspect(bind)
    mission_indexes = _index_names(inspector, "missions")
    if "ix_missions_slug" not in mission_indexes:
        op.create_index("ix_missions_slug", "missions", ["slug"], unique=True)

    if "mission_assignments" not in tables:
        op.create_table(
            "mission_assignments",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("child_id", sa.String(), nullable=False),
            sa.Column("mission_id", sa.String(), nullable=False),
            sa.Column("assignment_date", sa.Date(), nullable=False),
            sa.Column(
                "source",
                MISSION_ASSIGNMENT_SOURCE_ENUM,
                nullable=False,
                server_default=sa.text("'SYSTEM'::missionassignmentsource"),
            ),
            sa.Column(
                "status",
                MISSION_ASSIGNMENT_STATUS_ENUM,
                nullable=False,
                server_default=sa.text("'ASSIGNED'::missionassignmentstatus"),
            ),
            sa.Column(
                "surface",
                MISSION_SURFACE_ENUM,
                nullable=False,
                server_default=sa.text("'PARENT'::missionsurface"),
            ),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("selection_reason", sa.Text(), nullable=True),
            sa.Column("selection_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completion_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["child_id"], ["children.id"]),
            sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "child_id",
                "mission_id",
                "assignment_date",
                name="uq_mission_assignment_child_mission_date",
            ),
        )
        op.create_index("ix_mission_assignments_id", "mission_assignments", ["id"], unique=False)
        op.create_index(
            "ix_mission_assignments_child_date",
            "mission_assignments",
            ["child_id", "assignment_date"],
            unique=False,
        )
        op.create_index(
            "ix_mission_assignments_child_status_date",
            "mission_assignments",
            ["child_id", "status", "assignment_date"],
            unique=False,
        )
        op.create_index(
            "ix_mission_assignments_surface_date",
            "mission_assignments",
            ["surface", "assignment_date"],
            unique=False,
        )
        op.create_index(
            "ix_mission_assignments_mission_id",
            "mission_assignments",
            ["mission_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "mission_assignments" in tables:
        assignment_indexes = _index_names(inspector, "mission_assignments")
        for index_name in [
            "ix_mission_assignments_mission_id",
            "ix_mission_assignments_surface_date",
            "ix_mission_assignments_child_status_date",
            "ix_mission_assignments_child_date",
            "ix_mission_assignments_id",
        ]:
            if index_name in assignment_indexes:
                op.drop_index(index_name, table_name="mission_assignments")
        op.drop_table("mission_assignments")

    mission_indexes = _index_names(inspector, "missions")
    if "ix_missions_slug" in mission_indexes:
        op.drop_index("ix_missions_slug", table_name="missions")

    mission_columns = _column_names(inspector, "missions")
    for column_name in [
        "archived_at",
        "published_at",
        "metadata",
        "sort_order",
        "surface",
        "difficulty",
        "age_max",
        "age_min",
        "locale",
        "status",
        "selection_tags",
        "slug",
    ]:
        if column_name in mission_columns:
            op.drop_column("missions", column_name)

    if "conversation_prompts" in mission_columns:
        op.alter_column(
            "missions",
            "conversation_prompts",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=None,
        )

    op.execute(sa.text("DROP TYPE IF EXISTS missionassignmentstatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS missionassignmentsource"))
    op.execute(sa.text("DROP TYPE IF EXISTS missionsurface"))
    op.execute(sa.text("DROP TYPE IF EXISTS missionstatus"))