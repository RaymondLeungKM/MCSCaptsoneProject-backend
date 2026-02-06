"""
Fix the 'general' category to have proper capitalization and Chinese name
"""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import user, vocabulary, content, analytics, daily_words, parent_analytics
from app.models.vocabulary import Category


async def fix_general_category():
    async with AsyncSessionLocal() as db:
        # Find the general category
        result = await db.execute(
            select(Category).where(Category.name.ilike("general"))
        )
        general_category = result.scalar_one_or_none()
        
        if general_category:
            print(f"Found category: '{general_category.name}'")
            print(f"  Current name_cantonese: {general_category.name_cantonese}")
            
            # Update to proper capitalization and Chinese name
            general_category.name = "General"
            general_category.name_cantonese = "一般"
            
            await db.commit()
            
            print(f"\n✅ Updated category!")
            print(f"  New name: {general_category.name}")
            print(f"  New name_cantonese: {general_category.name_cantonese}")
        else:
            print("❌ General category not found")


if __name__ == "__main__":
    asyncio.run(fix_general_category())
