import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.v2_data import get_v2_user_detail_payload


class DashboardUserDetailPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_detail_payload_exposes_registration_activation_and_full_payment_history(self) -> None:
        user = SimpleNamespace(
            id=51,
            telegram_id=5051,
            username="demo",
            preferred_protocol="vless",
            is_blocked=False,
            trial_used=False,
            created_at=datetime(2026, 3, 1, 10, 0, 0),
            subscription_started_at=datetime(2026, 3, 5, 12, 30, 0),
            balance_rub=0,
            balance_reserved_rub=0,
        )
        payments = [
            SimpleNamespace(
                id=index,
                user_id=51,
                tariff_code="1m",
                payment_method="sbp_manual",
                payment_status="confirmed",
                amount=149,
                currency="RUB",
                duration_days=30,
                external_payment_id=None,
                reference=None,
                note=None,
                metadata_json=None,
                reviewed_by_actor_name=None,
                reviewed_at=None,
                rejection_reason=None,
                expires_at=None,
                confirmed_at=datetime(2026, 3, 5, 12, 30, 0),
                created_at=datetime(2026, 3, 5, 12, 30, 0),
            )
            for index in range(1, 13)
        ]
        detail = {
            "user": user,
            "status": "paid_active",
            "access_expires_at": "2026-04-05 12:30",
            "subscription_link_url": "https://client.amonora.ru/abcdefghijklmnop",
            "subscription_link_token": "abcdefghijklmnop",
            "subscription_link_last_viewed_at": "2026-04-05 18:29 Екб",
            "subscription_link_last_feed_accessed_at": "2026-04-05 18:30 Екб",
            "vpn_repair_state": {"repair_needed": False},
            "vpn_repair_events": [],
            "devices": [],
            "payments": payments,
            "payment_counts": {"total": 12, "confirmed": 12, "reviewable": 0},
            "support_ticket": None,
            "support_history": [],
        }

        with (
            patch("dashboard.v2_data.get_user_detail", new=AsyncMock(return_value=detail)),
            patch("dashboard.v2_data.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_active_device_slot_entitlements_for_user", new=AsyncMock(return_value=[])),
            patch("dashboard.v2_data.get_channel_subscription_statuses", new=AsyncMock(return_value={5051: {"status": "ok", "label": "OK", "checked_at": None}})),
            patch("dashboard.v2_data.get_payment_records", new=AsyncMock(return_value=payments)),
            patch("dashboard.v2_data.get_user_balance_history", new=AsyncMock(return_value=[])),
            patch("dashboard.v2_data.dashboard_user_status", return_value={"code": "active", "label": "Активен"}),
            patch("dashboard.v2_data._repair_action_guard", return_value=(False, "no-devices")),
            patch("dashboard.v2_data._latest_confirmed_tariff_by_user", return_value={}),
            patch("dashboard.v2_data._plan_label_for_user", return_value="1 месяц"),
            patch("dashboard.v2_data._plan_code_for_user", return_value="1m"),
            patch("dashboard.v2_data._plan_bucket_for_label", return_value="paid"),
        ):
            payload = await get_v2_user_detail_payload(51)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["user"]["created_at"], "2026-03-01 15:00 Екб")
        self.assertEqual(payload["user"]["subscription_started_at"], "2026-03-05 17:30 Екб")
        self.assertEqual(payload["user"]["payments_count"], 12)
        self.assertEqual(payload["user"]["subscription_link_url"], "https://client.amonora.ru/abcdefghijklmnop")
        self.assertEqual(payload["user"]["subscription_link_last_feed_accessed_at"], "2026-04-05 18:30 Екб")
        self.assertEqual(len(payload["payments"]), 12)


if __name__ == "__main__":
    unittest.main()
