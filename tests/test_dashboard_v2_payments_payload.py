import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from dashboard.v2_data import get_v2_payments_payload


class DashboardV2PaymentsPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_payments_payload_uses_revenue_confirmed_without_crashing(self) -> None:
        payment = type(
            "PaymentRecord",
            (),
            {
                "id": 17,
                "user_id": 7,
                "payment_status": "confirmed",
                "payment_method": "sbp_platega",
                "amount": 399,
                "created_at": datetime(2026, 3, 24, 12, 0, 0),
                "confirmed_at": datetime(2026, 3, 24, 12, 5, 0),
            },
        )()

        users_lookup_mock = AsyncMock(return_value={})

        with (
            patch("dashboard.v2_data._get_users_lookup", new=users_lookup_mock),
            patch("dashboard.v2_data.get_payment_records", new=AsyncMock(return_value=[payment])),
            patch("dashboard.v2_data._refresh_provider_payment_records", new=AsyncMock(return_value=[payment])),
            patch(
                "dashboard.v2_data._serialize_payment_record",
                return_value={"id": 17, "payment_status": "confirmed"},
            ),
            patch("dashboard.v2_data._build_selected_payment_user_context", new=AsyncMock(return_value={})),
            patch(
                "dashboard.v2_data.get_finance_dashboard",
                new=AsyncMock(
                    return_value={
                        "entries": [],
                        "selected_entry": None,
                        "recurring_rows": [],
                        "admins": [],
                        "filters": {"period_key": None},
                        "periods": [],
                        "summary": {},
                    }
                ),
            ),
            patch("dashboard.v2_data.get_finance_summary", new=AsyncMock(return_value={"income": 399})),
        ):
            payload = await get_v2_payments_payload()

        users_lookup_mock.assert_awaited_once_with([7])
        self.assertEqual(payload["summary"]["mrr"], 399)
        self.assertEqual(payload["summary"]["new_subscriptions"], 1)
        self.assertEqual(payload["summary"]["confirmed"], 1)


if __name__ == "__main__":
    unittest.main()
