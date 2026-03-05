#!/usr/bin/env python3
"""Fix missing database tables and columns"""
import psycopg2
from psycopg2 import sql

def table_exists(cur, table_name):
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (table_name,))
    return cur.fetchone()[0]

def column_exists(cur, table_name, column_name):
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        )
    """, (table_name, column_name))
    return cur.fetchone()[0]

def fix_schema():
    conn = psycopg2.connect('postgresql://vocab_user:Abcd1234@localhost/preschool_vocab_db')
    cur = conn.cursor()
    conn.autocommit = False
    
    print('Checking database schema...\n')
    
    # 1. Add language_preference column to children table
    if not column_exists(cur, 'children', 'language_preference'):
        print('Adding language_preference column...')
        try:
            cur.execute("CREATE TYPE languagepreference AS ENUM ('CANTONESE', 'ENGLISH', 'BILINGUAL')")
            print('  ✓ Created languagepreference enum type')
        except psycopg2.errors.DuplicateObject:
            print('  ✓ languagepreference enum type already exists')
            conn.rollback()
        
        try:
            cur.execute("ALTER TABLE children ADD COLUMN language_preference languagepreference DEFAULT 'CANTONESE'")
            conn.commit()
            print('  ✓ Added language_preference column to children table')
        except Exception as e:
            print(f'  ✗ Error adding column: {e}')
            conn.rollback()
    else:
        print('✓ language_preference column exists')
    
    # 2. Create daily_word_tracking table
    if not table_exists(cur, 'daily_word_tracking'):
        print('\nCreating daily_word_tracking table...')
        try:
            cur.execute("""
                CREATE TABLE daily_word_tracking (
                    id SERIAL PRIMARY KEY,
                    child_id VARCHAR NOT NULL REFERENCES children(id),
                    word_id VARCHAR NOT NULL REFERENCES words(id),
                    date TIMESTAMP WITH TIME ZONE NOT NULL,
                    exposure_count INTEGER DEFAULT 1,
                    used_actively BOOLEAN DEFAULT false,
                    mastery_confidence FLOAT DEFAULT 0.0,
                    learned_context JSONB,
                    include_in_story BOOLEAN DEFAULT true,
                    story_priority INTEGER DEFAULT 5,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """)
            cur.execute("CREATE INDEX ix_daily_word_tracking_date ON daily_word_tracking(date)")
            conn.commit()
            print('  ✓ Created daily_word_tracking table')
        except Exception as e:
            print(f'  ✗ Error creating table: {e}')
            conn.rollback()
    else:
        print('✓ daily_word_tracking table exists')
    
    # 3. Create generated_stories table
    if not table_exists(cur, 'generated_stories'):
        print('\nCreating generated_stories table...')
        try:
            cur.execute("""
                CREATE TABLE generated_stories (
                    id VARCHAR PRIMARY KEY,
                    child_id VARCHAR NOT NULL REFERENCES children(id),
                    title VARCHAR NOT NULL,
                    title_english VARCHAR,
                    theme VARCHAR,
                    generation_date TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                    content_cantonese TEXT NOT NULL,
                    content_english TEXT,
                    jyutping TEXT,
                    featured_words JSONB,
                    word_usage JSONB,
                    audio_url VARCHAR,
                    audio_duration_seconds INTEGER,
                    reading_time_minutes INTEGER DEFAULT 5,
                    word_count INTEGER,
                    difficulty_level VARCHAR DEFAULT 'easy',
                    cultural_references JSONB,
                    read_count INTEGER DEFAULT 0,
                    is_favorite BOOLEAN DEFAULT false,
                    parent_approved BOOLEAN DEFAULT true,
                    ai_model VARCHAR,
                    generation_prompt TEXT,
                    generation_time_seconds FLOAT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """)
            conn.commit()
            print('  ✓ Created generated_stories table')
        except Exception as e:
            print(f'  ✗ Error creating table: {e}')
            conn.rollback()
    else:
        print('✓ generated_stories table exists')
    
    # 4. Initialize alembic_version if it doesn't exist
    if not table_exists(cur, 'alembic_version'):
        print('\nInitializing Alembic version tracking...')
        try:
            cur.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))")
            # Stamp with the migration that includes daily_word_tracking
            cur.execute("INSERT INTO alembic_version (version_num) VALUES ('1f6c13cb81cd')")
            conn.commit()
            print('  ✓ Created alembic_version table and stamped at 1f6c13cb81cd')
        except Exception as e:
            print(f'  ✗ Error: {e}')
            conn.rollback()
    else:
        print('✓ alembic_version table exists')
    
    conn.close()
    print('\n✅ Schema fix complete!')

if __name__ == '__main__':
    fix_schema()
