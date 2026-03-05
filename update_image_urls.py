"""
Script to update existing image URLs in the database to store only paths
"""
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def update_image_urls():
    """Update all image URLs to store only paths (remove base URLs)"""
    
    async with AsyncSessionLocal() as db:
        try:
            # Update words table - remove base URLs (both localhost and public IP)
            result = await db.execute(
                text("""
                    UPDATE words 
                    SET image_url = REGEXP_REPLACE(image_url, '^https?://[^/]+', '')
                    WHERE image_url ~ '^https?://'
                """)
            )
            words_updated = result.rowcount
            
            # Update stories table if it exists
            try:
                result = await db.execute(
                    text("""
                        UPDATE stories 
                        SET cover_image_url = REGEXP_REPLACE(cover_image_url, '^https?://[^/]+', '')
                        WHERE cover_image_url ~ '^https?://'
                    """)
                )
                stories_updated = result.rowcount
            except Exception:
                stories_updated = 0
                print("Stories table not found or no cover_image_url column, skipping...")
            
            await db.commit()
            
            print(f"✅ Successfully updated image URLs to paths:")
            print(f"   - Words table: {words_updated} rows updated")
            print(f"   - Stories table: {stories_updated} rows updated")
            print(f"   - URLs now start with '/uploads' instead of full domain")
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Error updating image URLs: {e}")
            raise

if __name__ == "__main__":
    print("Starting image URL update...")
    asyncio.run(update_image_urls())
    print("Done!")
