"""add_phase8_advanced_ai_tables

Phase 8 – Advanced AI & Personalization

Adds:
  word_relationships      – knowledge-graph edges between vocabulary words (Epic 8.1)
  spaced_repetition_cards – per-child SM-2 spaced-repetition state (Epic 8.2)

Revision ID: f1a2b3c4d5e6
Revises: d7e8f9a0b1c2
Create Date: 2026-03-05 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enum types (PostgreSQL) – idempotent via PL/pgSQL exception block.
    # postgresql.ENUM with create_type=False is used in table definitions
    # so SQLAlchemy never fires a second CREATE TYPE event.
    # ------------------------------------------------------------------
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE relationshiptype AS ENUM (
                'semantic', 'category', 'phonetic', 'contextual', 'opposite'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    relationship_type_enum = postgresql.ENUM(name='relationshiptype', create_type=False)

    # ------------------------------------------------------------------
    # word_relationships  (Epic 8.1 knowledge graph)
    # ------------------------------------------------------------------
    op.create_table(
        'word_relationships',
        sa.Column('id',                sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column('word_id',           sa.String(),   sa.ForeignKey('words.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('related_word_id',   sa.String(),   sa.ForeignKey('words.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('relationship_type', relationship_type_enum, nullable=False,
                  server_default='semantic'),
        sa.Column('strength',          sa.Float(),    nullable=False, server_default='0.7'),
        sa.Column('source',            sa.String(),   nullable=False, server_default='system'),
        sa.Column('created_at',        sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',        sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('word_id', 'related_word_id', 'relationship_type',
                            name='uq_word_relationship'),
    )
    op.create_index('ix_word_relationships_word_id',         'word_relationships', ['word_id'],         unique=False)
    op.create_index('ix_word_relationships_related_word_id', 'word_relationships', ['related_word_id'], unique=False)

    # ------------------------------------------------------------------
    # spaced_repetition_cards  (Epic 8.2 SM-2 algorithm)
    # ------------------------------------------------------------------
    op.create_table(
        'spaced_repetition_cards',
        sa.Column('id',              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('child_id',        sa.String(),  sa.ForeignKey('children.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('word_id',         sa.String(),  sa.ForeignKey('words.id',    ondelete='CASCADE'),
                  nullable=False),
        # SM-2 state
        sa.Column('easiness_factor', sa.Float(),   nullable=False, server_default='2.5'),
        sa.Column('interval',        sa.Integer(), nullable=False, server_default='1'),
        sa.Column('repetitions',     sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_quality',    sa.Integer(), nullable=True),
        # Scheduling
        sa.Column('next_review',     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('last_reviewed',   sa.DateTime(timezone=True), nullable=True),
        # Flags
        sa.Column('is_new',          sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_graduated',    sa.Boolean(), nullable=False, server_default='false'),
        # Timestamps
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',      sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('child_id', 'word_id', name='uq_sr_card_child_word'),
    )
    op.create_index('ix_sr_cards_child_id',    'spaced_repetition_cards', ['child_id'],    unique=False)
    op.create_index('ix_sr_cards_next_review', 'spaced_repetition_cards', ['next_review'], unique=False)


def downgrade() -> None:
    op.drop_table('spaced_repetition_cards')
    op.drop_table('word_relationships')

    # Drop PostgreSQL enum types
    sa.Enum(name='relationshiptype').drop(op.get_bind(), checkfirst=True)
