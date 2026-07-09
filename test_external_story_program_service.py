import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.external_story_program_service import ExternalStoryProgramService


class ExternalStoryProgramServiceTests(unittest.TestCase):
    def test_invoke_prefers_generated_story_audio_reference_when_present(self):
        service = ExternalStoryProgramService()
        stdout = """Generated Story:
從前有一個小朋友。
==========
Generated SSML:
<speak>從前有一個小朋友。</speak>
==========
Success! Audio saved to: /tmp/external-story.mp3
Generated app story saved to database (ID: generated-story-123)
Generated app story audio URL: /uploads/audio/generated-story.mp3
Generated app story audio filename: generated-story.mp3
Vocab used: 睡前, 星星
Using model: demo-model
"""

        with patch.object(service, "_resolve_program_dir", return_value=Path("/tmp/story-program")), \
             patch.object(service, "_resolve_python_bin", return_value="python3"), \
             patch.object(service, "_run_program", return_value=(stdout, "")), \
             patch.object(service, "_extract_audio_path", return_value=Path(__file__)), \
             patch.object(service, "_copy_external_audio", side_effect=AssertionError("unexpected copy")):
            result = service.invoke("child-1", "2026-07-09", "bedtime")

        self.assertEqual(result.generated_story_id, "generated-story-123")
        self.assertEqual(result.audio_url, "/uploads/audio/generated-story.mp3")
        self.assertEqual(result.audio_filename, "generated-story.mp3")
        self.assertEqual(result.vocab_used, "睡前, 星星")
        self.assertEqual(result.story_text, "從前有一個小朋友。")


if __name__ == "__main__":
    unittest.main()
