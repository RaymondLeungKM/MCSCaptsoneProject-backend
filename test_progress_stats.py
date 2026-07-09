import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.endpoints.progress import get_progress_stats


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, *, scalar=None, scalar_items=None, rows=None):
        self._scalar = scalar
        self._scalar_items = scalar_items or []
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalars(self._scalar_items)

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, query):
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)

    async def commit(self):
        return None


class ProgressStatsTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats_ignore_zero_exposure_progress_rows(self):
        child = SimpleNamespace(id="child-1", parent_id="parent-1", current_streak=0)
        placeholder_progress = SimpleNamespace(
            word_id="word-0",
            exposure_count=0,
            mastered=False,
            visual_exposures=0,
            auditory_exposures=0,
            kinesthetic_exposures=0,
        )
        encountered_progress = SimpleNamespace(
            word_id="word-1",
            exposure_count=2,
            mastered=True,
            visual_exposures=1,
            auditory_exposures=0,
            kinesthetic_exposures=0,
        )
        fake_db = FakeSession(
            [
                FakeResult(scalar=child),
                FakeResult(scalar_items=[placeholder_progress, encountered_progress]),
                FakeResult(scalar_items=[]),
                FakeResult(scalar_items=[]),
                FakeResult(rows=[]),
                FakeResult(rows=[]),
            ]
        )

        with patch(
            "app.api.endpoints.progress.sync_child_metrics",
            AsyncMock(return_value=False),
        ):
            payload = await get_progress_stats(
                child_id="child-1",
                current_user=SimpleNamespace(id="parent-1"),
                db=fake_db,
            )

        self.assertEqual(payload["total_words"], 1)
        self.assertEqual(payload["mastered_words"], 1)
        self.assertEqual(payload["average_exposures_per_word"], 2.0)
        self.assertEqual(payload["active_vocabulary"], 0)
        self.assertEqual(payload["passive_vocabulary"], 1)


if __name__ == "__main__":
    unittest.main()