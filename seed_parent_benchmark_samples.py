"""
Seed parent benchmark cohort data so privacy-gated benchmark cards can be previewed.

This script is idempotent. It:
1. Finds a target parent+child (default: raymond@test.com and first child).
2. Ensures target parent has analytics consent enabled.
3. Creates sample peer parent/child accounts in the same age band.
4. Upserts ChildDayAnalytics rows for target + peers in the selected date range.
5. Seeds WordProgress rows across several shared categories so category benchmarks have real peer comparisons.
6. Seeds mission outcome rows so funnel statuses include started/completed/skipped/expired.
7. Seeds content performance rows so top/underperforming content lists are populated.

Usage:
  ./venv/bin/python seed_parent_benchmark_samples.py
    ./venv/bin/python seed_parent_benchmark_samples.py --target-email raymond@test.com --peer-users 100 --range-days 90
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, delete, select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
# Import related models so SQLAlchemy can resolve string-based relationships.
from app.models.analytics import Achievement, DailyStats, LearningSession  # noqa: F401
from app.models.community import CommunityPost, PostReaction  # noqa: F401
from app.models.content import Game, Mission, Story  # noqa: F401
from app.models.daily_words import DailyWordTracking  # noqa: F401
from app.models.generated_sentences import GeneratedSentence  # noqa: F401
from app.models.parent_analytics import (  # noqa: F401
    DailyLearningStats,
    LearningInsight,
    ParentalControl,
    WeeklyReport,
)
from app.models.analytics_foundation import (
    ChildDayAnalytics,
    ContentPerformanceAnalytics,
    MissionOutcomeAnalytics,
)
from app.models.vocabulary import Category, Word, WordProgress  # noqa: F401
from app.models.user import (
    Child,
    LanguagePreference,
    LearningStyle,
    TimeOfDay,
    User,
    UserRole,
)
from app.services.analytics_foundation import resolve_age_band

DEFAULT_PASSWORD = "BenchmarkDemo123!"
BENCHMARK_CATEGORY_LIMIT = 4
BENCHMARK_WORDS_PER_CATEGORY = 4
BENCHMARK_MISSION_SOURCE = "seed"

MISSION_CONTEXT_OPTIONS = ["playtime", "mealtime", "bedtime", "outdoor", "general"]


@dataclass(frozen=True)
class ContentSeedTemplate:
    content_type: str
    content_id: str
    category_id: str
    word_id: str | None
    completion_rate: float
    success_rate: float
    retention_score: float


@dataclass
class TargetContext:
    parent: User
    child: Child
    age_band: str


def _age_for_band(age_band: str, index: int = 0) -> int:
    if age_band == "3-4":
        return 3 + (index % 2)
    if age_band == "5-6":
        return 5 + (index % 2)
    if age_band == "7+":
        return 7 + (index % 3)
    return 5


async def _resolve_target_context(db, *, target_email: str, child_id: str | None) -> TargetContext:
    if child_id:
        child_result = await db.execute(select(Child).where(Child.id == child_id))
        child = child_result.scalar_one_or_none()
        if child is None:
            raise RuntimeError(f"Child not found: {child_id}")

        parent_result = await db.execute(select(User).where(User.id == child.parent_id))
        parent = parent_result.scalar_one_or_none()
        if parent is None:
            raise RuntimeError(f"Parent not found for child: {child_id}")

        return TargetContext(parent=parent, child=child, age_band=resolve_age_band(child.age))

    target_user_result = await db.execute(
        select(User).where(and_(User.email == target_email, User.role == UserRole.PARENT))
    )
    target_parent = target_user_result.scalar_one_or_none()

    if target_parent:
        target_child_result = await db.execute(
            select(Child)
            .where(Child.parent_id == target_parent.id)
            .order_by(Child.created_at.asc())
        )
        target_child = target_child_result.scalars().first()
        if target_child:
            return TargetContext(
                parent=target_parent,
                child=target_child,
                age_band=resolve_age_band(target_child.age),
            )

    fallback_result = await db.execute(
        select(Child, User)
        .join(User, User.id == Child.parent_id)
        .where(User.role == UserRole.PARENT)
        .order_by(Child.created_at.asc())
    )
    fallback_row = fallback_result.first()
    if fallback_row is None:
        raise RuntimeError("No parent+child records found. Seed base database first.")

    fallback_child, fallback_parent = fallback_row
    return TargetContext(
        parent=fallback_parent,
        child=fallback_child,
        age_band=resolve_age_band(fallback_child.age),
    )


async def _ensure_consent(user: User) -> None:
    user.consent_given = True
    user.consent_camera = True
    user.consent_microphone = True
    user.consent_analytics = True
    if not user.consent_given_at:
        user.consent_given_at = datetime.now(timezone.utc)


async def _upsert_peer_parent(db, *, peer_index: int, age_band: str) -> User:
    peer_id = f"sample-parent-benchmark-{age_band.replace('+', 'plus')}-{peer_index:02d}"
    email = f"benchmark.parent.{age_band.replace('+', 'plus')}.{peer_index:02d}@example.com"

    result = await db.execute(select(User).where(User.id == peer_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=peer_id,
            email=email,
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            full_name=f"Benchmark Parent {peer_index:02d}",
            role=UserRole.PARENT,
            is_active=True,
        )
        db.add(user)

    user.email = email
    user.full_name = f"Benchmark Parent {peer_index:02d}"
    user.role = UserRole.PARENT
    user.is_active = True
    await _ensure_consent(user)
    if not user.hashed_password:
        user.hashed_password = get_password_hash(DEFAULT_PASSWORD)

    return user


async def _upsert_peer_child(db, *, parent_id: str, peer_index: int, age_band: str) -> Child:
    child_id = f"sample-child-benchmark-{age_band.replace('+', 'plus')}-{peer_index:02d}"
    result = await db.execute(select(Child).where(Child.id == child_id))
    child = result.scalar_one_or_none()

    age = _age_for_band(age_band, peer_index)
    if child is None:
        child = Child(
            id=child_id,
            parent_id=parent_id,
            name=f"基準樣本{peer_index:02d}",
            avatar="🧩",
            age=age,
            birth_year=max(2016, datetime.now(timezone.utc).year - age),
            birth_month=6,
            level=3 + (peer_index % 3),
            xp=120 + peer_index * 7,
            words_learned=15 + peer_index,
            daily_goal=5,
            today_progress=2,
            learning_style=LearningStyle.MIXED,
            language_preference=LanguagePreference.CANTONESE,
            attention_span=15,
            preferred_time_of_day=TimeOfDay.EVENING,
            community_sharing_enabled=True,
            last_active=datetime.now(timezone.utc),
        )
        db.add(child)

    child.parent_id = parent_id
    child.name = f"基準樣本{peer_index:02d}"
    child.age = age
    child.language_preference = LanguagePreference.CANTONESE
    child.learning_style = LearningStyle.MIXED
    child.preferred_time_of_day = TimeOfDay.EVENING
    child.last_active = datetime.now(timezone.utc)

    return child


async def _upsert_day_row(
    db,
    *,
    child_id: str,
    day: date,
    age_band: str,
    words_encountered: int,
    words_mastered: int,
    minutes_total: int,
    mission_assigned: int,
    mission_completed: int,
    engagement_avg: float,
) -> None:
    result = await db.execute(
        select(ChildDayAnalytics).where(
            ChildDayAnalytics.child_id == child_id,
            ChildDayAnalytics.activity_day == day,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = ChildDayAnalytics(child_id=child_id, activity_day=day)
        db.add(row)

    row.age_band = age_band
    row.words_encountered = words_encountered
    row.words_mastered = words_mastered
    row.session_minutes_total = minutes_total
    row.mission_assigned_count = mission_assigned
    row.mission_completed_count = mission_completed
    row.engagement_events_count = max(minutes_total // 5, 1)
    row.engagement_score_sum = engagement_avg * row.engagement_events_count
    row.engagement_score_avg = engagement_avg
    row.active_days_7d = min(7, 1)
    row.active_days_28d = min(28, 1)


async def _load_benchmark_category_word_pool(
    db,
    *,
    category_limit: int = BENCHMARK_CATEGORY_LIMIT,
    words_per_category: int = BENCHMARK_WORDS_PER_CATEGORY,
) -> list[dict[str, object]]:
    rows = await db.execute(
        select(Category.id, Category.name_cantonese, Category.name, Word.id)
        .join(Word, Word.category == Category.id)
        .where(
            Category.is_active == True,
            Word.is_active == True,
            Word.created_by_child_id.is_(None),
        )
        .order_by(Category.sort_order.asc(), Category.name.asc(), Word.created_at.asc(), Word.id.asc())
    )

    category_map: dict[str, dict[str, object]] = {}
    for category_id, category_name_cantonese, category_name, word_id in rows.all():
        entry = category_map.setdefault(
            category_id,
            {
                "category_id": category_id,
                "category_name": category_name_cantonese or category_name or category_id,
                "word_ids": [],
            },
        )

        word_ids = entry["word_ids"]
        if len(word_ids) < words_per_category:
            word_ids.append(word_id)

    eligible_categories = [
        entry
        for entry in category_map.values()
        if len(entry["word_ids"]) >= words_per_category
    ]

    if len(eligible_categories) < category_limit:
        raise RuntimeError(
            f"Need at least {category_limit} categories with {words_per_category} active words for benchmark seeding; found {len(eligible_categories)}"
        )

    return eligible_categories[:category_limit]


async def _upsert_word_progress(
    db,
    *,
    child_id: str,
    word_id: str,
    mastered: bool,
    exposure_count: int,
    correct_attempts: int,
    total_attempts: int,
    practiced_at: datetime,
) -> None:
    result = await db.execute(
        select(WordProgress).where(
            WordProgress.child_id == child_id,
            WordProgress.word_id == word_id,
        )
    )
    progress = result.scalar_one_or_none()

    if progress is None:
        progress = WordProgress(child_id=child_id, word_id=word_id)
        db.add(progress)

    progress.exposure_count = exposure_count
    progress.mastered = mastered
    progress.mastered_at = practiced_at if mastered else None
    progress.last_practiced = practiced_at
    progress.pending_active_vocab_approval = False
    progress.active_vocab_requested_at = None
    progress.correct_attempts = correct_attempts
    progress.total_attempts = total_attempts
    progress.success_rate = (
        correct_attempts / total_attempts if total_attempts > 0 else 0.0
    )
    progress.visual_exposures = max(exposure_count // 3, 1)
    progress.auditory_exposures = max(exposure_count // 3, 1)
    progress.kinesthetic_exposures = max(
        exposure_count - progress.visual_exposures - progress.auditory_exposures,
        0,
    )


async def _seed_category_progress_profile(
    db,
    *,
    child_id: str,
    category_word_pool: list[dict[str, object]],
    mastered_counts: list[int],
    practiced_at: datetime,
) -> None:
    for category_index, category_entry in enumerate(category_word_pool):
        word_ids = list(category_entry["word_ids"])
        if not word_ids:
            continue

        mastered_count = min(mastered_counts[category_index], len(word_ids))
        for word_index, word_id in enumerate(word_ids):
            is_mastered = word_index < mastered_count
            exposure_count = 4 + category_index + word_index + mastered_count
            total_attempts = max(2, exposure_count - 1)
            incorrect_attempts = 0 if is_mastered else min(2 + (word_index % 2), total_attempts - 1)
            correct_attempts = total_attempts - incorrect_attempts

            await _upsert_word_progress(
                db,
                child_id=child_id,
                word_id=word_id,
                mastered=is_mastered,
                exposure_count=exposure_count,
                correct_attempts=correct_attempts,
                total_attempts=total_attempts,
                practiced_at=practiced_at,
            )


async def _replace_seeded_mission_outcomes_for_day(
    db,
    *,
    child_id: str,
    day: date,
    age_band: str,
    child_seed: int,
) -> None:
    await db.execute(
        delete(MissionOutcomeAnalytics).where(
            MissionOutcomeAnalytics.child_id == child_id,
            MissionOutcomeAnalytics.activity_day == day,
            MissionOutcomeAnalytics.source.in_(["seed", "seed-benchmark"]),
        )
    )

    assigned_count = 2
    started_count = 1 + (child_seed % 2)
    completed_count = 1 if (child_seed % 4) != 0 else 0
    skipped_count = 1 if (child_seed % 5) == 0 else 0
    expired_count = 1 if (child_seed % 7) == 0 else 0

    status_counts = {
        "assigned": assigned_count,
        "started": started_count,
        "completed": completed_count,
        "skipped": skipped_count,
        "expired": expired_count,
    }

    for status, count in status_counts.items():
        for index in range(count):
            context = MISSION_CONTEXT_OPTIONS[(child_seed + index) % len(MISSION_CONTEXT_OPTIONS)]
            completion_minutes = None
            if status in {"completed", "skipped", "expired"}:
                completion_minutes = 6 + ((child_seed + index) % 10)

            db.add(
                MissionOutcomeAnalytics(
                    activity_day=day,
                    child_id=child_id,
                    mission_id=None,
                    assignment_id=None,
                    source=BENCHMARK_MISSION_SOURCE,
                    context=context,
                    age_band=age_band,
                    status=status,
                    completion_minutes=completion_minutes,
                    is_cluster=False,
                    cluster_id=None,
                    seed_word_id=None,
                    payload={
                        "seed_profile": "benchmark",
                        "child_seed": child_seed,
                    },
                )
            )


def _build_content_seed_templates(
    category_word_pool: list[dict[str, object]],
) -> list[ContentSeedTemplate]:
    templates: list[ContentSeedTemplate] = []

    high_profiles = [
        ("word", "high-word", 0.95, 0.9, 0.86),
        ("story", "high-story", 0.88, 0.84, 0.82),
        ("game", "high-game", 0.84, 0.8, 0.79),
        ("story", "high-story-plus", 0.82, 0.78, 0.76),
        ("game", "high-game-plus", 0.8, 0.75, 0.74),
    ]
    low_profiles = [
        ("word", "low-word", 0.34, 0.3, 0.28),
        ("story", "low-story", 0.28, 0.24, 0.22),
        ("game", "low-game", 0.24, 0.2, 0.18),
        ("story", "low-story-plus", 0.2, 0.18, 0.16),
        ("game", "low-game-plus", 0.18, 0.15, 0.14),
    ]

    all_profiles = high_profiles + low_profiles
    for index, (content_type, profile_key, completion_rate, success_rate, retention_score) in enumerate(all_profiles):
        category_entry = category_word_pool[index % len(category_word_pool)]
        category_id = str(category_entry["category_id"])
        word_ids = list(category_entry["word_ids"])
        word_id = str(word_ids[index % len(word_ids)]) if word_ids else None

        templates.append(
            ContentSeedTemplate(
                content_type=content_type,
                content_id=f"benchmark-{profile_key}-{category_id}",
                category_id=category_id,
                word_id=word_id,
                completion_rate=completion_rate,
                success_rate=success_rate,
                retention_score=retention_score,
            )
        )

    return templates


async def _upsert_content_performance_row(
    db,
    *,
    day: date,
    child_id: str,
    age_band: str,
    template: ContentSeedTemplate,
    exposure_count: int,
) -> None:
    result = await db.execute(
        select(ContentPerformanceAnalytics).where(
            ContentPerformanceAnalytics.activity_day == day,
            ContentPerformanceAnalytics.child_id == child_id,
            ContentPerformanceAnalytics.content_type == template.content_type,
            ContentPerformanceAnalytics.content_id == template.content_id,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = ContentPerformanceAnalytics(
            activity_day=day,
            child_id=child_id,
            content_type=template.content_type,
            content_id=template.content_id,
        )
        db.add(row)

    completion_count = max(1, min(exposure_count, int(round(exposure_count * template.completion_rate))))
    success_count = max(0, min(completion_count, int(round(completion_count * template.success_rate))))

    row.age_band = age_band
    row.category_id = template.category_id
    row.word_id = template.word_id
    row.exposure_count = exposure_count
    row.completion_count = completion_count
    row.success_count = success_count
    row.post_exposure_mastery_delta = round(success_count / max(exposure_count, 1), 4)
    row.retention_proxy_score = round(template.retention_score, 4)


async def _seed_content_performance_profile(
    db,
    *,
    day: date,
    child_id: str,
    age_band: str,
    templates: list[ContentSeedTemplate],
    child_seed: int,
) -> None:
    for index, template in enumerate(templates):
        exposure_count = 4 + ((child_seed + index) % 4)
        await _upsert_content_performance_row(
            db,
            day=day,
            child_id=child_id,
            age_band=age_band,
            template=template,
            exposure_count=exposure_count,
        )


async def seed_benchmark_samples(
    *,
    target_email: str,
    child_id: str | None,
    peer_users: int,
    range_days: int,
) -> None:
    async with AsyncSessionLocal() as db:
        target = await _resolve_target_context(db, target_email=target_email, child_id=child_id)
        await _ensure_consent(target.parent)

        age_band = target.age_band
        peers_needed = max(peer_users, 100)
        category_word_pool = await _load_benchmark_category_word_pool(db)
        content_templates = _build_content_seed_templates(category_word_pool)

        peer_children: list[Child] = []
        for index in range(1, peers_needed + 1):
            parent = await _upsert_peer_parent(db, peer_index=index, age_band=age_band)
            child = await _upsert_peer_child(
                db,
                parent_id=parent.id,
                peer_index=index,
                age_band=age_band,
            )
            peer_children.append(child)

        # Persist parent/child rows first so analytics upserts satisfy FK checks.
        await db.flush()

        # One active day every 3 days across the selected window keeps rows compact
        # while still making the benchmark cards meaningful for 90-day views.
        today = date.today()
        practiced_at = datetime.now(timezone.utc)
        day_offsets = list(range(0, range_days, 3))

        for offset in day_offsets:
            day = today - timedelta(days=offset)
            day_seed = (today - day).days

            # Target child profile: slightly stronger than cohort average so card is visible.
            await _upsert_day_row(
                db,
                child_id=target.child.id,
                day=day,
                age_band=age_band,
                words_encountered=8,
                words_mastered=3,
                minutes_total=22,
                mission_assigned=2,
                mission_completed=2,
                engagement_avg=0.78,
            )
            await _replace_seeded_mission_outcomes_for_day(
                db,
                child_id=target.child.id,
                day=day,
                age_band=age_band,
                child_seed=1000 + day_seed,
            )
            await _seed_content_performance_profile(
                db,
                day=day,
                child_id=target.child.id,
                age_band=age_band,
                templates=content_templates,
                child_seed=1000 + day_seed,
            )

            for index, peer in enumerate(peer_children, start=1):
                await _upsert_day_row(
                    db,
                    child_id=peer.id,
                    day=day,
                    age_band=age_band,
                    words_encountered=5 + (index % 4),
                    words_mastered=1 + (index % 3),
                    minutes_total=14 + (index % 8),
                    mission_assigned=2,
                    mission_completed=1 + (index % 2),
                    engagement_avg=0.55 + ((index % 5) * 0.06),
                )
                await _replace_seeded_mission_outcomes_for_day(
                    db,
                    child_id=peer.id,
                    day=day,
                    age_band=age_band,
                    child_seed=index + day_seed,
                )
                await _seed_content_performance_profile(
                    db,
                    day=day,
                    child_id=peer.id,
                    age_band=age_band,
                    templates=content_templates,
                    child_seed=index + day_seed,
                )

        await _seed_category_progress_profile(
            db,
            child_id=target.child.id,
            category_word_pool=category_word_pool,
            mastered_counts=[3, 2, 1, 2],
            practiced_at=practiced_at,
        )

        for index, peer in enumerate(peer_children, start=1):
            peer_mastered_counts = [
                min(
                    BENCHMARK_WORDS_PER_CATEGORY,
                    max(0, 2 + ((index + category_index) % 3) - 1),
                )
                for category_index in range(len(category_word_pool))
            ]
            await _seed_category_progress_profile(
                db,
                child_id=peer.id,
                category_word_pool=category_word_pool,
                mastered_counts=peer_mastered_counts,
                practiced_at=practiced_at,
            )

        await db.commit()

        print("[seed-benchmark] complete")
        print(f"[seed-benchmark] target_parent={target.parent.email} id={target.parent.id}")
        print(f"[seed-benchmark] target_child={target.child.name} id={target.child.id}")
        print(f"[seed-benchmark] age_band={age_band}")
        print(f"[seed-benchmark] peer_children_seeded={len(peer_children)}")
        print(f"[seed-benchmark] day_rows_per_child={len(day_offsets)}")
        print(f"[seed-benchmark] mission_source={BENCHMARK_MISSION_SOURCE}")
        print(f"[seed-benchmark] content_templates={len(content_templates)}")
        print(
            "[seed-benchmark] category_word_pool="
            + ", ".join(
                f"{entry['category_name']}({len(entry['word_ids'])})"
                for entry in category_word_pool
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed parent benchmark cohort sample data")
    parser.add_argument("--target-email", default="raymond@test.com")
    parser.add_argument("--child-id", default=None)
    parser.add_argument("--peer-users", type=int, default=100)
    parser.add_argument("--range-days", type=int, default=90)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        seed_benchmark_samples(
            target_email=args.target_email,
            child_id=args.child_id,
            peer_users=args.peer_users,
            range_days=args.range_days,
        )
    )
