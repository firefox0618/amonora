import unittest

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from control_bot.dispatcher import create_control_event, mask_login_code, preference_category, send_panel_auth_code


class _FakeSession:
    async def close(self) -> None:
        return None


class _FakeBot:
    last_message = None

    def __init__(self, token: str) -> None:
        self.token = token
        self.session = _FakeSession()

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML", disable_web_page_preview: bool = True):
        del parse_mode, disable_web_page_preview
        _FakeBot.last_message = {"chat_id": chat_id, "text": text, "token": self.token}
        return SimpleNamespace(message_id=7788)


class _CreateEventSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _statement):
        return SimpleNamespace(
            scalar_one_or_none=lambda: None,
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _item) -> None:
        return None


class ControlDispatcherTests(unittest.IsolatedAsyncioTestCase):
    def test_mask_login_code_keeps_edges_only(self) -> None:
        self.assertEqual(mask_login_code("482913"), "48••13")
        self.assertEqual(mask_login_code("1234"), "1••4")
        self.assertEqual(mask_login_code("12"), "••")

    def test_preference_category_supports_granular_toggles(self) -> None:
        self.assertEqual(preference_category("users", "new_user"), "new_users")
        self.assertEqual(preference_category("users", "trial_started"), "trials")
        self.assertEqual(preference_category("access", "access_key_issued"), "access_keys")
        self.assertEqual(preference_category("access", "access_delivery_failed"), "users")

    async def test_send_panel_auth_code_sends_live_code_and_logs_masked_event(self) -> None:
        event_mock = AsyncMock()

        with (
            patch("control_bot.dispatcher.Bot", _FakeBot),
            patch("control_bot.dispatcher.create_control_event", event_mock),
            patch("control_bot.dispatcher.config.control_bot_token", "control-test-token"),
        ):
            message_id, bot_key = await send_panel_auth_code(
                admin_username="owner",
                telegram_id=7650618403,
                code="482913",
                ttl_minutes=10,
            )

        self.assertEqual(message_id, 7788)
        self.assertEqual(bot_key, "control")
        self.assertEqual(_FakeBot.last_message["text"], "♦️Код: <tg-spoiler>482913</tg-spoiler>")
        self.assertEqual(_FakeBot.last_message["chat_id"], 7650618403)

        event_mock.assert_awaited_once()
        payload = event_mock.await_args.kwargs["payload"]
        self.assertEqual(payload["admin_username"], "owner")
        self.assertEqual(payload["masked_code"], "48••13")
        self.assertEqual(payload["ttl_minutes"], 10)

    async def test_create_control_event_prefers_payload_trace_id_over_numeric_request_id(self) -> None:
        session = _CreateEventSession()

        with (
            patch("control_bot.dispatcher.async_session", return_value=session),
            patch("control_bot.dispatcher._deliver_message", new=AsyncMock(return_value=False)),
        ):
            event = await create_control_event(
                category="payments",
                severity="INFO",
                event_type="payment_sync",
                title="Payment Sync",
                message="demo",
                payload={"trace_id": "pay:trace-001"},
                request_id=123,
                dedupe_key="trace-pref-test",
            )

        self.assertTrue(session.committed)
        self.assertIs(event, session.added[0])
        self.assertEqual(event.request_id, "pay:trace-001")
        self.assertEqual(json.loads(event.payload_json)["request_id"], "pay:trace-001")


if __name__ == "__main__":
    unittest.main()
