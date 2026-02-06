import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
# Import all models to avoid relationship errors
from app.models import user, vocabulary, content, analytics, daily_words, parent_analytics
from app.models.vocabulary import Category

async def check_colors():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).order_by(Category.name))
        cats = result.scalars().all()
        
        print('\nCategory Colors:')
        print('-' * 60)
        for c in cats:
            print(f'{c.name:20} {c.icon:5} {c.color}')
        print('-' * 60)

if __name__ == "__main__":
    asyncio.run(check_colors())
