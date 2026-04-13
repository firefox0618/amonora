import os
import unittest

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


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

from test_bot import router as test_bot_router


class FakeMessage:
    def __init__(self, telegram_id: int = 1001, first_name: str = "Тест") -> None:
        self.from_user = SimpleNamespace(id=telegram_id, first_name=first_name, username="tester")
        self.answers: list[dict] = []
        self.edits: list[dict] = []

    async def answer(self, text: str, parse_mode: str | None = None, reply_markup=None, **kwargs):
        self.answers.append(
            {
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()

    async def answer_photo(self, photo, caption: str | None = None, parse_mode: str | None = None, reply_markup=None, **kwargs):
        self.answers.append(
            {
                "kind": "photo",
                "text": caption,
                "photo": photo,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()

    async def edit_text(self, text: str, parse_mode: str | None = None, reply_markup=None, **kwargs):
        self.edits.append(
            {
                "kind": "text",
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()

    async def edit_media(self, media, reply_markup=None, **kwargs):
        self.edits.append(
            {
                "kind": "media",
                "text": getattr(media, "caption", None),
                "media": media,
                "reply_markup": reply_markup,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()


class FakeCallback:
    def __init__(self, message: FakeMessage, data: str, telegram_id: int = 1001) -> None:
        self.message = message
        self.data = data
        self.bot = object()
        self.from_user = SimpleNamespace(id=telegram_id, first_name="Тест", username="tester")
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **kwargs):
        self.answers.append({"text": text, "show_alert": show_alert, "kwargs": kwargs})
        return SimpleNamespace()


class FakeAiogramBot:
    instances: list["FakeAiogramBot"] = []

    def __init__(self, token: str) -> None:
        self.token = token
        self.closed = False
        self.session = SimpleNamespace(close=self._close)
        self.__class__.instances.append(self)

    async def _close(self):
        self.closed = True


class TestBotRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_command_shows_agreement_screen_for_new_user(self) -> None:
        message = FakeMessage()

        with patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=None)):
            await test_bot_router.v2_start_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertEqual(message.answers[0]["kind"], "photo")
        self.assertIn("пользовательское соглашение", message.answers[0]["text"].lower())
        self.assertIn("принимаю", message.answers[0]["text"].lower())
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Пользовательское соглашение", "Принимаю"])

    async def test_start_command_opens_main_menu_for_existing_user_without_trial_history(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            trial_used=False,
            is_blocked=False,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=None,
        )
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=False,
            status_label="❌ Не активна",
            days_left_text="—",
            expires_text="—",
            balance_rub=0,
            tariff_title="Без тарифа",
            devices_count=0,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
        ):
            await test_bot_router.v2_start_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("статус", message.answers[0]["text"].lower())
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Моя подписка", "Ключ", "Продлить", "Информация", "Поддержка", "Бонусная система"])

    async def test_start_command_tracks_channel_post_token_in_v2_router(self) -> None:
        message = FakeMessage()
        new_user = SimpleNamespace(id=42, telegram_id=1001, username="tester", created_at=datetime.utcnow())

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(side_effect=[None, None])),
            patch.object(test_bot_router, "get_or_create_user", new=AsyncMock(return_value=(new_user, True))) as get_or_create_mock,
            patch.object(
                test_bot_router,
                "register_channel_post_touch",
                new=AsyncMock(return_value={"source_key": "inst_reels_april_01", "item_id": 17}),
            ) as touch_mock,
            patch.object(test_bot_router, "emit_bot_start_event", new=AsyncMock()) as emit_start_mock,
            patch.object(
                test_bot_router,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ) as bind_mock,
        ):
            await test_bot_router.v2_start_handler(message, command=SimpleNamespace(args="post_inst_reels_april_01"))

        get_or_create_mock.assert_awaited_once_with(
            telegram_id=1001,
            username="tester",
            referred_by_telegram_id=None,
            skip_initial_analytics_attribution=True,
        )
        touch_mock.assert_awaited_once_with("inst_reels_april_01", user_id=42, telegram_id=1001)
        emit_start_mock.assert_awaited_once_with(
            user_id=42,
            telegram_id=1001,
            source_type="channel_post",
            source_key="inst_reels_april_01",
            channel_item_id=17,
        )
        bind_mock.assert_awaited_once_with(42, None)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("пользовательское соглашение", message.answers[0]["text"].lower())

    async def test_start_command_preserves_referral_binding_in_v2_router(self) -> None:
        message = FakeMessage()
        new_user = SimpleNamespace(id=42, telegram_id=1001, username="tester", created_at=datetime.utcnow())

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(side_effect=[None, None])),
            patch.object(test_bot_router, "get_or_create_user", new=AsyncMock(return_value=(new_user, True))) as get_or_create_mock,
            patch.object(test_bot_router, "safe_upsert_user_attribution", new=AsyncMock()) as attribution_mock,
            patch.object(test_bot_router, "emit_bot_start_event", new=AsyncMock()) as emit_start_mock,
            patch.object(
                test_bot_router,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": True, "referrer_telegram_id": 555}),
            ) as bind_mock,
            patch.object(test_bot_router, "send_user_message", new=AsyncMock()) as send_message_mock,
        ):
            await test_bot_router.v2_start_handler(message, command=SimpleNamespace(args="ref_test123"))

        get_or_create_mock.assert_awaited_once_with(
            telegram_id=1001,
            username="tester",
            referred_by_telegram_id=None,
            skip_initial_analytics_attribution=False,
        )
        attribution_mock.assert_awaited_once()
        emit_start_mock.assert_awaited_once_with(
            user_id=42,
            telegram_id=1001,
            source_type="organic_bot",
            source_key="organic_bot",
            channel_item_id=None,
        )
        bind_mock.assert_awaited_once_with(42, "test123")
        send_message_mock.assert_awaited_once()
        self.assertEqual(len(message.answers), 1)
        self.assertIn("пользовательское соглашение", message.answers[0]["text"].lower())

    async def test_start_command_shows_trial_used_paywall_for_expired_trial_user(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            trial_used=True,
            is_blocked=False,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=datetime.utcnow() - timedelta(days=1),
        )

        with patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)):
            await test_bot_router.v2_start_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("пробный период уже был использован", message.answers[0]["text"].lower())
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Купить подписку", "Поддержка", "Главное меню"])

    async def test_start_command_opens_main_menu_for_user_with_active_subscription_and_used_trial(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            trial_used=True,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime.utcnow() + timedelta(days=10),
            trial_expires_at=datetime.utcnow() - timedelta(days=1),
        )
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="10 дн.",
            expires_text="20.04.2026 12:00",
            balance_rub=0,
            tariff_title="1 месяц",
            devices_count=0,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
        ):
            await test_bot_router.v2_start_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("✅", message.answers[0]["text"])
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Моя подписка", "Ключ", "Продлить", "Информация", "Поддержка", "Бонусная система"])

    async def test_legacy_buy_message_opens_v2_renew_screen(self) -> None:
        message = FakeMessage()
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="10 дн.",
            expires_text="20.04.2026 12:00",
            balance_rub=149,
            tariff_title="1 месяц",
            devices_count=1,
            device_limit=10,
            devices=(),
            single_connection_uri="https://client.amonoraconnect.com/token",
        )

        with (
            patch.object(
                test_bot_router,
                "get_user_by_telegram_id",
                new=AsyncMock(return_value=SimpleNamespace(id=42, telegram_id=1001)),
            ),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)),
        ):
            message.text = "💳 Купить"
            await test_bot_router.v2_renew_message_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertEqual(message.answers[0]["kind"], "photo")
        self.assertIn("продлить доступ", message.answers[0]["text"].lower())

    async def test_legacy_devices_message_opens_v2_my_devices(self) -> None:
        message = FakeMessage()
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="10 дн.",
            expires_text="20.04.2026 12:00",
            balance_rub=0,
            tariff_title="1 месяц",
            devices_count=1,
            device_limit=10,
            devices=(
                {
                    "id": 77,
                    "title": "Galaxy S24",
                    "kind": "public_slot",
                    "connection_uri": "https://client.amonoraconnect.com/token",
                },
            ),
            single_connection_uri="https://client.amonoraconnect.com/token",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            message.text = "📱 Устройства"
            await test_bot_router.v2_legacy_devices_message_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("мои устройства", message.answers[0]["text"].lower())

    async def test_accept_terms_edits_message_to_trial_intro(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_ACCEPT_TERMS_CALLBACK)

        with patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=None)):
            await test_bot_router.v2_accept_terms_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertEqual(callback.message.edits[0]["kind"], "media")
        self.assertIn("бесплатный пробный период", callback.message.edits[0]["text"].lower())
        self.assertEqual(len(callback.answers), 1)

    async def test_accept_terms_redirects_returning_trial_user_to_buy_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_ACCEPT_TERMS_CALLBACK)
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            trial_used=True,
            is_blocked=False,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=datetime.utcnow() - timedelta(days=2),
        )

        with patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)):
            await test_bot_router.v2_accept_terms_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("пробный период уже был использован", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Купить подписку", "Поддержка", "Главное меню"])

    async def test_load_test_user_summary_builds_happ_url_without_blocking_route_sync(self) -> None:
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            username="tester",
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime.utcnow() + timedelta(days=5),
            trial_expires_at=None,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                test_bot_router,
                "get_or_create_public_subscription_page_url_for_user",
                new=AsyncMock(return_value="https://client.amonoraconnect.com/abcdefghijklmnop"),
            ),
            patch.object(test_bot_router, "get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch.object(test_bot_router, "get_user_balance_summary", new=AsyncMock(return_value={"balance_available_rub": 0})),
            patch.object(test_bot_router, "get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch.object(test_bot_router, "get_public_subscription_bound_devices_for_user", new=AsyncMock(return_value=())),
            patch.object(
                test_bot_router,
                "_subscription_billing_summary_for_user",
                new=AsyncMock(return_value=("Тестовый тариф", None)),
            ),
        ):
            summary = await test_bot_router._load_test_user_summary(1001)

        self.assertEqual(summary.subscription_page_url, "https://client.amonoraconnect.com/abcdefghijklmnop")
        self.assertEqual(
            summary.happ_subscription_url,
            "https://client.amonoraconnect.com/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
        )

    def test_subscription_text_shows_manual_extension_amount(self) -> None:
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="10 дн.",
            expires_text="20.04.2026 12:00",
            balance_rub=0,
            tariff_title="1 месяц",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
            manual_extension_label="1 месяц",
        )

        text = test_bot_router._subscription_text(summary)

        self.assertIn("Ручное продление", text)
        self.assertIn("на 1 месяц", text)

    def test_renew_text_shows_manual_extension_amount(self) -> None:
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="10 дн.",
            expires_text="20.04.2026 12:00",
            balance_rub=0,
            tariff_title="1 месяц",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
            manual_extension_label="30 дней",
        )

        text = test_bot_router._renew_text(summary)

        self.assertIn("Ручное продление", text)
        self.assertIn("на 30 дней", text)

    async def test_trial_back_returns_to_agreement_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_SHOW_AGREEMENT_CALLBACK)

        await test_bot_router.v2_show_agreement_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertEqual(callback.message.edits[0]["kind"], "media")
        self.assertIn("пользовательское соглашение", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Пользовательское соглашение", "Принимаю"])

    async def test_subscription_check_shows_alert_for_unsubscribed_user(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_CHECK_SUBSCRIPTION_CALLBACK)

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "is_user_subscribed", new=AsyncMock(return_value=False)),
        ):
            await test_bot_router.v2_check_subscription_callback(callback)

        self.assertEqual(callback.message.edits, [])
        self.assertEqual(len(callback.answers), 1)
        self.assertTrue(callback.answers[0]["show_alert"])
        self.assertIn("не подписаны", callback.answers[0]["text"].lower())

    async def test_subscription_check_activates_trial_screen_for_subscribed_user(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_CHECK_SUBSCRIPTION_CALLBACK)
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            username="tester",
            trial_used=False,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=None,
        )
        activated_user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            username="tester",
            trial_used=True,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=datetime.utcnow() + timedelta(days=3),
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "is_user_subscribed", new=AsyncMock(return_value=True)),
            patch.object(test_bot_router, "get_or_create_user", new=AsyncMock(return_value=(user, True))) as get_or_create_user_mock,
            patch.object(test_bot_router, "activate_trial", new=AsyncMock(return_value=activated_user)) as activate_trial_mock,
        ):
            await test_bot_router.v2_check_subscription_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("пробный доступ активирован", callback.message.edits[0]["text"].lower())
        self.assertIn("happ", callback.message.edits[0]["text"].lower())
        self.assertIn("если приложения", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Ключ", "Инструкция", "Поддержка", "Главное меню"])
        get_or_create_user_mock.assert_awaited_once()
        activate_trial_mock.assert_awaited_once_with(42)

    async def test_subscription_check_uses_main_bot_fallback(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_CHECK_SUBSCRIPTION_CALLBACK)
        callback.bot = SimpleNamespace(token="test-bot-token")
        FakeAiogramBot.instances = []
        activated_user = SimpleNamespace(id=42, telegram_id=1001, trial_used=True, trial_expires_at=datetime.utcnow() + timedelta(days=3))

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "get_or_create_user", new=AsyncMock(return_value=(SimpleNamespace(id=42, telegram_id=1001, trial_used=False), True))),
            patch.object(test_bot_router, "activate_trial", new=AsyncMock(return_value=activated_user)),
            patch.object(test_bot_router.config, "bot_token", "main-bot-token"),
            patch.object(
                test_bot_router,
                "is_user_subscribed",
                new=AsyncMock(side_effect=[False, True]),
            ),
            patch.object(test_bot_router, "Bot", FakeAiogramBot),
        ):
            await test_bot_router.v2_check_subscription_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertEqual(len(FakeAiogramBot.instances), 1)
        self.assertTrue(FakeAiogramBot.instances[0].closed)

    async def test_trial_ready_instruction_entry_shows_os_picker(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_GUIDES_CALLBACK)

        await test_bot_router.v2_guides_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("выберите вашу ос или устройство", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Android", labels)
        self.assertIn("Windows", labels)
        self.assertIn("Apple TV", labels)
        self.assertIn("Android TV", labels)
        self.assertIn("Назад", labels)

    async def test_trial_ready_instruction_device_opens_platform_guide(self) -> None:
        callback = FakeCallback(FakeMessage(), f"{test_bot_router.V2_GUIDE_PREFIX}windows")

        await test_bot_router.v2_guide_instruction_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("инструкция для windows", callback.message.edits[0]["text"].lower())
        self.assertIn("ссылки для установки", callback.message.edits[0]["text"].lower())
        self.assertIn("setup-happ.x64.exe", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Главное меню", "Назад"])

    async def test_menu_command_shows_live_main_menu(self) -> None:
        message = FakeMessage()
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=75,
            tariff_title="Пробный период",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_menu_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertEqual(message.answers[0]["kind"], "photo")
        self.assertIn("статус", message.answers[0]["text"].lower())
        self.assertIn("✅", message.answers[0]["text"])
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Моя подписка", "Ключ", "Продлить", "Информация", "Поддержка", "Бонусная система"])

    async def test_my_subscription_screen_shows_live_fields(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_MY_SUBSCRIPTION_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(
                {
                    "id": 42,
                    "title": "Pixel",
                    "country_name": "Германия",
                    "protocol": "VLESS",
                    "connection_uri": "vless://example",
                },
            ),
            single_connection_uri="vless://example",
            subscription_page_url="https://client.amonoraconnect.com/abcdefghijklmnop",
            happ_subscription_url="https://client.amonoraconnect.com/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_my_subscription_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("тариф", callback.message.edits[0]["text"].lower())
        self.assertIn("happ", callback.message.edits[0]["text"].lower())
        self.assertIn("/happ/add?sub=", callback.message.edits[0]["text"])
        buttons = [button for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        labels = [button.text for button in buttons]
        self.assertIn("Ключ", labels)
        self.assertIn("Мои устройства", labels)
        self.assertIn("Назад", labels)
        key_button = next(button for button in buttons if button.text == "Ключ")
        self.assertEqual(key_button.callback_data, test_bot_router.V2_KEY_MENU_CALLBACK)

    async def test_renew_screen_shows_tariffs(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_RENEW_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="30 дн.",
            expires_text="10.05.2026 12:00",
            balance_rub=250,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with (
            patch.object(
                test_bot_router,
                "get_user_by_telegram_id",
                new=AsyncMock(return_value=SimpleNamespace(id=42, telegram_id=1001)),
            ),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)),
        ):
            await test_bot_router.v2_renew_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("продлить доступ", callback.message.edits[0]["text"].lower())
        self.assertIn("текущий тариф", callback.message.edits[0]["text"].lower())
        self.assertIn("баланс", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("⚡️ 1 месяц — 149 ₽", labels)
        self.assertIn("🔥 3 месяца — 399 ₽ (-10%)", labels)
        self.assertIn("👑 6 месяцев — 749 ₽ (-15%)", labels)
        self.assertIn("💫 12 месяцев — 1390 ₽ (-20%)", labels)
        self.assertIn("⭐️ Пополнить баланс", labels)
        self.assertIn("Назад", labels)
        self.assertNotIn("⭐️ Telegram Stars", callback.message.edits[0]["text"])

    async def test_renew_screen_uses_internal_user_id_for_pending_discount_lookup(self) -> None:
        telegram_id = 7_650_618_403
        callback = FakeCallback(FakeMessage(telegram_id=telegram_id), test_bot_router.V2_RENEW_CALLBACK, telegram_id=telegram_id)
        summary = test_bot_router.TestUserSummary(
            telegram_id=telegram_id,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="30 дн.",
            expires_text="10.05.2026 12:00",
            balance_rub=250,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with (
            patch.object(
                test_bot_router,
                "get_user_by_telegram_id",
                new=AsyncMock(return_value=SimpleNamespace(id=42, telegram_id=telegram_id)),
            ),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)) as discount_mock,
        ):
            await test_bot_router.v2_renew_callback(callback)

        discount_mock.assert_awaited_once_with(42)

    async def test_support_screen_shows_help_text_and_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_SUPPORT_CALLBACK)

        await test_bot_router.v2_support_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("поддержка amonora", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Открыть поддержку", "Назад"])

    async def test_info_screen_shows_sections_and_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_INFO_CALLBACK)

        await test_bot_router.v2_info_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("информация", callback.message.edits[0]["text"].lower())
        self.assertIn("документы", callback.message.edits[0]["text"].lower())
        keyboard = callback.message.edits[0]["reply_markup"].inline_keyboard
        labels = [button.text for row in keyboard for button in row]
        self.assertEqual(labels, ["Инструкции", "Документы", "Канал", "Назад"])
        self.assertEqual(keyboard[0][0].callback_data, test_bot_router.V2_INFO_GUIDES_CALLBACK)

    async def test_info_guides_callback_shows_os_picker_with_info_back(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_INFO_GUIDES_CALLBACK)

        await test_bot_router.v2_info_guides_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        keyboard = callback.message.edits[0]["reply_markup"].inline_keyboard
        labels = [button.text for row in keyboard for button in row]
        self.assertIn("Apple TV", labels)
        self.assertIn("Android TV", labels)
        self.assertEqual(keyboard[-1][0].callback_data, test_bot_router.V2_INFO_CALLBACK)

    async def test_info_documents_screen_shows_document_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_INFO_DOCS_CALLBACK)

        await test_bot_router.v2_info_docs_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("юридическая информация", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Пользовательское соглашение", "Политика конфиденциальности", "Политика возврата", "Назад"])

    async def test_bonus_screen_shows_live_referral_link_and_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_BONUS_CALLBACK)
        bonus_summary = test_bot_router.TestBonusSummary(
            referral_link="https://t.me/amonora_bot?start=ref_test123",
            invited_count=2,
            paid_count=1,
            earned_total_rub=50,
            balance_available_rub=50,
        )

        with patch.object(test_bot_router, "_load_bonus_summary", new=AsyncMock(return_value=bonus_summary)):
            await test_bot_router.v2_bonus_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("зарабатывай бонусы", callback.message.edits[0]["text"].lower())
        self.assertIn("ref_test123", callback.message.edits[0]["text"])
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Моя статистика", "Пригласить друга", "Ввести промокод", "Подарить подписку", "Назад"])

    async def test_bonus_stats_screen_shows_live_stats(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_BONUS_STATS_CALLBACK)
        bonus_summary = test_bot_router.TestBonusSummary(
            referral_link="https://t.me/amonora_bot?start=ref_test123",
            invited_count=4,
            paid_count=2,
            earned_total_rub=100,
            balance_available_rub=75,
        )

        with patch.object(test_bot_router, "_load_bonus_summary", new=AsyncMock(return_value=bonus_summary)):
            await test_bot_router.v2_bonus_stats_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("моя статистика", callback.message.edits[0]["text"].lower())
        self.assertIn("100 ₽", callback.message.edits[0]["text"])

    async def test_bonus_promo_screen_shows_new_copy_and_back(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_BONUS_PROMO_CALLBACK)

        await test_bot_router.v2_bonus_promo_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("есть промокод или подарок", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Назад"])

    async def test_bonus_gift_screen_shows_tariff_button(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_BONUS_GIFT_CALLBACK)

        await test_bot_router.v2_bonus_gift_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("подарить подписку другу", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Тариф", "Назад"])

    async def test_bonus_gift_tariffs_screen_shows_gift_tariffs(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_BONUS_GIFT_TARIFFS_CALLBACK)

        await test_bot_router.v2_bonus_gift_tariffs_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("подарочный тариф", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(
            labels,
            ["⚡️ 1 месяц — 149 ₽", "🔥 3 месяца — 399 ₽", "👑 6 месяцев — 749 ₽", "💫 12 месяцев — 1390 ₽", "Назад"],
        )

    async def test_bonus_gift_tariff_choice_opens_gift_payment_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:bonus:gift:tariff:3m")

        await test_bot_router.v2_bonus_gift_tariff_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("подарочная подписка", callback.message.edits[0]["text"].lower())
        self.assertIn("3 месяца", callback.message.edits[0]["text"])
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Оплатить подарок", "Назад"])

    async def test_bonus_gift_pay_opens_payment_methods_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:bonus:gift:pay:1m")

        await test_bot_router.v2_bonus_gift_pay_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("выберите удобный способ оплаты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["СБП", "СБП(ручная)", "Криптовалюта", "Назад"])

    async def test_bonus_gift_payment_method_creates_platega_invoice(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:bonus:gift:method:sbp:3m")
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime.utcnow() + timedelta(days=30),
        )
        record = SimpleNamespace(
            id=109,
            amount=399,
            payment_method="sbp_platega",
            list_price_amount=399,
            balance_reserved_amount=0,
            metadata_json='{"checkout_url":"https://pay.example/gift"}',
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                test_bot_router,
                "build_balance_breakdown_for_price",
                new=AsyncMock(return_value={"list_price_amount": 399, "balance_amount": 0, "payable_amount": 399}),
            ),
            patch.object(test_bot_router, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "ensure_platega_payment_record", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router, "PlategaClient", return_value=SimpleNamespace(configured=True)),
            patch.object(test_bot_router.config, "enable_platega_sbp_user_flow", True),
        ):
            await test_bot_router.v2_bonus_gift_payment_method_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("страница оплаты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Оплатить", labels)
        self.assertIn("Проверить оплату", labels)

    async def test_bonus_promo_message_handler_applies_discount_code(self) -> None:
        message = FakeMessage()
        message.text = "amonora-sale"
        user = SimpleNamespace(id=42, telegram_id=1001)
        test_bot_router.PROMO_INPUT_WAITERS.add(1001)

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                test_bot_router,
                "redeem_promo_code_for_user",
                new=AsyncMock(return_value={"ok": True, "kind": "discount_percent", "discount_percent": 25}),
            ),
        ):
            await test_bot_router.v2_bonus_promo_message_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("скидка <b>25%</b>", message.answers[0]["text"].lower())
        self.assertNotIn(1001, test_bot_router.PROMO_INPUT_WAITERS)

    async def test_key_menu_screen_explains_connect_and_copy_flows(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_KEY_MENU_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
            subscription_page_url="https://client.amonoraconnect.com/abcdefghijklmnop",
            happ_subscription_url="https://client.amonoraconnect.com/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_key_menu_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("ключ доступа", callback.message.edits[0]["text"].lower())
        self.assertIn("откроет сайт amonora", callback.message.edits[0]["text"].lower())
        self.assertIn("сразу вставить в happ", callback.message.edits[0]["text"].lower())
        buttons = [button for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        labels = [button.text for button in buttons]
        self.assertEqual(labels, ["Подключить", "Скопировать ключ", "Назад"])
        connect_button = next(button for button in buttons if button.text == "Подключить")
        self.assertEqual(connect_button.url, summary.happ_subscription_url)

    async def test_copy_key_screen_shows_general_key_text_and_back(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_COPY_KEY_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(
                {
                    "id": 42,
                    "title": "Pixel",
                    "country_name": "Германия",
                    "protocol": "VLESS",
                    "connection_uri": "vless://example",
                    "device_type": "android",
                    "device_model": "Pixel",
                    "os_version": "14",
                },
            ),
            single_connection_uri="vless://example",
            subscription_page_url="https://client.amonoraconnect.com/abcdefghijklmnop",
            happ_subscription_url="https://client.amonoraconnect.com/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_copy_key_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("ваш ключ доступа", callback.message.edits[0]["text"].lower())
        self.assertIn("https://client.amonoraconnect.com/abcdefghijklmnop", callback.message.edits[0]["text"])
        self.assertIn("вставить из буфера обмена", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Назад"])

    async def test_copy_key_screen_allows_public_subscription_link_without_devices(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_COPY_KEY_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=0,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
            subscription_page_url="https://client.amonoraconnect.com/abcdefghijklmnop",
            happ_subscription_url="https://client.amonoraconnect.com/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_copy_key_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("client.amonoraconnect.com/abcdefghijklmnop", callback.message.edits[0]["text"])

    async def test_my_devices_screen_shows_count_and_slot_button(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_MY_DEVICES_CALLBACK)
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=2,
            device_limit=3,
            devices=(
                {
                    "id": 42,
                    "title": "Pixel",
                    "country_name": "Германия",
                    "protocol": "VLESS",
                    "connection_uri": "vless://one",
                    "device_type": "android",
                    "device_model": "Pixel 8",
                    "os_version": "14",
                },
                {
                    "id": 43,
                    "title": "Note_20",
                    "country_name": "Дания",
                    "protocol": "TROJAN",
                    "connection_uri": "trojan://two",
                    "device_type": "android",
                    "device_model": "Galaxy Note 20",
                    "os_version": "13",
                },
            ),
            single_connection_uri=None,
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_my_devices_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("сейчас подключено", callback.message.edits[0]["text"].lower())
        self.assertIn("2 из 3", callback.message.edits[0]["text"])
        self.assertIn("выбери нужное устройство", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Pixel", "Note_20", "Купить дополнительный слот", "Назад"])

    async def test_device_detail_screen_shows_model_os_and_delete_button(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:mydevices:view:42")
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(
                {
                    "id": 42,
                    "title": "Pixel",
                    "country_name": "Германия",
                    "protocol": "VLESS",
                    "connection_uri": "vless://one",
                    "device_type": "android",
                    "device_model": "Pixel 8",
                    "os_version": "14",
                },
            ),
            single_connection_uri="vless://one",
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_my_device_detail_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        text = callback.message.edits[0]["text"]
        self.assertIn("информация об устройстве", text.lower())
        self.assertIn("Pixel 8", text)
        self.assertIn("Android", text)
        self.assertIn("14", text)
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Удалить устройство", "Назад"])

    async def test_device_delete_callback_refreshes_devices_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:mydevices:delete:42")
        user = SimpleNamespace(id=501)
        vpn_client = SimpleNamespace(
            id=42,
            user_id=501,
            protocol="vless",
            xui_client_id="uuid-1",
            client_uuid="uuid-1",
            email="device_501_1",
            client_data='{"country_code":"de","provider_type":"xui"}',
        )
        refreshed_summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=0,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )
        fake_provisioner = SimpleNamespace(
            delete_vless_client=AsyncMock(return_value={"success": True}),
            close=AsyncMock(),
        )

        with (
            patch.object(test_bot_router, "_get_owned_test_device_for_telegram", new=AsyncMock(return_value=(user, vpn_client))),
            patch.object(test_bot_router, "get_vless_provisioner", return_value=fake_provisioner),
            patch.object(test_bot_router, "delete_vpn_client_and_return", new=AsyncMock(return_value=vpn_client)),
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=refreshed_summary)),
        ):
            await test_bot_router.v2_my_device_delete_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("мои устройства", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Купить дополнительный слот", "Назад"])

    async def test_public_slot_delete_callback_refreshes_devices_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:mydevices:delete:public:2")
        user = SimpleNamespace(id=501)
        refreshed_summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=0,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                test_bot_router,
                "clear_public_subscription_device_slot_binding",
                new=AsyncMock(return_value=True),
            ) as clear_mock,
            patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=refreshed_summary)),
        ):
            await test_bot_router.v2_my_device_delete_callback(callback)

        clear_mock.assert_awaited_once()
        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("мои устройства", callback.message.edits[0]["text"].lower())

    async def test_device_slot_screen_shows_payment_methods(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_DEVICE_SLOT_CALLBACK)

        await test_bot_router.v2_device_slot_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("полная стоимость", callback.message.edits[0]["text"].lower())
        self.assertIn("сбп", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["СБП", "СБП(ручная)", "Криптовалюта", "Назад"])

    async def test_renew_tariff_choice_opens_payment_methods_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:renew:tariff:3m")

        with (
            patch.object(
                test_bot_router,
                "get_user_by_telegram_id",
                new=AsyncMock(return_value=SimpleNamespace(id=42, telegram_id=1001)),
            ),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)),
        ):
            await test_bot_router.v2_renew_methods_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("3 месяца", callback.message.edits[0]["text"])
        self.assertIn("полная стоимость", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["СБП", "СБП(ручная)", "Криптовалюта", "Назад"])

    async def test_balance_topup_screen_shows_amounts(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:renew:tariff:balance")
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_renew_methods_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("добавьте средства на баланс", callback.message.edits[0]["text"].lower())
        self.assertIn("150 ₽", callback.message.edits[0]["text"])
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["100 р", "300 р", "500 р", "1000 р", "Назад"])

    async def test_balance_amount_choice_opens_payment_methods_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:balance:amount:500")
        summary = test_bot_router.TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="3 дн.",
            expires_text="10.04.2026 12:00",
            balance_rub=150,
            tariff_title="3 месяца",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri=None,
        )

        with patch.object(test_bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)):
            await test_bot_router.v2_balance_topup_amount_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("текущий баланс", callback.message.edits[0]["text"].lower())
        self.assertIn("500 ₽", callback.message.edits[0]["text"])
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["СБП", "СБП(ручная)", "Криптовалюта", "Назад"])

    async def test_renew_payment_method_creates_platega_invoice(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:renew:sbp:1m")
        user = SimpleNamespace(id=42, telegram_id=1001)
        record = SimpleNamespace(
            id=77,
            amount=149,
            payment_method="sbp_platega",
            list_price_amount=149,
            balance_reserved_amount=0,
            metadata_json='{"checkout_url":"https://pay.example/renew"}',
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)),
            patch.object(
                test_bot_router,
                "build_balance_breakdown_for_price",
                new=AsyncMock(return_value={"list_price_amount": 149, "balance_amount": 0, "payable_amount": 149}),
            ),
            patch.object(test_bot_router, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "ensure_platega_payment_record", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router, "PlategaClient", return_value=SimpleNamespace(configured=True)),
            patch.object(test_bot_router.config, "enable_platega_sbp_user_flow", True),
        ):
            await test_bot_router.v2_renew_payment_method_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("страница оплаты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Оплатить", labels)
        self.assertIn("Проверить оплату", labels)

    async def test_renew_payment_method_handles_sbp_manual_callback(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:renew:sbp_manual:1m")
        user = SimpleNamespace(id=42, telegram_id=1001)
        record = SimpleNamespace(
            id=87,
            amount=149,
            payment_method="sbp_manual",
            list_price_amount=149,
            balance_reserved_amount=0,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_load_pending_discount_payload", new=AsyncMock(return_value=None)),
            patch.object(
                test_bot_router,
                "build_balance_breakdown_for_price",
                new=AsyncMock(return_value={"list_price_amount": 149, "balance_amount": 0, "payable_amount": 149}),
            ),
            patch.object(test_bot_router, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "create_balance_aware_manual_payment_record", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router.config, "enable_manual_sbp_user_flow", True),
            patch.object(test_bot_router.config, "manual_sbp_details", "СБП: тестовые реквизиты"),
        ):
            await test_bot_router.v2_renew_payment_method_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("реквизиты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Я оплатил(а)", labels)
        self.assertIn("Проверить статус", labels)

    async def test_renew_payment_method_tolerates_legacy_tariff_suffix_with_colon(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:renew:sbp:legacy:1m")

        with patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=SimpleNamespace(id=42, telegram_id=1001))):
            await test_bot_router.v2_renew_payment_method_callback(callback)

        self.assertEqual(callback.answers[-1]["text"], "Тариф не найден.")
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_balance_manual_payment_creates_review_request(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:balance:sbp_manual:500")
        user = SimpleNamespace(id=42, telegram_id=1001)
        record = SimpleNamespace(
            id=91,
            amount=500,
            payment_method="sbp_manual",
            list_price_amount=500,
            balance_reserved_amount=0,
        )

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_find_open_balance_topup_intent", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "create_balance_aware_manual_payment_record", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router.config, "enable_manual_sbp_user_flow", True),
            patch.object(test_bot_router.config, "manual_sbp_details", "СБП: тестовые реквизиты"),
        ):
            await test_bot_router.v2_balance_payment_method_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("реквизиты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Я оплатил(а)", labels)
        self.assertIn("Проверить статус", labels)

    async def test_renew_external_check_handles_platega_sync_error(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:renew:external:check:77:1m")
        user = SimpleNamespace(id=42, telegram_id=1001)
        record = SimpleNamespace(id=77, user_id=42)

        with (
            patch.object(test_bot_router, "get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "sync_platega_record_by_id", new=AsyncMock(side_effect=test_bot_router.PlategaError("boom"))),
        ):
            await test_bot_router.v2_renew_external_check_callback(callback)

        self.assertEqual(callback.answers[-1]["text"], "Не удалось проверить оплату")
        self.assertTrue(callback.answers[-1]["show_alert"])

    async def test_device_slot_payment_method_creates_platega_invoice(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:pay:slot:sbp")
        user = SimpleNamespace(
            id=42,
            telegram_id=1001,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime.utcnow() + timedelta(days=30),
        )
        record = SimpleNamespace(
            id=99,
            amount=49,
            payment_method="sbp_platega",
            list_price_amount=49,
            balance_reserved_amount=0,
            metadata_json='{"checkout_url":"https://pay.example/slot"}',
        )
        context = {
            "eligible": True,
            "remaining_capacity": 2,
            "price_rub": 49,
            "duration_days": 29,
            "expires_at": datetime.utcnow() + timedelta(days=29),
            "expires_text": "2026-05-09 12:00:00",
            "current_limit": 3,
            "next_limit": 4,
        }

        with (
            patch.object(test_bot_router, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(test_bot_router, "_device_slot_context_for_user", new=AsyncMock(return_value=context)),
            patch.object(
                test_bot_router,
                "build_balance_breakdown_for_price",
                new=AsyncMock(return_value={"list_price_amount": 49, "balance_amount": 0, "payable_amount": 49}),
            ),
            patch.object(test_bot_router, "get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch.object(test_bot_router, "ensure_platega_payment_record", new=AsyncMock(return_value=record)),
            patch.object(test_bot_router, "PlategaClient", return_value=SimpleNamespace(configured=True)),
            patch.object(test_bot_router.config, "enable_platega_sbp_user_flow", True),
        ):
            await test_bot_router.v2_device_slot_payment_method_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("страница оплаты", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Оплатить", labels)
        self.assertIn("Проверить оплату", labels)

    def test_screen_asset_mapping_uses_subscription_and_info_images(self) -> None:
        self.assertEqual(test_bot_router.SCREEN_IMAGE_FILENAMES["key"], "sakura_my_subscription.jpg")
        self.assertEqual(test_bot_router.SCREEN_IMAGE_FILENAMES["documents"], "sakura_info.png")
        self.assertEqual(test_bot_router.SCREEN_IMAGE_FILENAMES["my_devices"], "sakura_my_subscription.jpg")
        self.assertEqual(test_bot_router.SCREEN_IMAGE_FILENAMES["info"], "sakura_info.png")

    async def test_android_device_screen_contains_download_and_install_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:device:android")

        await test_bot_router.v2_device_instruction_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("инструкция для android", callback.message.edits[0]["text"].lower())
        self.assertIn("ссылки для установки", callback.message.edits[0]["text"].lower())
        self.assertIn("play.google.com", callback.message.edits[0]["text"].lower())
        self.assertIn("happ.apk", callback.message.edits[0]["text"].lower())
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(labels, ["Главное меню", "Назад"])

    async def test_devices_screen_does_not_show_main_menu_button(self) -> None:
        callback = FakeCallback(FakeMessage(), test_bot_router.V2_DEVICES_CALLBACK)

        await test_bot_router.v2_devices_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertNotIn("Главное меню", labels)

    def test_device_detail_falls_back_to_os_name_when_version_missing(self) -> None:
        text = test_bot_router._device_detail_text(
            {
                "device_type": "windows",
                "device_model": "Windows PC",
                "os_version": "",
                "os_name": "Windows",
            }
        )

        self.assertIn("Версия ОС: <b>Windows</b>", text)

    def test_device_display_row_normalizes_known_windows_and_android_os_versions(self) -> None:
        windows_row = test_bot_router._device_display_row(
            SimpleNamespace(id=1, email="device_1", protocol="vless"),
            {
                "device_type": "windows",
                "device_model": "Windows PC",
                "os_version": "2603201341504",
                "protocol": "vless",
            },
        )
        android_row = test_bot_router._device_display_row(
            SimpleNamespace(id=2, email="device_2", protocol="vless"),
            {
                "device_type": "android",
                "device_model": "Galaxy",
                "os_version": "1743595",
                "protocol": "vless",
            },
        )

        self.assertEqual(windows_row["os_version"], "11_10.0.26200")
        self.assertEqual(android_row["os_version"], "15")

    async def test_installed_screen_hides_back_and_main_menu_buttons(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:installed:android")

        await test_bot_router.v2_installed_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        labels = [button.text for row in callback.message.edits[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Подключиться", labels)
        self.assertIn("Поддержка", labels)
        self.assertIn("Инструкция", labels)
        self.assertNotIn("Главное меню", labels)
        self.assertNotIn("Назад", labels)

    async def test_connect_placeholder_screen_is_shown_after_install(self) -> None:
        callback = FakeCallback(FakeMessage(), "testv2:connect:android")

        await test_bot_router.v2_connect_placeholder_callback(callback)

        self.assertEqual(len(callback.message.edits), 1)
        self.assertIn("используйте сценарий через", callback.message.edits[0]["text"].lower())
        self.assertIn("моя подписка", callback.message.edits[0]["text"].lower())

    async def test_legacy_profiles_stay_admin_only(self) -> None:
        message = FakeMessage()

        with patch.object(test_bot_router, "is_test_bot_allowed", return_value=False):
            await test_bot_router.legacy_profiles_handler(message)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("доступ ограничен", message.answers[0]["text"].lower())


if __name__ == "__main__":
    unittest.main()
