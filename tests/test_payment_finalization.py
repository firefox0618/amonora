import unittest

from datetime import datetime
from unittest.mock import AsyncMock, patch

from bot.payment_flow import (
    finalize_balance_topup_payment,
    finalize_device_slot_payment,
    finalize_payment_record_product,
    finalize_subscription_payment,
)
from bot.utils.device_slots import DEVICE_SLOT_PRODUCT_TYPE
from bot.utils.tariffs import Tariff


TEST_TARIFF = Tariff(
    code="1m",
    title="1 month",
    duration_days=30,
    rub_price=149,
    stars_price=100,
)


class PaymentFinalizationContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.control_event_patcher = patch("bot.payment_flow.create_control_event", new=AsyncMock())
        self.control_event_patcher.start()

    def tearDown(self) -> None:
        self.control_event_patcher.stop()

    async def test_finalize_subscription_payment_success_calls_activation_expiry_and_sync(self) -> None:
        expires_at = datetime(2026, 3, 19, 12, 0, 0)
        updated_user = type("User", (), {"telegram_id": 1001})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF) as get_tariff_mock,
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock(return_value=expires_at)) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock(return_value=False)) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=77,
                tariff_code="1m",
                payment_id="pay-123",
                payment_source="crypto_bot",
            )

        self.assertIsNotNone(result)
        self.assertIs(result["user"], updated_user)
        self.assertEqual(result["tariff"], TEST_TARIFF)
        self.assertEqual(result["expires_at"], expires_at)
        self.assertEqual(result["expires_text"], "2026-03-19 12:00:00")
        self.assertFalse(result["sync_failed"])
        self.assertIsNone(result["repair_reason"])
        self.assertFalse(result["auto_retry_attempted"])
        self.assertFalse(result["auto_retry_succeeded"])

        get_tariff_mock.assert_called_once_with("1m")
        activate_mock.assert_awaited_once_with(
            user_id=77,
            tariff_code="1m",
            payment_id="pay-123",
            duration_days=30,
            payment_source="crypto_bot",
        )
        expires_mock.assert_awaited_once_with(77)
        sync_mock.assert_awaited_once_with(77, expires_at)
        repair_event_mock.assert_not_awaited()
        clear_repair_mock.assert_awaited_once_with(77)
        mark_repair_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_rejects_unknown_tariff(self) -> None:
        with (
            patch("bot.payment_flow.get_tariff", return_value=None) as get_tariff_mock,
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock()) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock()) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock()) as sync_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=77,
                tariff_code="missing",
                payment_id="pay-123",
                payment_source="crypto_bot",
            )

        self.assertIsNone(result)
        get_tariff_mock.assert_called_once_with("missing")
        activate_mock.assert_not_awaited()
        expires_mock.assert_not_awaited()
        sync_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_reports_sync_failed_without_rolling_back_activation(self) -> None:
        expires_at = datetime(2026, 3, 20, 8, 30, 0)
        updated_user = type("User", (), {"telegram_id": 1002})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock(return_value=expires_at)) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock(side_effect=[True, True])) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=88,
                tariff_code="1m",
                payment_id="pay-456",
                payment_source="telegram_stars",
            )

        self.assertIsNotNone(result)
        self.assertTrue(result["sync_failed"])
        self.assertEqual(result["expires_at"], expires_at)
        self.assertEqual(result["repair_reason"], "post_payment_sync_failed")
        self.assertTrue(result["auto_retry_attempted"])
        self.assertFalse(result["auto_retry_succeeded"])
        activate_mock.assert_awaited_once()
        expires_mock.assert_awaited_once_with(88)
        self.assertEqual(sync_mock.await_count, 2)
        repair_event_mock.assert_awaited_once_with(88, "failed", "auto_repair_failed")
        mark_repair_mock.assert_awaited_once_with(88, "post_payment_sync_failed")
        clear_repair_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_does_not_sync_if_activation_fails(self) -> None:
        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=None)) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock()) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock()) as sync_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=99,
                tariff_code="1m",
                payment_id="pay-789",
                payment_source="manual_sbp",
            )

        self.assertIsNone(result)
        activate_mock.assert_awaited_once()
        expires_mock.assert_not_awaited()
        sync_mock.assert_not_awaited()
        clear_repair_mock.assert_not_awaited()
        mark_repair_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_marks_access_incomplete_when_expiry_missing(self) -> None:
        updated_user = type("User", (), {"telegram_id": 1005})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock(return_value=None)) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock()) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=66,
                tariff_code="1m",
                payment_id="pay-660",
                payment_source="manual_sbp",
            )

        self.assertIsNotNone(result)
        self.assertFalse(result["sync_failed"])
        self.assertIsNone(result["expires_at"])
        self.assertEqual(result["repair_reason"], "post_payment_access_incomplete")
        activate_mock.assert_awaited_once()
        expires_mock.assert_awaited_once_with(66)
        sync_mock.assert_not_awaited()
        repair_event_mock.assert_not_awaited()
        clear_repair_mock.assert_not_awaited()
        mark_repair_mock.assert_awaited_once_with(66, "post_payment_access_incomplete")

    async def test_finalize_subscription_payment_surfaces_expiry_read_failure_after_activation(self) -> None:
        updated_user = type("User", (), {"telegram_id": 1003})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)) as activate_mock,
            patch(
                "bot.payment_flow.get_access_expires_at",
                new=AsyncMock(side_effect=RuntimeError("expiry lookup failed")),
            ) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock()) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "expiry lookup failed"):
                await finalize_subscription_payment(
                    user_id=55,
                    tariff_code="1m",
                    payment_id="pay-999",
                    payment_source="crypto_bot",
                )

        activate_mock.assert_awaited_once()
        expires_mock.assert_awaited_once_with(55)
        sync_mock.assert_not_awaited()
        repair_event_mock.assert_not_awaited()
        clear_repair_mock.assert_not_awaited()
        mark_repair_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_repeated_direct_calls_replay_orchestration(self) -> None:
        expires_at = datetime(2026, 3, 21, 18, 45, 0)
        updated_user = type("User", (), {"telegram_id": 1004})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)) as activate_mock,
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock(return_value=expires_at)) as expires_mock,
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock(return_value=False)) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            first = await finalize_subscription_payment(
                user_id=42,
                tariff_code="1m",
                payment_id="dup-pay",
                payment_source="telegram_stars",
            )
            second = await finalize_subscription_payment(
                user_id=42,
                tariff_code="1m",
                payment_id="dup-pay",
                payment_source="telegram_stars",
            )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(activate_mock.await_count, 2)
        self.assertEqual(expires_mock.await_count, 2)
        self.assertEqual(sync_mock.await_count, 2)
        repair_event_mock.assert_not_awaited()
        self.assertEqual(clear_repair_mock.await_count, 2)
        mark_repair_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_returns_none_when_in_progress_effect_never_applies(self) -> None:
        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(None, "in_progress")),
            ),
            patch("bot.payment_flow._wait_for_payment_effect", new=AsyncMock(return_value=False)) as wait_mock,
            patch(
                "bot.payment_flow._build_subscription_payment_result_snapshot",
                new=AsyncMock(return_value={"should_not": "happen"}),
            ) as snapshot_mock,
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock()) as activate_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=42,
                tariff_code="1m",
                payment_id="dup-pay",
                payment_source="telegram_stars",
                payment_record_id=501,
            )

        self.assertIsNone(result)
        wait_mock.assert_awaited_once_with(501, effect_kind="subscription_activation")
        snapshot_mock.assert_not_awaited()
        activate_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_does_not_release_claim_after_activation_if_marking_fails(self) -> None:
        updated_user = type("User", (), {"telegram_id": 1007})()
        payment_record = type(
            "PaymentRecord",
            (),
            {
                "id": 601,
                "confirmed_at": datetime(2026, 3, 22, 12, 0, 0),
                "payment_method": "manual_sbp",
                "list_price_amount": 149,
                "balance_applied_amount": 0,
                "amount": 149,
            },
        )()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(payment_record, "claimed")),
            ),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)),
            patch(
                "bot.payment_flow.mark_payment_record_effect_applied",
                new=AsyncMock(side_effect=[RuntimeError("mark failed"), payment_record]),
            ) as mark_mock,
            patch("bot.payment_flow.release_payment_record_effect_claim", new=AsyncMock()) as release_mock,
            patch("bot.payment_flow._ensure_subscription_access_state", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "mark failed"):
                await finalize_subscription_payment(
                    user_id=42,
                    tariff_code="1m",
                    payment_id="dup-pay",
                    payment_source="telegram_stars",
                    payment_record_id=601,
                )

        self.assertEqual(mark_mock.await_count, 2)
        release_mock.assert_not_awaited()

    async def test_finalize_subscription_payment_clears_marker_when_auto_retry_recovers_sync(self) -> None:
        expires_at = datetime(2026, 3, 22, 9, 15, 0)
        updated_user = type("User", (), {"telegram_id": 1006})()

        with (
            patch("bot.payment_flow.get_tariff", return_value=TEST_TARIFF),
            patch("bot.payment_flow.activate_paid_subscription", new=AsyncMock(return_value=updated_user)),
            patch("bot.payment_flow.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("bot.payment_flow.sync_user_vpn_access", new=AsyncMock(side_effect=[True, False])) as sync_mock,
            patch("bot.payment_flow.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("bot.payment_flow.clear_vpn_repair_needed", new=AsyncMock()) as clear_repair_mock,
            patch("bot.payment_flow.mark_vpn_repair_needed", new=AsyncMock()) as mark_repair_mock,
        ):
            result = await finalize_subscription_payment(
                user_id=67,
                tariff_code="1m",
                payment_id="pay-670",
                payment_source="manual_sbp",
            )

        self.assertIsNotNone(result)
        self.assertFalse(result["sync_failed"])
        self.assertIsNone(result["repair_reason"])
        self.assertTrue(result["auto_retry_attempted"])
        self.assertTrue(result["auto_retry_succeeded"])
        self.assertEqual(sync_mock.await_count, 2)
        repair_event_mock.assert_awaited_once_with(67, "success", "auto_repair_success")
        clear_repair_mock.assert_awaited_once_with(67)
        mark_repair_mock.assert_not_awaited()

    async def test_finalize_payment_record_product_creates_device_slot_entitlement_without_subscription_activation(self) -> None:
        expires_at = datetime(2026, 4, 24, 12, 0, 0)
        starts_at = datetime(2026, 3, 24, 12, 0, 0)
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 91,
                "user_id": 77,
                "tariff_code": "device_slot_addon",
                "metadata_json": (
                    '{"product_type":"device_slot_addon","slots_count":1,"unit_price_rub":49,"total_amount_rub":49}'
                ),
                "list_price_amount": 49,
                "amount": 49,
                "balance_applied_amount": 0,
                "confirmed_at": datetime(2026, 3, 24, 12, 30, 0),
                "created_at": datetime(2026, 3, 24, 12, 0, 0),
            },
        )()
        user = type(
            "User",
            (),
            {
                "id": 77,
                "telegram_id": 1077,
                "subscription_status": "active",
                "subscription_expires_at": expires_at,
                "subscription_started_at": starts_at,
                "is_blocked": False,
            },
        )()

        with (
            patch("bot.payment_flow.get_payment_record_by_id", new=AsyncMock(return_value=record)) as get_record_mock,
            patch("bot.payment_flow.get_user_by_id", new=AsyncMock(return_value=user)) as get_user_mock,
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(record, "claimed")),
            ) as claim_mock,
            patch("bot.payment_flow.release_payment_record_effect_claim", new=AsyncMock()) as release_mock,
            patch("bot.payment_flow.create_device_slot_entitlement", new=AsyncMock(return_value=object())) as entitlement_mock,
            patch("bot.payment_flow.mark_payment_record_effect_applied", new=AsyncMock()) as applied_mock,
            patch("bot.payment_flow.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={77: 1})),
            patch("bot.payment_flow.finalize_subscription_payment", new=AsyncMock()) as subscription_finalize_mock,
        ):
            result = await finalize_payment_record_product(
                user_id=77,
                payment_source="manual_sbp",
                payment_record_id=91,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["product_type"], DEVICE_SLOT_PRODUCT_TYPE)
        self.assertEqual(result["expires_at"], expires_at)
        self.assertEqual(result["device_limit"], 4)
        self.assertEqual(result["slots_count"], 1)
        self.assertEqual(get_record_mock.await_count, 2)
        claim_mock.assert_awaited_once_with(91, effect_kind="device_slot_activation")
        release_mock.assert_not_awaited()
        get_user_mock.assert_awaited_once_with(77)
        entitlement_mock.assert_awaited_once_with(
            user_id=77,
            payment_record_id=91,
            slots_count=1,
            unit_price_rub=49,
            total_amount_rub=49,
            starts_at=starts_at,
            expires_at=expires_at,
        )
        applied_mock.assert_awaited_once_with(91, effect_kind="device_slot_activation")
        subscription_finalize_mock.assert_not_awaited()

    async def test_finalize_device_slot_payment_uses_subscription_end_for_long_plan(self) -> None:
        expires_at = datetime(2026, 10, 3, 12, 0, 0)
        starts_at = datetime(2026, 4, 3, 12, 0, 0)
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 92,
                "user_id": 78,
                "metadata_json": (
                    '{"product_type":"device_slot_addon","slots_count":1,"unit_price_rub":49,"total_amount_rub":49}'
                ),
                "list_price_amount": 49,
                "amount": 49,
                "confirmed_at": datetime(2026, 4, 3, 12, 10, 0),
                "created_at": datetime(2026, 4, 3, 12, 0, 0),
            },
        )()
        user = type(
            "User",
            (),
            {
                "id": 78,
                "telegram_id": 1078,
                "subscription_status": "active",
                "subscription_expires_at": expires_at,
                "subscription_started_at": starts_at,
                "is_blocked": False,
            },
        )()

        with (
            patch("bot.payment_flow.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch("bot.payment_flow.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(record, "claimed")),
            ) as claim_mock,
            patch("bot.payment_flow.release_payment_record_effect_claim", new=AsyncMock()) as release_mock,
            patch("bot.payment_flow.create_device_slot_entitlement", new=AsyncMock(return_value=object())) as entitlement_mock,
            patch("bot.payment_flow.mark_payment_record_effect_applied", new=AsyncMock()) as applied_mock,
            patch("bot.payment_flow.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={78: 1})),
        ):
            result = await finalize_device_slot_payment(
                user_id=78,
                payment_source="manual_sbp",
                payment_record_id=92,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["expires_at"], expires_at)
        self.assertEqual(result["expires_text"], "2026-10-03 12:00:00")
        claim_mock.assert_awaited_once_with(92, effect_kind="device_slot_activation")
        release_mock.assert_not_awaited()
        entitlement_mock.assert_awaited_once_with(
            user_id=78,
            payment_record_id=92,
            slots_count=1,
            unit_price_rub=49,
            total_amount_rub=49,
            starts_at=starts_at,
            expires_at=expires_at,
        )
        applied_mock.assert_awaited_once_with(92, effect_kind="device_slot_activation")

    async def test_finalize_device_slot_payment_does_not_release_claim_after_entitlement_if_marking_fails(self) -> None:
        expires_at = datetime(2026, 10, 3, 12, 0, 0)
        starts_at = datetime(2026, 4, 3, 12, 0, 0)
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 93,
                "user_id": 79,
                "metadata_json": (
                    '{"product_type":"device_slot_addon","slots_count":1,"unit_price_rub":49,"total_amount_rub":49}'
                ),
                "list_price_amount": 49,
                "amount": 49,
                "confirmed_at": datetime(2026, 4, 3, 12, 10, 0),
                "created_at": datetime(2026, 4, 3, 12, 0, 0),
            },
        )()
        user = type(
            "User",
            (),
            {
                "id": 79,
                "telegram_id": 1079,
                "subscription_status": "active",
                "subscription_expires_at": expires_at,
                "subscription_started_at": starts_at,
                "is_blocked": False,
            },
        )()

        with (
            patch("bot.payment_flow.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch("bot.payment_flow.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(record, "claimed")),
            ),
            patch("bot.payment_flow.release_payment_record_effect_claim", new=AsyncMock()) as release_mock,
            patch("bot.payment_flow.create_device_slot_entitlement", new=AsyncMock(return_value=object())),
            patch(
                "bot.payment_flow.mark_payment_record_effect_applied",
                new=AsyncMock(side_effect=[RuntimeError("slot mark failed"), record]),
            ) as mark_mock,
            patch("bot.payment_flow.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={79: 1})),
        ):
            with self.assertRaisesRegex(RuntimeError, "slot mark failed"):
                await finalize_device_slot_payment(
                    user_id=79,
                    payment_source="manual_sbp",
                    payment_record_id=93,
                )

        self.assertEqual(mark_mock.await_count, 2)
        release_mock.assert_not_awaited()

    async def test_finalize_balance_topup_payment_does_not_release_claim_after_credit_if_marking_fails(self) -> None:
        record = type(
            "PaymentRecord",
            (),
            {
                "id": 94,
                "user_id": 80,
                "tariff_code": "balance_topup",
                "payment_method": "sbp_platega",
                "amount": 300,
                "metadata_json": '{"product_type":"balance_topup"}',
            },
        )()
        topped_up_user = type("User", (), {"id": 80, "telegram_id": 1080, "balance_rub": 1300})()

        with (
            patch("bot.payment_flow.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch(
                "bot.payment_flow.claim_payment_record_effect",
                new=AsyncMock(return_value=(record, "claimed")),
            ),
            patch("bot.payment_flow.credit_user_balance", new=AsyncMock(return_value=topped_up_user)),
            patch(
                "bot.payment_flow.mark_payment_record_effect_applied",
                new=AsyncMock(side_effect=[RuntimeError("topup mark failed"), record]),
            ) as mark_mock,
            patch("bot.payment_flow.release_payment_record_effect_claim", new=AsyncMock()) as release_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "topup mark failed"):
                await finalize_balance_topup_payment(
                    user_id=80,
                    payment_record_id=94,
                )

        self.assertEqual(mark_mock.await_count, 2)
        release_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
