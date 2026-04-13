import unittest

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings, get_user_device_status_payload
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardUserDeviceStatusServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unified_link_device_returns_view_only_status(self) -> None:
        user = SimpleNamespace(id=12, vpn_repair_needed=False)

        with patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)):
            payload = await get_user_device_status_payload(12, -100001)

        assert payload is not None
        self.assertEqual(payload["device_id"], -100001)
        self.assertEqual(payload["status_key"], "unknown")
        self.assertEqual(payload["status_reason"], "Устройство из единой ссылки пока доступно только для просмотра")

    async def test_missing_device_returns_stale_card_status(self) -> None:
        user = SimpleNamespace(id=13, vpn_repair_needed=False)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=None)),
        ):
            payload = await get_user_device_status_payload(13, 99)

        assert payload is not None
        self.assertEqual(payload["device_id"], 99)
        self.assertEqual(payload["status_key"], "unknown")
        self.assertEqual(payload["status_reason"], "Устройство уже удалено или карточка устарела. Обновите пользователя.")

    async def test_device_from_another_user_returns_stale_card_status(self) -> None:
        user = SimpleNamespace(id=14, vpn_repair_needed=False)
        device = SimpleNamespace(
            id=100,
            user_id=999,
            protocol="vless",
            client_uuid="uuid-100",
            email="device_100@example.com",
            client_data="{}",
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
        ):
            payload = await get_user_device_status_payload(14, 100)

        assert payload is not None
        self.assertEqual(payload["device_id"], 100)
        self.assertEqual(payload["status_key"], "unknown")
        self.assertEqual(
            payload["status_reason"],
            "Карточка устройства устарела или относится к другому пользователю. Обновите карточку пользователя.",
        )

    async def test_xui_live_ip_marks_device_healthy(self) -> None:
        user = SimpleNamespace(id=7, vpn_repair_needed=False)
        device = SimpleNamespace(
            id=51,
            user_id=7,
            protocol="vless",
            client_uuid="uuid-51",
            email="device_51@example.com",
            client_data='{"country_code":"de","mode":"stable","device_name":"Pixel"}',
        )
        fake_xui = SimpleNamespace(
            login=AsyncMock(return_value=True),
            resolve_client_inbound_id=AsyncMock(return_value=443),
            get_client_ips=AsyncMock(return_value=["203.0.113.10"]),
            close=AsyncMock(),
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
            patch("dashboard.services.has_active_access_from_user", return_value=True),
            patch("dashboard.services._get_last_device_activation_at", new=AsyncMock(return_value=None)),
            patch("dashboard.services.XUIClient", return_value=fake_xui),
        ):
            payload = await get_user_device_status_payload(7, 51)

        assert payload is not None
        self.assertEqual(payload["status_key"], "healthy")
        self.assertEqual(payload["status_reason"], "Есть живой IP с сервера")
        self.assertEqual(payload["mode_label"], "Стабильный")

    async def test_xui_missing_live_signal_marks_device_healthy(self) -> None:
        user = SimpleNamespace(id=8, vpn_repair_needed=False)
        device = SimpleNamespace(
            id=52,
            user_id=8,
            protocol="vless",
            client_uuid="uuid-52",
            email="device_52@example.com",
            client_data='{"country_code":"de","resolved_mode":"mobile","device_name":"iPhone"}',
        )
        fake_xui = SimpleNamespace(
            login=AsyncMock(return_value=True),
            resolve_client_inbound_id=AsyncMock(return_value=443),
            get_client_ips=AsyncMock(return_value=[]),
            close=AsyncMock(),
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
            patch("dashboard.services.has_active_access_from_user", return_value=True),
            patch("dashboard.services._get_last_device_activation_at", new=AsyncMock(return_value=None)),
            patch("dashboard.services.XUIClient", return_value=fake_xui),
        ):
            payload = await get_user_device_status_payload(8, 52)

        assert payload is not None
        self.assertEqual(payload["status_key"], "healthy")
        self.assertEqual(payload["status_reason"], "Ключ найден на сервере, явных проблем не видно")
        self.assertEqual(payload["mode_label"], "Мобильный")

    async def test_xray_recent_activation_marks_device_healthy(self) -> None:
        user = SimpleNamespace(id=9, vpn_repair_needed=False)
        device = SimpleNamespace(
            id=53,
            user_id=9,
            protocol="vless",
            client_uuid="uuid-53",
            email="device_53@example.com",
            client_data='{"country_code":"dk","connection_profile":"reserve","device_name":"Windows"}',
        )
        fake_provisioner = SimpleNamespace(
            health_check=AsyncMock(return_value=True),
            _load_state=AsyncMock(
                return_value={
                    "config": {
                        "inbounds": [
                            {
                                "protocol": "vless",
                                "listen": "@xhttp-dk",
                                "settings": {"clients": [{"id": "uuid-53", "email": "device_53@example.com"}]},
                            }
                        ]
                    }
                }
            ),
            close=AsyncMock(),
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
            patch("dashboard.services.has_active_access_from_user", return_value=True),
            patch(
                "dashboard.services._get_last_device_activation_at",
                new=AsyncMock(return_value=datetime.now(timezone.utc) - timedelta(hours=2)),
            ),
            patch("dashboard.services.get_vless_provisioner", return_value=fake_provisioner),
        ):
            payload = await get_user_device_status_payload(9, 53)

        assert payload is not None
        self.assertEqual(payload["status_key"], "healthy")
        self.assertEqual(payload["status_reason"], "Недавно было подключение")
        self.assertEqual(payload["mode_label"], "Резерв")

    async def test_inactive_access_marks_device_broken(self) -> None:
        user = SimpleNamespace(id=11, vpn_repair_needed=False)
        device = SimpleNamespace(
            id=55,
            user_id=11,
            protocol="vless",
            client_uuid="uuid-55",
            email="device_55@example.com",
            client_data='{"country_code":"de","device_name":"Galaxy"}',
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
            patch("dashboard.services.has_active_access_from_user", return_value=False),
        ):
            payload = await get_user_device_status_payload(11, 55)

        assert payload is not None
        self.assertEqual(payload["status_key"], "broken")
        self.assertEqual(payload["status_reason"], "Доступ не активен, ключ не будет работать")

    async def test_repair_needed_marks_device_broken(self) -> None:
        user = SimpleNamespace(id=10, vpn_repair_needed=True)
        device = SimpleNamespace(
            id=54,
            user_id=10,
            protocol="vless",
            client_uuid="uuid-54",
            email="device_54@example.com",
            client_data='{"country_code":"de","device_name":"MacBook"}',
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_vpn_client_by_id", new=AsyncMock(return_value=device)),
        ):
            payload = await get_user_device_status_payload(10, 54)

        assert payload is not None
        self.assertEqual(payload["status_key"], "broken")
        self.assertEqual(payload["status_reason"], "Доступ помечен как требующий ремонта")


class DashboardUserDeviceStatusApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = MemoryStore()
        cls.startup_handlers = list(dashboard_main.app.router.on_startup)
        dashboard_main.app.router.on_startup.clear()
        cls.client_cm = TestClient(dashboard_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        dashboard_main.app.router.on_startup[:] = cls.startup_handlers

    def setUp(self) -> None:
        self.store.reset()
        self.client.cookies.clear()
        dashboard_main._V2_READ_CACHE.clear()

    def fake_session_factory(self):
        return FakeAsyncSession(self.store)

    def set_session_cookie(self, token: str) -> None:
        self.client.cookies.set(dashboard_settings()["cookie_name"], token)

    def _authenticate(self) -> None:
        token = "device-status-token"
        self._run(create_session(self.store.admin.id, token))
        self.set_session_cookie(token)

    def test_force_detail_refresh_bypasses_cache_and_updates_cached_payload(self) -> None:
        first_payload = {"user": {"id": 17, "username": "alice"}, "devices": [], "payments": [], "payment_counts": {"total": 0}}
        second_payload = {"user": {"id": 17, "username": "alice-refreshed"}, "devices": [], "payments": [], "payment_counts": {"total": 0}}
        detail_mock = AsyncMock(side_effect=[first_payload, second_payload])

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_user_detail_payload", detail_mock),
        ):
            self._authenticate()
            first_response = self.client.get("/dashboard/api/v2/users/17")
            cached_response = self.client.get("/dashboard/api/v2/users/17")
            forced_response = self.client.get("/dashboard/api/v2/users/17?force=1")
            refreshed_cached_response = self.client.get("/dashboard/api/v2/users/17")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(cached_response.status_code, 200)
        self.assertEqual(forced_response.status_code, 200)
        self.assertEqual(refreshed_cached_response.status_code, 200)
        self.assertEqual(first_response.json()["data"]["user"]["username"], "alice")
        self.assertEqual(cached_response.json()["data"]["user"]["username"], "alice")
        self.assertEqual(forced_response.json()["data"]["user"]["username"], "alice-refreshed")
        self.assertEqual(refreshed_cached_response.json()["data"]["user"]["username"], "alice-refreshed")
        self.assertEqual(detail_mock.await_count, 2)

    def test_device_status_endpoint_returns_live_payload(self) -> None:
        payload = {
            "device_id": 91,
            "mode_label": "Стабильный",
            "status_key": "healthy",
            "status_label": "🟢 Исправен",
            "status_reason": "Есть живой IP с сервера",
            "status_checked_at": "2026-04-07 12:00 Екб",
        }

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_user_device_status_payload", new=AsyncMock(return_value=payload)),
        ):
            self._authenticate()
            response = self.client.post("/dashboard/api/v2/users/17/devices/91/status")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"], payload)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardUserDeviceStatusApiTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
