import json
import os
import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

from bot.handlers import devices as devices_handlers
from bot.handlers import tariffs as tariffs_handlers
from bot.utils.tariffs import Tariff
from aiogram.exceptions import TelegramBadRequest


TEST_TARIFF = Tariff(
    code="1m",
    title="1 month",
    duration_days=30,
    rub_price=149,
    stars_price=100,
)


class FakeMessage:
    def __init__(self, successful_payment, telegram_id: int = 1010) -> None:
        self.successful_payment = successful_payment
        self.from_user = SimpleNamespace(id=telegram_id)
        self.answers: list[dict] = []

    async def answer(self, text: str, parse_mode: str | None = None, **kwargs):
        self.answers.append({"text": text, "parse_mode": parse_mode, "kwargs": kwargs})
        return SimpleNamespace()


class FakeEditableMessage:
    def __init__(self) -> None:
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def edit_text(self, text: str, parse_mode: str | None = None, **kwargs):
        self.edits.append({"text": text, "parse_mode": parse_mode, "kwargs": kwargs})
        return SimpleNamespace()

    async def answer(self, text: str, parse_mode: str | None = None, **kwargs):
        self.answers.append({"text": text, "parse_mode": parse_mode, "kwargs": kwargs})
        return SimpleNamespace()


class FakeCallback:
    def __init__(self, data: str, message=None, telegram_id: int = 1010) -> None:
        self.data = data
        self.message = message or FakeEditableMessage()
        self.from_user = SimpleNamespace(id=telegram_id)
        self.answers: list[dict] = []
        self.bot = object()

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answers.append({"text": text, "show_alert": show_alert})
        return SimpleNamespace()


class TelegramStarsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_successful_payment_without_applied_effect_retries_finalization(self) -> None:
        successful_payment = SimpleNamespace(
            invoice_payload=json.dumps({"tariff_code": "1m"}),
            telegram_payment_charge_id="charge-retry",
            currency="XTR",
            total_amount=100,
        )
        message = FakeMessage(successful_payment)
        user = SimpleNamespace(id=91)
        record = SimpleNamespace(
            id=19,
            metadata_json=None,
            list_price_amount=149,
            balance_applied_amount=0,
            balance_reserved_amount=0,
            amount=149,
        )
        payment_result = {
            "tariff": TEST_TARIFF,
            "expires_text": "2026-04-25 10:00:00",
            "list_price_amount": 149,
            "balance_applied_amount": 0,
            "paid_amount": 149,
            "sync_failed": False,
        }

        with (
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers, "create_external_payment_record", new=AsyncMock(return_value=record)),
            patch.object(tariffs_handlers, "confirm_external_payment_record", new=AsyncMock(return_value=(record, False))),
            patch.object(tariffs_handlers, "payment_record_effect_applied", return_value=False),
            patch.object(
                tariffs_handlers,
                "finalize_subscription_payment",
                new=AsyncMock(return_value=payment_result),
            ) as finalize_mock,
            patch.object(tariffs_handlers, "sync_income_entry_for_payment_record", new=AsyncMock()) as sync_income_mock,
            patch.object(tariffs_handlers, "notify_referral_bonus", new=AsyncMock(return_value=False)),
        ):
            await tariffs_handlers.successful_payment_handler(message, bot=object())

        finalize_mock.assert_awaited_once_with(
            user_id=91,
            tariff_code="1m",
            payment_id="charge-retry",
            payment_source="telegram_stars",
            payment_record_id=19,
        )
        sync_income_mock.assert_awaited_once_with(19)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("2026-04-25 10:00:00", message.answers[0]["text"])

    async def test_duplicate_successful_payment_does_not_finalize_twice(self) -> None:
        successful_payment = SimpleNamespace(
            invoice_payload=json.dumps({"tariff_code": "1m"}),
            telegram_payment_charge_id="charge-1",
            currency="XTR",
            total_amount=100,
        )
        message = FakeMessage(successful_payment)
        user = SimpleNamespace(id=77)
        record = SimpleNamespace(
            id=11,
            list_price_amount=149,
            balance_applied_amount=0,
            balance_reserved_amount=0,
            amount=149,
        )

        with (
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers, "create_external_payment_record", new=AsyncMock(return_value=record)),
            patch.object(tariffs_handlers, "confirm_external_payment_record", new=AsyncMock(return_value=(record, False))),
            patch.object(tariffs_handlers, "payment_record_effect_applied", return_value=True),
            patch.object(
                tariffs_handlers,
                "get_access_expires_at",
                new=AsyncMock(return_value=datetime(2026, 3, 23, 19, 45, 0)),
            ),
            patch.object(tariffs_handlers, "finalize_subscription_payment", new=AsyncMock()) as finalize_mock,
            patch.object(tariffs_handlers, "sync_income_entry_for_payment_record", new=AsyncMock()) as sync_income_mock,
            patch.object(tariffs_handlers, "notify_referral_bonus", new=AsyncMock()) as bonus_mock,
        ):
            await tariffs_handlers.successful_payment_handler(message, bot=object())

        finalize_mock.assert_not_awaited()
        sync_income_mock.assert_not_awaited()
        bonus_mock.assert_not_awaited()
        self.assertEqual(len(message.answers), 1)
        self.assertEqual(message.answers[0]["parse_mode"], "HTML")
        self.assertIn("2026-03-23 19:45:00", message.answers[0]["text"])

    async def test_first_successful_payment_still_finalizes_subscription(self) -> None:
        successful_payment = SimpleNamespace(
            invoice_payload=json.dumps({"tariff_code": "1m"}),
            telegram_payment_charge_id="charge-2",
            currency="XTR",
            total_amount=100,
        )
        message = FakeMessage(successful_payment)
        user = SimpleNamespace(id=88)
        record = SimpleNamespace(id=12)
        payment_result = {
            "tariff": TEST_TARIFF,
            "expires_text": "2026-04-22 10:00:00",
            "list_price_amount": 149,
            "balance_applied_amount": 0,
            "paid_amount": 149,
            "sync_failed": False,
        }

        with (
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers, "create_external_payment_record", new=AsyncMock(return_value=record)),
            patch.object(tariffs_handlers, "confirm_external_payment_record", new=AsyncMock(return_value=(record, True))),
            patch.object(
                tariffs_handlers,
                "finalize_subscription_payment",
                new=AsyncMock(return_value=payment_result),
            ) as finalize_mock,
            patch.object(tariffs_handlers, "sync_income_entry_for_payment_record", new=AsyncMock()) as sync_income_mock,
            patch.object(tariffs_handlers, "notify_referral_bonus", new=AsyncMock(return_value=False)),
        ):
            await tariffs_handlers.successful_payment_handler(message, bot=object())

        finalize_mock.assert_awaited_once_with(
            user_id=88,
            tariff_code="1m",
            payment_id="charge-2",
            payment_source="telegram_stars",
            payment_record_id=12,
        )
        sync_income_mock.assert_awaited_once_with(12)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("2026-04-22 10:00:00", message.answers[0]["text"])


class TariffPaymentFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_crypto_invoice_duplicate_without_applied_effect_retries_finalization(self) -> None:
        callback = FakeCallback("tariff:crypto:check:1m:invoice-1")
        record = SimpleNamespace(
            id=31,
            user_id=77,
            tariff_code="1m",
            external_payment_id="invoice-1",
            metadata_json=None,
            payment_status="pending",
        )
        payment_result = {
            "tariff": TEST_TARIFF,
            "expires_text": "2026-04-26 12:00:00",
            "list_price_amount": 149,
            "balance_applied_amount": 0,
            "paid_amount": 149,
            "sync_failed": False,
        }

        with (
            patch.object(tariffs_handlers, "get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers.CryptoPayClient, "parse_invoice_payload", return_value={"user_id": 77, "tariff_code": "1m"}),
            patch.object(tariffs_handlers, "confirm_external_payment_record", new=AsyncMock(return_value=(record, False))),
            patch.object(tariffs_handlers, "payment_record_effect_applied", return_value=False),
            patch.object(tariffs_handlers, "sync_income_entry_for_payment_record", new=AsyncMock()) as sync_income_mock,
            patch.object(
                tariffs_handlers,
                "finalize_subscription_payment",
                new=AsyncMock(return_value=payment_result),
            ) as finalize_mock,
            patch.object(tariffs_handlers, "notify_referral_bonus", new=AsyncMock(return_value=False)),
            patch.object(
                tariffs_handlers,
                "CryptoPayClient",
                return_value=SimpleNamespace(
                    configured=True,
                    get_invoice=AsyncMock(return_value={"status": "paid", "payload": "{}", "invoice_id": "invoice-1", "fiat": "RUB"}),
                ),
            ),
        ):
            await tariffs_handlers.crypto_check_callback(callback, bot=object())

        sync_income_mock.assert_awaited_once_with(31)
        finalize_mock.assert_awaited_once_with(
            user_id=77,
            tariff_code="1m",
            payment_id="invoice-1",
            payment_source="crypto_bot",
            payment_record_id=31,
        )
        self.assertEqual(callback.answers[-1]["text"], "Оплата подтверждена")

    async def test_sbp_tariff_method_keeps_auto_flow_when_manual_fallback_also_enabled(self) -> None:
        callback = FakeCallback("tariff:method:sbp:1m")
        user = SimpleNamespace(id=77, telegram_id=1010)

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(
                tariffs_handlers,
                "_load_user_and_breakdown",
                new=AsyncMock(return_value=(user, {"payable_amount": 149, "balance_amount": 0})),
            ),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "_show_manual_payment", new=AsyncMock()) as manual_mock,
            patch.object(tariffs_handlers, "_show_platega_payment", new=AsyncMock()) as platega_mock,
            patch.object(tariffs_handlers.config, "enable_platega_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "enable_manual_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "force_manual_sbp_user_flow", True),
        ):
            await tariffs_handlers.tariff_method_callback(callback)

        platega_mock.assert_awaited_once()
        manual_mock.assert_not_awaited()

    async def test_sbp_manual_button_uses_manual_flow_when_both_options_enabled(self) -> None:
        callback = FakeCallback("tariff:method:sbp_manual:1m")
        user = SimpleNamespace(id=77, telegram_id=1010)

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(
                tariffs_handlers,
                "_load_user_and_breakdown",
                new=AsyncMock(return_value=(user, {"payable_amount": 149, "balance_amount": 0})),
            ),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "_show_manual_payment", new=AsyncMock()) as manual_mock,
            patch.object(tariffs_handlers, "_show_platega_payment", new=AsyncMock()) as platega_mock,
            patch.object(tariffs_handlers.config, "enable_platega_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "enable_manual_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "force_manual_sbp_user_flow", True),
        ):
            await tariffs_handlers.tariff_method_callback(callback)

        manual_mock.assert_awaited_once()
        platega_mock.assert_not_awaited()
        self.assertIn("если автоматический qr по сбп не сработал", manual_mock.await_args.kwargs["intro_note"].lower())

    async def test_balance_topup_sbp_still_uses_platega_when_emergency_manual_fallback_enabled(self) -> None:
        callback = FakeCallback("balance:method:sbp:300")
        user = SimpleNamespace(id=77, telegram_id=1010)

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "_show_platega_balance_topup_payment", new=AsyncMock()) as topup_mock,
            patch.object(tariffs_handlers.config, "enable_platega_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "enable_manual_sbp_user_flow", True),
            patch.object(tariffs_handlers.config, "force_manual_sbp_user_flow", True),
        ):
            await tariffs_handlers.balance_method_callback(callback)

        topup_mock.assert_awaited_once_with(callback, method="sbp", amount_rub=300, user=user)

    async def test_tariff_method_reuses_existing_open_intent_across_methods(self) -> None:
        callback = FakeCallback("tariff:method:sbp_manual:1m")
        user = SimpleNamespace(id=77, telegram_id=1010)
        existing_record = SimpleNamespace(
            id=51,
            payment_method="sbp_platega",
            payment_status="pending",
            amount=149,
            list_price_amount=149,
            balance_reserved_amount=0,
            metadata_json=json.dumps({"checkout_url": "https://example.test/pay/51"}),
        )

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(
                tariffs_handlers,
                "_load_user_and_breakdown",
                new=AsyncMock(return_value=(user, {"payable_amount": 149, "balance_amount": 0})),
            ),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=existing_record)),
            patch.object(tariffs_handlers, "_show_manual_payment", new=AsyncMock()) as manual_mock,
            patch.object(tariffs_handlers, "_show_platega_payment", new=AsyncMock()) as platega_mock,
        ):
            await tariffs_handlers.tariff_method_callback(callback)

        manual_mock.assert_not_awaited()
        platega_mock.assert_not_awaited()
        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("активный счёт", callback.message.edits[0]["text"].lower())
        self.assertIn("не создавать дубль", callback.message.edits[0]["text"].lower())
        self.assertEqual(callback.answers[-1]["text"], "Уже есть активный счёт")
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_device_slot_method_reuses_existing_manual_request(self) -> None:
        callback = FakeCallback("device-slot:method:crypto")
        user = SimpleNamespace(id=77, telegram_id=1010)
        context = {
            "price_rub": 49,
            "duration_days": 30,
            "eligible": True,
            "remaining_capacity": 2,
            "current_limit": 3,
            "next_limit": 4,
            "expires_text": "2026-05-01 12:00:00",
        }
        existing_record = SimpleNamespace(
            id=63,
            payment_method="crypto_manual",
            payment_status="awaiting_admin_review",
            amount=49,
            list_price_amount=49,
            balance_reserved_amount=0,
            metadata_json=json.dumps({"product_type": "device_slot_addon", "slots_count": 1}),
        )

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "_device_slot_context_for_user", new=AsyncMock(return_value=context)),
            patch.object(
                tariffs_handlers,
                "build_balance_breakdown_for_price",
                new=AsyncMock(return_value={"payable_amount": 49, "balance_amount": 0, "list_price_amount": 49}),
            ),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=existing_record)),
            patch.object(tariffs_handlers, "_show_device_slot_manual_payment", new=AsyncMock()) as manual_mock,
            patch.object(tariffs_handlers, "_show_device_slot_platega_payment", new=AsyncMock()) as platega_mock,
            patch.object(tariffs_handlers.config, "enable_manual_crypto_user_flow", True),
        ):
            await tariffs_handlers.device_slot_method_callback(callback)

        manual_mock.assert_not_awaited()
        platega_mock.assert_not_awaited()
        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("активная заявка", callback.message.edits[0]["text"].lower())
        self.assertIn("отправлена на проверку", callback.message.edits[0]["text"].lower())
        self.assertEqual(callback.answers[-1]["text"], "Уже есть активная заявка")
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_balance_topup_method_reuses_existing_open_invoice(self) -> None:
        callback = FakeCallback("balance:method:crypto:300")
        user = SimpleNamespace(id=77, telegram_id=1010)
        existing_record = SimpleNamespace(
            id=71,
            payment_method="sbp_platega",
            payment_status="pending",
            amount=300,
            list_price_amount=300,
            balance_reserved_amount=0,
            metadata_json=json.dumps({"payload_type": "balance_topup", "checkout_url": "https://example.test/topup/71"}),
        )

        with (
            patch.object(tariffs_handlers, "_blocked_payment_guard", new=AsyncMock(return_value=None)),
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_open_payment_intent_for_user", new=AsyncMock(return_value=existing_record)),
            patch.object(tariffs_handlers, "_show_platega_balance_topup_payment", new=AsyncMock()) as topup_mock,
            patch.object(tariffs_handlers.config, "enable_platega_crypto_user_flow", True),
        ):
            await tariffs_handlers.balance_method_callback(callback)

        topup_mock.assert_not_awaited()
        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("активный счёт", callback.message.edits[0]["text"].lower())
        self.assertIn("не создавать дубль", callback.message.edits[0]["text"].lower())
        self.assertEqual(callback.answers[-1]["text"], "Уже есть активный счёт")
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_device_limit_state_keeps_buy_more_for_active_non_admin_subscription(self) -> None:
        user = SimpleNamespace(
            id=77,
            telegram_id=7070,
            subscription_status="active",
            subscription_source="manual_vip",
            subscription_expires_at=datetime(2026, 5, 1, 12, 0, 0),
            is_blocked=False,
            active_device_slot_addons=0,
        )

        with patch.object(devices_handlers, "_annotate_user_device_slots", new=AsyncMock(return_value=0)):
            state = await devices_handlers._device_limit_state(user, devices_count=3)

        self.assertEqual(state["device_limit"], 3)
        self.assertTrue(state["can_buy_more"])

    async def test_manual_payment_submitted_ignores_message_not_modified(self) -> None:
        callback = FakeCallback("tariff:manual:paid:51:1m")
        callback.message.edit_text = AsyncMock(
            side_effect=TelegramBadRequest(MagicMock(), "message is not modified")
        )
        record_before = SimpleNamespace(id=51, user_id=77, payment_status="awaiting_user_payment")
        updated = SimpleNamespace(
            id=51,
            user_id=77,
            payment_status="awaiting_admin_review",
            payment_method="sbp_manual",
            list_price_amount=149,
            balance_reserved_amount=0,
            amount=149,
        )
        user = SimpleNamespace(id=77, telegram_id=1010)

        with (
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers, "get_payment_record_by_id", new=AsyncMock(return_value=record_before)),
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "mark_manual_payment_record_submitted", new=AsyncMock(return_value=updated)),
            patch.object(tariffs_handlers, "notify_support_admins_about_manual_payment", new=AsyncMock()) as notify_mock,
        ):
            await tariffs_handlers.manual_payment_submitted_callback(callback)

        notify_mock.assert_awaited_once_with(51)
        self.assertEqual(callback.answers[-1]["text"], "Заявка отправлена на проверку")

    async def test_manual_payment_status_ignores_message_not_modified(self) -> None:
        callback = FakeCallback("tariff:manual:status:51:1m")
        callback.message.edit_text = AsyncMock(
            side_effect=TelegramBadRequest(MagicMock(), "message is not modified")
        )
        user = SimpleNamespace(id=77, telegram_id=1010)
        record = SimpleNamespace(
            id=51,
            user_id=77,
            payment_status="awaiting_admin_review",
            payment_method="sbp_manual",
            list_price_amount=149,
            balance_reserved_amount=0,
            amount=149,
        )

        with (
            patch.object(tariffs_handlers, "get_tariff", return_value=TEST_TARIFF),
            patch.object(tariffs_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(tariffs_handlers, "get_payment_record_by_id", new=AsyncMock(return_value=record)),
        ):
            await tariffs_handlers.manual_payment_status_callback(callback)

        self.assertEqual(callback.answers[-1]["text"], "Заявка ещё на проверке")
        self.assertTrue(callback.answers[-1]["show_alert"])


if __name__ == "__main__":
    unittest.main()
