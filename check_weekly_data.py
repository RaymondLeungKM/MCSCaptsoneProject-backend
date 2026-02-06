import asyncio
from app.db.session import get_db
from sqlalchemy import select
from app.models.user import Child
from app.models.vocabulary import WordProgress
from datetime import datetime, timedelta

async def check_data():
    async for db in get_db():
        # Get first child
        result = await db.execute(select(Child).limit(1))
        child = result.scalar_one_or_none()
        if not child:
            print('No children found')
            return
        
        print(f'Child: {child.name} (ID: {child.id})')
        print(f'Child.words_learned: {child.words_learned}')
        
        # Check total word progress
        result = await db.execute(select(WordProgress).where(WordProgress.child_id == child.id))
        all_progress = result.scalars().all()
        print(f'\nTotal WordProgress records: {len(all_progress)}')
        
        # Check records with last_practiced
        with_dates = [p for p in all_progress if p.last_practiced]
        print(f'Records with last_practiced: {len(with_dates)}')
        
        if with_dates:
            print('\nRecent last_practiced dates:')
            sorted_dates = sorted(with_dates, key=lambda x: x.last_practiced, reverse=True)[:10]
            for p in sorted_dates:
                print(f'  - {p.last_practiced} (word_id: {p.word_id}, exposure: {p.exposure_count})')
        
        # Check last 7 days
        today = datetime.now()
        seven_days_ago = today - timedelta(days=6)
        print(f'\nToday: {today}')
        print(f'Looking for records since: {seven_days_ago}')
        recent = [p for p in with_dates if p.last_practiced >= seven_days_ago]
        print(f'Records in last 7 days: {len(recent)}')
        
        # Test the actual query used in API
        from datetime import date
        seven_days_ago_date = date.today() - timedelta(days=6)
        seven_days_ago_dt = datetime.combine(seven_days_ago_date, datetime.min.time())
        print(f'\nAPI uses date: {seven_days_ago_date}')
        print(f'Converted to datetime: {seven_days_ago_dt}')
        
        # Count with the actual query
        from sqlalchemy import func, and_
        result = await db.execute(
            select(func.count(WordProgress.id.distinct()))
            .where(
                and_(
                    WordProgress.child_id == child.id,
                    WordProgress.last_practiced >= seven_days_ago_dt
                )
            )
        )
        count = result.scalar()
        print(f'Count from API query: {count}')
        
        break

asyncio.run(check_data())
