import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Verify environment variables are loaded
db_url = os.getenv('DATABASE_URL')
print(f"DATABASE_URL from env: {db_url}")

if not db_url or 'vocab_user' not in db_url:
    print("ERROR: DATABASE_URL not loaded correctly from .env file!")
    print("Please check that .env file exists and contains:")
    print("DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db")
    print("ASYNC_DATABASE_URL=postgresql+asyncpg://vocab_user:postgres2026@localhost/preschool_vocab_db")
    exit(1)

from app.db.session import engine
from app.db.base import Base
# Import models so metadata is populated
from app.models import vocabulary  # noqa: F401
from app.models import user  # noqa: F401
from app.models import content  # noqa: F401
from app.models import analytics  # noqa: F401
from app.models import parent_analytics  # noqa: F401
from app.models import generated_sentences  # noqa: F401
from app.models import daily_words  # noqa: F401

async def init_db():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('✓ Database tables created successfully!')

asyncio.run(init_db())
