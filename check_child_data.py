"""
Quick script to check if child has word tracking data
"""
import asyncio
import asyncpg

async def check_data():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/preschool_vocab')    
    # Check child
    child_id = '44624173-4b69-42a7-a135-b0e035be436a'
    child = await conn.fetchrow('SELECT * FROM children WHERE id = $1', child_id)
    
    if child:
        print(f'✓ Child found: {child["name"]}, age {child["age"]}')
    else:
        print(f'✗ Child not found with ID: {child_id}')
        await conn.close()
        return
    
    # Check word tracking for today
    from datetime import datetime
    today = datetime.now().date()
    
    words_today = await conn.fetch('''
        SELECT * FROM daily_word_tracking 
        WHERE child_id = $1 
        AND date::date = $2
        AND include_in_story = TRUE
        ORDER BY story_priority DESC
        LIMIT 10
    ''', child_id, today)
    
    print(f'\n📅 Words tracked for TODAY ({today}): {len(words_today)}')
    
    if words_today:
        for w in words_today:
            print(f'  - Word ID: {w["word_id"]}, Exposure: {w["exposure_count"]}, Priority: {w["story_priority"]}')
    else:
        print('  ⚠️  No words tracked for today with include_in_story=TRUE')
        print('  This will cause "No words learned today" error!')
    
    # Check all word tracking
    all_words = await conn.fetch('''
        SELECT * FROM daily_word_tracking 
        WHERE child_id = $1 
        ORDER BY date DESC 
        LIMIT 10
    ''', child_id)
    
    print(f'\n📚 All tracked words (last 10): {len(all_words)}')
    
    if all_words:
        for w in all_words[:5]:
            print(f'  - Date: {w["date"]}, Word: {w["word_id"]}, Include in story: {w["include_in_story"]}')
    else:
        print('  ⚠️  No words tracked at all for this child!')
        print('  You need to use the /track-word endpoint first.')
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_data())
