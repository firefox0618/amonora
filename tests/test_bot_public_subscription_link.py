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

from bot.handlers import start as start_handlers
from bot.keyboards.home import home_keyboard


class BotPublicSubscriptionLinkTests(unittest.IsolatedAsyncioTestCase):
    def test_home_keyboard_contains_public_subscription_button(self) -> None:
        labels = [button.text for row in home_keyboard.inline_keyboard for button in row]

        self.assertIn("🔗 Единая ссылка", labels)

    async def test_home_subscription_page_callback_renders_page_url(self) -> None:
        editable_message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=145),
            message=editable_message,
            answer=AsyncMock(),
        )
        user = SimpleNamespace(id=42)

        with (
            patch.object(start_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                start_handlers,
                "get_or_create_public_subscription_page_url_for_user",
                new=AsyncMock(return_value="https://client.amonoraconnect.com/abcdefghijklmnop"),
            ),
        ):
            await start_handlers.home_subscription_page_callback(callback)

        editable_message.edit_text.assert_awaited_once()
        call = editable_message.edit_text.await_args
        self.assertIn("Единая ссылка на подписку", call.args[0])
        keyboard = call.kwargs["reply_markup"]
        self.assertEqual(keyboard.inline_keyboard[0][0].url, "https://client.amonoraconnect.com/abcdefghijklmnop")
        callback.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
