import unittest

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ops import access_reminders
from ops.access_reminders import _trigger_match_for_user


class AccessReminderTriggerTests(unittest.TestCase):
    def test_trial_active_2h_trigger_matches_only_active_segment(self) -> None:
        now = datetime(2026, 4, 3, 14, 5, 0)
        rule = SimpleNamespace(
            key="trial_active_2h",
            config_json='{"kind":"trial_hours_since_start","hours":2,"segment":"active"}',
        )
        user = SimpleNamespace(
            id=91,
            telegram_id=123450,
            username="trial_user",
            is_blocked=False,
            trial_used=True,
            trial_started_at=now - timedelta(hours=2, minutes=5),
            trial_expires_at=now + timedelta(days=2),
            trial_channel_unsubscribed_at=None,
            trial_activity_level="active",
            subscription_status="inactive",
            subscription_source=None,
            subscription_expires_at=None,
            created_at=now - timedelta(days=1),
            last_activity_at=now - timedelta(minutes=1),
            vpn_repair_needed=False,
            vpn_repair_marked_at=None,
        )

        matched, dedupe_key = _trigger_match_for_user(rule, user, device_count=1, now_utc=now)

        self.assertTrue(matched)
        self.assertEqual(dedupe_key, f"trigger:trial_active_2h:91:{user.trial_started_at.isoformat()}")

    def test_trial_low_2h_trigger_skips_paused_trial(self) -> None:
        now = datetime(2026, 4, 3, 14, 5, 0)
        rule = SimpleNamespace(
            key="trial_low_2h",
            config_json='{"kind":"trial_hours_since_start","hours":2,"segment":"low"}',
        )
        user = SimpleNamespace(
            id=92,
            telegram_id=123451,
            username="paused_trial",
            is_blocked=False,
            trial_used=True,
            trial_started_at=now - timedelta(hours=5),
            trial_expires_at=now + timedelta(days=2),
            trial_channel_unsubscribed_at=now - timedelta(hours=1),
            trial_activity_level="low",
            subscription_status="inactive",
            subscription_source=None,
            subscription_expires_at=None,
            created_at=now - timedelta(days=1),
            last_activity_at=now - timedelta(hours=1),
            vpn_repair_needed=False,
            vpn_repair_marked_at=None,
        )

        matched, dedupe_key = _trigger_match_for_user(rule, user, device_count=0, now_utc=now)

        self.assertFalse(matched)
        self.assertIsNone(dedupe_key)

    def test_trial_final_trigger_matches_last_six_hours(self) -> None:
        now = datetime(2026, 4, 3, 18, 0, 0)
        rule = SimpleNamespace(
            key="trial_final_6h",
            config_json='{"kind":"trial_hours_before_expiry","hours":6}',
        )
        user = SimpleNamespace(
            id=93,
            telegram_id=123452,
            username="final_trial",
            is_blocked=False,
            trial_used=True,
            trial_started_at=now - timedelta(days=2),
            trial_expires_at=now + timedelta(hours=5, minutes=30),
            trial_channel_unsubscribed_at=None,
            trial_activity_level="low",
            subscription_status="inactive",
            subscription_source=None,
            subscription_expires_at=None,
            created_at=now - timedelta(days=2),
            last_activity_at=now - timedelta(minutes=5),
            vpn_repair_needed=False,
            vpn_repair_marked_at=None,
        )

        matched, dedupe_key = _trigger_match_for_user(rule, user, device_count=0, now_utc=now)

        self.assertTrue(matched)
        self.assertEqual(dedupe_key, f"trigger:trial_final_6h:93:{user.trial_expires_at.isoformat()}")

    def test_subscription_expiry_trigger_matches_three_days_before(self) -> None:
        now = datetime(2026, 3, 22, 7, 30, 0)
        rule = SimpleNamespace(
            key="subscription_expires_3d",
            config_json='{"kind":"days_before_access_expiry","days":3,"send_hour":12}',
        )
        user = SimpleNamespace(
            id=77,
            telegram_id=123456,
            username="user77",
            is_blocked=False,
            trial_used=True,
            trial_expires_at=None,
            subscription_status="active",
            subscription_source="telegram_stars",
            subscription_expires_at=datetime(2026, 3, 25, 18, 0, 0),
            created_at=datetime(2026, 3, 1, 8, 0, 0),
            last_activity_at=datetime(2026, 3, 21, 18, 0, 0),
            vpn_repair_needed=False,
            vpn_repair_marked_at=None,
        )

        matched, dedupe_key = _trigger_match_for_user(rule, user, device_count=1, now_utc=now)

        self.assertTrue(matched)
        self.assertEqual(dedupe_key, "trigger:subscription_expires_3d:77:2026-03-25")

    def test_start_no_action_trigger_requires_user_to_stay_idle(self) -> None:
        now = datetime(2026, 3, 22, 9, 10, 0)
        rule = SimpleNamespace(
            key="start_no_action_1h",
            config_json='{"kind":"start_no_action_hours","hours":1}',
        )
        user = SimpleNamespace(
            id=88,
            telegram_id=987654,
            username="new_user",
            is_blocked=False,
            trial_used=False,
            trial_expires_at=None,
            subscription_status="inactive",
            subscription_source=None,
            subscription_expires_at=None,
            created_at=now - timedelta(hours=2),
            last_activity_at=now - timedelta(minutes=20),
            vpn_repair_needed=False,
            vpn_repair_marked_at=None,
        )

        matched, dedupe_key = _trigger_match_for_user(rule, user, device_count=0, now_utc=now)

        self.assertFalse(matched)
        self.assertIsNone(dedupe_key)


class AccessReminderTriggerDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_backoff_suppresses_recent_forbidden_results(self) -> None:
        now = datetime(2026, 4, 3, 18, 0, 0)
        event_state = {
            "last_result": "forbidden",
            "last_attempt_at": (now - timedelta(hours=2)).isoformat(),
        }

        self.assertTrue(access_reminders._notification_backoff_active(event_state, now))
        self.assertFalse(access_reminders._notification_backoff_active(event_state, now + timedelta(days=2)))

    async def test_failed_trigger_delivery_only_logs_info(self) -> None:
        rule = SimpleNamespace(
            id=5,
            key="start_no_action_3h",
            title="🚀 Старт без действий — через 3 часа",
            template_body="test body",
            buttons_json=None,
        )
        user = SimpleNamespace(
            id=263,
            telegram_id=6026887227,
        )

        with (
            patch.object(access_reminders, "create_broadcast_campaign", AsyncMock(return_value=SimpleNamespace(id=77))),
            patch.object(access_reminders, "dispatch_campaign", AsyncMock(return_value={"sent": 0, "failed": 1})),
            patch.object(access_reminders, "register_trigger_delivery_log", AsyncMock()) as register_log,
            patch.object(access_reminders.logger, "info") as info_log,
        ):
            result = await access_reminders._dispatch_trigger_campaign(
                rule,
                user,
                dedupe_key="trigger:start_no_action_3h:263:2026-04-02",
            )

        self.assertEqual(result, "failed")
        register_log.assert_awaited_once()
        info_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
