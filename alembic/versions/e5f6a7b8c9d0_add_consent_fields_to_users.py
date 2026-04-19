"""add_consent_fields_to_users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('consent_given', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('consent_given_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('consent_camera', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('consent_microphone', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('consent_analytics', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('users', 'consent_analytics')
    op.drop_column('users', 'consent_microphone')
    op.drop_column('users', 'consent_camera')
    op.drop_column('users', 'consent_given_at')
    op.drop_column('users', 'consent_given')
