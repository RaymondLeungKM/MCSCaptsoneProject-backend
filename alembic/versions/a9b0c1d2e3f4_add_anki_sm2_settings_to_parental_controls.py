"""add_anki_sm2_settings_to_parental_controls

Adds Anki-modified SM-2 algorithm tuning columns to the parental_controls
table so parents can customise how the spaced-repetition schedule behaves
for their child.

New columns
-----------
sr_easy_bonus            float  – extra interval multiplier on an "Easy" answer (default 1.3)
sr_interval_modifier     float  – global scale applied to every computed interval (default 1.0)
sr_max_interval_days     int    – hard ceiling on any single interval (default 36500 = ~100 yr)
sr_graduating_interval   int    – interval (days) when a new card is first answered correctly (default 1)
sr_easy_interval         int    – interval (days) granted on an "Easy" answer for new cards (default 4)
sr_lapse_interval_pct    float  – fraction of the old interval to keep after a lapse/Again (default 0.0)

Revision ID: a9b0c1d2e3f4
Revises: f1a2b3c4d5e6
Create Date: 2026-06-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9b0c1d2e3f4'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('parental_controls', sa.Column('sr_easy_bonus',          sa.Float(),   nullable=False, server_default='1.3'))
    op.add_column('parental_controls', sa.Column('sr_interval_modifier',   sa.Float(),   nullable=False, server_default='1.0'))
    op.add_column('parental_controls', sa.Column('sr_max_interval_days',   sa.Integer(), nullable=False, server_default='36500'))
    op.add_column('parental_controls', sa.Column('sr_graduating_interval', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('parental_controls', sa.Column('sr_easy_interval',       sa.Integer(), nullable=False, server_default='4'))
    op.add_column('parental_controls', sa.Column('sr_lapse_interval_pct',  sa.Float(),   nullable=False, server_default='0.0'))


def downgrade() -> None:
    op.drop_column('parental_controls', 'sr_lapse_interval_pct')
    op.drop_column('parental_controls', 'sr_easy_interval')
    op.drop_column('parental_controls', 'sr_graduating_interval')
    op.drop_column('parental_controls', 'sr_max_interval_days')
    op.drop_column('parental_controls', 'sr_interval_modifier')
    op.drop_column('parental_controls', 'sr_easy_bonus')
