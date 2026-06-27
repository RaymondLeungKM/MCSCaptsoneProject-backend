"""
Concept cluster mission generation service (P2).

Builds 1-2 hop concept neighborhoods from the word graph and produces
mission drafts that can be injected into daily mission assignment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import List

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.word_personalization import WordRelationship
from app.models.vocabulary import Category, Word, WordProgress
from app.services.word_graph_service import auto_seed_relationships


@dataclass
class ClusterMissionDraft:
    cluster_id: str
    seed_word_id: str
    cluster_depth: int
    cluster_strategy: str
    target_word_ids: list[str]
    target_words_display: list[str]
    context: str
    theme_label: str
    related_theme_labels: list[str]
    title: str
    description: str
    conversation_prompts: list[str]


THEME_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "動物": ("animals", "animal", "動物"),
    "食物": ("food", "foods", "食物"),
    "蔬果": (
        "fruits & vegetables",
        "fruits and vegetables",
        "fruit & vegetables",
        "fruit and vegetables",
        "vegetables",
        "fruits",
        "蔬果",
    ),
    "玩具": ("toys", "toy", "玩具"),
    "大自然": ("nature", "natural", "大自然"),
    "文具": ("stationery", "school supplies", "文具"),
    "交通工具": (
        "transportation",
        "transport",
        "vehicles",
        "vehicle",
        "交通工具",
    ),
    "日常物品": ("household", "household items", "daily items", "日常物品"),
    "廚具": ("kitchen", "kitchenware", "cookware", "廚具"),
    "浴室用品": ("bathroom", "bathroom items", "浴室用品"),
    "電子產品": ("electronics", "electronic", "devices", "電子產品"),
    "衣服": ("clothing", "clothes", "衣物", "衣服"),
    "家庭": ("family", "families", "家庭"),
}


CATEGORY_THEME_LABELS: dict[str, str] = {
    alias: theme_label
    for theme_label, aliases in THEME_LABEL_ALIASES.items()
    for alias in aliases
}


def _display_word(word: Word | None) -> str:
    if word is None:
        return ""
    cantonese = (word.word_cantonese or "").strip()

    # Only surface human-readable Cantonese/Chinese labels in cluster missions.
    if (
        cantonese
        and "粵語詞語" not in cantonese
        and "繁體中文" not in cantonese
        and _contains_cjk(cantonese)
    ):
        return cantonese
    return ""


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", value))


def _normalize_category_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower().replace("&", " and ")
    normalized = re.sub(r"[-_/]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _resolve_theme_label(*values: str | None) -> str:
    for value in values:
        normalized = _normalize_category_key(value)
        if normalized in CATEGORY_THEME_LABELS:
            return CATEGORY_THEME_LABELS[normalized]

    for value in values:
        if value and value.strip():
            return value.strip()

    return "生活"


def _pick_theme_labels(categories: list[str]) -> tuple[str, list[str]]:
    labels = _dedupe_preserve_order([_resolve_theme_label(category) for category in categories])
    if not labels:
        return "生活", []

    primary = labels[0]
    related = [label for label in labels[1:] if label != primary][:2]
    return primary, related


def _context_phrase(context: str) -> str:
    mapping = {
        "mealtime": "用餐情境",
        "outdoor": "戶外觀察",
        "bedtime": "睡前共讀",
        "playtime": "遊戲情境",
    }
    return mapping.get(context, "生活情境")


def _build_cluster_description(
    *,
    seed_display: str,
    display_words: list[str],
    context: str,
    theme_label: str,
) -> str:
    context_label = _context_phrase(context)
    cjk_words = [word for word in display_words if _contains_cjk(word)]
    headline_words = (cjk_words or display_words)[:3]

    # If words are mostly non-Chinese labels, avoid listing them in a Chinese
    # sentence to keep mission copy natural for parents and children.
    if len(cjk_words) < 2:
        return (
            f"圍繞「{theme_label}」主題與「{seed_display}」進行{context_label}練習，"
            "先辨認再開口，最後用完整句描述孩子看到或做到的內容。"
        )

    headline = "、".join(headline_words)
    return (
        f"這組任務會圍繞「{theme_label}」主題，串連相關詞語（{headline}），"
        f"在{context_label}中先辨認再輸出，建立穩定語用連結。"
    )


def _build_cluster_title(*, theme_label: str, seed_display: str) -> str:
    return f"{theme_label}主題串連：{seed_display}"


def _build_practical_prompts(
    *,
    context: str,
    seed_display: str,
    display_words: list[str],
) -> list[str]:
    second_word = display_words[1] if len(display_words) > 1 else seed_display

    if context == "mealtime":
        return [
            f"開飯前請孩子指出兩樣食物：『{seed_display}』同『{second_word}』。",
            f"請孩子講一句完整句：『我今日想食{seed_display}。』",
            "食完飯後，請孩子再講一次最容易混淆的詞語，並說出它的顏色或味道。",
        ]

    if context == "outdoor":
        return [
            f"去公園時請孩子找出『{seed_display}』或『{second_word}』相關事物。",
            f"請孩子用『{seed_display}』講一句觀察句，例如：『我見到...』。",
            "活動結束前，請孩子重複一次新詞並配合動作表達意思。",
        ]

    if context == "bedtime":
        return [
            f"睡前親子共讀時，請孩子指出『{seed_display}』同『{second_word}』。",
            f"請孩子用『{seed_display}』講一句故事句，家長再接續下一句。",
            "故事結尾請孩子再讀一次最容易混淆的詞語，幫助鞏固記憶。",
        ]

    return [
        f"請孩子先認讀『{seed_display}』同『{second_word}』。",
        f"請孩子用『{seed_display}』講一句生活情境句。",
        "完成後請孩子再說一次最容易混淆的詞語，並指出它和其他詞的分別。",
    ]


def _pick_context_from_categories(categories: List[str]) -> str:
    normalized = {_normalize_category_key(value) for value in categories if value}
    if {"food", "食物", "fruits & vegetables", "fruits and vegetables", "蔬果", "kitchen", "廚具"} & normalized:
        return "mealtime"
    if {"nature", "animals", "大自然", "動物", "transportation", "交通工具"} & normalized:
        return "outdoor"
    if {"family", "家庭"} & normalized:
        return "bedtime"
    return "playtime"


async def _pick_seed_word(
    db: AsyncSession,
    *,
    child_id: str,
) -> Word | None:
    base_query = (
        select(Word, WordProgress)
        .join(WordProgress, WordProgress.word_id == Word.id)
        .where(
            and_(
                WordProgress.child_id == child_id,
                Word.is_active == True,
                WordProgress.exposure_count > 0,
                WordProgress.mastered.is_(False),
            )
        )
        .order_by(
            WordProgress.success_rate.asc(),
            WordProgress.exposure_count.desc(),
            Word.created_at.desc(),
        )
    )

    # Prefer seed words that are already connected in the graph so cluster
    # expansion is less likely to return <2 words and abort mission creation.
    connected_result = await db.execute(
        base_query.where(
            exists(
                select(1).where(
                    and_(
                        WordRelationship.word_id == Word.id,
                        WordRelationship.strength >= 0.45,
                    )
                )
            )
        ).limit(1)
    )
    row = connected_result.first()
    if row:
        return row[0]

    # Fallback to the original ranking if no connected candidate exists.
    result = await db.execute(base_query.limit(1))
    row = result.first()
    return row[0] if row else None


async def _collect_cluster_word_ids(
    db: AsyncSession,
    *,
    seed_word_id: str,
    max_hops: int = 2,
    min_strength: float = 0.45,
    max_words: int = 6,
) -> list[str]:
    visited = {seed_word_id}
    frontier = [seed_word_id]

    for _ in range(max_hops):
        if not frontier or len(visited) >= max_words:
            break

        edge_result = await db.execute(
            select(WordRelationship)
            .where(
                WordRelationship.word_id.in_(frontier),
                WordRelationship.strength >= min_strength,
            )
            .order_by(WordRelationship.strength.desc())
            .limit(max_words * 4)
        )
        edges = edge_result.scalars().all()

        next_frontier: list[str] = []
        for edge in edges:
            if edge.related_word_id in visited:
                continue
            visited.add(edge.related_word_id)
            next_frontier.append(edge.related_word_id)
            if len(visited) >= max_words:
                break

        frontier = next_frontier

    return list(visited)


async def generate_cluster_mission_draft(
    db: AsyncSession,
    *,
    child_id: str,
    assignment_date: date,
) -> ClusterMissionDraft | None:
    seed = await _pick_seed_word(db, child_id=child_id)
    if seed is None:
        return None

    # After DB cleanup + reseed, the word graph table can be empty even when
    # words/progress exist. Bootstrap the seed neighborhood lazily so cluster
    # missions still generate without requiring a separate graph warm-up job.
    seed_edge_result = await db.execute(
        select(WordRelationship.id)
        .where(WordRelationship.word_id == seed.id)
        .limit(1)
    )
    if seed_edge_result.scalar_one_or_none() is None:
        await auto_seed_relationships(db, seed.id)

    cluster_word_ids = await _collect_cluster_word_ids(
        db,
        seed_word_id=seed.id,
        max_hops=2,
        min_strength=0.45,
        max_words=6,
    )

    if len(cluster_word_ids) < 2:
        return None

    words_result = await db.execute(
        select(Word, Category)
        .outerjoin(Category, Category.id == Word.category)
        .where(Word.id.in_(cluster_word_ids), Word.is_active == True)
    )
    rows = words_result.all()
    word_map = {word.id: word for word, _ in rows}
    category_map = {word.id: category for word, category in rows}

    ordered_ids = [seed.id] + [word_id for word_id in cluster_word_ids if word_id != seed.id]
    ordered_ids = [word_id for word_id in ordered_ids if word_id in word_map][:5]

    if len(ordered_ids) < 2:
        return None

    display_words = [_display_word(word_map.get(word_id)) for word_id in ordered_ids]
    display_words = _dedupe_preserve_order(display_words)

    if len(display_words) < 2:
        return None

    categories = []
    for word_id in ordered_ids:
        category = category_map.get(word_id)
        if category is None:
            continue
        categories.append(category.name_cantonese or category.name)

    theme_label, related_theme_labels = _pick_theme_labels(categories)
    context = _pick_context_from_categories(categories)

    seed_display = _display_word(seed) or "重點詞語"
    return ClusterMissionDraft(
        cluster_id=f"cluster-{child_id[:8]}-{assignment_date.strftime('%Y%m%d')}-{seed.id[:8]}",
        seed_word_id=seed.id,
        cluster_depth=2,
        cluster_strategy="two_hop_bridge",
        target_word_ids=ordered_ids,
        target_words_display=display_words,
        context=context,
        theme_label=theme_label,
        related_theme_labels=related_theme_labels,
        title=_build_cluster_title(theme_label=theme_label, seed_display=seed_display),
        description=_build_cluster_description(
            seed_display=seed_display,
            display_words=display_words,
            context=context,
            theme_label=theme_label,
        ),
        conversation_prompts=_build_practical_prompts(
            context=context,
            seed_display=seed_display,
            display_words=display_words,
        ),
    )
