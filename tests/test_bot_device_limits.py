import os
import unittest
from types import SimpleNamespace


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

from bot.config import config
from bot.utils.access import get_device_limit_for_telegram_id, get_device_limit_for_user
from bot.utils.texts import device_limit_text

config.admin_ids = [1]
config.support_admin_ids = [1]


class BotDeviceLimitTests(unittest.TestCase):
    def test_admin_device_limit_is_10(self) -> None:
        admin_user = SimpleNamespace(telegram_id=1)
        regular_user = SimpleNamespace(telegram_id=42)

        self.assertEqual(get_device_limit_for_user(admin_user), 10)
        self.assertEqual(get_device_limit_for_user(regular_user), 3)
        self.assertEqual(get_device_limit_for_telegram_id(1), 10)
        self.assertEqual(get_device_limit_for_telegram_id(42), 3)

    def test_device_limit_text_uses_dynamic_limit(self) -> None:
        self.assertIn("10 устройств", device_limit_text(10))
        self.assertIn("3 устройств", device_limit_text(3))

    def test_regular_user_device_limit_includes_active_extra_slots(self) -> None:
        user = SimpleNamespace(telegram_id=42, active_device_slot_addons=2)

        self.assertEqual(get_device_limit_for_user(user), 5)

    def test_admin_limit_is_not_extended_by_paid_slots(self) -> None:
        admin_user = SimpleNamespace(telegram_id=1, active_device_slot_addons=5)

        self.assertEqual(get_device_limit_for_user(admin_user), 10)


if __name__ == "__main__":
    unittest.main()
