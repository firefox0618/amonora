from unittest import IsolatedAsyncioTestCase
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest

from bot.handlers.devices import _edit_or_send, _get_owned_device_for_telegram, _parse_device_target_callback


class EditOrSendTests(IsolatedAsyncioTestCase):
    async def test_returns_sent_message_when_edit_fails(self) -> None:
        original = MagicMock()
        original.edit_text = AsyncMock(side_effect=TelegramBadRequest(MagicMock(), "message can't be edited"))
        fallback = MagicMock()
        fallback.chat.id = 100
        fallback.message_id = 200
        original.answer = AsyncMock(return_value=fallback)

        result = await _edit_or_send(original, "hello")

        self.assertIs(result, fallback)
        original.answer.assert_awaited_once()

    async def test_returns_original_message_when_not_modified(self) -> None:
        original = MagicMock()
        original.edit_text = AsyncMock(side_effect=TelegramBadRequest(MagicMock(), "message is not modified"))
        original.answer = AsyncMock()

        result = await _edit_or_send(original, "same")

        self.assertIs(result, original)
        original.answer.assert_not_awaited()


class OwnedDeviceLookupTests(IsolatedAsyncioTestCase):
    async def test_returns_device_only_when_owned_by_current_user(self) -> None:
        user = SimpleNamespace(id=10, telegram_id=100)
        device = SimpleNamespace(id=77, user_id=10)
        with (
            patch("bot.handlers.devices.get_user_by_telegram_id", AsyncMock(return_value=user)),
            patch("bot.handlers.devices.get_vpn_client_by_id", AsyncMock(return_value=device)),
        ):
            found_user, found_device = await _get_owned_device_for_telegram(100, 77)

        self.assertIs(found_user, user)
        self.assertIs(found_device, device)

    async def test_rejects_device_owned_by_another_user(self) -> None:
        user = SimpleNamespace(id=10, telegram_id=100)
        other_device = SimpleNamespace(id=77, user_id=11)
        with (
            patch("bot.handlers.devices.get_user_by_telegram_id", AsyncMock(return_value=user)),
            patch("bot.handlers.devices.get_vpn_client_by_id", AsyncMock(return_value=other_device)),
        ):
            found_user, found_device = await _get_owned_device_for_telegram(100, 77)

        self.assertIs(found_user, user)
        self.assertIsNone(found_device)


class DeviceCallbackParsingTests(IsolatedAsyncioTestCase):
    async def test_accepts_legacy_vpn_view_callback(self) -> None:
        self.assertEqual(
            _parse_device_target_callback("device:view:77", action="view"),
            ("legacy_device", 77),
        )

    async def test_accepts_normalized_public_view_callback(self) -> None:
        self.assertEqual(
            _parse_device_target_callback("device:view:public:2", action="view"),
            ("public_slot", 2),
        )

    async def test_accepts_legacy_public_delete_callback(self) -> None:
        self.assertEqual(
            _parse_device_target_callback("device:public:delete:3", action="delete"),
            ("public_slot", 3),
        )

    async def test_accepts_normalized_public_delete_callback(self) -> None:
        self.assertEqual(
            _parse_device_target_callback("device:delete:public:4", action="delete"),
            ("public_slot", 4),
        )


class DeviceDeleteCallbackTests(IsolatedAsyncioTestCase):
    async def test_normalized_public_delete_callback_clears_slot_and_refreshes_list(self) -> None:
        callback = SimpleNamespace(
            data="device:delete:public:2",
            from_user=SimpleNamespace(id=100),
            message=MagicMock(answer=AsyncMock()),
            answer=AsyncMock(),
        )
        user = SimpleNamespace(id=55)

        with (
            patch("bot.handlers.devices.get_user_by_telegram_id", AsyncMock(return_value=user)),
            patch("bot.handlers.devices.clear_public_subscription_device_slot_binding", AsyncMock(return_value=True)) as clear_mock,
            patch("bot.handlers.devices._show_devices_list", AsyncMock()) as show_mock,
        ):
            from bot.handlers.devices import delete_device_callback

            await delete_device_callback(callback)

        clear_mock.assert_awaited_once()
        self.assertEqual(clear_mock.await_args.kwargs["slot_index"], 2)
        show_mock.assert_awaited_once_with(callback.message, user)
        callback.answer.assert_awaited_once()
