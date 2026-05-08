import unittest
from datetime import date

from app.services.child_metrics import calculate_current_streak


class CalculateCurrentStreakTests(unittest.TestCase):
    def test_returns_zero_without_activity(self):
        self.assertEqual(
            calculate_current_streak([], as_of=date(2026, 5, 8)),
            0,
        )

    def test_counts_consecutive_days_ending_today(self):
        self.assertEqual(
            calculate_current_streak(
                [date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)],
                as_of=date(2026, 5, 8),
            ),
            3,
        )

    def test_counts_consecutive_days_ending_yesterday(self):
        self.assertEqual(
            calculate_current_streak(
                [date(2026, 5, 5), date(2026, 5, 6), date(2026, 5, 7)],
                as_of=date(2026, 5, 8),
            ),
            3,
        )

    def test_resets_to_latest_run_when_gap_exists(self):
        self.assertEqual(
            calculate_current_streak(
                [date(2026, 5, 4), date(2026, 5, 6), date(2026, 5, 7)],
                as_of=date(2026, 5, 8),
            ),
            2,
        )

    def test_returns_zero_when_latest_activity_is_stale(self):
        self.assertEqual(
            calculate_current_streak(
                [date(2026, 5, 3), date(2026, 5, 4)],
                as_of=date(2026, 5, 8),
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()