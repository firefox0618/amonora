import os
import unittest

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

from bot.handlers import start as start_handler_module


class FakeMessage:
    def __init__(self, telegram_id: int = 1010, first_name: str = "Иван") -> None:
        self.from_user = SimpleNamespace(id=telegram_id, username="ivan", first_name=first_name)
        self.answers: list[dict] = []

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


class FakeCallback:
    def __init__(
        self,
        message: FakeMessage,
        *,
        telegram_id: int = 1010,
        username: str = "ivan",
        first_name: str = "Иван",
        bot: object | None = None,
    ) -> None:
        self.message = message
        self.from_user = SimpleNamespace(id=telegram_id, username=username, first_name=first_name)
        self.bot = bot if bot is not None else object()
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **kwargs):
        self.answers.append(
            {
                "text": text,
                "show_alert": show_alert,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace()


class BotStartTrialTests(unittest.IsolatedAsyncioTestCase):
    async def test_campaign_open_devices_cta_opens_devices_screen(self) -> None:
        callback = FakeCallback(FakeMessage(), telegram_id=2020, username="petr", first_name="Пётр")
        callback.data = "campaign:cta:77:open_devices"

        with (
            patch.object(start_handler_module, "mark_delivery_clicked", new=AsyncMock()) as clicked_mock,
            patch.object(start_handler_module, "home_devices_callback", new=AsyncMock()) as devices_mock,
        ):
            await start_handler_module.campaign_cta_callback(callback)

        clicked_mock.assert_awaited_once_with(77)
        devices_mock.assert_awaited_once_with(callback)

    async def test_first_start_requires_channel_subscription_and_shows_confirm_button(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            username="ivan",
            trial_used=False,
        )

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(user, True))),
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "has_active_access_from_user", return_value=False),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=False)),
            patch.object(start_handler_module, "activate_trial", new=AsyncMock()) as activate_trial_mock,
        ):
            await start_handler_module.start_handler(message, bot=object(), command=None)

        activate_trial_mock.assert_not_awaited()
        self.assertEqual(len(message.answers), 1)
        self.assertIn("1. подпишись на канал", message.answers[0]["text"].lower())
        labels = [button.text for row in message.answers[0]["reply_markup"].inline_keyboard for button in row]
        self.assertIn("📡 Подписаться на канал", labels)
        self.assertIn("✅ Подписался", labels)
        self.assertIn("📜 Пользовательское соглашение", labels)

    async def test_first_start_activates_trial_when_user_is_already_subscribed(self) -> None:
        message = FakeMessage()
        created_user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            username="ivan",
            trial_used=False,
        )
        activated_user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            username="ivan",
            trial_expires_at=SimpleNamespace(strftime=lambda fmt: "2026-03-30 12:00:00"),
        )

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(created_user, True))),
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "has_active_access_from_user", return_value=False),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=True)),
            patch.object(start_handler_module, "activate_trial", new=AsyncMock(return_value=activated_user)) as activate_trial_mock,
            patch.object(start_handler_module, "_send_home", new=AsyncMock()) as send_home_mock,
        ):
            await start_handler_module.start_handler(message, bot=object(), command=None)

        activate_trial_mock.assert_awaited_once_with(77)
        send_home_mock.assert_awaited_once_with(message, 1010)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("пробный доступ активирован", message.answers[0]["text"].lower())

    async def test_subscription_confirmation_button_activates_trial_without_restart(self) -> None:
        callback_message = FakeMessage(telegram_id=9999, first_name="Bot")
        callback = FakeCallback(
            callback_message,
            telegram_id=2020,
            username="petr",
            first_name="Пётр",
        )
        user = SimpleNamespace(
            id=88,
            telegram_id=2020,
            username="petr",
            trial_used=False,
        )
        activated_user = SimpleNamespace(
            id=88,
            telegram_id=2020,
            username="petr",
            trial_expires_at=SimpleNamespace(strftime=lambda fmt: "2026-03-30 12:00:00"),
        )

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(user, False))) as get_or_create_mock,
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "has_active_access_from_user", return_value=False),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=True)),
            patch.object(start_handler_module, "activate_trial", new=AsyncMock(return_value=activated_user)) as activate_trial_mock,
            patch.object(start_handler_module, "_send_home", new=AsyncMock()) as send_home_mock,
        ):
            await start_handler_module.start_trial_subscription_confirmed_callback(callback)

        get_or_create_mock.assert_awaited_once_with(
            telegram_id=2020,
            username="petr",
            referred_by_telegram_id=None,
            skip_initial_analytics_attribution=False,
        )
        activate_trial_mock.assert_awaited_once_with(88)
        send_home_mock.assert_awaited_once_with(callback_message, 2020)
        self.assertEqual(len(callback.answers), 1)
        self.assertFalse(callback.answers[0]["show_alert"])
        self.assertEqual(len(callback_message.answers), 1)
        self.assertIn("пробный доступ активирован", callback_message.answers[0]["text"].lower())

    async def test_subscription_confirmation_button_warns_when_user_still_not_subscribed(self) -> None:
        callback = FakeCallback(FakeMessage(), telegram_id=2020, username="petr", first_name="Пётр")

        with (
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=False)),
            patch.object(start_handler_module, "activate_trial", new=AsyncMock()) as activate_trial_mock,
        ):
            await start_handler_module.start_trial_subscription_confirmed_callback(callback)

        activate_trial_mock.assert_not_awaited()
        self.assertEqual(len(callback.answers), 1)
        self.assertTrue(callback.answers[0]["show_alert"])
        self.assertIn("пока не вижу подписку", callback.answers[0]["text"].lower())
        self.assertEqual(callback.message.answers, [])

    async def test_paused_trial_without_subscription_shows_pause_message(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=90,
            telegram_id=1010,
            username="ivan",
            trial_used=True,
            trial_expires_at=SimpleNamespace(strftime=lambda fmt: "2026-04-05 12:00:00"),
            trial_channel_unsubscribed_at=object(),
        )

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(user, False))),
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "trial_is_paused_by_channel_from_user", return_value=True),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=False)),
        ):
            await start_handler_module.start_handler(message, bot=object(), command=None)

        self.assertEqual(len(message.answers), 1)
        self.assertIn("пробный доступ приостановлен", message.answers[0]["text"].lower())

    async def test_paused_trial_with_subscription_resumes_existing_trial(self) -> None:
        message = FakeMessage()
        paused_user = SimpleNamespace(
            id=91,
            telegram_id=1010,
            username="ivan",
            trial_used=True,
            trial_expires_at=SimpleNamespace(strftime=lambda fmt: "2026-04-05 12:00:00"),
            trial_channel_unsubscribed_at=object(),
        )
        resumed_user = SimpleNamespace(
            id=91,
            telegram_id=1010,
            username="ivan",
            trial_used=True,
            trial_expires_at=SimpleNamespace(strftime=lambda fmt: "2026-04-05 12:00:00"),
            trial_channel_unsubscribed_at=None,
        )
        access_expires_at = SimpleNamespace(strftime=lambda fmt: "2026-04-05 12:00:00")

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(paused_user, False))),
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "trial_is_paused_by_channel_from_user", side_effect=[True, False]),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=True)),
            patch.object(start_handler_module, "resume_trial_after_channel_resubscribe", new=AsyncMock(return_value=resumed_user)) as resume_mock,
            patch.object(start_handler_module, "get_access_expires_at_from_user", return_value=access_expires_at),
            patch.object(start_handler_module, "sync_user_vpn_access_with_single_retry", new=AsyncMock(return_value={"sync_failed": False})) as sync_mock,
            patch.object(start_handler_module, "has_active_access_from_user", return_value=True),
            patch.object(start_handler_module, "_send_home", new=AsyncMock()) as send_home_mock,
        ):
            await start_handler_module.start_handler(message, bot=object(), command=None)

        resume_mock.assert_awaited_once_with(91)
        sync_mock.assert_awaited_once_with(91, access_expires_at)
        send_home_mock.assert_awaited_once_with(message, 1010)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("активный доступ", message.answers[0]["text"].lower())

    async def test_start_with_channel_post_token_registers_touch_without_breaking_trial_flow(self) -> None:
        message = FakeMessage()
        user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            username="ivan",
            trial_used=False,
        )
        command = SimpleNamespace(args="post_channelabc")

        with (
            patch.object(start_handler_module, "get_or_create_user", new=AsyncMock(return_value=(user, True))) as get_or_create_mock,
            patch.object(
                start_handler_module,
                "bind_referrer_by_token",
                new=AsyncMock(return_value={"bound": False, "referrer_telegram_id": None}),
            ),
            patch.object(start_handler_module, "register_channel_post_touch", new=AsyncMock()) as touch_mock,
            patch.object(start_handler_module, "has_active_access_from_user", return_value=False),
            patch.object(start_handler_module, "is_user_subscribed", new=AsyncMock(return_value=False)),
            patch.object(start_handler_module, "activate_trial", new=AsyncMock()) as activate_trial_mock,
        ):
            await start_handler_module.start_handler(message, bot=object(), command=command)

        get_or_create_mock.assert_awaited_once_with(
            telegram_id=1010,
            username="ivan",
            referred_by_telegram_id=None,
            skip_initial_analytics_attribution=True,
        )
        touch_mock.assert_awaited_once_with(
            "channelabc",
            user_id=77,
            telegram_id=1010,
        )
        activate_trial_mock.assert_not_awaited()
        self.assertEqual(len(message.answers), 1)
        self.assertIn("1. подпишись на канал", message.answers[0]["text"].lower())


if __name__ == "__main__":
    unittest.main()
