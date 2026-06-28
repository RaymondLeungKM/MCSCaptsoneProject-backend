import unittest
from types import SimpleNamespace

from app.api.endpoints.vocabulary import approve_active_vocab_request


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, scalar=None, scalar_items=None):
        self._scalar = scalar
        self._scalar_items = scalar_items or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalars(self._scalar_items)


class FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.committed = False
        self.refreshed = []

    async def execute(self, _query):
        if not self._results:
            raise AssertionError("No fake DB results left for execute()")
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed.append(obj)


class ActiveVocabApprovalEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_approve_active_vocab_request_uses_latest_tracking_row_when_duplicates_exist(self):
        child = SimpleNamespace(id="child-1", parent_id="parent-1")
        progress = SimpleNamespace(
            child_id="child-1",
            word_id="word-1",
            pending_active_vocab_approval=True,
            active_vocab_requested_at="2026-06-22T10:00:00Z",
            mastered=False,
            mastered_at=None,
        )
        older_tracking = SimpleNamespace(
            id=10,
            used_actively=False,
            mastery_confidence=0.2,
            learned_context={"activity": "game"},
            story_priority=2,
        )
        latest_tracking = SimpleNamespace(
            id=11,
            used_actively=False,
            mastery_confidence=0.7,
            learned_context={"activity": "review", "note": "keep"},
            story_priority=4,
        )
        session = FakeSession(
            [
                FakeResult(scalar=child),
                FakeResult(scalar=progress),
                FakeResult(scalar_items=[latest_tracking, older_tracking]),
            ]
        )

        response = await approve_active_vocab_request(
            word_id="word-1",
            child_id="child-1",
            current_user=SimpleNamespace(id="parent-1"),
            db=session,
        )

        self.assertIs(response, progress)
        self.assertFalse(progress.pending_active_vocab_approval)
        self.assertIsNone(progress.active_vocab_requested_at)
        self.assertTrue(progress.mastered)
        self.assertIsNotNone(progress.mastered_at)

        self.assertTrue(latest_tracking.used_actively)
        self.assertEqual(latest_tracking.mastery_confidence, 1.0)
        self.assertEqual(latest_tracking.story_priority, 8)
        self.assertEqual(
            latest_tracking.learned_context,
            {
                "activity": "parent_confirmed_active_vocab",
                "source": "parent_dashboard",
                "note": "keep",
            },
        )

        self.assertFalse(older_tracking.used_actively)
        self.assertEqual(older_tracking.mastery_confidence, 0.2)
        self.assertEqual(session.added, [])
        self.assertTrue(session.committed)
        self.assertEqual(session.refreshed, [progress])


if __name__ == "__main__":
    unittest.main()
