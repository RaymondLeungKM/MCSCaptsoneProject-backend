"""add_game_sessions_table

Revision ID: d4e5f6a7b8c9
Revises: c6fbc884e68c
Create Date: 2026-03-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c6fbc884e68c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'game_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('child_id', sa.String(), nullable=False),
        sa.Column('game_id', sa.String(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_score', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('duration_seconds', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('words_seen', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('words_correct', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('stars', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('xp_earned', sa.Integer(), nullable=True, server_default='0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ['child_id'], ['children.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_game_sessions_id'), 'game_sessions', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_game_sessions_child_id'), 'game_sessions', ['child_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_game_sessions_child_id'), table_name='game_sessions')
    op.drop_index(op.f('ix_game_sessions_id'), table_name='game_sessions')
    op.drop_table('game_sessions')
