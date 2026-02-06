"""merge_story_fields_into_generated_stories

Revision ID: 9c7f3d1a2e1b
Revises: b0a67c10f34e
Create Date: 2026-02-06 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c7f3d1a2e1b'
down_revision = 'b0a67c10f34e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('generated_stories', sa.Column('vocab_used', sa.String(length=500), nullable=True))
    op.add_column('generated_stories', sa.Column('story_text', sa.Text(), nullable=True))
    op.add_column('generated_stories', sa.Column('story_text_ssml', sa.Text(), nullable=True))
    op.add_column('generated_stories', sa.Column('story_generate_provdier', sa.String(length=100), nullable=True))
    op.add_column('generated_stories', sa.Column('story_generate_model', sa.String(length=100), nullable=True))
    op.add_column('generated_stories', sa.Column('audio_filename', sa.String(length=255), nullable=True))
    op.add_column('generated_stories', sa.Column('audio_generate_provider', sa.String(length=100), nullable=True))
    op.add_column('generated_stories', sa.Column('audio_generate_voice_name', sa.String(length=100), nullable=True))
    op.add_column(
        'generated_stories',
        sa.Column('generated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.add_column('generated_stories', sa.Column('generated_by', sa.String(length=100), nullable=True))

    op.execute("UPDATE generated_stories SET story_text = COALESCE(story_text, content_cantonese)")
    op.execute("UPDATE generated_stories SET story_text_ssml = COALESCE(story_text_ssml, content_cantonese)")
    op.execute("UPDATE generated_stories SET audio_filename = COALESCE(audio_filename, '')")
    op.execute(
        "UPDATE generated_stories SET generated_at = COALESCE(generated_at, generation_date, created_at, CURRENT_TIMESTAMP)"
    )

    op.alter_column('generated_stories', 'story_text', nullable=False)
    op.alter_column('generated_stories', 'story_text_ssml', nullable=False)
    op.alter_column('generated_stories', 'audio_filename', nullable=False)
    op.alter_column('generated_stories', 'generated_at', nullable=False)

    op.execute("DROP TABLE IF EXISTS story")
    op.execute("DROP SEQUENCE IF EXISTS story_story_id_seq")


def downgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS story_story_id_seq")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS story (
            story_id BIGINT NOT NULL DEFAULT nextval('story_story_id_seq'::regclass),
            vocab_used VARCHAR(500),
            story_text TEXT NOT NULL,
            story_text_ssml TEXT NOT NULL,
            story_generate_provdier VARCHAR(100),
            story_generate_model VARCHAR(100),
            audio_filename VARCHAR(255) NOT NULL,
            audio_generate_provider VARCHAR(100),
            audio_generate_voice_name VARCHAR(100),
            generated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            generated_by VARCHAR(100),
            PRIMARY KEY (story_id)
        )
        """
    )

    op.execute("ALTER SEQUENCE story_story_id_seq OWNED BY story.story_id")

    op.drop_column('generated_stories', 'generated_by')
    op.drop_column('generated_stories', 'generated_at')
    op.drop_column('generated_stories', 'audio_generate_voice_name')
    op.drop_column('generated_stories', 'audio_generate_provider')
    op.drop_column('generated_stories', 'audio_filename')
    op.drop_column('generated_stories', 'story_generate_model')
    op.drop_column('generated_stories', 'story_generate_provdier')
    op.drop_column('generated_stories', 'story_text_ssml')
    op.drop_column('generated_stories', 'story_text')
    op.drop_column('generated_stories', 'vocab_used')
