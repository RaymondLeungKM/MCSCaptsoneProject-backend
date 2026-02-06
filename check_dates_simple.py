#!/usr/bin/env python
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        # Check word progress dates
        result = await db.execute(text("""
            SELECT 
                wp.word_id,
                wp.last_practiced,
                wp.exposure_count,
                w.word
            FROM word_progress wp
            JOIN words w ON wp.word_id = w.id
            WHERE wp.child_id = 'test-child-ui'
            ORDER BY wp.last_practiced DESC NULLS LAST
            LIMIT 10
        """))
        
        print("Last practiced dates in database:")
        print("-" * 80)
        for row in result:
            print(f"Word: {row.word:20} | Last Practiced: {row.last_practiced} | Exposures: {row.exposure_count}")
        
        # Check count for Feb 1 onwards
        result2 = await db.execute(text("""
            SELECT COUNT(DISTINCT wp.id)
            FROM word_progress wp
            WHERE wp.child_id = 'test-child-ui'
            AND wp.last_practiced >= '2026-02-01 00:00:00'
        """))
        count = result2.scalar()
        print(f"\nWords practiced since Feb 1, 2026: {count}")
        
        # Check total count with any last_practiced
        result3 = await db.execute(text("""
            SELECT COUNT(DISTINCT wp.id)
            FROM word_progress wp
            WHERE wp.child_id = 'test-child-ui'
            AND wp.last_practiced IS NOT NULL
        """))
        total_count = result3.scalar()
        print(f"Total words with last_practiced: {total_count}")

asyncio.run(main())
