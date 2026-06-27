"""Backfill cached word embeddings for existing vocabulary.

Usage:
  python backfill_word_embeddings.py
  python backfill_word_embeddings.py --limit 200 --batch-size 50
  python backfill_word_embeddings.py --category animals --dry-run
  python backfill_word_embeddings.py --force-refresh
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, or_, select

from app.db.session import AsyncSessionLocal
from app.models import analytics  # noqa: F401
from app.models import analytics_foundation  # noqa: F401
from app.models import community  # noqa: F401
from app.models import content  # noqa: F401
from app.models import daily_words  # noqa: F401
from app.models import generated_sentences  # noqa: F401
from app.models import parent_analytics  # noqa: F401
from app.models import word_personalization  # noqa: F401
from app.models import user  # noqa: F401
from app.models.vocabulary import Category, Word
from app.services.word_embedding_service import get_word_embedding_service


async def backfill_word_embeddings(
    *,
    limit: int | None,
    batch_size: int,
    category: str | None,
    force_refresh: bool,
    dry_run: bool,
) -> None:
    async with AsyncSessionLocal() as db:
        query = (
            select(Word)
            .join(Category, Word.category == Category.id, isouter=True)
            .where(Word.is_active == True)
            .order_by(Word.created_at.asc(), Word.word.asc())
        )

        if category:
            normalized = category.strip().lower()
            query = query.where(
                or_(
                    func.lower(Word.category) == normalized,
                    func.lower(Category.name) == normalized,
                )
            )

        if limit is not None:
            query = query.limit(max(limit, 1))

        result = await db.execute(query)
        words = result.scalars().all()
        if not words:
            print("[backfill-word-embeddings] no matching active words found")
            return

        service = get_word_embedding_service()
        stats = await service.backfill_embeddings(
            db,
            words=words,
            batch_size=max(batch_size, 1),
            force_refresh=force_refresh,
            dry_run=dry_run,
        )

        mode = "dry-run" if dry_run else "committed"
        print(f"[backfill-word-embeddings] mode={mode}")
        print(f"[backfill-word-embeddings] category={category or 'all'}")
        print(f"[backfill-word-embeddings] total_scanned={stats['total_scanned']}")
        print(f"[backfill-word-embeddings] total_stale={stats['total_stale']}")
        print(f"[backfill-word-embeddings] total_written={stats['total_written']}")
        print(f"[backfill-word-embeddings] batches={stats['batches']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill cached word embeddings")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of words to process")
    parser.add_argument("--batch-size", type=int, default=100, help="Embedding batch size")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter by category id or category name",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Recompute embeddings even if cache looks fresh")
    parser.add_argument("--dry-run", action="store_true", help="Report stale counts without writing embeddings")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        backfill_word_embeddings(
            limit=args.limit,
            batch_size=max(args.batch_size, 1),
            category=args.category,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
        )
    )