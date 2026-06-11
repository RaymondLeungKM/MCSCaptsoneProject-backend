"""allow null child_id for curated stories

Revision ID: e7f8a9b0c1d2
Revises: c1d2e3f4a5b6, c8d9e0f1a2b3
Create Date: 2026-06-12 00:42:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7f8a9b0c1d2"
down_revision = ("c1d2e3f4a5b6", "c8d9e0f1a2b3")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "generated_stories" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("generated_stories")}
    child_col = columns.get("child_id")
    if not child_col:
        return

    if not child_col.get("nullable", True):
        op.alter_column(
            "generated_stories",
            "child_id",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "generated_stories" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("generated_stories")}
    child_col = columns.get("child_id")
    if not child_col:
        return

    if child_col.get("nullable", False):
        null_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM generated_stories WHERE child_id IS NULL")
        ).scalar_one()

        if null_count:
            raise RuntimeError(
                "Cannot downgrade: generated_stories contains rows with NULL child_id."
            )

        op.alter_column(
            "generated_stories",
            "child_id",
            existing_type=sa.String(),
            nullable=False,
        )
