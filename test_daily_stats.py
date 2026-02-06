#!/usr/bin/env python3
"""
Test script to verify DailyLearningStats are being created correctly
"""
import asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db_context
from app.models.user import Child
from app.models.parent_analytics import DailyLearningStats


async def check_daily_stats():
    """Check if daily learning stats exist for children"""
    async with get_db_context() as db:
        # Get all children
        result = await db.execute(select(Child))
        children = result.scalars().all()
        
        if not children:
            print("❌ No children found in database")
            return
        
        print(f"Found {len(children)} child(ren)")
        print()
        
        for child in children:
            print(f"📊 Child: {child.name} (ID: {child.id})")
            print(f"   Total words learned: {child.words_learned}")
            print(f"   Level: {child.level}, XP: {child.xp}")
            print()
            
            # Check daily stats for last 7 days
            seven_days_ago = date.today() - timedelta(days=6)
            stats_result = await db.execute(
                select(DailyLearningStats)
                .where(
                    DailyLearningStats.child_id == child.id,
                    DailyLearningStats.date >= seven_days_ago
                )
                .order_by(DailyLearningStats.date)
            )
            daily_stats = stats_result.scalars().all()
            
            if daily_stats:
                print(f"   📈 Daily Stats (Last 7 Days):")
                for stat in daily_stats:
                    print(f"      {stat.date}: {stat.words_learned} words learned, "
                          f"{stat.words_reviewed} reviewed, {stat.xp_earned} XP")
                
                # Calculate weekly totals
                total_words = sum(s.words_learned for s in daily_stats)
                total_reviewed = sum(s.words_reviewed for s in daily_stats)
                total_xp = sum(s.xp_earned for s in daily_stats)
                print()
                print(f"   📊 Weekly Totals:")
                print(f"      Words Learned: {total_words}")
                print(f"      Words Reviewed: {total_reviewed}")
                print(f"      XP Earned: {total_xp}")
            else:
                print(f"   ⚠️  No daily stats found for last 7 days")
                print(f"      This child may not have learned any words recently")
            
            print()
            print("=" * 70)
            print()


if __name__ == "__main__":
    print("🔍 Checking DailyLearningStats...")
    print()
    asyncio.run(check_daily_stats())
