import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from dashboard.finance import payment_method_counts_as_revenue
from dashboard.models import FinanceEntry, PaymentRecord
from dashboard.services import (
    _build_traffic_baseline_payload,
    _finance_summary_from_entries,
    _traffic_baseline_is_current,
    apply_traffic_baseline_to_snapshots,
    dashboard_day_start,
    dashboard_local_date,
    get_runtime_tariffs_list,
)
from dashboard.v2_data import _ordered_plan_rows, _payment_revenue_moment


class DashboardBusinessRulesTests(unittest.TestCase):
    def test_only_platega_sbp_and_crypto_count_as_revenue(self) -> None:
        self.assertTrue(payment_method_counts_as_revenue("sbp_platega"))
        self.assertTrue(payment_method_counts_as_revenue("crypto_platega"))
        self.assertFalse(payment_method_counts_as_revenue("sbp_manual"))
        self.assertFalse(payment_method_counts_as_revenue("crypto_manual"))
        self.assertFalse(payment_method_counts_as_revenue("crypto_bot"))

    def test_finance_summary_excludes_non_revenue_payment_income(self) -> None:
        entries = [
            FinanceEntry(
                id=1,
                entry_type="income",
                status="posted",
                amount=1000,
                currency="RUB",
                category="subscription_payment",
                source_type="payment_record",
                source_id="11",
                occurred_at=datetime(2026, 3, 24, 10, 0, 0),
                created_at=datetime(2026, 3, 24, 10, 0, 0),
            ),
            FinanceEntry(
                id=2,
                entry_type="income",
                status="posted",
                amount=700,
                currency="RUB",
                category="subscription_payment",
                source_type="payment_record",
                source_id="12",
                occurred_at=datetime(2026, 3, 24, 10, 5, 0),
                created_at=datetime(2026, 3, 24, 10, 5, 0),
            ),
            FinanceEntry(
                id=3,
                entry_type="income",
                status="posted",
                amount=300,
                currency="RUB",
                category="operations_income",
                source_type=None,
                source_id=None,
                occurred_at=datetime(2026, 3, 24, 10, 10, 0),
                created_at=datetime(2026, 3, 24, 10, 10, 0),
            ),
            FinanceEntry(
                id=4,
                entry_type="expense",
                status="posted",
                amount=250,
                currency="RUB",
                category="operations",
                source_type=None,
                source_id=None,
                occurred_at=datetime(2026, 3, 24, 10, 15, 0),
                created_at=datetime(2026, 3, 24, 10, 15, 0),
            ),
        ]
        payment_records = {
            "11": PaymentRecord(id=11, payment_method="sbp_platega", payment_status="confirmed", amount=1000),
            "12": PaymentRecord(id=12, payment_method="sbp_manual", payment_status="confirmed", amount=700),
        }

        summary = _finance_summary_from_entries(entries, payment_records)

        self.assertEqual(summary["income"], 1300)
        self.assertEqual(summary["expense"], 250)
        self.assertEqual(summary["net"], 1050)

    def test_ordered_plan_rows_keep_tariffs_in_expected_sequence(self) -> None:
        rows = _ordered_plan_rows(
            {
                "12 месяцев": 2,
                "Пробный период": 1,
                "3 месяца": 4,
                "1 месяц": 8,
                "6 месяцев": 3,
            }
        )

        self.assertEqual(
            [item["label"] for item in rows],
            ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев", "Пробный период"],
        )

    def test_traffic_baseline_detects_current_month(self) -> None:
        self.assertTrue(
            _traffic_baseline_is_current({"reset_at": datetime.now(UTC).isoformat(), "servers": {}})
        )
        self.assertFalse(
            _traffic_baseline_is_current({"reset_at": "2026-02-01T00:00:00", "servers": {}})
        )

    def test_traffic_baseline_uses_raw_snapshot_network_counters(self) -> None:
        baseline = _build_traffic_baseline_payload(
            [
                {
                    "id": 7,
                    "name": "Germany Main",
                    "network_sent_gb": 50.25,
                    "network_recv_gb": 74.75,
                }
            ],
            reset_at=datetime(2026, 4, 1, 10, 0, 0),
        )

        with patch("dashboard.services._runtime_cache_peek", return_value=baseline):
            adjusted, applied = apply_traffic_baseline_to_snapshots(
                [
                    {
                        "id": 7,
                        "name": "Germany Main",
                        "total_transfer_gb": 125.0,
                    }
                ]
            )

        self.assertEqual(applied["servers"]["7"], 125.0)
        self.assertEqual(adjusted[0]["total_transfer_gb"], 0.0)

    def test_runtime_tariffs_list_uses_base_durations_after_promo_removal(self) -> None:
        rows = {item["code"]: item for item in get_runtime_tariffs_list()}

        self.assertEqual(rows["1m"]["duration_days"], 30)
        self.assertEqual(rows["3m"]["duration_days"], 90)
        self.assertEqual(rows["6m"]["duration_days"], 180)
        self.assertEqual(rows["12m"]["duration_days"], 365)

    def test_dashboard_day_start_uses_ekb_midnight(self) -> None:
        now = datetime(2026, 4, 1, 1, 30, 0)

        self.assertEqual(dashboard_day_start(now), datetime(2026, 3, 31, 19, 0, 0))

    def test_dashboard_local_date_uses_ekb_timezone(self) -> None:
        self.assertEqual(
            dashboard_local_date(datetime(2026, 3, 31, 21, 30, 0)),
            datetime(2026, 4, 1, 0, 0, 0).date(),
        )

    def test_payment_revenue_moment_prefers_confirmation_time(self) -> None:
        record = PaymentRecord(
            id=11,
            payment_method="sbp_platega",
            payment_status="confirmed",
            amount=1495,
            created_at=datetime(2026, 3, 31, 20, 10, 0),
            confirmed_at=datetime(2026, 3, 31, 18, 40, 0),
        )

        self.assertEqual(_payment_revenue_moment(record), datetime(2026, 3, 31, 18, 40, 0))


if __name__ == "__main__":
    unittest.main()
