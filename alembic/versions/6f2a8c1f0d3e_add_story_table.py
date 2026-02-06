"""add_story_table

Revision ID: 6f2a8c1f0d3e
Revises: 1f6c13cb81cd
Create Date: 2026-02-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f2a8c1f0d3e'
down_revision = '1f6c13cb81cd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS story_story_id_seq")

    op.create_table(
        'story',
        sa.Column(
            'story_id',
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('story_story_id_seq'::regclass)"),
        ),
        sa.Column('vocab_used', sa.String(length=500), nullable=True),
        sa.Column('story_text', sa.Text(), nullable=False),
        sa.Column('story_text_ssml', sa.Text(), nullable=False),
        sa.Column('story_generate_provdier', sa.String(length=100), nullable=True),
        sa.Column('story_generate_model', sa.String(length=100), nullable=True),
        sa.Column('audio_filename', sa.String(length=255), nullable=False),
        sa.Column('audio_generate_provider', sa.String(length=100), nullable=True),
        sa.Column('audio_generate_voice_name', sa.String(length=100), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('generated_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('story_id'),
    )

    op.execute("ALTER SEQUENCE story_story_id_seq OWNED BY story.story_id")


def downgrade() -> None:
    op.drop_table('story')
    op.execute("DROP SEQUENCE IF EXISTS story_story_id_seq")
