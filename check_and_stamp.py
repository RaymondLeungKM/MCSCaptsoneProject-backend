#!/usr/bin/env python3
"""Check existing tables and stamp Alembic version appropriately"""
import psycopg2

def check_and_stamp():
    conn = psycopg2.connect('postgresql://vocab_user:Abcd1234@localhost/preschool_vocab_db')
    cur = conn.cursor()
    
    # Get all existing tables
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    tables = set(row[0] for row in cur.fetchall())
    
    print("Existing tables:")
    for t in sorted(tables):
        print(f"  - {t}")
    print()
    
    # Check which migration tables exist
    has_story = 'story' in tables
    has_daily_learning_stats = 'daily_learning_stats' in tables
    has_generated_sentences = 'generated_sentences' in tables
    
    print(f"story table exists: {has_story}")
    print(f"daily_learning_stats table exists: {has_daily_learning_stats}")
    print(f"generated_sentences table exists: {has_generated_sentences}")
    print()
    
    # Determine appropriate version to stamp
    if has_generated_sentences:
        target_version = '7d1dc1c04fdd'  # Latest - has generated_sentences
        migration_name = "add_generated_sentences_table (latest)"
    elif has_story and has_daily_learning_stats:
        target_version = 'b0a67c10f34e'  # Merge heads
        migration_name = "merge_heads"
    elif has_story or has_daily_learning_stats:
        # One branch is applied, need to figure out which
        if has_story:
            target_version = '6f2a8c1f0d3e'
            migration_name = "add_story_table"
        else:
            target_version = '74e12a1dca87'
            migration_name = "add_parent_analytics_tables"
    else:
        target_version = '1f6c13cb81cd'  # Current stamp from fix_schema.py
        migration_name = "add_daily_word_tracking_and_generated_stories"
    
    print(f"Recommended stamp version: {target_version} ({migration_name})")
    print()
    
    # Update alembic_version
    cur.execute("UPDATE alembic_version SET version_num = %s", (target_version,))
    conn.commit()
    
    print(f"✓ Stamped database at version: {target_version}")
    
    conn.close()

if __name__ == '__main__':
    check_and_stamp()
