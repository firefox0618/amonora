import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2TrafficContractSmokeTests(unittest.TestCase):
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

    async def fake_traffic_payload(self, force_refresh=False):
        return {
            "overview": {
                "current_bandwidth": 18.5,
                "current_bandwidth_label": "18.5 Mbps",
                "total_transfer_gb": 123.4,
                "regions_online": 2,
                "servers_reporting": 2,
                "active_connections": 11,
            },
            "bandwidth_by_server": [
                {
                    "server": "Germany Main",
                    "traffic": 18.5,
                    "rx": 12.4,
                    "tx": 6.1,
                    "connections": 10,
                    "country": "Germany",
                    "transfer_gb": 123.4,
                }
            ],
            "connections_by_region": [{"region": "DE", "connections": 8}],
            "peak_hours": [{"hour": "18:00", "activity": 14}],
            "top_countries": [{"country": "Germany", "connections": 8}],
            "traffic_mix": [{"label": "Germany", "value": 18.5}],
        }

    def test_dashboard_api_v2_traffic_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/traffic")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_traffic_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-traffic-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_traffic_payload", self.fake_traffic_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/traffic")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {
                "overview",
                "bandwidth_by_server",
                "connections_by_region",
                "peak_hours",
                "top_countries",
                "traffic_mix",
            },
        )

    def test_dashboard_api_v2_traffic_returns_list_like_primary_series_with_valid_session(self) -> None:
        token = "api-traffic-series-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_traffic_payload", self.fake_traffic_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/traffic")

        self.assertEqual(response.status_code, 200)
        series = response.json()["data"]["bandwidth_by_server"]
        self.assertIsInstance(series, list)
        self.assertEqual(len(series), 1)

    def test_dashboard_api_v2_traffic_reset_invalidates_traffic_and_overview_cache(self) -> None:
        token = "api-traffic-reset-token"
        dashboard_main._V2_READ_CACHE.update(
            {
                "traffic": (9999999999.0, {"stale": True}),
                "overview": (9999999999.0, {"stale": True}),
                "users": (9999999999.0, {"stale": False}),
            }
        )

        async def fake_reset_traffic_baseline(admin, ip_address):
            return {"reset_at": "2026-04-01T09:27:55", "servers": {}}

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "reset_traffic_baseline", fake_reset_traffic_baseline),
            patch.object(dashboard_main, "get_v2_traffic_payload", self.fake_traffic_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/traffic/reset")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertNotIn("traffic", dashboard_main._V2_READ_CACHE)
        self.assertNotIn("overview", dashboard_main._V2_READ_CACHE)
        self.assertIn("users", dashboard_main._V2_READ_CACHE)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2TrafficContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
