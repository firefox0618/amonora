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
os.environ.setdefault("VPN_HOST", "ffconnect.amonoraconnect.com")

from bot.db import _new_user_control_event_message, _trial_started_control_event_message
from bot.handlers.devices import _credential_delivery_event_message


class ControlNotificationCopyTests(unittest.TestCase):
    def test_new_user_notification_is_compact_single_line(self) -> None:
        text = _new_user_control_event_message(850509278, "leerawww")
        self.assertEqual(
            text,
            "Telegram ID: <code>850509278</code> • Username: <b>@leerawww</b>",
        )

    def test_trial_notification_is_compact_single_line(self) -> None:
        text = _trial_started_control_event_message(119, 1926159631, None)
        self.assertEqual(
            text,
            "User: <code>119</code> • Tg ID: <code>1926159631</code> • Пробный доступ до: <b>—</b>",
        )

    def test_key_notification_hides_country_for_key_flows(self) -> None:
        text = _credential_delivery_event_message(
            user_id=115,
            device_name="Телефон",
            protocol="vless",
            country_name="Германия",
            include_country=False,
        )
        self.assertEqual(
            text,
            "Пользователь: <code>115</code> • Устройство: <b>Телефон</b> • Протокол: <b>vless</b>",
        )

    def test_config_notification_can_still_include_country(self) -> None:
        text = _credential_delivery_event_message(
            user_id=115,
            device_name="Телефон",
            protocol="wireguard",
            country_name="Германия",
            include_country=True,
        )
        self.assertEqual(
            text,
            "Пользователь: <code>115</code> • Устройство: <b>Телефон</b> • Протокол: <b>wireguard</b> • Страна: <b>Германия</b>",
        )


if __name__ == "__main__":
    unittest.main()
