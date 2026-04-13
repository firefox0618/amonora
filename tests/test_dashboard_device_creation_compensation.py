import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard import services as dashboard_services


class DashboardDeviceCreationCompensationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_region_capacity_error_reports_retired_estonia(self) -> None:
        snapshot = {
            "country_code": "ee",
            "status": "active",
            "host_status": "ok",
            "ssh_status": "active",
            "xui_status": "ok",
            "cpu_percent": 10,
            "memory_used_percent": 10,
            "disk_used_percent": 10,
            "load": "0.10",
            "overall_state": "healthy",
        }
        rule = SimpleNamespace(
            max_active_devices=1,
            cpu_percent_soft_limit=None,
            memory_percent_soft_limit=None,
            disk_percent_soft_limit=None,
            load_average_soft_limit=None,
        )
        with (
            patch.object(dashboard_services, "get_server_snapshots", new=AsyncMock(return_value=[snapshot])),
            patch.object(dashboard_services, "count_region_vpn_clients", new=AsyncMock(return_value=1)),
            patch.object(dashboard_services, "get_region_limit_rule", return_value=rule),
        ):
            error = await dashboard_services._dashboard_region_capacity_error("ee")

        self.assertEqual(error, "Регион Эстония выведен из продуктового контура. Создай устройство в Германии или Дании.")

    async def test_create_device_for_user_rejects_when_region_capacity_is_exceeded(self) -> None:
        user = SimpleNamespace(
            id=77,
            telegram_id=7077,
            username="demo",
            subscription_status="active",
            subscription_expires_at=datetime(2026, 5, 1, 12, 0, 0),
            is_blocked=False,
            active_device_slot_addons=0,
        )
        admin = SimpleNamespace(id=5, display_name="Owner")
        with (
            patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=user)),
            patch.object(dashboard_services, "get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 5, 1, 12, 0, 0))),
            patch.object(dashboard_services, "get_active_device_slot_counts_for_users", new=AsyncMock(return_value={77: 0})),
            patch.object(dashboard_services, "get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch.object(
                dashboard_services,
                "_dashboard_region_capacity_error",
                new=AsyncMock(return_value="Регион Эстония выведен из продуктового контура. Создай устройство в Германии или Дании."),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Регион Эстония выведен из продуктового контура. Создай устройство в Германии или Дании."):
                await dashboard_services.create_device_for_user(
                    77,
                    "Office",
                    "windows",
                    "vless",
                    "ee",
                    admin,
                    "127.0.0.1",
                )

    async def test_create_device_for_user_cleans_up_vless_device_when_metadata_update_fails(self) -> None:
        user = SimpleNamespace(
            id=77,
            telegram_id=7077,
            username="demo",
            subscription_status="active",
            subscription_expires_at=datetime(2026, 5, 1, 12, 0, 0),
            is_blocked=False,
            active_device_slot_addons=0,
        )
        admin = SimpleNamespace(id=5, display_name="Owner")
        provision_result = SimpleNamespace(
            vpn_client_id=81,
            client_uuid="uuid-81",
            email="dashboard_77_device",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=user)),
            patch.object(dashboard_services, "get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 5, 1, 12, 0, 0))),
            patch.object(dashboard_services, "get_active_device_slot_counts_for_users", new=AsyncMock(return_value={77: 0})),
            patch.object(dashboard_services, "get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "get_vless_provisioner", return_value=provisioner),
            patch.object(dashboard_services, "update_vpn_client_metadata", new=AsyncMock(side_effect=RuntimeError("metadata failed"))),
            patch.object(dashboard_services, "_cleanup_dashboard_created_device_after_failure", new=AsyncMock(return_value=True)) as cleanup_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "metadata failed"):
                await dashboard_services.create_device_for_user(
                    77,
                    "Office",
                    "windows",
                    "vless",
                    "de",
                    admin,
                    "127.0.0.1",
                )

        cleanup_mock.assert_awaited_once()
        cleanup_call = cleanup_mock.await_args.kwargs
        self.assertEqual(cleanup_call["device_id"], 81)
        self.assertEqual(cleanup_call["protocol"], "vless")
        self.assertEqual(cleanup_call["client_uuid"], "uuid-81")
        self.assertEqual(cleanup_call["email"], "dashboard_77_device")
        self.assertEqual(cleanup_call["metadata"]["device_name"], "Office")
        self.assertEqual(cleanup_call["metadata"]["country_code"], "de")

    async def test_create_device_for_user_queues_finalize_job_when_dashboard_cleanup_fails(self) -> None:
        user = SimpleNamespace(
            id=77,
            telegram_id=7077,
            username="demo",
            subscription_status="active",
            subscription_expires_at=datetime(2026, 5, 1, 12, 0, 0),
            is_blocked=False,
            active_device_slot_addons=0,
        )
        admin = SimpleNamespace(id=5, display_name="Owner")
        provision_result = SimpleNamespace(
            vpn_client_id=81,
            client_uuid="uuid-81",
            email="dashboard_77_device",
            metadata={"country_code": "de", "provider_type": "xui", "stream_network": "tcp", "transport_label": "TCP"},
        )
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(return_value=provision_result),
            close=AsyncMock(),
        )

        with (
            patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=user)),
            patch.object(dashboard_services, "get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 5, 1, 12, 0, 0))),
            patch.object(dashboard_services, "get_active_device_slot_counts_for_users", new=AsyncMock(return_value={77: 0})),
            patch.object(dashboard_services, "get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "get_vless_provisioner", return_value=provisioner),
            patch.object(dashboard_services, "update_vpn_client_metadata", new=AsyncMock(side_effect=RuntimeError("metadata failed"))),
            patch.object(dashboard_services, "_cleanup_dashboard_created_device_after_failure", new=AsyncMock(return_value=False)),
            patch.object(dashboard_services, "enqueue_finalize_created_device_job", new=AsyncMock()) as enqueue_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "metadata failed"):
                await dashboard_services.create_device_for_user(
                    77,
                    "Office",
                    "windows",
                    "vless",
                    "de",
                    admin,
                    "127.0.0.1",
                )

        enqueue_mock.assert_awaited_once()
        self.assertEqual(enqueue_mock.await_args.kwargs["device_id"], 81)
        self.assertEqual(enqueue_mock.await_args.kwargs["user_id"], 77)
        self.assertEqual(enqueue_mock.await_args.kwargs["protocol"], "vless")
        self.assertEqual(enqueue_mock.await_args.kwargs["access_expires_at"], datetime(2026, 5, 1, 12, 0, 0))
        self.assertTrue(str(enqueue_mock.await_args.kwargs["request_id"]).startswith("dev:"))


if __name__ == "__main__":
    unittest.main()
