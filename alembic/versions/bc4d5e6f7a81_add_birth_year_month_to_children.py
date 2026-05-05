"""add birth year and month to children

Revision ID: bc4d5e6f7a81
Revises: ab3c4d5e6f71
Create Date: 2026-05-01 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "bc4d5e6f7a81"
down_revision = "ab3c4d5e6f71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("children")}

    if "birth_year" not in columns:
        op.add_column("children", sa.Column("birth_year", sa.Integer(), nullable=True))
    if "birth_month" not in columns:
        op.add_column("children", sa.Column("birth_month", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE children
            SET birth_year = EXTRACT(YEAR FROM CURRENT_DATE)::int - age
            WHERE birth_year IS NULL
            """
        )
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("children")}

    if "birth_month" in columns:
        op.drop_column("children", "birth_month")
    if "birth_year" in columns:
        op.drop_column("children", "birth_year")