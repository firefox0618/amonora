import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2SettingsContractSmokeTests(unittest.TestCase):
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

    async def fake_settings_payload(self, doc=None):
        return {
            "service_statuses": {"dashboard": {"label": "Dashboard", "status": "active"}},
            "logs": {"dashboard": "ok"},
            "env_rows": [["DASHBOARD_PORT", "8088"]],
            "api_keys": [["CRYPTO_PAY_API_TOKEN", "***masked***"]],
            "audits": [],
            "tariffs": {"1m": 149},
            "tariff_options": [{"code": "1m", "label": "1 month"}],
            "docs": {"title": "Docs"},
            "docs_settings": {"branch": "develop"},
            "managed_servers": [{"id": 1, "name": "Amonora Core"}],
            "payment_methods": {"telegram_stars": True, "sbp_platega": True, "crypto_platega": True, "sbp_manual": False, "crypto_manual": False, "crypto_bot": False},
        }

    def test_dashboard_api_v2_settings_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/settings")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_settings_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-settings-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_settings_payload", self.fake_settings_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/settings")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {
                "service_statuses",
                "logs",
                "env_rows",
                "api_keys",
                "audits",
                "tariffs",
                "tariff_options",
                "docs",
                "docs_settings",
                "managed_servers",
                "payment_methods",
            },
        )

    def test_dashboard_api_v2_settings_returns_list_like_env_rows_with_valid_session(self) -> None:
        token = "api-settings-env-rows-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_settings_payload", self.fake_settings_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/settings")

        self.assertEqual(response.status_code, 200)
        env_rows = response.json()["data"]["env_rows"]
        self.assertIsInstance(env_rows, list)
        self.assertEqual(len(env_rows), 1)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2SettingsContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
