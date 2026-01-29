"""
Clear all users from database
"""
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import delete


async def clear_users():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()
        print('✅ All users cleared from database')


if __name__ == "__main__":
    asyncio.run(clear_users())
