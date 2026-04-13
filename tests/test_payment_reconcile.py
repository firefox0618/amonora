import unittest

from unittest.mock import AsyncMock, patch

from dashboard.models import PaymentRecord

import bot.payment_flow as payment_flow


def build_record(
    *,
    record_id: int = 1,
    user_id: int | None = 77,
    tariff_code: str = "1m",
    payment_method: str = "sbp_platega",
    metadata_json: str | None = None,
    amount: int = 149,
) -> PaymentRecord:
    return PaymentRecord(
        id=record_id,
        user_id=user_id,
        external_payment_id=f"ext-{record_id}",
        tariff_code=tariff_code,
        payment_method=payment_method,
        payment_status="confirmed",
        amount=amount,
        currency="RUB",
        duration_days=30,
        metadata_json=metadata_json,
    )


class PaymentReconcileTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_payment_record_product_routes_balance_topup_to_dedicated_finalizer(self) -> None:
        record = build_record(
            tariff_code="balance_topup",
            metadata_json='{"payload_type":"balance_topup","product_type":"balance_topup"}',
            amount=500,
        )

        with (
            patch.object(payment_flow, "get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch.object(
                payment_flow,
                "finalize_balance_topup_payment",
                new=AsyncMock(return_value={"product_type": "balance_topup"}),
            ) as topup_mock,
            patch.object(payment_flow, "finalize_subscription_payment", new=AsyncMock()) as sub_mock,
        ):
            result = await payment_flow.finalize_payment_record_product(
                user_id=77,
                payment_source="reconcile_sbp_platega",
                payment_record_id=record.id,
                tariff_code=record.tariff_code,
                payment_id=record.external_payment_id,
            )

        self.assertEqual(result, {"product_type": "balance_topup"})
        topup_mock.assert_awaited_once_with(user_id=77, payment_record_id=record.id)
        sub_mock.assert_not_called()

    async def test_reconcile_confirmed_payment_records_processes_only_fixable_rows(self) -> None:
        record_ok = build_record(record_id=11, user_id=44, tariff_code="1m")
        record_skip = build_record(record_id=12, user_id=None, tariff_code="1m")
        record_ok_after_effect = build_record(
            record_id=11,
            user_id=44,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-05T01:00:00","effect_kind":"subscription_activation","access_sync_state":"success"}',
        )
        record_ok_converged = build_record(
            record_id=11,
            user_id=44,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-05T01:00:00","effect_kind":"subscription_activation","access_sync_state":"success","finance_synced_at":"2026-04-05T01:01:00","reconcile_state":"converged","reconciled_at":"2026-04-05T01:01:00"}',
        )

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record_ok, record_skip]),
            ),
            patch.object(
                payment_flow,
                "refresh_payment_record_reconcile_state",
                new=AsyncMock(side_effect=[None, record_ok_after_effect, record_ok_converged]),
            ),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=object())) as finance_mock,
            patch.object(
                payment_flow,
                "finalize_payment_record_product",
                new=AsyncMock(return_value={"product_type": "subscription", "effect_applied_now": True}),
            ) as finalize_mock,
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 2,
                "reconciled": 1,
                "failed": 0,
                "skipped": 1,
                "finance_synced": 1,
                "finance_only": 0,
            },
        )
        finance_mock.assert_awaited_once_with(record_ok.id)
        finalize_mock.assert_awaited_once()

    async def test_reconcile_confirmed_payment_records_marks_failed_when_finalize_returns_none(self) -> None:
        record = build_record(record_id=21, user_id=55, tariff_code="1m")

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record]),
            ),
            patch.object(payment_flow, "refresh_payment_record_reconcile_state", new=AsyncMock(return_value=None)),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=None)),
            patch.object(payment_flow, "finalize_payment_record_product", new=AsyncMock(return_value=None)),
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=5)

        self.assertEqual(
            result,
            {
                "checked": 1,
                "reconciled": 0,
                "failed": 1,
                "skipped": 0,
                "finance_synced": 0,
                "finance_only": 0,
            },
        )

    async def test_reconcile_confirmed_payment_records_syncs_finance_only_rows_without_reapplying_effect(self) -> None:
        record = build_record(record_id=31, user_id=88, tariff_code="1m")
        record.metadata_json = (
            '{"effect_applied_at":"2026-04-03T10:00:00",'
            '"effect_kind":"subscription_activation",'
            '"access_sync_state":"success"}'
        )
        record_converged = build_record(
            record_id=31,
            user_id=88,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-03T10:00:00","effect_kind":"subscription_activation","access_sync_state":"success","finance_synced_at":"2026-04-03T10:01:00","reconcile_state":"converged","reconciled_at":"2026-04-03T10:01:00"}',
        )

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record]),
            ),
            patch.object(
                payment_flow,
                "refresh_payment_record_reconcile_state",
                new=AsyncMock(side_effect=[record, record_converged]),
            ),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=object())) as finance_mock,
            patch.object(payment_flow, "finalize_payment_record_product", new=AsyncMock()) as finalize_mock,
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 1,
                "reconciled": 1,
                "failed": 0,
                "skipped": 0,
                "finance_synced": 1,
                "finance_only": 1,
            },
        )
        finance_mock.assert_awaited_once_with(31)
        finalize_mock.assert_not_called()

    async def test_reconcile_confirmed_payment_records_retries_access_sync_for_applied_subscription_with_failed_sync_state(self) -> None:
        record = build_record(record_id=41, user_id=91, tariff_code="1m")
        record.metadata_json = (
            '{"effect_applied_at":"2026-04-03T10:00:00",'
            '"effect_kind":"subscription_activation",'
            '"access_sync_state":"failed",'
            '"finance_synced_at":"2026-04-03T10:01:00"}'
        )
        record_converged = build_record(
            record_id=41,
            user_id=91,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-03T10:00:00","effect_kind":"subscription_activation","access_sync_state":"success","finance_synced_at":"2026-04-03T10:01:00","reconcile_state":"converged","reconciled_at":"2026-04-03T10:02:00"}',
        )

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record]),
            ),
            patch.object(
                payment_flow,
                "refresh_payment_record_reconcile_state",
                new=AsyncMock(side_effect=[record, record_converged]),
            ),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=None)),
            patch.object(
                payment_flow,
                "_reconcile_applied_subscription_payment",
                new=AsyncMock(return_value={"product_type": "subscription", "effect_applied_now": False}),
            ) as resync_mock,
            patch.object(payment_flow, "finalize_payment_record_product", new=AsyncMock()) as finalize_mock,
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 1,
                "reconciled": 1,
                "failed": 0,
                "skipped": 0,
                "finance_synced": 0,
                "finance_only": 0,
            },
        )
        resync_mock.assert_awaited_once_with(
            user_id=91,
            tariff_code="1m",
            payment_record_id=41,
        )
        finalize_mock.assert_not_called()

    async def test_reconcile_confirmed_payment_records_treats_missing_access_state_as_access_retry_candidate(self) -> None:
        record = build_record(record_id=51, user_id=93, tariff_code="1m")
        record.metadata_json = (
            '{"effect_applied_at":"2026-04-03T10:00:00",'
            '"effect_kind":"subscription_activation",'
            '"finance_synced_at":"2026-04-03T10:01:00"}'
        )
        record_converged = build_record(
            record_id=51,
            user_id=93,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-03T10:00:00","effect_kind":"subscription_activation","access_sync_state":"success","finance_synced_at":"2026-04-03T10:01:00","reconcile_state":"converged","reconciled_at":"2026-04-03T10:02:00"}',
        )

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record]),
            ),
            patch.object(
                payment_flow,
                "refresh_payment_record_reconcile_state",
                new=AsyncMock(side_effect=[record, record_converged]),
            ),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=None)),
            patch.object(
                payment_flow,
                "_reconcile_applied_subscription_payment",
                new=AsyncMock(return_value={"product_type": "subscription", "effect_applied_now": False}),
            ) as resync_mock,
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 1,
                "reconciled": 1,
                "failed": 0,
                "skipped": 0,
                "finance_synced": 0,
                "finance_only": 0,
            },
        )
        resync_mock.assert_awaited_once_with(
            user_id=93,
            tariff_code="1m",
            payment_record_id=51,
        )

    async def test_reconcile_confirmed_payment_records_fails_if_finance_stays_unsynced_after_effect_reconcile(self) -> None:
        record = build_record(record_id=61, user_id=95, tariff_code="1m")
        record.metadata_json = (
            '{"effect_applied_at":"2026-04-03T10:00:00",'
            '"effect_kind":"subscription_activation",'
            '"access_sync_state":"failed"}'
        )
        record_after_access = build_record(
            record_id=61,
            user_id=95,
            tariff_code="1m",
            metadata_json='{"effect_applied_at":"2026-04-03T10:00:00","effect_kind":"subscription_activation","access_sync_state":"success"}',
        )

        with (
            patch.object(
                payment_flow,
                "list_confirmed_payment_records_needing_full_reconcile",
                new=AsyncMock(return_value=[record]),
            ),
            patch.object(
                payment_flow,
                "refresh_payment_record_reconcile_state",
                new=AsyncMock(side_effect=[record, record_after_access, record_after_access]),
            ),
            patch("dashboard.finance.sync_income_entry_for_payment_record", new=AsyncMock(return_value=None)),
            patch.object(payment_flow, "clear_payment_record_finance_synced", new=AsyncMock()),
            patch.object(
                payment_flow,
                "_reconcile_applied_subscription_payment",
                new=AsyncMock(return_value={"product_type": "subscription", "effect_applied_now": False}),
            ) as resync_mock,
        ):
            result = await payment_flow.reconcile_confirmed_payment_records(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 1,
                "reconciled": 0,
                "failed": 1,
                "skipped": 0,
                "finance_synced": 0,
                "finance_only": 0,
            },
        )
        resync_mock.assert_awaited_once_with(
            user_id=95,
            tariff_code="1m",
            payment_record_id=61,
        )

    async def test_notify_payment_result_supports_balance_topup(self) -> None:
        with patch.object(payment_flow, "send_user_message_and_refresh_home", new=AsyncMock()) as notify_mock:
            await payment_flow.notify_payment_result(
                bot=None,
                telegram_id=99001,
                payment_result={
                    "product_type": "balance_topup",
                    "amount_rub": 500,
                    "balance_rub": 900,
                },
            )

        notify_mock.assert_awaited_once()
        args = notify_mock.await_args.args
        self.assertEqual(args[0], 99001)
        self.assertIn("500", args[1])
        self.assertIn("900", args[1])


if __name__ == "__main__":
    unittest.main()
