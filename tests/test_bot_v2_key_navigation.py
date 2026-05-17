import os
import unittest


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

from bot.services.user.models import TestUserSummary
from bot.ui.keyboards.inline.user import _subscription_key_menu_keyboard
from bot.user_flow.constants import V2_MENU_CALLBACK


class BotV2KeyNavigationTests(unittest.TestCase):
    def test_key_screen_keyboard_matches_unified_subscription_layout(self) -> None:
        summary = TestUserSummary(
            telegram_id=1001,
            access_active=True,
            status_label="✅ Подписка активна",
            days_left_text="5 дн.",
            expires_text="01.01.2027 00:00",
            balance_rub=0,
            tariff_title="1 месяц",
            devices_count=1,
            device_limit=3,
            devices=(),
            single_connection_uri="vless://example",
            subscription_page_url="https://client.amonora.ru/abcdefghijklmnop",
            subscription_feed_url="https://client.amonora.ru/abcdefghijklmnop?feed=1",
            subscription_extended_feed_url="https://client.amonora.ru/abcdefghijklmnop?feed=1&include_extra=1",
            happ_subscription_url="https://client.amonora.ru/happ/add?sub=https%3A%2F%2Fclient.amonora.ru%2Fabcdefghijklmnop",
        )

        keyboard = _subscription_key_menu_keyboard(summary)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        back_button = keyboard.inline_keyboard[-1][0]
        copy_button = keyboard.inline_keyboard[1][0]

        self.assertEqual(
            labels,
            ["🌐 Страница", "📲 Happ", "📋 Скопировать ссылку", "Мои устройства", "Назад"],
        )
        self.assertEqual(keyboard.inline_keyboard[0][0].url, summary.subscription_page_url)
        self.assertEqual(keyboard.inline_keyboard[0][1].url, summary.happ_subscription_url)
        self.assertEqual(copy_button.copy_text.text, summary.subscription_feed_url)
        self.assertEqual(back_button.text, "Назад")
        self.assertEqual(back_button.callback_data, V2_MENU_CALLBACK)
