from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, List, Optional

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


def coerce_story_page_audio_segments(
    raw_segments: Any,
    duration_seconds: Optional[int],
) -> List[StoryPageAudioSegment]:
    if not isinstance(raw_segments, list):
        return []

    resolved_duration = float(duration_seconds) if duration_seconds and duration_seconds > 0 else None
    segments: list[StoryPageAudioSegment] = []

    for raw_segment in raw_segments:
        try:
            segment = StoryPageAudioSegment.model_validate(raw_segment)
        except Exception:
            continue

        start_time = max(0.0, float(segment.start_time_seconds))
        end_time = max(start_time, float(segment.end_time_seconds))
        if resolved_duration is not None:
            start_time = min(start_time, resolved_duration)
            end_time = min(end_time, resolved_duration)
            start_ratio = round(start_time / resolved_duration, 6)
            end_ratio = round(end_time / resolved_duration, 6)
        else:
            start_ratio = max(0.0, min(1.0, float(segment.start_ratio)))
            end_ratio = max(start_ratio, min(1.0, float(segment.end_ratio)))

        segments.append(
            StoryPageAudioSegment(
                page_index=int(segment.page_index),
                start_ratio=start_ratio,
                end_ratio=end_ratio,
                start_time_seconds=round(start_time, 3),
                end_time_seconds=round(end_time, 3),
                text_length=max(0, int(segment.text_length)),
            )
        )

    segments.sort(key=lambda segment: segment.page_index)
    if segments and resolved_duration is not None:
        last_segment = segments[-1]
        segments[-1] = StoryPageAudioSegment(
            page_index=last_segment.page_index,
            start_ratio=last_segment.start_ratio,
            end_ratio=1.0,
            start_time_seconds=last_segment.start_time_seconds,
            end_time_seconds=round(resolved_duration, 3),
            text_length=last_segment.text_length,
        )

    return segments


def build_story_payload(story: GeneratedStory) -> GeneratedStoryResponse:
    resolved_duration = resolve_story_audio_duration_seconds(story)
    payload = {
        field_name: getattr(story, field_name)
        for field_name in GeneratedStoryResponse.model_fields
        if field_name != "page_audio_segments"
    }
    payload["audio_duration_seconds"] = resolved_duration
    stored_segments = coerce_story_page_audio_segments(
        getattr(story, "page_audio_segments", None),
        resolved_duration,
    )
    payload["page_audio_segments"] = stored_segments or build_story_page_audio_segments(
        story.content_cantonese or story.story_text or "",
        resolved_duration,
    )
    return GeneratedStoryResponse(**payload)