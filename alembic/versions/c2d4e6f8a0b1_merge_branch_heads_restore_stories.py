"""merge branch heads and restore branch story schema

Revision ID: c2d4e6f8a0b1
Revises: a4d1e6b9c2f3, a1b2c3d4e5f6
Create Date: 2026-04-26 18:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'c2d4e6f8a0b1'
down_revision = ('a4d1e6b9c2f3', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if 'stories' not in inspector.get_table_names():
        op.create_table(
            'stories',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('cover_image_url', sa.String(), nullable=True),
            sa.Column('duration', sa.String(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('pages', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('target_words', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('comprehension_questions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('difficulty', sa.String(), nullable=True, server_default='easy'),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
            sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )

    story_indexes = {index['name'] for index in inspector.get_indexes('stories')}
    if op.f('ix_stories_id') not in story_indexes:
        op.create_index(op.f('ix_stories_id'), 'stories', ['id'], unique=False)

    if 'story_progress' not in inspector.get_table_names():
        op.create_table(
            'story_progress',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('child_id', sa.String(), nullable=False),
            sa.Column('story_id', sa.String(), nullable=False),
            sa.Column('completed', sa.Boolean(), nullable=True, server_default='false'),
            sa.Column('repeat_count', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('last_read', sa.DateTime(timezone=True), nullable=True),
            sa.Column('pages_completed', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['child_id'], ['children.id']),
            sa.ForeignKeyConstraint(['story_id'], ['stories.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    story_progress_indexes = {index['name'] for index in inspector.get_indexes('story_progress')}
    if op.f('ix_story_progress_id') not in story_progress_indexes:
        op.create_index(op.f('ix_story_progress_id'), 'story_progress', ['id'], unique=False)


def downgrade() -> None:
    pass