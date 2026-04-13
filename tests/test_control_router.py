import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest

from control_bot.router import _render_callback


def _bad_request(message: str) -> TelegramBadRequest:
    method = SimpleNamespace(__api_method__="editMessageText")
    return TelegramBadRequest(method=method, message=message)


class ControlRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_callback_ignores_not_modified_error(self) -> None:
        callback = SimpleNamespace(
            message=SimpleNamespace(
                edit_text=AsyncMock(
                    side_effect=_bad_request(
                        "Bad Request: message is not modified: specified new message content"
                    )
                )
            )
        )

        await _render_callback(callback, "same text", None)

        callback.message.edit_text.assert_awaited_once()

    async def test_render_callback_reraises_other_bad_request(self) -> None:
        callback = SimpleNamespace(
            message=SimpleNamespace(
                edit_text=AsyncMock(side_effect=_bad_request("Bad Request: chat not found"))
            )
        )

        with self.assertRaises(TelegramBadRequest):
            await _render_callback(callback, "text", None)


if __name__ == "__main__":
    unittest.main()
