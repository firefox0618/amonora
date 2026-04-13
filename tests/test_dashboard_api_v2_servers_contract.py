import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2ServersContractSmokeTests(unittest.TestCase):
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

    async def fake_servers_payload(self, server_id=None, force_refresh=False):
        node = {
            "id": 1,
            "name": "Germany Main",
            "country_code": "de",
            "country_name": "Germany",
            "status": "active",
            "public_ip": "213.108.20.34",
            "provider": "Aeza",
            "host": "ffconnect.amonoraconnect.com",
            "cpu_percent": 20,
            "memory_used_percent": 35,
            "disk_used_percent": 41,
            "xui_clients": 12,
            "panel_clients": 12,
            "active_devices": 10,
            "total_devices": 13,
            "active_users": 8,
            "network_rx_mbps": 12.4,
            "network_tx_mbps": 6.1,
            "total_network_mbps": 18.5,
            "total_transfer_gb": 123.4,
            "ping_ms": 21.5,
            "ping_label": "21.5 ms",
            "uptime": "2 days, 4:10:00",
            "overall_state": "healthy",
            "status_message": "All good",
            "service_pills": [{"label": "xray", "value": "ok"}],
            "load": "0.42",
        }
        return {
            "summary": {
                "total": 2,
                "active": 2,
                "active_devices": 14,
                "total_devices": 18,
            },
            "nodes": [node],
            "selected_node": node if server_id else None,
            "vpn_summary": {"active_access": 11},
            "managed_servers": [
                {
                    "id": 1,
                    "name": "Germany Main",
                    "country_name": "Germany",
                    "provider": "Aeza",
                    "public_ip": "213.108.20.34",
                    "status": "active",
                }
            ],
        }

    def test_dashboard_api_v2_servers_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/servers")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_servers_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-servers-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_servers_payload", self.fake_servers_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/servers")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {"summary", "nodes", "selected_node", "vpn_summary", "managed_servers"},
        )

    def test_dashboard_api_v2_servers_returns_list_like_nodes_with_valid_session(self) -> None:
        token = "api-servers-nodes-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_servers_payload", self.fake_servers_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/servers")

        self.assertEqual(response.status_code, 200)
        nodes = response.json()["data"]["nodes"]
        self.assertIsInstance(nodes, list)
        self.assertEqual(len(nodes), 1)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2ServersContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
