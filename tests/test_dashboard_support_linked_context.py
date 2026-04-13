import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard import v2_data


class DashboardSupportLinkedContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_selected_support_user_context_uses_internal_user_id_for_user_href(self) -> None:
        user = SimpleNamespace(id=42, username="alice", telegram_id=5001, trial_used=False)
        ticket_detail = {
            "user": user,
            "payments": [{"id": 77}],
        }
        user_detail = {
            "user": user,
            "status": "paid_active",
            "access_expires_at": "2026-04-20 12:00",
            "devices": [{"id": 1}, {"id": 2}],
            "vpn_repair_state": {
                "repair_needed": True,
                "reason": "post_payment_sync_failed",
                "reason_label": "Post-payment VPN sync failed",
            },
            "support_ticket": {"status_label": "В работе"},
            "vpn_repair_events": [],
        }

        with (
            patch("dashboard.v2_data.get_user_detail", new=AsyncMock(return_value=user_detail)),
            patch("dashboard.v2_data._plan_label_for_user", return_value="Платный доступ"),
        ):
            payload = await v2_data._build_selected_support_user_context(ticket_detail)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_href"], "/users?user_id=42")
        self.assertEqual(payload["latest_payment_href"], "/payments?record_id=77")
        self.assertFalse(payload["can_grant_trial"])
        self.assertTrue(payload["repair_action"]["can_repair"])

    async def test_build_selected_support_user_context_returns_none_without_linked_user(self) -> None:
        payload = await v2_data._build_selected_support_user_context({"user": None, "payments": []})
        self.assertIsNone(payload)


if __name__ == "__main__":
    unittest.main()
