from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Optional

from mutagen.mp3 import MP3

from app.models.daily_words import GeneratedStory
from app.schemas.stories import GeneratedStoryResponse, StoryPageAudioSegment

STORY_PAGE_TARGET_CHARS = 120


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_narrative_chunks(text: str) -> tuple[list[str], str]:
    normalized_text = (text or "").strip()
    if not normalized_text:
        return [], " "

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n+", normalized_text)
        if paragraph.strip()
    ]
    if len(paragraphs) > 1:
        return paragraphs, "\n\n"

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", normalized_text)
        if sentence.strip()
    ]
    if sentences:
        return sentences, " "

    return [normalized_text], " "


def paginate_story_text(text: str, target_chars: int = STORY_PAGE_TARGET_CHARS) -> list[str]:
    normalized_text = (text or "").strip()
    if not normalized_text:
        return [""]

    chunks, joiner = _get_narrative_chunks(normalized_text)
    story_pages: list[str] = []
    current_chunk = ""

    for chunk in chunks:
        candidate = f"{current_chunk}{joiner}{chunk}" if current_chunk else chunk
        if current_chunk and len(candidate) > target_chars:
            story_pages.append(current_chunk.strip())
            current_chunk = chunk
        else:
            current_chunk = candidate

    if current_chunk:
        story_pages.append(current_chunk.strip())

    return story_pages or [normalized_text]


def _resolve_story_audio_path(story: GeneratedStory) -> Optional[Path]:
    backend_root = _backend_root()

    audio_url = (story.audio_url or "").strip()
    if audio_url and not audio_url.startswith(("http://", "https://")):
        candidate = backend_root / audio_url.lstrip("/")
        if candidate.is_file():
            return candidate

    audio_filename = (story.audio_filename or "").strip()
    if audio_filename:
        candidate = backend_root / "uploads" / "audio" / audio_filename
        if candidate.is_file():
            return candidate

    return None


def resolve_story_audio_duration_seconds(story: GeneratedStory) -> Optional[int]:
    if story.audio_duration_seconds and story.audio_duration_seconds > 0:
        return int(story.audio_duration_seconds)

    audio_path = _resolve_story_audio_path(story)
    if audio_path is not None:
        try:
            duration_seconds = MP3(str(audio_path)).info.length
            if math.isfinite(duration_seconds) and duration_seconds > 0:
                return max(1, int(round(duration_seconds)))
        except Exception:
            pass

    if story.reading_time_minutes and story.reading_time_minutes > 0:
        return int(story.reading_time_minutes) * 60

    normalized_text = (story.content_cantonese or story.story_text or "").strip()
    if normalized_text:
        return max(1, int(len(normalized_text) / 2.8))

    return None


def build_story_page_audio_segments(
    text: str,
    duration_seconds: Optional[int],
) -> List[StoryPageAudioSegment]:
    pages = paginate_story_text(text)
    if not pages or duration_seconds is None or duration_seconds <= 0:
        return []

    page_char_counts = [len(page.strip()) for page in pages]
    total_chars = sum(page_char_counts)
    segments: list[StoryPageAudioSegment] = []

    cumulative_chars = 0
    for index, count in enumerate(page_char_counts):
        if total_chars > 0:
            start_ratio = cumulative_chars / total_chars
            cumulative_chars += count
            end_ratio = cumulative_chars / total_chars
        else:
            start_ratio = index / len(pages)
            end_ratio = (index + 1) / len(pages)

        segments.append(
            StoryPageAudioSegment(
                page_index=index,
                start_ratio=start_ratio,
                end_ratio=end_ratio,
                start_time_seconds=round(start_ratio * duration_seconds, 3),
                end_time_seconds=round(end_ratio * duration_seconds, 3),
                text_length=count,
            )
        )

    return segments


def build_story_payload(story: GeneratedStory) -> GeneratedStoryResponse:
    resolved_duration = resolve_story_audio_duration_seconds(story)
    payload = GeneratedStoryResponse.model_validate(story).model_dump()
    payload["audio_duration_seconds"] = resolved_duration
    payload["page_audio_segments"] = build_story_page_audio_segments(
        story.content_cantonese or story.story_text or "",
        resolved_duration,
    )
    return GeneratedStoryResponse(**payload)