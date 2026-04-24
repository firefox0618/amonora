import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest


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

from bot import router as bot_router
from bot.services.user.models import TestBonusSummary
from bot.ui.keyboards.inline.user import _my_devices_keyboard
from bot.ui.screens.user import SCREEN_IMAGE_FILENAMES, _bonus_text, _screen_photo
from bot.user_flow.constants import V2_KEY_MENU_CALLBACK


class FakeEditableMessage:
    def __init__(self) -> None:
        self.edit_media = AsyncMock()
        self.edit_caption = AsyncMock()
        self.edit_text = AsyncMock()
        self.edit_reply_markup = AsyncMock()
        self.answer = AsyncMock()
        self.answer_photo = AsyncMock()


class FakeCallback:
    def __init__(self, telegram_id: int = 42, data: str | None = None, message: FakeEditableMessage | None = None) -> None:
        self.from_user = SimpleNamespace(id=telegram_id)
        self.data = data
        self.message = message or FakeEditableMessage()
        self.answer = AsyncMock()


class BotMainRuntimeCopyTests(TestCase):
    def test_bonus_copy_is_single_updated_phrase(self) -> None:
        summary = TestBonusSummary(
            referral_link="https://t.me/example",
            invited_count=3,
            paid_count=2,
            earned_total_rub=100,
            balance_available_rub=50,
        )

        text = _bonus_text(summary)

        self.assertIn("50 ₽ тебе за каждого приглашённого друга", text)
        self.assertNotIn("100 ₽", text)

    def test_my_devices_keyboard_can_return_to_key_menu(self) -> None:
        summary = SimpleNamespace(devices=())

        keyboard = _my_devices_keyboard(summary, back_callback=V2_KEY_MENU_CALLBACK)

        self.assertEqual(keyboard.inline_keyboard[-1][0].text, "Назад")
        self.assertEqual(keyboard.inline_keyboard[-1][0].callback_data, V2_KEY_MENU_CALLBACK)

    def test_screen_photo_falls_back_to_main_menu_asset_when_file_is_missing(self) -> None:
        with patch.dict(SCREEN_IMAGE_FILENAMES, {"info": "missing.png"}):
            photo = _screen_photo("info")

        self.assertTrue(str(photo.path).endswith("sakura_main_menu.jpg"))


class BotMainRuntimeHandlerTests(IsolatedAsyncioTestCase):
    async def test_ensure_home_reply_keyboard_sends_persistent_button(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())

        await bot_router._ensure_home_reply_keyboard(message)

        message.answer.assert_awaited_once()
        _, kwargs = message.answer.await_args
        self.assertEqual(kwargs["reply_markup"].keyboard[0][0].text, "Главный экран")

    async def test_reply_menu_text_routes_to_main_menu_screen(self) -> None:
        message = SimpleNamespace(from_user=SimpleNamespace(id=77))

        with (
            patch.object(bot_router, "_ensure_home_reply_keyboard", new=AsyncMock()) as ensure_keyboard,
            patch.object(bot_router, "_show_returning_user_screen", new=AsyncMock(return_value=True)) as show_screen,
        ):
            await bot_router.v2_reply_menu_handler(message)

        ensure_keyboard.assert_awaited_once_with(message)
        show_screen.assert_awaited_once_with(message, 77)

    async def test_my_devices_callback_uses_key_menu_as_back_destination(self) -> None:
        callback = FakeCallback(data=bot_router.V2_MY_DEVICES_CALLBACK)
        summary = SimpleNamespace()

        with (
            patch.object(bot_router, "_ack_callback_quietly", new=AsyncMock()),
            patch.object(bot_router, "_load_test_user_summary", new=AsyncMock(return_value=summary)),
            patch.object(bot_router, "_devices_page_text", return_value="devices"),
            patch.object(bot_router, "_my_devices_keyboard", return_value="keyboard") as devices_keyboard,
            patch.object(bot_router, "_edit_screen", new=AsyncMock()) as edit_screen,
        ):
            await bot_router.v2_my_devices_callback(callback)

        devices_keyboard.assert_called_once_with(summary, back_callback=bot_router.V2_KEY_MENU_CALLBACK)
        edit_screen.assert_awaited_once()

    async def test_edit_screen_keeps_instruction_updates_in_same_message(self) -> None:
        message = FakeEditableMessage()
        message.edit_media = AsyncMock(
            side_effect=TelegramBadRequest(method=MagicMock(), message="message can't be edited")
        )
        callback = FakeCallback(message=message)

        with patch.object(bot_router, "_screen_photo", return_value="photo"):
            await bot_router._edit_screen(
                callback,
                "Инструкция",
                MagicMock(),
                screen_key="instruction",
            )

        message.edit_caption.assert_awaited_once()
        message.answer_photo.assert_not_awaited()
        message.answer.assert_not_awaited()
