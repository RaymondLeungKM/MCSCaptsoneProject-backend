"""
Migration: Consolidate 'general' into 'Custom', rename Custom → 'My Collection'

Steps:
1. Move all words from 'general' category into 'Custom'
2. Rename 'Custom' → name='My Collection', name_cantonese='我的 My Collection', icon='📸'
3. Deactivate the 'general' category
4. Recalculate word_count on 'My Collection'
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

CUSTOM_ID = "b2950953-d03a-446b-bf7c-393aee8c51e5"
GENERAL_ID = "3e25af13-099b-4fde-a9bc-3fa7df181175"

async def main():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/preschool_vocab",
        echo=True,
    )
    async with AsyncSession(engine) as session:
        async with session.begin():
            # 1. Move words from general → Custom
            result = await session.execute(
                text("UPDATE words SET category = :custom WHERE category = :general"),
                {"custom": CUSTOM_ID, "general": GENERAL_ID},
            )
            print(f"Moved {result.rowcount} words from 'general' to 'My Collection'")

            # 2. Rename Custom category
            await session.execute(
                text("""
                    UPDATE categories
                    SET name = 'My Collection',
                        name_cantonese = '我的',
                        icon = '📸',
                        description = 'Words and photos collected from your surroundings',
                        description_cantonese = '從你的環境中收集的詞語和相片'
                    WHERE id = :custom_id
                """),
                {"custom_id": CUSTOM_ID},
            )
            print("Renamed 'Custom' → 'My Collection'")

            # 3. Deactivate general category
            await session.execute(
                text("UPDATE categories SET is_active = false WHERE id = :general_id"),
                {"general_id": GENERAL_ID},
            )
            print("Deactivated 'general' category")

            # 4. Recalculate word_count
            await session.execute(
                text("""
                    UPDATE categories
                    SET word_count = (
                        SELECT COUNT(*) FROM words
                        WHERE category = :custom_id AND is_active = true
                    )
                    WHERE id = :custom_id
                """),
                {"custom_id": CUSTOM_ID},
            )
            print("Recalculated word_count for 'My Collection'")

    await engine.dispose()
    print("\nMigration complete!")

asyncio.run(main())
