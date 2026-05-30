import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.api.endpoints.analytics import _normalize_activity_day
from app.api.endpoints.parent_dashboard import (
    _build_category_mastery_progress,
    _normalize_tracking_day,
    _rounded_minutes_from_total_seconds,
    _summarize_sessions_by_day,
)


def make_session(
    start_time: datetime,
    end_time: datetime,
    *,
    duration_minutes: int = 0,
):
    return SimpleNamespace(
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
    )


class ParentAnalyticsAggregationTests(unittest.TestCase):
    def test_normalizes_hkt_day_boundaries(self):
        timestamp = datetime(2026, 5, 29, 16, 58, 36, tzinfo=timezone.utc)

        self.assertEqual(_normalize_tracking_day(timestamp), date(2026, 5, 30))
        self.assertEqual(_normalize_activity_day(timestamp), date(2026, 5, 30))

    def test_session_summary_merges_adjacent_fragments_before_counting(self):
        sessions = [
            make_session(
                datetime(2026, 5, 27, 15, 10, 36, tzinfo=timezone.utc),
                datetime(2026, 5, 27, 15, 10, 42, tzinfo=timezone.utc),
            ),
            make_session(
                datetime(2026, 5, 27, 15, 10, 42, tzinfo=timezone.utc),
                datetime(2026, 5, 27, 15, 11, 25, tzinfo=timezone.utc),
            ),
            make_session(
                datetime(2026, 5, 29, 16, 58, 26, tzinfo=timezone.utc),
                datetime(2026, 5, 29, 16, 58, 50, tzinfo=timezone.utc),
            ),
        ]

        summary = _summarize_sessions_by_day(
            sessions,
            start_day=date(2026, 5, 27),
            end_day=date(2026, 5, 30),
            now_utc=datetime(2026, 5, 30, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(summary[date(2026, 5, 27)]["session_count"], 1)
        self.assertAlmostEqual(summary[date(2026, 5, 27)]["total_seconds"], 49.0)
        self.assertEqual(summary[date(2026, 5, 30)]["session_count"], 1)
        self.assertAlmostEqual(summary[date(2026, 5, 30)]["total_seconds"], 24.0)

    def test_rounds_minutes_after_merging(self):
        self.assertEqual(_rounded_minutes_from_total_seconds(95.0), 2)
        self.assertEqual(_rounded_minutes_from_total_seconds(4.0), 0)
        self.assertEqual(_rounded_minutes_from_total_seconds(24.0), 0)
        self.assertEqual(
            _rounded_minutes_from_total_seconds(24.0, has_words=True),
            1,
        )

    def test_category_mastery_progress_uses_mastered_words(self):
        progress = _build_category_mastery_progress(
            category_id="animals",
            category_name="Animals",
            category_name_cantonese="動物",
            total_words=10,
            mastered_words=3,
            recent_activity=2,
        )

        self.assertEqual(progress.words_learned, 3)
        self.assertEqual(progress.total_words, 10)
        self.assertEqual(progress.recent_activity, 2)
        self.assertEqual(progress.progress_percentage, 30.0)


if __name__ == "__main__":
    unittest.main()