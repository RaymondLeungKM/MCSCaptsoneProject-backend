"""
Create the PostgreSQL database
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Connect to PostgreSQL server (to 'postgres' database)
try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        database="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Create database
    cursor.execute("CREATE DATABASE preschool_vocab")
    print("✅ Database 'preschool_vocab' created successfully!")
    
    cursor.close()
    conn.close()
    
except psycopg2.errors.DuplicateDatabase:
    print("ℹ️  Database 'preschool_vocab' already exists")
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure PostgreSQL is running on localhost:5432")
    print("2. Check username/password in this script (currently: postgres/postgres)")
    print("3. Or update your .env file with correct credentials")
