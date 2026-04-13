import unittest

from datetime import datetime
from unittest.mock import patch

from dashboard.v2_data import _build_repair_attention_payload


class DashboardOverviewAttentionTests(unittest.TestCase):
    def test_build_repair_attention_payload_surfaces_repair_needed_users(self) -> None:
        users = [
            type(
                "User",
                (),
                {
                    "id": 10,
                    "telegram_id": 10010,
                    "username": "alice",
                    "is_blocked": False,
                    "trial_used": False,
                    "trial_expires_at": None,
                    "subscription_status": "active",
                    "subscription_expires_at": datetime(2026, 3, 25, 12, 15, 0),
                    "subscription_source": "telegram_stars",
                    "vpn_repair_needed": True,
                    "vpn_repair_reason": "manual_repair_failed",
                    "vpn_repair_marked_at": datetime(2026, 3, 20, 12, 15, 0),
                },
            )(),
            type(
                "User",
                (),
                {
                    "id": 11,
                    "telegram_id": 10011,
                    "username": "bob",
                    "is_blocked": False,
                    "trial_used": False,
                    "trial_expires_at": None,
                    "subscription_status": "inactive",
                    "subscription_expires_at": None,
                    "subscription_source": "",
                    "vpn_repair_needed": False,
                    "vpn_repair_reason": None,
                    "vpn_repair_marked_at": None,
                },
            )(),
        ]
        events = [
            type(
                "VpnRepairEvent",
                (),
                {
                    "user_id": 10,
                    "result": "failed",
                    "reason": "manual_repair_failed",
                    "created_at": datetime(2026, 3, 20, 12, 16, 0),
                },
            )(),
        ]

        with patch("dashboard.v2_data.utcnow", return_value=datetime(2026, 3, 20, 16, 0, 0)):
            payload = _build_repair_attention_payload(users, events, {10: 1})

        self.assertEqual(payload["summary"]["repair_needed"], 1)
        self.assertEqual(payload["summary"]["escalated_repairs"], 0)
        self.assertEqual(len(payload["repair_needed_users"]), 1)
        self.assertEqual(payload["repair_needed_users"][0]["user_id"], 10)
        self.assertEqual(payload["repair_needed_users"][0]["reason"], "manual_repair_sync_failed")
        self.assertEqual(payload["repair_needed_users"][0]["reason_label"], "Manual repair sync failed")
        self.assertEqual(payload["repair_needed_users"][0]["priority"], "medium")
        self.assertEqual(payload["repair_needed_users"][0]["marked_age_hours"], 3)
        self.assertEqual(payload["repair_needed_users"][0]["access_status"], "paid_active")
        self.assertEqual(payload["repair_needed_users"][0]["devices_count"], 1)
        self.assertTrue(payload["repair_needed_users"][0]["can_repair"])
        self.assertIsNone(payload["repair_needed_users"][0]["repair_block_reason"])
        self.assertFalse(payload["repair_needed_users"][0]["is_escalated"])
        self.assertFalse(payload["repair_needed_users"][0]["has_repeated_failures"])
        self.assertFalse(payload["repair_needed_users"][0]["is_payment_related"])

    def test_build_repair_attention_payload_marks_repeated_failed_repairs(self) -> None:
        users = [
            type(
                "User",
                (),
                {
                    "id": 22,
                    "telegram_id": 10022,
                    "username": "carol",
                    "is_blocked": False,
                    "trial_used": False,
                    "trial_expires_at": None,
                    "subscription_status": "active",
                    "subscription_expires_at": datetime(2026, 3, 25, 14, 0, 0),
                    "subscription_source": "telegram_stars",
                    "vpn_repair_needed": True,
                    "vpn_repair_reason": "manual_repair_failed",
                    "vpn_repair_marked_at": datetime(2026, 3, 20, 14, 0, 0),
                },
            )(),
        ]
        events = [
            type(
                "VpnRepairEvent",
                (),
                {
                    "user_id": 22,
                    "result": "failed",
                    "reason": "manual_repair_failed",
                    "created_at": datetime(2026, 3, 20, 14, 5, 0),
                },
            )(),
            type(
                "VpnRepairEvent",
                (),
                {
                    "user_id": 22,
                    "result": "failed",
                    "reason": "manual_repair_failed_no_devices",
                    "created_at": datetime(2026, 3, 20, 14, 2, 0),
                },
            )(),
        ]

        with patch("dashboard.v2_data.utcnow", return_value=datetime(2026, 3, 20, 20, 30, 0)):
            payload = _build_repair_attention_payload(users, events, {22: 2})

        self.assertEqual(payload["summary"]["repair_needed"], 1)
        self.assertEqual(payload["summary"]["escalated_repairs"], 1)
        self.assertEqual(payload["summary"]["repeated_failed_repairs"], 1)
        self.assertEqual(payload["repair_needed_users"][0]["reason"], "manual_repair_sync_failed")
        self.assertEqual(payload["repair_needed_users"][0]["reason_label"], "Manual repair sync failed")
        self.assertEqual(payload["repair_needed_users"][0]["priority"], "high")
        self.assertTrue(payload["repair_needed_users"][0]["is_escalated"])
        self.assertEqual(payload["repair_needed_users"][0]["marked_age_hours"], 6)
        self.assertTrue(payload["repair_needed_users"][0]["has_repeated_failures"])
        self.assertEqual(payload["repair_needed_users"][0]["failed_repair_attempts"], 2)
        self.assertTrue(payload["repair_needed_users"][0]["can_repair"])

    def test_build_repair_attention_payload_tracks_payment_related_repairs(self) -> None:
        users = [
            type(
                "User",
                (),
                {
                    "id": 33,
                    "telegram_id": 10033,
                    "username": "dave",
                    "is_blocked": False,
                    "trial_used": False,
                    "trial_expires_at": None,
                    "subscription_status": "active",
                    "subscription_expires_at": datetime(2026, 3, 25, 15, 0, 0),
                    "subscription_source": "telegram_stars",
                    "vpn_repair_needed": True,
                    "vpn_repair_reason": "post_payment_sync_failed",
                    "vpn_repair_marked_at": datetime(2026, 3, 20, 15, 0, 0),
                },
            )(),
        ]
        events = []

        with patch("dashboard.v2_data.utcnow", return_value=datetime(2026, 3, 20, 18, 0, 0)):
            payload = _build_repair_attention_payload(users, events, {33: 1})

        self.assertEqual(payload["summary"]["payment_related_repairs"], 1)
        self.assertEqual(payload["summary"]["high_priority_repairs"], 1)
        self.assertEqual(len(payload["payment_related_users"]), 1)
        self.assertEqual(payload["payment_related_users"][0]["reason_label"], "Post-payment VPN sync failed")
        self.assertEqual(payload["repair_needed_users"][0]["priority"], "high")
        self.assertFalse(payload["repair_needed_users"][0]["is_escalated"])
        self.assertTrue(payload["repair_needed_users"][0]["is_payment_related"])
        self.assertTrue(payload["repair_needed_users"][0]["can_repair"])

    def test_build_repair_attention_payload_blocks_repair_without_devices(self) -> None:
        users = [
            type(
                "User",
                (),
                {
                    "id": 44,
                    "telegram_id": 10044,
                    "username": "erin",
                    "is_blocked": False,
                    "trial_used": False,
                    "trial_expires_at": None,
                    "subscription_status": "active",
                    "subscription_expires_at": datetime(2026, 3, 25, 15, 0, 0),
                    "subscription_source": "telegram_stars",
                    "vpn_repair_needed": True,
                    "vpn_repair_reason": "manual_repair_failed",
                    "vpn_repair_marked_at": datetime(2026, 3, 20, 15, 0, 0),
                },
            )(),
        ]

        with patch("dashboard.v2_data.utcnow", return_value=datetime(2026, 3, 20, 18, 0, 0)):
            payload = _build_repair_attention_payload(users, [], {44: 0})

        self.assertFalse(payload["repair_needed_users"][0]["can_repair"])
        self.assertEqual(payload["repair_needed_users"][0]["repair_block_reason"], "manual_repair_no_devices")


if __name__ == "__main__":
    unittest.main()
