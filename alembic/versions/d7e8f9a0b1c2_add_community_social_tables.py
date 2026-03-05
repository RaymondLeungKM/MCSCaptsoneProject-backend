"""add_community_social_tables

Phase 10 – Community & Social Sharing

Adds:
  community_posts         – child photo check-ins (Epic 10.1)
  post_reactions          – anonymous likes on community posts
  parent_friendships      – parent-level social connections (Epic 10.2)
  community_challenges    – weekly group challenges
  challenge_participations – per-child progress in a challenge

Revision ID: d7e8f9a0b1c2
Revises: c6fbc884e68c
Create Date: 2026-03-05 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b1c2'
down_revision = 'c6fbc884e68c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enum types (PostgreSQL) – use PL/pgSQL exception block so this is
    # idempotent even if a previous (failed) run already created the type.
    # ------------------------------------------------------------------
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE moderationstatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE friendshipstatus AS ENUM ('pending', 'accepted', 'blocked');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE challengestatus AS ENUM ('active', 'completed', 'expired');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # postgresql.ENUM with create_type=False – only references the existing type,
    # never fires a CREATE TYPE DDL event.
    moderationstatus = postgresql.ENUM(name='moderationstatus', create_type=False)
    friendshipstatus = postgresql.ENUM(name='friendshipstatus', create_type=False)
    challengestatus  = postgresql.ENUM(name='challengestatus',  create_type=False)

    # ------------------------------------------------------------------
    # community_posts
    # ------------------------------------------------------------------
    op.create_table(
        'community_posts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('child_id', sa.String(), sa.ForeignKey('children.id', ondelete='CASCADE'), nullable=False),
        sa.Column('word_id',  sa.String(), sa.ForeignKey('words.id',    ondelete='SET NULL'), nullable=True),
        sa.Column('image_url',            sa.String(), nullable=False),
        sa.Column('word_text',            sa.String(), nullable=True),
        sa.Column('word_text_cantonese',  sa.String(), nullable=True),
        sa.Column('caption',              sa.String(), nullable=True),
        sa.Column('is_anonymous',         sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('moderation_status',    moderationstatus, nullable=False, server_default='pending'),
        sa.Column('moderated_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('moderated_at',         sa.DateTime(timezone=True), nullable=True),
        sa.Column('moderation_note',      sa.String(), nullable=True),
        sa.Column('reaction_count',       sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at',           sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',           sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_community_posts_id',              'community_posts', ['id'],               unique=False)
    op.create_index('ix_community_posts_child_id',        'community_posts', ['child_id'],         unique=False)
    op.create_index('ix_community_posts_moderation_status','community_posts', ['moderation_status'], unique=False)

    # ------------------------------------------------------------------
    # post_reactions
    # ------------------------------------------------------------------
    op.create_table(
        'post_reactions',
        sa.Column('id',            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('post_id',       sa.String(), sa.ForeignKey('community_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('child_id',      sa.String(), sa.ForeignKey('children.id',        ondelete='CASCADE'), nullable=False),
        sa.Column('reaction_type', sa.String(), nullable=False, server_default='star'),
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('post_id', 'child_id', name='uq_reaction_post_child'),
    )
    op.create_index('ix_post_reactions_post_id', 'post_reactions', ['post_id'], unique=False)

    # ------------------------------------------------------------------
    # parent_friendships
    # ------------------------------------------------------------------
    op.create_table(
        'parent_friendships',
        sa.Column('id',           sa.String(), primary_key=True),
        sa.Column('requester_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('addressee_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status',       friendshipstatus, nullable=False, server_default='pending'),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('requester_id', 'addressee_id', name='uq_friendship_pair'),
    )
    op.create_index('ix_parent_friendships_id',           'parent_friendships', ['id'],           unique=False)
    op.create_index('ix_parent_friendships_requester_id', 'parent_friendships', ['requester_id'], unique=False)
    op.create_index('ix_parent_friendships_addressee_id', 'parent_friendships', ['addressee_id'], unique=False)

    # ------------------------------------------------------------------
    # community_challenges
    # ------------------------------------------------------------------
    op.create_table(
        'community_challenges',
        sa.Column('id',             sa.String(), primary_key=True),
        sa.Column('title',          sa.String(), nullable=False),
        sa.Column('title_zh',       sa.String(), nullable=True),
        sa.Column('description',    sa.Text(),   nullable=True),
        sa.Column('description_zh', sa.Text(),   nullable=True),
        sa.Column('target_count',   sa.Integer(), nullable=False, server_default='5'),
        sa.Column('category',       sa.String(), nullable=True),
        sa.Column('emoji',          sa.String(), nullable=False, server_default='🏆'),
        sa.Column('status',         challengestatus, nullable=False, server_default='active'),
        sa.Column('starts_at',      sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at',        sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at',     sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_community_challenges_id',     'community_challenges', ['id'],     unique=False)
    op.create_index('ix_community_challenges_status', 'community_challenges', ['status'], unique=False)

    # ------------------------------------------------------------------
    # challenge_participations
    # ------------------------------------------------------------------
    op.create_table(
        'challenge_participations',
        sa.Column('id',           sa.String(), primary_key=True),
        sa.Column('challenge_id', sa.String(), sa.ForeignKey('community_challenges.id', ondelete='CASCADE'), nullable=False),
        sa.Column('child_id',     sa.String(), sa.ForeignKey('children.id',             ondelete='CASCADE'), nullable=False),
        sa.Column('progress',     sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('challenge_id', 'child_id', name='uq_participation_challenge_child'),
    )
    op.create_index('ix_challenge_participations_id',           'challenge_participations', ['id'],           unique=False)
    op.create_index('ix_challenge_participations_challenge_id', 'challenge_participations', ['challenge_id'], unique=False)
    op.create_index('ix_challenge_participations_child_id',     'challenge_participations', ['child_id'],     unique=False)


def downgrade() -> None:
    op.drop_table('challenge_participations')
    op.drop_table('community_challenges')
    op.drop_table('parent_friendships')
    op.drop_table('post_reactions')
    op.drop_table('community_posts')

    # Drop enum types
    sa.Enum(name='challengestatus').drop(op.get_bind(),  checkfirst=True)
    sa.Enum(name='friendshipstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='moderationstatus').drop(op.get_bind(), checkfirst=True)
