import unittest
from types import SimpleNamespace

from app.services.story_audio_metadata import build_story_payload


def make_story(*, page_audio_segments=None, audio_duration_seconds=12):
    return SimpleNamespace(
        id="story-1",
        child_id=None,
        title="Story",
        title_english=None,
        theme=None,
        story_type="curated",
        generation_date="2026-07-08T00:00:00",
        generated_at="2026-07-08T00:00:00",
        generated_by="test",
        content_cantonese="第一頁。第二頁。",
        content_english=None,
        jyutping=None,
        vocab_used=None,
        story_text="第一頁。第二頁。",
        story_text_ssml="<speak>第一頁。第二頁。</speak>",
        story_generate_provdier=None,
        story_generate_model=None,
        featured_words=[],
        word_usage=None,
        audio_url="/uploads/audio/story.mp3",
        audio_duration_seconds=audio_duration_seconds,
        audio_filename="story.mp3",
        page_audio_segments=page_audio_segments,
        audio_generate_provider="azure",
        audio_generate_voice_name="voice",
        reading_time_minutes=5,
        word_count=6,
        difficulty_level="easy",
        cultural_references=None,
        read_count=0,
        is_favorite=False,
        parent_approved=True,
        is_active=True,
        sort_order=0,
        ai_model=None,
        created_at="2026-07-08T00:00:00",
        updated_at=None,
    )


class StoryAudioMetadataTests(unittest.TestCase):
    def test_build_story_payload_prefers_stored_segments(self):
        story = make_story(
            page_audio_segments=[
                {
                    "page_index": 0,
                    "start_ratio": 0.0,
                    "end_ratio": 0.4,
                    "start_time_seconds": 0.0,
                    "end_time_seconds": 4.8,
                    "text_length": 3,
                },
                {
                    "page_index": 1,
                    "start_ratio": 0.4,
                    "end_ratio": 0.95,
                    "start_time_seconds": 4.8,
                    "end_time_seconds": 11.4,
                    "text_length": 3,
                },
            ]
        )

        payload = build_story_payload(story)

        self.assertEqual(len(payload.page_audio_segments), 2)
        self.assertEqual(payload.page_audio_segments[0].start_time_seconds, 0.0)
        self.assertEqual(payload.page_audio_segments[1].end_time_seconds, 12.0)
        self.assertEqual(payload.page_audio_segments[1].end_ratio, 1.0)

    def test_build_story_payload_falls_back_when_stored_segments_invalid(self):
        story = make_story(page_audio_segments=[{"bad": "payload"}])

        payload = build_story_payload(story)

        self.assertGreaterEqual(len(payload.page_audio_segments), 1)
        self.assertEqual(payload.page_audio_segments[-1].end_ratio, 1.0)


if __name__ == "__main__":
    unittest.main()