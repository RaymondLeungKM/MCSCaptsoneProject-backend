"""Backfill AI word-relationship enrichment for older words missing AI links.

Usage:
  python backfill_word_relationship_enrichment.py
  python backfill_word_relationship_enrichment.py --limit 100 --batch-size 20
  python backfill_word_relationship_enrichment.py --category animals --min-age-days 30
  python backfill_word_relationship_enrichment.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from app.api.endpoints.vocabulary import _attach_ai_relationship_suggestions
from app.db.session import AsyncSessionLocal
from app.models import analytics  # noqa: F401
from app.models import analytics_foundation  # noqa: F401
from app.models import community  # noqa: F401
from app.models import content  # noqa: F401
from app.models import daily_words  # noqa: F401
from app.models import generated_sentences  # noqa: F401
from app.models import parent_analytics  # noqa: F401
from app.models import user  # noqa: F401
from app.models import word_personalization  # noqa: F401
from app.models.vocabulary import Category, Word
from app.models.word_personalization import WordRelationship


async def backfill_word_relationship_enrichment(
    *,
    limit: int | None,
    batch_size: int,
    category: str | None,
    min_age_days: int,
    dry_run: bool,
) -> None:
    async with AsyncSessionLocal() as db:
        ai_outgoing_exists = (
            select(WordRelationship.id)
            .where(
                WordRelationship.word_id == Word.id,
                WordRelationship.source.is_not(None),
                WordRelationship.source.ilike("ai%"),
            )
            .exists()
        )
        ai_incoming_exists = (
            select(WordRelationship.id)
            .where(
                WordRelationship.related_word_id == Word.id,
                WordRelationship.source.is_not(None),
                WordRelationship.source.ilike("ai%"),
            )
            .exists()
        )

        query = (
            select(Word)
            .join(Category, Word.category == Category.id, isouter=True)
            .where(
                Word.is_active == True,
                ~ai_outgoing_exists,
                ~ai_incoming_exists,
            )
            .order_by(Word.created_at.asc(), Word.word.asc())
        )

        if min_age_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
            query = query.where(Word.created_at <= cutoff)

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
        candidate_words = [word for word in result.scalars().all() if (word.word or "").strip()]

        total_candidates = len(candidate_words)
        print(f"[backfill-word-relationships] dry_run={dry_run}")
        print(f"[backfill-word-relationships] category={category or 'all'}")
        print(f"[backfill-word-relationships] min_age_days={max(min_age_days, 0)}")
        print("[backfill-word-relationships] mode=missing_ai_relationships")
        print(f"[backfill-word-relationships] total_candidates={total_candidates}")

        if total_candidates == 0:
            print("[backfill-word-relationships] no words missing AI relationships matched filters")
            return

        if dry_run:
            preview_size = min(total_candidates, 20)
            print(f"[backfill-word-relationships] previewing_first={preview_size}")
            for index, word in enumerate(candidate_words[:preview_size], start=1):
                print(
                    "[backfill-word-relationships] "
                    f"candidate_{index}: id={word.id} word={word.word!r} category={word.category!r} "
                    f"created_at={word.created_at}"
                )
            return

        processed = 0
        enriched_words = 0
        relationships_added = 0
        unchanged = 0
        failed = 0

        for word in candidate_words:
            processed += 1
            try:
                linked_count = await _attach_ai_relationship_suggestions(db=db, word=word)
            except Exception as exc:
                failed += 1
                print(
                    f"[backfill-word-relationships] error word_id={word.id} word={word.word!r}: {exc}"
                )
                continue

            if linked_count > 0:
                enriched_words += 1
                relationships_added += linked_count
            else:
                unchanged += 1

            if processed % max(batch_size, 1) == 0:
                print(
                    "[backfill-word-relationships] progress "
                    f"processed={processed}/{total_candidates} "
                    f"enriched_words={enriched_words} relationships_added={relationships_added} "
                    f"unchanged={unchanged} failed={failed}"
                )

        print(f"[backfill-word-relationships] processed={processed}")
        print(f"[backfill-word-relationships] enriched_words={enriched_words}")
        print(f"[backfill-word-relationships] relationships_added={relationships_added}")
        print(f"[backfill-word-relationships] unchanged={unchanged}")
        print(f"[backfill-word-relationships] failed={failed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill AI relationship enrichment for words missing AI links"
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of words to process")
    parser.add_argument("--batch-size", type=int, default=20, help="Progress report interval")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter by category id or category name",
    )
    parser.add_argument(
        "--min-age-days",
        type=int,
        default=0,
        help="Only include words created at least this many days ago",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching words without writing relationship changes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        backfill_word_relationship_enrichment(
            limit=args.limit,
            batch_size=max(args.batch_size, 1),
            category=args.category,
            min_age_days=max(args.min_age_days, 0),
            dry_run=args.dry_run,
        )
    )
