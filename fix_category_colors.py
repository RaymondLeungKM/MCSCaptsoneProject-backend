"""
Fix categories with missing or default colors by auto-assigning appropriate colors
"""
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
# Import key models to ensure relationships are configured
from app.models import user, vocabulary, content, analytics, daily_words, parent_analytics
from app.models.vocabulary import Category
from app.core.category_colors import get_category_color


async def fix_category_colors():
    async with AsyncSessionLocal() as db:
        # Get all categories
        result = await db.execute(select(Category).order_by(Category.created_at))
        categories = result.scalars().all()
        
        print(f"Found {len(categories)} categories")
        print("-" * 60)
        
        updated_count = 0
        for i, category in enumerate(categories):
            old_color = category.color
            
            # Check if category has no color, default color, or gray color
            needs_update = (
                not category.color or 
                category.color in ["bg-sky", "bg-gray", "bg-slate-400"] or
                category.color == ""
            )
            
            if needs_update:
                # Assign appropriate color based on name and position
                new_color = get_category_color(category.name, i)
                category.color = new_color
                updated_count += 1
                print(f"✓ Updated '{category.name}': {old_color or '(none)'} → {new_color}")
            else:
                print(f"  Skipped '{category.name}': Already has color {old_color}")
        
        await db.commit()
        print("-" * 60)
        print(f"\n✅ Updated {updated_count} categories!")
        print(f"   {len(categories) - updated_count} categories already had colors")


if __name__ == "__main__":
    asyncio.run(fix_category_colors())
