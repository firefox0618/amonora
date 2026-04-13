import unittest
from datetime import datetime
from unittest.mock import patch

from dashboard.v2_data import _build_support_attention


class DashboardSupportActionabilityTests(unittest.TestCase):
    def test_build_support_attention_returns_oldest_open_tickets(self) -> None:
        tickets = [
            {
                "user_id": 10,
                "username": "alice",
                "status": "in_progress",
                "created_at": "2026-03-20T12:00:00+00:00",
                "updated_at": "2026-03-20T13:00:00+00:00",
                "last_user_message_preview": "Need help with access",
            },
            {
                "user_id": 11,
                "username": "bob",
                "status": "new",
                "created_at": "2026-03-19T10:00:00+00:00",
                "updated_at": "2026-03-20T11:00:00+00:00",
                "last_user_message_preview": "Payment not confirmed",
            },
            {
                "user_id": 12,
                "username": "carol",
                "status": "closed",
                "created_at": "2026-03-18T09:00:00+00:00",
                "updated_at": "2026-03-18T10:00:00+00:00",
                "last_user_message_preview": "Resolved",
            },
        ]

        with patch("dashboard.v2_data.utcnow", return_value=datetime(2026, 3, 20, 18, 0, 0)):
            payload = _build_support_attention(tickets)

        self.assertEqual([item["user_id"] for item in payload], [11, 10])
        self.assertEqual(payload[0]["priority"], "high")
        self.assertTrue(payload[0]["is_escalated"])
        self.assertEqual(payload[0]["age_hours"], 32.0)
        self.assertEqual(payload[0]["href"], "/support?ticket_id=11")
        self.assertEqual(payload[0]["preview"], "Payment not confirmed")


if __name__ == "__main__":
    unittest.main()
