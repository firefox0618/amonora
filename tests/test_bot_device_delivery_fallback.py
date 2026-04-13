import os
import unittest

from datetime import datetime
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
os.environ.setdefault("VPN_HOST", "ffconnect.amonoraconnect.com")
os.environ.setdefault("VPN_HOST_DK", "dk.amonoraconnect.com")

from bot.handlers import devices as devices_handler


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[dict] = []

    async def answer(self, text: str, parse_mode: str | None = None, **kwargs):
        self.answers.append({"text": text, "parse_mode": parse_mode, "kwargs": kwargs})
        return SimpleNamespace()


class FakeState:
    def __init__(self, data: dict) -> None:
        self._data = data
        self.clear = AsyncMock()

    async def get_data(self) -> dict:
        return dict(self._data)


class DeviceDeliveryFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_provisioned_device_after_failure_removes_remote_and_local_state(self) -> None:
        provisioner = SimpleNamespace(
            delete_vless_client=AsyncMock(return_value={"success": True}),
            close=AsyncMock(),
        )

        with (
            patch.object(devices_handler, "get_vless_provisioner", return_value=provisioner),
            patch.object(devices_handler, "delete_vpn_client_and_return", new=AsyncMock(return_value=SimpleNamespace(id=70))) as delete_mock,
        ):
            cleaned = await devices_handler._cleanup_provisioned_device_after_failure(
                device_id=70,
                protocol="vless",
                client_uuid="uuid-70",
                email="device_70_1",
                xui_client_id=None,
                metadata={"country_code": "de", "provider_type": "xui", "inbound_id": 1},
            )

        self.assertTrue(cleaned)
        provisioner.delete_vless_client.assert_awaited_once_with(
            client_uuid="uuid-70",
            email="device_70_1",
            metadata={"country_code": "de", "provider_type": "xui", "inbound_id": 1},
        )
        provisioner.close.assert_awaited_once()
        delete_mock.assert_awaited_once_with(70)

    async def test_delivery_failure_after_provisioning_returns_recovery_text(self) -> None:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1010),
            message=FakeMessage(),
        )
        state = FakeState({"device_name": "Office Laptop", "device_type": "windows"})
        user = SimpleNamespace(id=77)
        provision_result = SimpleNamespace(
            vpn_client_id=55,
            client_uuid="uuid-55",
            email="device_77_1",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        device = SimpleNamespace(id=55, protocol="vless", user_id=77, email="device_77_1")
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(devices_handler, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                devices_handler,
                "get_access_expires_at",
                new=AsyncMock(return_value=datetime(2026, 3, 23, 22, 0, 0)),
            ),
            patch.object(devices_handler, "_region_capacity_error", new=AsyncMock(return_value=None)),
            patch.object(devices_handler, "mode_supported_in_region", return_value=True),
            patch.object(devices_handler, "get_vless_provisioner", return_value=provisioner),
            patch.object(devices_handler, "update_vpn_client_metadata", new=AsyncMock()),
            patch.object(devices_handler, "get_vpn_client_by_id", new=AsyncMock(return_value=device)),
            patch.object(devices_handler, "_edit_or_send", new=AsyncMock()),
            patch.object(devices_handler, "_send_vless_config", new=AsyncMock(side_effect=RuntimeError("send failed"))),
            patch.object(devices_handler, "_emit_credential_delivery_event", new=AsyncMock()) as delivery_event_mock,
            patch.object(devices_handler, "_emit_provisioning_failure_event", new=AsyncMock()) as provisioning_event_mock,
            patch.object(devices_handler, "_emit_delivery_failure_event", new=AsyncMock()) as failed_delivery_mock,
            patch.object(devices_handler, "_mark_trial_technical_engagement_safe", new=AsyncMock()) as mark_trial_mock,
        ):
            handled = await devices_handler._create_device_from_selection(
                callback,
                state,
                country_code="de",
                mode="auto",
            )

        self.assertFalse(handled)
        provisioning_event_mock.assert_not_awaited()
        delivery_event_mock.assert_not_awaited()
        failed_delivery_mock.assert_awaited_once()
        self.assertEqual(
            failed_delivery_mock.await_args.args,
            (77, 55, "vless", "de", "delivery failed after provisioning"),
        )
        self.assertTrue(str(failed_delivery_mock.await_args.kwargs["request_id"]).startswith("dev:"))
        mark_trial_mock.assert_not_awaited()
        state.clear.assert_awaited_once()
        self.assertEqual(len(callback.message.answers), 1)
        self.assertEqual(callback.message.answers[0]["parse_mode"], "HTML")
        self.assertIn("Подключение уже создано", callback.message.answers[0]["text"])

    async def test_metadata_failure_after_provisioning_triggers_cleanup(self) -> None:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1011),
            message=FakeMessage(),
        )
        state = FakeState({"device_name": "Office Laptop", "device_type": "windows"})
        user = SimpleNamespace(id=78)
        provision_result = SimpleNamespace(
            vpn_client_id=56,
            client_uuid="uuid-56",
            email="device_78_1",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(devices_handler, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                devices_handler,
                "get_access_expires_at",
                new=AsyncMock(return_value=datetime(2026, 3, 23, 22, 0, 0)),
            ),
            patch.object(devices_handler, "_region_capacity_error", new=AsyncMock(return_value=None)),
            patch.object(devices_handler, "mode_supported_in_region", return_value=True),
            patch.object(devices_handler, "get_vless_provisioner", return_value=provisioner),
            patch.object(devices_handler, "update_vpn_client_metadata", new=AsyncMock(side_effect=RuntimeError("metadata failed"))),
            patch.object(devices_handler, "_cleanup_provisioned_device_after_failure", new=AsyncMock(return_value=True)) as cleanup_mock,
            patch.object(devices_handler, "_emit_provisioning_failure_event", new=AsyncMock()) as provisioning_event_mock,
        ):
            handled = await devices_handler._create_device_from_selection(
                callback,
                state,
                country_code="de",
                mode="auto",
            )

        self.assertFalse(handled)
        cleanup_mock.assert_awaited_once()
        cleanup_call = cleanup_mock.await_args.kwargs
        self.assertEqual(cleanup_call["device_id"], 56)
        self.assertEqual(cleanup_call["protocol"], "vless")
        self.assertEqual(cleanup_call["client_uuid"], "uuid-56")
        self.assertEqual(cleanup_call["email"], "device_78_1")
        self.assertIsNone(cleanup_call["xui_client_id"])
        self.assertEqual(cleanup_call["metadata"]["device_name"], "Office Laptop")
        self.assertEqual(cleanup_call["metadata"]["device_type"], "windows")
        self.assertEqual(cleanup_call["metadata"]["country_code"], "de")
        self.assertEqual(cleanup_call["metadata"]["protocol"], "vless")
        provisioning_event_mock.assert_awaited_once()
        self.assertEqual(len(callback.message.answers), 1)
        self.assertEqual(callback.message.answers[0]["text"], devices_handler.PANEL_OPERATION_ERROR_TEXT)

    async def test_metadata_failure_after_provisioning_queues_finalize_job_when_immediate_cleanup_fails(self) -> None:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1013),
            message=FakeMessage(),
        )
        state = FakeState({"device_name": "Office Laptop", "device_type": "windows"})
        user = SimpleNamespace(id=80)
        provision_result = SimpleNamespace(
            vpn_client_id=58,
            client_uuid="uuid-58",
            email="device_80_1",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(devices_handler, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                devices_handler,
                "get_access_expires_at",
                new=AsyncMock(return_value=datetime(2026, 3, 23, 22, 0, 0)),
            ),
            patch.object(devices_handler, "_region_capacity_error", new=AsyncMock(return_value=None)),
            patch.object(devices_handler, "mode_supported_in_region", return_value=True),
            patch.object(devices_handler, "get_vless_provisioner", return_value=provisioner),
            patch.object(devices_handler, "update_vpn_client_metadata", new=AsyncMock(side_effect=RuntimeError("metadata failed"))),
            patch.object(devices_handler, "_cleanup_provisioned_device_after_failure", new=AsyncMock(return_value=False)),
            patch.object(devices_handler, "enqueue_finalize_created_device_job", new=AsyncMock()) as enqueue_mock,
            patch.object(devices_handler, "_emit_provisioning_failure_event", new=AsyncMock()),
        ):
            handled = await devices_handler._create_device_from_selection(
                callback,
                state,
                country_code="de",
                mode="auto",
            )

        self.assertFalse(handled)
        enqueue_mock.assert_awaited_once()
        self.assertEqual(enqueue_mock.await_args.kwargs["device_id"], 58)
        self.assertEqual(enqueue_mock.await_args.kwargs["user_id"], 80)
        self.assertEqual(enqueue_mock.await_args.kwargs["protocol"], "vless")
        self.assertEqual(enqueue_mock.await_args.kwargs["access_expires_at"], datetime(2026, 3, 23, 22, 0, 0))
        self.assertTrue(str(enqueue_mock.await_args.kwargs["request_id"]).startswith("dev:"))

    async def test_fetch_failure_after_provisioning_cleans_device_and_returns_generic_error(self) -> None:
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1012),
            message=FakeMessage(),
        )
        state = FakeState({"device_name": "Tablet", "device_type": "android"})
        user = SimpleNamespace(id=79)
        provision_result = SimpleNamespace(
            vpn_client_id=57,
            client_uuid="uuid-57",
            email="device_79_1",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(devices_handler, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(
                devices_handler,
                "get_access_expires_at",
                new=AsyncMock(return_value=datetime(2026, 3, 23, 22, 0, 0)),
            ),
            patch.object(devices_handler, "_region_capacity_error", new=AsyncMock(return_value=None)),
            patch.object(devices_handler, "mode_supported_in_region", return_value=True),
            patch.object(devices_handler, "get_vless_provisioner", return_value=provisioner),
            patch.object(devices_handler, "update_vpn_client_metadata", new=AsyncMock()),
            patch.object(devices_handler, "get_vpn_client_by_id", new=AsyncMock(return_value=None)),
            patch.object(devices_handler, "_cleanup_provisioned_device_after_failure", new=AsyncMock(return_value=True)) as cleanup_mock,
        ):
            handled = await devices_handler._create_device_from_selection(
                callback,
                state,
                country_code="de",
                mode="auto",
            )

        self.assertFalse(handled)
        cleanup_mock.assert_awaited_once()
        state.clear.assert_awaited_once()
        self.assertEqual(len(callback.message.answers), 1)
        self.assertEqual(callback.message.answers[0]["text"], devices_handler.PANEL_OPERATION_ERROR_TEXT)


if __name__ == "__main__":
    unittest.main()
