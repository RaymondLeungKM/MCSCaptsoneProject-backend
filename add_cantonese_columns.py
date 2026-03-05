#!/usr/bin/env python3
"""Add missing Cantonese columns to categories and words tables"""
import psycopg2

def add_missing_columns():
    conn = psycopg2.connect('postgresql://vocab_user:Abcd1234@localhost/preschool_vocab_db')
    cur = conn.cursor()
    
    print("Adding missing Cantonese columns...\n")
    
    # Add columns to categories table
    print("Categories table:")
    columns_to_add = [
        ("name_cantonese", "VARCHAR"),
        ("description_cantonese", "TEXT"),
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cur.execute(f"ALTER TABLE categories ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"  ✓ Added {col_name}")
        except psycopg2.errors.DuplicateColumn:
            print(f"  ✓ {col_name} already exists")
            conn.rollback()
        except Exception as e:
            print(f"  ✗ Error adding {col_name}: {e}")
            conn.rollback()
    
    # Add columns to words table
    print("\nWords table:")
    columns_to_add = [
        ("word_cantonese", "VARCHAR"),
        ("jyutping", "VARCHAR"),
        ("definition_cantonese", "TEXT"),
        ("example_cantonese", "TEXT"),
        ("audio_url_english", "VARCHAR"),
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cur.execute(f"ALTER TABLE words ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"  ✓ Added {col_name}")
        except psycopg2.errors.DuplicateColumn:
            print(f"  ✓ {col_name} already exists")
            conn.rollback()
        except Exception as e:
            print(f"  ✗ Error adding {col_name}: {e}")
            conn.rollback()
    
    # Create index on word_cantonese
    print("\nCreating index:")
    try:
        cur.execute("CREATE INDEX ix_words_word_cantonese ON words(word_cantonese)")
        conn.commit()
        print("  ✓ Created index on words.word_cantonese")
    except psycopg2.errors.DuplicateTable:
        print("  ✓ Index on words.word_cantonese already exists")
        conn.rollback()
    except Exception as e:
        print(f"  ✗ Error creating index: {e}")
        conn.rollback()
    
    conn.close()
    print("\n✅ Cantonese columns added successfully!")

if __name__ == '__main__':
    add_missing_columns()
