"""add extended generated_stories_log columns for standalone story generator

Revision ID: d1b2c3e4f5a6
Revises: a9b0c1d2e3f4, e7f8a9b0c1d2
Create Date: 2026-06-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d1b2c3e4f5a6"
down_revision = ("a9b0c1d2e3f4", "e7f8a9b0c1d2")
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "generated_stories_log" not in tables:
        return

    columns = _column_names(inspector, "generated_stories_log")

    if "child_id" not in columns:
        op.add_column("generated_stories_log", sa.Column("child_id", sa.String(), nullable=True))
    if "param_gen_date" not in columns:
        op.add_column("generated_stories_log", sa.Column("param_gen_date", sa.Date(), nullable=True))
    if "param_story_cat" not in columns:
        op.add_column("generated_stories_log", sa.Column("param_story_cat", sa.String(), nullable=True))

    if "story1_text_org_from_llm" not in columns:
        op.add_column("generated_stories_log", sa.Column("story1_text_org_from_llm", sa.Text(), nullable=True))
    if "story1_text_polished" not in columns:
        op.add_column("generated_stories_log", sa.Column("story1_text_polished", sa.Text(), nullable=True))
    if "story2_text_org_from_llm" not in columns:
        op.add_column("generated_stories_log", sa.Column("story2_text_org_from_llm", sa.Text(), nullable=True))
    if "story2_text_polished" not in columns:
        op.add_column("generated_stories_log", sa.Column("story2_text_polished", sa.Text(), nullable=True))

    if "evaluation_CoT_JSON_story1" not in columns:
        op.add_column(
            "generated_stories_log",
            sa.Column("evaluation_CoT_JSON_story1", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "evaluation_metrics_JSON_story1" not in columns:
        op.add_column(
            "generated_stories_log",
            sa.Column("evaluation_metrics_JSON_story1", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "evaluation_CoT_JSON_story2" not in columns:
        op.add_column(
            "generated_stories_log",
            sa.Column("evaluation_CoT_JSON_story2", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "evaluation_metrics_JSON_story2" not in columns:
        op.add_column(
            "generated_stories_log",
            sa.Column("evaluation_metrics_JSON_story2", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    if "evaluation_final_score_story1" not in columns:
        op.add_column("generated_stories_log", sa.Column("evaluation_final_score_story1", sa.Float(), nullable=True))
    if "evaluation_final_score_story2" not in columns:
        op.add_column("generated_stories_log", sa.Column("evaluation_final_score_story2", sa.Float(), nullable=True))

    if "story_generate_model_story1" not in columns:
        op.add_column("generated_stories_log", sa.Column("story_generate_model_story1", sa.String(), nullable=True))
    if "story_generate_model_story2" not in columns:
        op.add_column("generated_stories_log", sa.Column("story_generate_model_story2", sa.String(), nullable=True))
    if "story_generate_model_judge" not in columns:
        op.add_column("generated_stories_log", sa.Column("story_generate_model_judge", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "generated_stories_log" not in tables:
        return

    columns = _column_names(inspector, "generated_stories_log")

    for column_name in [
        "story_generate_model_judge",
        "story_generate_model_story2",
        "story_generate_model_story1",
        "evaluation_final_score_story2",
        "evaluation_final_score_story1",
        "evaluation_metrics_JSON_story2",
        "evaluation_CoT_JSON_story2",
        "evaluation_metrics_JSON_story1",
        "evaluation_CoT_JSON_story1",
        "story2_text_polished",
        "story2_text_org_from_llm",
        "story1_text_polished",
        "story1_text_org_from_llm",
        "param_story_cat",
        "param_gen_date",
        "child_id",
    ]:
        if column_name in columns:
            op.drop_column("generated_stories_log", column_name)
