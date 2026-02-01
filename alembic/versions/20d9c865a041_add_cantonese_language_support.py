"""add_cantonese_language_support

Revision ID: 20d9c865a041
Revises: 38d721215dde
Create Date: 2026-02-01 00:31:13.191946

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20d9c865a041'
down_revision = '38d721215dde'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Cantonese fields to categories table
    op.add_column('categories', sa.Column('name_cantonese', sa.String(), nullable=True))
    op.add_column('categories', sa.Column('description_cantonese', sa.Text(), nullable=True))
    
    # Add Cantonese fields to words table
    op.add_column('words', sa.Column('word_cantonese', sa.String(), nullable=True))
    op.add_column('words', sa.Column('jyutping', sa.String(), nullable=True))
    op.add_column('words', sa.Column('definition_cantonese', sa.Text(), nullable=True))
    op.add_column('words', sa.Column('example_cantonese', sa.Text(), nullable=True))
    op.add_column('words', sa.Column('audio_url_english', sa.String(), nullable=True))
    
    # Create index on word_cantonese
    op.create_index(op.f('ix_words_word_cantonese'), 'words', ['word_cantonese'], unique=False)
    
    # Add language_preference to children table
    # First create the enum type (using uppercase to match SQLAlchemy enum names)
    op.execute("CREATE TYPE languagepreference AS ENUM ('CANTONESE', 'ENGLISH', 'BILINGUAL')")
    op.add_column('children', sa.Column('language_preference', 
                                        sa.Enum('CANTONESE', 'ENGLISH', 'BILINGUAL', 
                                               name='languagepreference'), 
                                        nullable=True))
    # Set default value for existing rows
    op.execute("UPDATE children SET language_preference = 'CANTONESE' WHERE language_preference IS NULL")


def downgrade() -> None:
    # Remove language_preference from children
    op.drop_column('children', 'language_preference')
    op.execute("DROP TYPE languagepreference")
    
    # Remove index
    op.drop_index(op.f('ix_words_word_cantonese'), table_name='words')
    
    # Remove Cantonese fields from words
    op.drop_column('words', 'audio_url_english')
    op.drop_column('words', 'example_cantonese')
    op.drop_column('words', 'definition_cantonese')
    op.drop_column('words', 'jyutping')
    op.drop_column('words', 'word_cantonese')
    
    # Remove Cantonese fields from categories
    op.drop_column('categories', 'description_cantonese')
    op.drop_column('categories', 'name_cantonese')
