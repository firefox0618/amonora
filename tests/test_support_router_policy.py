import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ContentType

from support_bot.router import (
    SUPPORT_PANEL_TICKET_LIMIT,
    _dashboard_keyboard,
    _is_supported_user_message,
    _normalize_filter,
    _render_admin_panel,
)


class SupportRouterPolicyTests(unittest.TestCase):
    def test_text_and_allowed_media_are_supported(self) -> None:
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type="text")))
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type="photo")))
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type="video")))
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type="audio")))

    def test_video_notes_and_other_unsupported_media_are_rejected(self) -> None:
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type="video_note")))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type="document")))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type="voice")))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type="animation")))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type="sticker")))

    def test_aiogram_content_type_enums_are_normalized(self) -> None:
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type=ContentType.TEXT)))
        self.assertTrue(_is_supported_user_message(SimpleNamespace(content_type=ContentType.PHOTO)))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type=ContentType.VIDEO_NOTE)))
        self.assertFalse(_is_supported_user_message(SimpleNamespace(content_type=ContentType.DOCUMENT)))

    def test_dashboard_keyboard_limits_ticket_list_to_five_rows(self) -> None:
        tickets = [
            {"user_id": 1000 + idx, "full_name": f"User {idx}", "status": "new", "assigned_admin_id": None}
            for idx in range(8)
        ]

        keyboard = _dashboard_keyboard(tickets, "all", viewer_admin_id=1)

        ticket_rows = [
            row for row in keyboard.inline_keyboard if row and row[0].callback_data.startswith("support:open:")
        ]
        self.assertEqual(len(ticket_rows), SUPPORT_PANEL_TICKET_LIMIT)


class SupportRouterSyntheticFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_admin_panel_requests_real_user_ticket_slice(self) -> None:
        fake_bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
        tickets = [{"user_id": 1001, "full_name": "Real User", "status": "new", "assigned_admin_id": None}]
        counts = {"all": 1, "new": 1, "in_progress": 0, "closed": 0, "mine": 0}

        with (
            patch("support_bot.router.get_ticket_counts", new=AsyncMock(return_value=counts)) as counts_mock,
            patch("support_bot.router.list_tickets", new=AsyncMock(return_value=tickets)) as tickets_mock,
        ):
            await _render_admin_panel(
                fake_bot,
                chat_id=101,
                message_id=None,
                viewer_admin_id=202,
                filter_mode="queue",
            )

        counts_mock.assert_awaited_once_with(202, exclude_synthetic=True)
        tickets_mock.assert_awaited_once_with(
            _normalize_filter("queue"),
            admin_id=202,
            limit=SUPPORT_PANEL_TICKET_LIMIT,
            exclude_synthetic=True,
        )
        fake_bot.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
