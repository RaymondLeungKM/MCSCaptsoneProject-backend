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
import random
from collections import defaultdict
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
WEEKDAY_ACTIVITY_BIAS = {
    0: 0.10,
    1: 0.06,
    2: 0.03,
    3: 0.05,
    4: 0.08,
    5: -0.07,
    6: -0.10,
}


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


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _clamp_float(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _build_daily_participation_profile(
    *,
    day: date,
    day_index: int,
    total_days: int,
    child_seed: int,
    child_index: int,
    is_target: bool,
) -> dict[str, object]:
    profile_rng = random.Random(f"benchmark-profile:{child_seed}:{child_index}:{int(is_target)}")
    day_rng = random.Random(f"benchmark-day:{child_seed}:{child_index}:{day.toordinal()}")

    phase = day_index / max(total_days - 1, 1)
    weekday_bias = WEEKDAY_ACTIVITY_BIAS[day.weekday()]
    child_baseline = 0.50 + (0.05 if is_target else -0.02) + profile_rng.uniform(-0.08, 0.07)
    trend = profile_rng.uniform(-0.04, 0.06) * phase
    burst = 0.0
    burst_roll = day_rng.random()
    if burst_roll < 0.08:
        burst = 0.12 + profile_rng.uniform(0.0, 0.05)
    elif burst_roll < 0.14:
        burst = -0.10 - profile_rng.uniform(0.0, 0.04)

    score = child_baseline + weekday_bias + trend + burst + day_rng.uniform(-0.10, 0.10)
    active_threshold = 0.56 if is_target else 0.58
    is_active = score >= active_threshold

    if not is_active:
        return {"is_active": False}

    intensity = _clamp_float(0.38 + (score * 0.42) + day_rng.uniform(-0.04, 0.06), 0.22, 0.94)
    words_encountered = _clamp_int(
        int(round(3 + (score * 4) + day_rng.randint(0, 2))),
        2,
        9,
    )

    # Keep mastery sparse in benchmark seeding so platform-level daily averages
    # are plausible even with a larger synthetic peer cohort.
    if is_target:
        mastery_probability = _clamp_float(0.20 + max(score - 0.56, 0.0) * 0.60, 0.06, 0.62)
    else:
        mastery_probability = _clamp_float(0.07 + max(score - 0.60, 0.0) * 0.30, 0.02, 0.30)

    words_mastered = 1 if day_rng.random() < mastery_probability else 0
    if words_mastered > 0 and score > 0.82 and day_rng.random() < (0.10 if is_target else 0.03):
        words_mastered += 1
    words_mastered = _clamp_int(words_mastered, 0, max(0, words_encountered // 2))

    minutes_total = _clamp_int(
        int(round(10 + (score * 16) + day_rng.randint(-1, 5))),
        8,
        28,
    )
    mission_assigned = _clamp_int(
        1 + int(score > 0.68) + int(day_rng.random() > 0.75),
        1,
        3,
    )
    mission_completed = min(
        mission_assigned,
        1 + int(score > 0.74) + int(day_rng.random() > 0.58),
    )

    return {
        "is_active": True,
        "words_encountered": words_encountered,
        "words_mastered": words_mastered,
        "minutes_total": minutes_total,
        "mission_assigned": mission_assigned,
        "mission_completed": mission_completed,
        "engagement_avg": round(intensity, 2),
    }


def _count_recent_active_days(active_days: list[date], current_day: date, window_days: int) -> int:
    start_day = current_day - timedelta(days=window_days - 1)
    return sum(1 for active_day in active_days if start_day <= active_day <= current_day)


async def _clear_seeded_participation_rows(
    db,
    *,
    child_ids: list[str],
    start_day: date,
    end_day: date,
) -> None:
    await db.execute(
        delete(ChildDayAnalytics).where(
            ChildDayAnalytics.child_id.in_(child_ids),
            ChildDayAnalytics.activity_day >= start_day,
            ChildDayAnalytics.activity_day <= end_day,
        )
    )
    await db.execute(
        delete(ContentPerformanceAnalytics).where(
            ContentPerformanceAnalytics.child_id.in_(child_ids),
            ContentPerformanceAnalytics.activity_day >= start_day,
            ContentPerformanceAnalytics.activity_day <= end_day,
        )
    )
    await db.execute(
        delete(MissionOutcomeAnalytics).where(
            MissionOutcomeAnalytics.child_id.in_(child_ids),
            MissionOutcomeAnalytics.activity_day >= start_day,
            MissionOutcomeAnalytics.activity_day <= end_day,
            MissionOutcomeAnalytics.source.in_(["seed", "seed-benchmark"]),
        )
    )


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
    row.active_days_7d = 1
    row.active_days_28d = 1


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

        seeded_child_ids = [target.child.id, *[child.id for child in peer_children]]
        today = date.today()
        range_start = today - timedelta(days=range_days - 1)
        await _clear_seeded_participation_rows(
            db,
            child_ids=seeded_child_ids,
            start_day=range_start,
            end_day=today,
        )

        practiced_at = datetime.now(timezone.utc)
        day_offsets = list(range(range_days - 1, -1, -1))
        active_history_by_child: dict[str, list[date]] = defaultdict(list)
        target_seed = 1000

        for day_index, offset in enumerate(day_offsets):
            day = today - timedelta(days=offset)
            day_seed = (today - day).days

            target_profile = _build_daily_participation_profile(
                day=day,
                day_index=day_index,
                total_days=range_days,
                child_seed=target_seed,
                child_index=0,
                is_target=True,
            )
            if target_profile["is_active"]:
                active_history_by_child[target.child.id].append(day)
                await _upsert_day_row(
                    db,
                    child_id=target.child.id,
                    day=day,
                    age_band=age_band,
                    words_encountered=int(target_profile["words_encountered"]),
                    words_mastered=int(target_profile["words_mastered"]),
                    minutes_total=int(target_profile["minutes_total"]),
                    mission_assigned=int(target_profile["mission_assigned"]),
                    mission_completed=int(target_profile["mission_completed"]),
                    engagement_avg=float(target_profile["engagement_avg"]),
                )
                target_row_result = await db.execute(
                    select(ChildDayAnalytics).where(
                        ChildDayAnalytics.child_id == target.child.id,
                        ChildDayAnalytics.activity_day == day,
                    )
                )
                target_row = target_row_result.scalar_one_or_none()
                if target_row is not None:
                    target_row.active_days_7d = _count_recent_active_days(
                        active_history_by_child[target.child.id],
                        day,
                        7,
                    )
                    target_row.active_days_28d = _count_recent_active_days(
                        active_history_by_child[target.child.id],
                        day,
                        28,
                    )
            await _replace_seeded_mission_outcomes_for_day(
                db,
                child_id=target.child.id,
                day=day,
                age_band=age_band,
                child_seed=target_seed + day_seed,
            )
            await _seed_content_performance_profile(
                db,
                day=day,
                child_id=target.child.id,
                age_band=age_band,
                templates=content_templates,
                child_seed=target_seed + day_seed,
            )

            for index, peer in enumerate(peer_children, start=1):
                peer_seed = 2000 + (index * 37)
                peer_profile = _build_daily_participation_profile(
                    day=day,
                    day_index=day_index,
                    total_days=range_days,
                    child_seed=peer_seed,
                    child_index=index,
                    is_target=False,
                )
                if peer_profile["is_active"]:
                    active_history_by_child[peer.id].append(day)
                    await _upsert_day_row(
                        db,
                        child_id=peer.id,
                        day=day,
                        age_band=age_band,
                        words_encountered=int(peer_profile["words_encountered"]),
                        words_mastered=int(peer_profile["words_mastered"]),
                        minutes_total=int(peer_profile["minutes_total"]),
                        mission_assigned=int(peer_profile["mission_assigned"]),
                        mission_completed=int(peer_profile["mission_completed"]),
                        engagement_avg=float(peer_profile["engagement_avg"]),
                    )
                    peer_row_result = await db.execute(
                        select(ChildDayAnalytics).where(
                            ChildDayAnalytics.child_id == peer.id,
                            ChildDayAnalytics.activity_day == day,
                        )
                    )
                    peer_row = peer_row_result.scalar_one_or_none()
                    if peer_row is not None:
                        peer_row.active_days_7d = _count_recent_active_days(
                            active_history_by_child[peer.id],
                            day,
                            7,
                        )
                        peer_row.active_days_28d = _count_recent_active_days(
                            active_history_by_child[peer.id],
                            day,
                            28,
                        )
                await _replace_seeded_mission_outcomes_for_day(
                    db,
                    child_id=peer.id,
                    day=day,
                    age_band=age_band,
                    child_seed=peer_seed + day_seed,
                )
                await _seed_content_performance_profile(
                    db,
                    day=day,
                    child_id=peer.id,
                    age_band=age_band,
                    templates=content_templates,
                    child_seed=peer_seed + day_seed,
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
        print(f"[seed-benchmark] day_window_days={range_days}")
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
