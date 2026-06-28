import unittest
from datetime import date
from types import SimpleNamespace

from app.api.endpoints.parent_dashboard import _benchmark_tip, get_parent_benchmarks


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, rows=None, scalar=None, scalar_items=None):
        self._rows = rows or []
        self._scalar = scalar
        self._scalar_items = scalar_items or []

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

    def scalars(self):
        return FakeScalars(self._scalar_items)

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)


class P5FairnessSafetyLanguageTests(unittest.IsolatedAsyncioTestCase):
    def test_benchmark_tips_avoid_harmful_or_ranking_language(self):
        disallowed_terms = [
            "失敗",
            "懲罰",
            "笨",
            "差過",
            "落後",
            "排名",
            "worst",
            "failure",
            "stupid",
            "behind",
        ]

        for metric in ["pace", "engagement"]:
            for band in ["ahead", "on_track", "needs_support"]:
                tip = _benchmark_tip(metric, band)
                self.assertTrue(tip)
                for term in disallowed_terms:
                    self.assertNotIn(term, tip)

    async def test_parent_benchmark_recommendations_are_supportive(self):
        parent_user = SimpleNamespace(id="parent-1", consent_analytics=True)
        child = SimpleNamespace(id="child-1", parent_id="parent-1", age=5)

        child_rows = [
            SimpleNamespace(
                child_id="child-1",
                activity_day=date(2026, 6, 20),
                words_mastered=4,
                session_minutes_total=11,
            ),
            SimpleNamespace(
                child_id="child-1",
                activity_day=date(2026, 6, 21),
                words_mastered=5,
                session_minutes_total=12,
            ),
        ]
        cohort_rows = child_rows + [
            SimpleNamespace(
                child_id="child-2",
                activity_day=date(2026, 6, 20),
                words_mastered=3,
                session_minutes_total=8,
            ),
            SimpleNamespace(
                child_id="child-2",
                activity_day=date(2026, 6, 21),
                words_mastered=3,
                session_minutes_total=9,
            ),
        ]

        benchmark_session = FakeSession(
            [
                FakeResult(scalar=child),
                FakeResult(scalar_items=child_rows),
                FakeResult(scalar_items=cohort_rows),
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            category="food",
                            total_count=12,
                            mastered_count=7,
                        )
                    ]
                ),
                FakeResult(
                    rows=[
                        SimpleNamespace(
                            category="food",
                            total_count=30,
                            mastered_count=12,
                        )
                    ]
                ),
                FakeResult(
                    rows=[
                        SimpleNamespace(id="food", name_cantonese="食物", name="Food")
                    ]
                ),
            ]
        )

        response = await get_parent_benchmarks(
            child_id="child-1",
            range_days=28,
            minimum_cohort_threshold=2,
            current_user=parent_user,
            db=benchmark_session,
        )

        all_tips = [response.pace_benchmark.tips, response.engagement_benchmark.tips] + [
            item.tips for item in response.category_benchmarks
        ]
        for tip in all_tips:
            self.assertIn("可", tip)
            self.assertNotIn("排名", tip)
            self.assertNotIn("落後", tip)


if __name__ == "__main__":
    unittest.main()
