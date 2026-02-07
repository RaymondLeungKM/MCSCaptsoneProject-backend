"""List all children in database"""
import asyncio
import asyncpg

async def list_children():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/preschool_vocab')
    
    children = await conn.fetch('SELECT id, name, age, parent_id FROM children ORDER BY name LIMIT 20')
    
    print(f'Total children in database: {len(children)}')
    print()
    
    if children:
        for child in children:
            print(f'ID: {child["id"]}')
            print(f'  Name: {child["name"]}, Age: {child["age"]}')
            print(f'  Parent: {child["parent_id"]}')
            print()
    else:
        print('No children found in database!')
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(list_children())
