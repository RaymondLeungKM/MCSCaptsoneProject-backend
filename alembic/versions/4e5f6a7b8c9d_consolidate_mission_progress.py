"""consolidate mission progress into assignments

Revision ID: 4e5f6a7b8c9d
Revises: 3d4e5f6a7b8c
Create Date: 2026-07-14 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "4e5f6a7b8c9d"
down_revision = "3d4e5f6a7b8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "mission_progress" not in inspector.get_table_names():
        return

    # A legacy row has no assignment identity. Its HKT completion day is the
    # only reliable historical key, so it is merged into that dated assignment.
    op.execute(
        sa.text(
            """
            WITH ranked_progress AS (
                SELECT DISTINCT ON (
                    child_id,
                    mission_id,
                    ((COALESCE(completed_date, created_at, NOW()) AT TIME ZONE 'Asia/Hong_Kong')::date)
                )
                    id,
                    child_id,
                    mission_id,
                    completed,
                    completed_date,
                    parent_notes,
                    created_at,
                    ((COALESCE(completed_date, created_at, NOW()) AT TIME ZONE 'Asia/Hong_Kong')::date)
                        AS assignment_date
                FROM mission_progress
                ORDER BY
                    child_id,
                    mission_id,
                    ((COALESCE(completed_date, created_at, NOW()) AT TIME ZONE 'Asia/Hong_Kong')::date),
                    completed_date DESC NULLS LAST,
                    id DESC
            )
            INSERT INTO mission_assignments (
                id,
                child_id,
                mission_id,
                assignment_date,
                source,
                status,
                surface,
                priority,
                selection_reason,
                started_at,
                completed_at,
                completion_notes,
                created_at
            )
            SELECT
                'legacy-mission-progress-' || progress.id,
                progress.child_id,
                progress.mission_id,
                progress.assignment_date,
                'SEED'::missionassignmentsource,
                CASE
                    WHEN COALESCE(progress.completed, false)
                        THEN 'COMPLETED'::missionassignmentstatus
                    ELSE 'ASSIGNED'::missionassignmentstatus
                END,
                COALESCE(mission.surface, 'PARENT'::missionsurface),
                COALESCE(mission.sort_order, 100),
                'Migrated from legacy mission_progress',
                CASE
                    WHEN COALESCE(progress.completed, false)
                        THEN COALESCE(progress.completed_date, progress.created_at)
                    ELSE NULL
                END,
                CASE
                    WHEN COALESCE(progress.completed, false)
                        THEN COALESCE(progress.completed_date, progress.created_at)
                    ELSE NULL
                END,
                progress.parent_notes,
                progress.created_at
            FROM ranked_progress AS progress
            JOIN missions AS mission ON mission.id = progress.mission_id
            ON CONFLICT (child_id, mission_id, assignment_date) DO UPDATE
            SET
                status = CASE
                    WHEN EXCLUDED.status = 'COMPLETED'::missionassignmentstatus
                        THEN EXCLUDED.status
                    ELSE mission_assignments.status
                END,
                started_at = COALESCE(
                    mission_assignments.started_at,
                    EXCLUDED.started_at
                ),
                completed_at = COALESCE(
                    mission_assignments.completed_at,
                    EXCLUDED.completed_at
                ),
                completion_notes = COALESCE(
                    mission_assignments.completion_notes,
                    EXCLUDED.completion_notes
                )
            """
        )
    )

    index_names = {index["name"] for index in inspector.get_indexes("mission_progress")}
    if "ix_mission_progress_id" in index_names:
        op.drop_index("ix_mission_progress_id", table_name="mission_progress")
    op.drop_table("mission_progress")


def downgrade() -> None:
    op.create_table(
        "mission_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("child_id", sa.String(), nullable=False),
        sa.Column("mission_id", sa.String(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=True),
        sa.Column("completed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["child_id"], ["children.id"]),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mission_progress_id", "mission_progress", ["id"], unique=False)