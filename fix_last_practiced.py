#!/usr/bin/env python
"""
Fix last_practiced dates for existing word progress records
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        # Set last_practiced to today for all words that have been exposed
        # Spread them over the last 7 days for realistic chart data
        result = await db.execute(text("""
            SELECT id, exposure_count
            FROM word_progress
            WHERE child_id = 'test-child-ui'
            AND exposure_count > 0
            ORDER BY id
        """))
        
        records = result.fetchall()
        print(f"Found {len(records)} word progress records to update")
        
        # Distribute words over the last 7 days
        dates_to_use = []
        for i in range(7):
            date = datetime.now() - timedelta(days=6-i)
            dates_to_use.append(date)
        
        # Update each record
        updates = []
        for idx, (record_id, exposure_count) in enumerate(records):
            # Cycle through the 7 days
            date_to_use = dates_to_use[idx % 7]
            updates.append((record_id, date_to_use))
        
        # Batch update
        for record_id, date_to_use in updates:
            await db.execute(
                text("UPDATE word_progress SET last_practiced = :date WHERE id = :id"),
                {"date": date_to_use, "id": record_id}
            )
        
        await db.commit()
        print(f"Updated {len(updates)} records with last_practiced dates")
        
        # Verify the update
        result = await db.execute(text("""
            SELECT COUNT(DISTINCT id)
            FROM word_progress
            WHERE child_id = 'test-child-ui'
            AND last_practiced >= '2026-02-01 00:00:00'
        """))
        count = result.scalar()
        print(f"\nWords with last_practiced since Feb 1: {count}")
        
        # Show sample dates
        result2 = await db.execute(text("""
            SELECT word_id, last_practiced, exposure_count
            FROM word_progress
            WHERE child_id = 'test-child-ui'
            AND last_practiced IS NOT NULL
            ORDER BY last_practiced DESC
            LIMIT 5
        """))
        print("\nSample updated records:")
        for row in result2:
            print(f"  Word ID: {row.word_id[:8]}... | Last Practiced: {row.last_practiced} | Exposures: {row.exposure_count}")

asyncio.run(main())
