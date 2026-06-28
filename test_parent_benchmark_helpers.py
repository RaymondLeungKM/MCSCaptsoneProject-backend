import unittest

from app.api.endpoints.parent_dashboard import (
    _benchmark_band,
    _percentile_band,
    _trend_label,
)


class ParentBenchmarkHelperTests(unittest.TestCase):
    def test_benchmark_band_thresholds(self):
        self.assertEqual(_benchmark_band(12, 10), "ahead")
        self.assertEqual(_benchmark_band(9.5, 10), "on_track")
        self.assertEqual(_benchmark_band(7, 10), "needs_support")

    def test_percentile_band(self):
        values = [1, 2, 3, 4]
        self.assertEqual(_percentile_band(values, 1), "P25-P50")
        self.assertEqual(_percentile_band(values, 4), "P75-P100")

    def test_trend_label(self):
        self.assertEqual(_trend_label(10, 12), "up")
        self.assertEqual(_trend_label(10, 8), "down")
        self.assertEqual(_trend_label(10, 10.2), "flat")


if __name__ == "__main__":
    unittest.main()
