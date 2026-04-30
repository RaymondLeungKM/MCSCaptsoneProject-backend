"""add community_posts and post_reactions tables

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-04-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE moderationstatus AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """))
    moderationstatus = postgresql.ENUM(name='moderationstatus', create_type=False)

    if 'community_posts' not in inspector.get_table_names():
        op.create_table(
            'community_posts',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('child_id', sa.String(), nullable=False),
            sa.Column('word_id', sa.String(), nullable=True),
            sa.Column('word_text', sa.String(), nullable=True),
            sa.Column('word_text_cantonese', sa.String(), nullable=True),
            sa.Column('caption', sa.Text(), nullable=True),
            sa.Column('image_url', sa.String(), nullable=False),
            sa.Column('is_anonymous', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column(
                'moderation_status',
                moderationstatus,
                nullable=False,
                server_default='pending',
            ),
            sa.Column('moderation_note', sa.Text(), nullable=True),
            sa.Column('moderated_by', sa.String(), nullable=True),
            sa.Column('moderated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('reaction_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['moderated_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )

    community_post_indexes = {index['name'] for index in inspector.get_indexes('community_posts')}
    if 'ix_community_posts_id' not in community_post_indexes:
        op.create_index('ix_community_posts_id', 'community_posts', ['id'])
    if 'ix_community_posts_child_id' not in community_post_indexes:
        op.create_index('ix_community_posts_child_id', 'community_posts', ['child_id'])
    if 'ix_community_posts_word_id' not in community_post_indexes:
        op.create_index('ix_community_posts_word_id', 'community_posts', ['word_id'])
    if 'ix_community_posts_moderation_status' not in community_post_indexes:
        op.create_index('ix_community_posts_moderation_status', 'community_posts', ['moderation_status'])

    if 'post_reactions' not in inspector.get_table_names():
        op.create_table(
            'post_reactions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('post_id', sa.String(), nullable=False),
            sa.Column('child_id', sa.String(), nullable=False),
            sa.Column('reaction_type', sa.String(), nullable=False, server_default='star'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['post_id'], ['community_posts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('post_id', 'child_id', 'reaction_type', name='uq_post_reactions_post_child_type'),
        )

    post_reaction_indexes = {index['name'] for index in inspector.get_indexes('post_reactions')}
    if 'ix_post_reactions_post_id' not in post_reaction_indexes:
        op.create_index('ix_post_reactions_post_id', 'post_reactions', ['post_id'])
    if 'ix_post_reactions_child_id' not in post_reaction_indexes:
        op.create_index('ix_post_reactions_child_id', 'post_reactions', ['child_id'])


def downgrade() -> None:
    op.drop_table('post_reactions')
    op.drop_index('ix_community_posts_moderation_status', table_name='community_posts')
    op.drop_index('ix_community_posts_word_id', table_name='community_posts')
    op.drop_index('ix_community_posts_child_id', table_name='community_posts')
    op.drop_index('ix_community_posts_id', table_name='community_posts')
    op.drop_table('community_posts')
    op.execute("DROP TYPE IF EXISTS moderationstatus")
