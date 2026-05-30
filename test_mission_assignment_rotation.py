import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.endpoints.missions import (
    _build_mission_summary_payload,
    _current_hkt_date,
    _rank_candidate_missions,
    _serialize_assigned_mission,
    _was_completed_recently,
)
from app.models.content import (
    MissionAssignmentStatus,
    MissionAssignmentSource,
    MissionContext,
    MissionSurface,
)


def make_mission(mission_id: str, *, sort_order: int, created_at: datetime):
    return SimpleNamespace(
        id=mission_id,
        slug=mission_id,
        title=mission_id,
        description="",
        context=MissionContext.GENERAL,
        is_offline=False,
        status="published",
        locale="zh-HK",
        age_min=None,
        age_max=None,
        difficulty=None,
        surface="both",
        sort_order=sort_order,
        selection_tags=[],
        catalog_metadata=None,
        published_at=None,
        archived_at=None,
        target_words=[],
        conversation_prompts=[],
        is_active=True,
        created_at=created_at,
        updated_at=None,
    )


def make_assignment(
    mission_id: str,
    *,
    assignment_date: date,
    completed_at: datetime,
    status: MissionAssignmentStatus = MissionAssignmentStatus.COMPLETED,
):
    return SimpleNamespace(
        id=f"assignment-{mission_id}-{assignment_date.isoformat()}",
        child_id="child-1",
        mission_id=mission_id,
        assignment_date=assignment_date,
        source=MissionAssignmentSource.SYSTEM,
        status=status,
        surface=MissionSurface.PARENT,
        priority=1,
        selection_reason=None,
        selection_metadata=None,
        available_from=None,
        expires_at=None,
        started_at=completed_at,
        completed_at=completed_at,
        skipped_at=None,
        completion_notes="一起完成",
        created_at=completed_at,
        updated_at=None,
    )


class MissionAssignmentRotationTests(unittest.TestCase):
    def test_current_hkt_date_uses_hong_kong_day_boundary(self):
        self.assertEqual(
            _current_hkt_date(datetime(2026, 5, 29, 16, 30, tzinfo=timezone.utc)),
            date(2026, 5, 30),
        )

    def test_rank_candidate_missions_prefers_unseen_then_oldest_assignment(self):
        assignment_date = date(2026, 5, 29)
        missions = [
            make_mission(
                "recently-assigned",
                sort_order=0,
                created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
            make_mission(
                "never-seen",
                sort_order=1,
                created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
            ),
            make_mission(
                "older-assigned",
                sort_order=2,
                created_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
            ),
        ]
        assignment_history = {
            "recently-assigned": (assignment_date - timedelta(days=1), None),
            "older-assigned": (assignment_date - timedelta(days=7), None),
        }

        ranked = _rank_candidate_missions(
            missions,
            assignment_history=assignment_history,
            assignment_date=assignment_date,
        )

        self.assertEqual(
            [mission.id for mission in ranked],
            ["never-seen", "older-assigned", "recently-assigned"],
        )

    def test_rank_candidate_missions_defers_recently_completed_missions(self):
        assignment_date = date(2026, 5, 29)
        missions = [
            make_mission(
                "recently-completed",
                sort_order=0,
                created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
            make_mission(
                "eligible",
                sort_order=1,
                created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
            ),
        ]
        assignment_history = {
            "recently-completed": (
                assignment_date - timedelta(days=3),
                datetime(2026, 5, 27, tzinfo=timezone.utc),
            ),
            "eligible": (assignment_date - timedelta(days=4), None),
        }

        ranked = _rank_candidate_missions(
            missions,
            assignment_history=assignment_history,
            assignment_date=assignment_date,
        )

        self.assertEqual(
            [mission.id for mission in ranked],
            ["eligible", "recently-completed"],
        )

    def test_recent_completion_uses_hkt_local_date_for_cooldown(self):
        self.assertTrue(
            _was_completed_recently(
                datetime(2026, 5, 29, 18, 0, tzinfo=timezone.utc),
                assignment_date=date(2026, 6, 5),
            )
        )

    def test_build_mission_summary_payload_tracks_streak_points_and_history(self):
        local_today = date(2026, 5, 30)
        daily_mission = make_mission(
            "daily-1",
            sort_order=0,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        offline_mission = make_mission(
            "offline-1",
            sort_order=1,
            created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )
        offline_mission.is_offline = True
        offline_mission.context = MissionContext.OUTDOOR

        completed_rows = [
            (
                make_assignment(
                    offline_mission.id,
                    assignment_date=local_today,
                    completed_at=datetime(2026, 5, 30, 4, 0, tzinfo=timezone.utc),
                ),
                offline_mission,
            ),
            (
                make_assignment(
                    daily_mission.id,
                    assignment_date=local_today - timedelta(days=1),
                    completed_at=datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc),
                ),
                daily_mission,
            ),
            (
                make_assignment(
                    "daily-older",
                    assignment_date=local_today - timedelta(days=2),
                    completed_at=datetime(2026, 5, 28, 8, 0, tzinfo=timezone.utc),
                ),
                make_mission(
                    "daily-older",
                    sort_order=2,
                    created_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
                ),
            ),
        ]

        summary = _build_mission_summary_payload(
            child_id="child-1",
            local_today=local_today,
            completed_rows=completed_rows,
        )

        self.assertEqual(summary["completed_today"], 1)
        self.assertEqual(summary["completed_this_week"], 3)
        self.assertEqual(summary["streak_days"], 3)
        self.assertEqual(summary["total_completed"], 3)
        self.assertEqual(summary["family_points"], 35)
        self.assertEqual(summary["level_title"], "陪跑新手")
        self.assertEqual(summary["points_to_next_level"], 15)
        self.assertEqual(len(summary["recent_completions"]), 3)
        self.assertEqual(summary["recent_completions"][0]["title"], offline_mission.title)
        self.assertEqual(summary["recent_completions"][0]["points_earned"], 15)

    def test_serialize_assigned_mission_keeps_current_assignment_status(self):
        mission = make_mission(
            "mission-1",
            sort_order=0,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        assignment = SimpleNamespace(
            id="assignment-1",
            child_id="child-1",
            mission_id="mission-1",
            assignment_date=date(2026, 5, 29),
            source=MissionAssignmentSource.SYSTEM,
            status=MissionAssignmentStatus.ASSIGNED,
            surface="both",
            priority=1,
            selection_reason="Rotated from published daily mission catalog",
            selection_metadata={},
            available_from=None,
            expires_at=None,
            started_at=None,
            completed_at=None,
            skipped_at=None,
            completion_notes=None,
            created_at=datetime(2026, 5, 29, tzinfo=timezone.utc),
            updated_at=None,
        )
        progress = SimpleNamespace(
            completed=True,
            completed_date=datetime(2026, 5, 20, tzinfo=timezone.utc),
            parent_notes="old note",
        )

        payload = _serialize_assigned_mission(
            mission,
            child_id="child-1",
            assignment_date=date(2026, 5, 29),
            assignment=assignment,
            progress=progress,
        )

        self.assertEqual(payload["assignment"]["status"], MissionAssignmentStatus.ASSIGNED)
        self.assertIsNone(payload["assignment"]["completed_at"])
        self.assertIsNone(payload["assignment"]["completion_notes"])


if __name__ == "__main__":
    unittest.main()