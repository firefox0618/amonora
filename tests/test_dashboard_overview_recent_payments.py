import unittest

from datetime import datetime

from dashboard.v2_data import _sort_payments_latest_first


class DashboardOverviewRecentPaymentsTests(unittest.TestCase):
    def test_sort_payments_latest_first_orders_newest_records_first(self) -> None:
        payment_older = type(
            "PaymentRecord",
            (),
            {
                "id": 10,
                "user_id": 1,
                "payment_status": "confirmed",
                "payment_method": "sbp_manual",
                "amount": 199,
                "currency": "RUB",
                "duration_days": 30,
                "reference": None,
                "note": None,
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": datetime(2026, 3, 24, 11, 0, 0),
                "created_at": datetime(2026, 3, 24, 11, 0, 0),
                "metadata_json": None,
                "external_payment_id": None,
            },
        )()
        payment_latest = type(
            "PaymentRecord",
            (),
            {
                "id": 12,
                "user_id": 1,
                "payment_status": "confirmed",
                "payment_method": "sbp_manual",
                "amount": 299,
                "currency": "RUB",
                "duration_days": 30,
                "reference": None,
                "note": None,
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": datetime(2026, 3, 25, 13, 0, 0),
                "created_at": datetime(2026, 3, 25, 13, 0, 0),
                "metadata_json": None,
                "external_payment_id": None,
            },
        )()
        payment_middle = type(
            "PaymentRecord",
            (),
            {
                "id": 11,
                "user_id": 1,
                "payment_status": "pending",
                "payment_method": "sbp_manual",
                "amount": 249,
                "currency": "RUB",
                "duration_days": 30,
                "reference": None,
                "note": None,
                "reviewed_by_actor_name": None,
                "reviewed_at": None,
                "rejection_reason": None,
                "expires_at": None,
                "confirmed_at": None,
                "created_at": datetime(2026, 3, 24, 18, 0, 0),
                "metadata_json": None,
                "external_payment_id": None,
            },
        )()
        self.assertEqual(
            [item.id for item in _sort_payments_latest_first([payment_older, payment_latest, payment_middle])],
            [12, 11, 10],
        )


if __name__ == "__main__":
    unittest.main()
