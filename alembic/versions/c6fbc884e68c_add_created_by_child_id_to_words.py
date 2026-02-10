"""add_created_by_child_id_to_words

Revision ID: c6fbc884e68c
Revises: 7d1dc1c04fdd
Create Date: 2026-02-10 16:17:41.508695

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6fbc884e68c'
down_revision = '7d1dc1c04fdd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_by_child_id column to words table
    op.add_column('words', sa.Column('created_by_child_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_words_created_by_child_id'), 'words', ['created_by_child_id'], unique=False)
    op.create_foreign_key('fk_words_created_by_child_id', 'words', 'children', ['created_by_child_id'], ['id'])


def downgrade() -> None:
    # Remove created_by_child_id column from words table
    op.drop_constraint('fk_words_created_by_child_id', 'words', type_='foreignkey')
    op.drop_index(op.f('ix_words_created_by_child_id'), table_name='words')
    op.drop_column('words', 'created_by_child_id')
