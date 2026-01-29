"""add_unique_constraint_word_progress

Revision ID: 38d721215dde
Revises: c3391ff732ce
Create Date: 2026-01-27 23:17:04.120738

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '38d721215dde'
down_revision = 'c3391ff732ce'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint on (child_id, word_id) to prevent duplicate progress records
    op.create_unique_constraint(
        'uq_word_progress_child_word',
        'word_progress',
        ['child_id', 'word_id']
    )


def downgrade() -> None:
    # Remove the unique constraint
    op.drop_constraint('uq_word_progress_child_word', 'word_progress', type_='unique')
