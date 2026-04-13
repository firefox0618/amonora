import unittest

from datetime import datetime

from dashboard.services import _serialize_payment_record
from dashboard.v2_data import _serialize_payment_record as _serialize_payment_record_v2
from dashboard.v2_data import _available_payment_status_actions, _build_pending_manual_payment_attention


class DashboardPaymentActionabilityTests(unittest.TestCase):
    def test_build_pending_manual_payment_attention_marks_oldest_and_stale_items(self) -> None:
        users_lookup = {
            10: type("User", (), {"id": 10, "username": "alice", "telegram_id": 10010})(),
            11: type("User", (), {"id": 11, "username": "bob", "telegram_id": 10011})(),
        }
        payments = [
            type(
                "PaymentRecord",
                (),
                {
                    "id": 501,
                    "user_id": 10,
                    "payment_status": "awaiting_admin_review",
                    "created_at": datetime(2026, 3, 20, 8, 0, 0),
                },
            )(),
            type(
                "PaymentRecord",
                (),
                {
                    "id": 502,
                    "user_id": 11,
                    "payment_status": "awaiting_admin_review",
                    "created_at": datetime(2026, 3, 20, 18, 0, 0),
                },
            )(),
        ]

        payload = _build_pending_manual_payment_attention(payments, users_lookup, datetime(2026, 3, 21, 0, 30, 0))

        self.assertEqual([item["record_id"] for item in payload], [501, 502])
        self.assertTrue(payload[0]["is_stale"])
        self.assertTrue(payload[0]["is_escalated"])
        self.assertFalse(payload[1]["is_stale"])
        self.assertFalse(payload[1]["is_escalated"])
        self.assertEqual(payload[0]["priority"], "high")
        self.assertEqual(payload[1]["priority"], "medium")
        self.assertEqual(payload[0]["username"], "alice")
        self.assertEqual(payload[0]["href"], "/payments?record_id=501")

    def test_available_status_actions_hides_review_actions_for_auto_provider_payment(self) -> None:
        record = type(
            "PaymentRecord",
            (),
            {
                "payment_status": "pending",
                "payment_method": "sbp_platega",
            },
        )()

        self.assertEqual(_available_payment_status_actions(record), [])

    def test_serialize_payment_record_exposes_manual_reminder_flag_for_open_sbp(self) -> None:
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 55,
                "user_id": 10,
                "tariff_code": "3m",
                "payment_method": "sbp_manual",
                "payment_status": "awaiting_admin_review",
                "amount": 1390,
                "list_price_amount": 1390,
                "balance_reserved_amount": 0,
                "balance_applied_amount": 0,
                "currency": "RUB",
                "duration_days": 90,
                "reference": None,
                "note": None,
                "metadata_json": "{}",
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": None,
                "created_at": datetime(2026, 4, 2, 12, 0, 0),
            },
        )()

        payload = _serialize_payment_record(record, {})

        self.assertTrue(payload["can_send_reminder"])

    def test_v2_serialize_payment_record_exposes_manual_reminder_flag_for_open_sbp(self) -> None:
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 56,
                "user_id": 10,
                "tariff_code": "12m",
                "payment_method": "sbp_manual",
                "payment_status": "awaiting_admin_review",
                "amount": 1390,
                "currency": "RUB",
                "duration_days": 365,
                "reference": None,
                "note": None,
                "metadata_json": "{}",
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": None,
                "created_at": datetime(2026, 4, 2, 13, 0, 0),
                "external_payment_id": None,
            },
        )()

        payload = _serialize_payment_record_v2(record, {})

        self.assertTrue(payload["can_send_reminder"])

    def test_payment_serializers_prefer_product_title_for_addon_label(self) -> None:
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 57,
                "user_id": 10,
                "tariff_code": "device_slot_addon",
                "payment_method": "sbp_manual",
                "payment_status": "awaiting_user_payment",
                "amount": 49,
                "list_price_amount": 49,
                "balance_reserved_amount": 0,
                "balance_applied_amount": 0,
                "currency": "RUB",
                "duration_days": 30,
                "reference": None,
                "note": None,
                "metadata_json": '{"product_title":"+1 устройство до конца подписки"}',
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": None,
                "created_at": datetime(2026, 4, 2, 14, 0, 0),
                "external_payment_id": None,
            },
        )()

        payload = _serialize_payment_record(record, {})
        payload_v2 = _serialize_payment_record_v2(record, {})

        self.assertEqual(payload["tariff_label"], "+1 устройство до конца подписки")
        self.assertEqual(payload_v2["tariff_label"], "+1 устройство до конца подписки")
