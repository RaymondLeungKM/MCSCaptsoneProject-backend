import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.endpoints.children import _replace_child_interests


class _ChildWithoutLazyInterestAccess(SimpleNamespace):
    @property
    def interests(self):
        raise AssertionError("_replace_child_interests should not access child.interests")


class ReplaceChildInterestsTests(unittest.IsolatedAsyncioTestCase):
    async def test_replaces_interests_without_touching_relationship(self):
        child = _ChildWithoutLazyInterestAccess(id="child-1")
        db = MagicMock()
        db.execute = AsyncMock()
        db.add_all = MagicMock()

        with patch(
            "app.api.endpoints.children._resolve_interest_category_ids",
            AsyncMock(return_value=["animals", "music"]),
        ):
            await _replace_child_interests(db, child, ["Animals", "Music"])

        db.execute.assert_awaited_once()
        inserted = db.add_all.call_args.args[0]
        self.assertEqual([item.child_id for item in inserted], ["child-1", "child-1"])
        self.assertEqual([item.category_id for item in inserted], ["animals", "music"])

    async def test_skips_insert_when_no_interests_resolve(self):
        child = _ChildWithoutLazyInterestAccess(id="child-1")
        db = MagicMock()
        db.execute = AsyncMock()
        db.add_all = MagicMock()

        with patch(
            "app.api.endpoints.children._resolve_interest_category_ids",
            AsyncMock(return_value=[]),
        ):
            await _replace_child_interests(db, child, [])

        db.execute.assert_awaited_once()
        db.add_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()