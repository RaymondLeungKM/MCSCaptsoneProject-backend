import unittest
from datetime import date

from fastapi import HTTPException

from app.api.endpoints.admin_analytics import (
    _build_funnel_metrics,
    _confidence_signal,
    _effectiveness_score,
    _resolve_date_range,
)


class AdminAnalyticsHelperTests(unittest.TestCase):
    def test_resolve_date_range_uses_defaults_when_omitted(self):
        start_day, end_day = _resolve_date_range(None, date(2026, 6, 21), default_days=7)
        self.assertEqual(end_day, date(2026, 6, 21))
        self.assertEqual(start_day, date(2026, 6, 15))

    def test_resolve_date_range_rejects_inverted_window(self):
        with self.assertRaises(HTTPException):
            _resolve_date_range(date(2026, 6, 22), date(2026, 6, 21))

    def test_build_funnel_metrics_computes_rates(self):
        metrics = _build_funnel_metrics(
            {
                "assigned": 20,
                "started": 10,
                "completed": 8,
                "skipped": 1,
                "expired": 1,
            }
        )
        self.assertEqual(metrics.assigned, 20)
        self.assertEqual(metrics.started, 10)
        self.assertEqual(metrics.completed, 8)
        self.assertEqual(metrics.start_rate, 0.5)
        self.assertEqual(metrics.completion_rate, 0.4)
        self.assertEqual(metrics.completion_from_started_rate, 0.8)

    def test_effectiveness_score_and_confidence_signal(self):
        self.assertEqual(_confidence_signal(4), "low")
        self.assertEqual(_confidence_signal(10), "medium")
        self.assertEqual(_confidence_signal(30), "high")

        score = _effectiveness_score(0.8, 0.75, 0.6)
        self.assertAlmostEqual(score, 0.7425, places=4)


if __name__ == "__main__":
    unittest.main()
