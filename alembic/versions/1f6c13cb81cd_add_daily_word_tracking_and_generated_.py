"""add_daily_word_tracking_and_generated_stories

Revision ID: 1f6c13cb81cd
Revises: 20d9c865a041
Create Date: 2026-02-01 01:22:25.888914

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '1f6c13cb81cd'
down_revision = '20d9c865a041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create daily_word_tracking table
    op.create_table(
        'daily_word_tracking',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('child_id', sa.String(), nullable=False),
        sa.Column('word_id', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exposure_count', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('used_actively', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('mastery_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('learned_context', JSONB, nullable=True),
        sa.Column('include_in_story', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('story_priority', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_word_tracking_date'), 'daily_word_tracking', ['date'], unique=False)
    
    # Create generated_stories table
    op.create_table(
        'generated_stories',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('child_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('title_english', sa.String(), nullable=True),
        sa.Column('theme', sa.String(), nullable=True),
        sa.Column('generation_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('content_cantonese', sa.String(), nullable=False),
        sa.Column('content_english', sa.String(), nullable=True),
        sa.Column('jyutping', sa.String(), nullable=True),
        sa.Column('featured_words', JSONB, nullable=True),
        sa.Column('word_usage', JSONB, nullable=True),
        sa.Column('audio_url', sa.String(), nullable=True),
        sa.Column('audio_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('reading_time_minutes', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('difficulty_level', sa.String(), nullable=True, server_default="'easy'"),
        sa.Column('cultural_references', JSONB, nullable=True),
        sa.Column('read_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('is_favorite', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('parent_approved', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('ai_model', sa.String(), nullable=True),
        sa.Column('generation_prompt', sa.String(), nullable=True),
        sa.Column('generation_time_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('generated_stories')
    op.drop_index(op.f('ix_daily_word_tracking_date'), table_name='daily_word_tracking')
    op.drop_table('daily_word_tracking')

