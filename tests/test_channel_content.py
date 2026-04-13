import os
import unittest

from datetime import datetime
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

import control_bot.channel_content as channel_content


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AsyncSessionWithoutItems:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement):
        return _ScalarResult(None)


class ChannelContentTests(unittest.TestCase):
    def test_parse_channel_post_start_token_accepts_only_post_prefix(self) -> None:
        self.assertEqual(channel_content.parse_channel_post_start_token("post_abc123"), "abc123")
        self.assertIsNone(channel_content.parse_channel_post_start_token("ref_abc123"))
        self.assertIsNone(channel_content.parse_channel_post_start_token(""))

    def test_can_transition_channel_status_for_main_happy_path(self) -> None:
        self.assertTrue(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_QUEUED,
                channel_content.CHANNEL_STATUS_GENERATING,
            )
        )
        self.assertTrue(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_GENERATING,
                channel_content.CHANNEL_STATUS_DRAFT,
            )
        )
        self.assertTrue(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_DRAFT,
                channel_content.CHANNEL_STATUS_APPROVED,
            )
        )
        self.assertTrue(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_APPROVED,
                channel_content.CHANNEL_STATUS_PUBLISHING,
            )
        )
        self.assertTrue(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_PUBLISHING,
                channel_content.CHANNEL_STATUS_PUBLISHED,
            )
        )
        self.assertFalse(
            channel_content.can_transition_channel_status(
                channel_content.CHANNEL_STATUS_PUBLISHED,
                channel_content.CHANNEL_STATUS_DRAFT,
            )
        )

    def test_validate_channel_copy_rejects_risky_public_wording(self) -> None:
        okay, reason = channel_content.validate_channel_copy("<b>Спокойный</b> пост про стабильное соединение и приложения.")
        self.assertTrue(okay)
        self.assertIsNone(reason)

        risky_okay, risky_reason = channel_content.validate_channel_copy(
            "Даём обход блокировок и полную анонимность без ограничений закона."
        )
        self.assertFalse(risky_okay)
        self.assertIsNotNone(risky_reason)

    def test_parse_channel_schedule_input_supports_relative_and_absolute_formats(self) -> None:
        now = datetime(2026, 3, 31, 10, 15)

        self.assertEqual(
            channel_content.parse_channel_schedule_input("завтра 12:00", now=now),
            datetime(2026, 4, 1, 12, 0),
        )
        self.assertEqual(
            channel_content.parse_channel_schedule_input("2026-04-02 13:45", now=now),
            datetime(2026, 4, 2, 13, 45),
        )


class ChannelContentAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_channel_post_touch_tracks_fallback_source_without_channel_item(self) -> None:
        with (
            patch.object(channel_content, "ensure_schema", new=AsyncMock(return_value=None)),
            patch.object(
                channel_content,
                "async_session",
                new=lambda: _AsyncSessionWithoutItems(),
            ),
            patch.object(
                channel_content,
                "safe_upsert_user_attribution",
                new=AsyncMock(return_value=None),
            ) as attribution_mock,
            patch.object(
                channel_content,
                "emit_link_touched_event",
                new=AsyncMock(return_value=None),
            ) as link_touched_mock,
        ):
            result = await channel_content.register_channel_post_touch(
                "inst_reels_april_01",
                user_id=556,
                telegram_id=700700700,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["item_id"], None)
        self.assertEqual(result["source_key"], "inst_reels_april_01")
        self.assertTrue(result["fallback_tracked"])
        attribution_mock.assert_awaited_once_with(
            user_id=556,
            telegram_id=700700700,
            source_type="channel_post",
            source_key="inst_reels_april_01",
            channel_item_id=None,
            seen_at=unittest.mock.ANY,
        )
        link_touched_mock.assert_awaited_once_with(
            user_id=556,
            telegram_id=700700700,
            source_type="channel_post",
            source_key="inst_reels_april_01",
            channel_item_id=None,
        )


if __name__ == "__main__":
    unittest.main()
