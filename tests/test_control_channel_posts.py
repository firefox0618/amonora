import unittest

from types import SimpleNamespace

from control_bot.channel_posts import extract_channel_post_target, parse_channel_post_buttons


class ControlChannelPostsTests(unittest.TestCase):
    def test_extract_channel_post_target_from_forward_origin(self) -> None:
        message = SimpleNamespace(
            forward_origin=SimpleNamespace(
                type="channel",
                chat=SimpleNamespace(id=-100123, title="Amonora VPN"),
                message_id=77,
            ),
            forward_from_chat=None,
            forward_from_message_id=None,
        )

        target = extract_channel_post_target(message)

        self.assertIsNotNone(target)
        self.assertEqual(target.chat_id, -100123)
        self.assertEqual(target.message_id, 77)
        self.assertEqual(target.chat_title, "Amonora VPN")

    def test_extract_channel_post_target_from_legacy_forward_fields(self) -> None:
        message = SimpleNamespace(
            forward_origin=None,
            forward_from_chat=SimpleNamespace(id=-100456, title="Legacy Channel", type="channel"),
            forward_from_message_id=19,
        )

        target = extract_channel_post_target(message)

        self.assertIsNotNone(target)
        self.assertEqual(target.chat_id, -100456)
        self.assertEqual(target.message_id, 19)
        self.assertEqual(target.chat_title, "Legacy Channel")

    def test_extract_channel_post_target_ignores_non_channel_messages(self) -> None:
        message = SimpleNamespace(
            forward_origin=SimpleNamespace(type="user"),
            forward_from_chat=SimpleNamespace(id=-100456, title="Group", type="supergroup"),
            forward_from_message_id=19,
        )

        self.assertIsNone(extract_channel_post_target(message))

    def test_parse_channel_post_buttons_supports_username_and_multi_button_row(self) -> None:
        keyboard, button_count = parse_channel_post_buttons(
            "Бот | @amonora_bot || Канал | t.me/amonora_new\nСайт | https://www.amonoraconnect.com"
        )

        self.assertEqual(button_count, 3)
        self.assertEqual(keyboard.inline_keyboard[0][0].url, "https://t.me/amonora_bot")
        self.assertEqual(keyboard.inline_keyboard[0][1].url, "https://t.me/amonora_new")
        self.assertEqual(keyboard.inline_keyboard[1][0].text, "Сайт")

    def test_parse_channel_post_buttons_rejects_invalid_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "формат"):
            parse_channel_post_buttons("Просто текст без ссылки")

    def test_parse_channel_post_buttons_rejects_invalid_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "https://"):
            parse_channel_post_buttons("Кнопка | example.com")


if __name__ == "__main__":
    unittest.main()
