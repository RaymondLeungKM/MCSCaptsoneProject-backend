"""add story theme column

Revision ID: c1d2e3f4a5b6
Revises: b0a67c10f34e
Create Date: 2026-06-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "b0a67c10f34e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if "stories" in table_names:
        story_columns = {column["name"] for column in inspector.get_columns("stories")}
        if "theme" not in story_columns:
            op.add_column("stories", sa.Column("theme", sa.String(), nullable=True))

    if "generated_stories" in table_names:
        generated_columns = {
            column["name"] for column in inspector.get_columns("generated_stories")
        }

        if "story_type" not in generated_columns:
            op.add_column(
                "generated_stories",
                sa.Column(
                    "story_type",
                    sa.String(),
                    nullable=False,
                    server_default="generated",
                ),
            )

        if "is_active" not in generated_columns:
            op.add_column(
                "generated_stories",
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("true"),
                ),
            )

        if "sort_order" not in generated_columns:
            op.add_column(
                "generated_stories",
                sa.Column(
                    "sort_order",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )

        op.execute(
            "UPDATE generated_stories SET story_type = COALESCE(story_type, 'generated')"
        )
        op.execute("UPDATE generated_stories SET is_active = COALESCE(is_active, true)")
        op.execute("UPDATE generated_stories SET sort_order = COALESCE(sort_order, 0)")

        op.alter_column("generated_stories", "story_type", server_default=None)
        op.alter_column("generated_stories", "is_active", server_default=None)
        op.alter_column("generated_stories", "sort_order", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if "generated_stories" in table_names:
        generated_columns = {
            column["name"] for column in inspector.get_columns("generated_stories")
        }
        if "sort_order" in generated_columns:
            op.drop_column("generated_stories", "sort_order")
        if "is_active" in generated_columns:
            op.drop_column("generated_stories", "is_active")
        if "story_type" in generated_columns:
            op.drop_column("generated_stories", "story_type")

    if "stories" in table_names:
        story_columns = {column["name"] for column in inspector.get_columns("stories")}
        if "theme" in story_columns:
            op.drop_column("stories", "theme")