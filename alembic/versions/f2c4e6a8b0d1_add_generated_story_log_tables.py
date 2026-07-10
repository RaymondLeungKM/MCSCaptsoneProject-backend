"""add generated story log tables

Revision ID: f2c4e6a8b0d1
Revises: 1b2c3d4e5f7a
Create Date: 2026-07-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f2c4e6a8b0d1"
down_revision = "1b2c3d4e5f7a"
branch_labels = None
depends_on = None
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "generated_stories_log" not in table_names:
        op.create_table(
            "generated_stories_log",
            sa.Column("story_id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("child_id", sa.String(length=100), nullable=True),
            sa.Column("param_gen_date", sa.Date(), nullable=True),
            sa.Column("param_story_cat", sa.String(length=100), nullable=True),
            sa.Column("vocab_used", sa.String(length=500), nullable=True),
            sa.Column("story_text", sa.Text(), nullable=False),
            sa.Column("story1_text_org_from_llm", sa.Text(), nullable=True),
            sa.Column("story1_text_polished", sa.Text(), nullable=True),
            sa.Column("story2_text_org_from_llm", sa.Text(), nullable=True),
            sa.Column("story2_text_polished", sa.Text(), nullable=True),
            sa.Column("evaluation_CoT_JSON_story1", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("evaluation_metrics_JSON_story1", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("evaluation_CoT_JSON_story2", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("evaluation_metrics_JSON_story2", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("evaluation_final_score_story1", sa.Float(), nullable=True),
            sa.Column("evaluation_final_score_story2", sa.Float(), nullable=True),
            sa.Column("story_text_ssml", sa.Text(), nullable=False),
            sa.Column("story_generate_provdier", sa.String(length=100), nullable=True),
            sa.Column("story_generate_model", sa.String(length=100), nullable=True),
            sa.Column("story_generate_model_story1", sa.String(length=255), nullable=True),
            sa.Column("story_generate_model_story2", sa.String(length=255), nullable=True),
            sa.Column("story_generate_model_judge", sa.String(length=255), nullable=True),
            sa.Column("audio_filename", sa.String(length=255), nullable=False),
            sa.Column("audio_generate_provider", sa.String(length=100), nullable=True),
            sa.Column("audio_generate_voice_name", sa.String(length=100), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("generated_by", sa.String(length=100), nullable=True),
            sa.PrimaryKeyConstraint("story_id", name="generated_stories_log_pkey"),
        )
    if "generated_stories_batch_log" not in table_names:
        op.create_table(
            "generated_stories_batch_log",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("child_id", sa.String(length=100), nullable=True),
            sa.Column("batch_datetime", sa.String(length=50), nullable=True),
            sa.Column("story_cat", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("error_code", sa.String(length=50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id", name="generated_stories_batch_log_pkey"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "generated_stories_batch_log" in table_names:
        op.drop_table("generated_stories_batch_log")

    if "generated_stories_log" in table_names:
        op.drop_table("generated_stories_log")
