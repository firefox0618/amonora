import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2UsersContractSmokeTests(unittest.TestCase):
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

    async def fake_users_payload(
        self,
        q: str = "",
        status_filter: str = "all",
        plan_filter: str = "all",
        issue_filter: str = "all",
        page: int = 1,
        page_size: int = 100,
    ):
        return {
            "items": [
                {
                    "id": 101,
                    "username": "alice",
                    "telegram_id": 123456,
                    "plan": "1 month",
                    "preferred_protocol": "vless",
                    "devices": 2,
                    "payments": 5,
                    "status": "active",
                    "is_blocked": False,
                    "access_expires_at": "2026-04-18 12:00",
                    "last_device_at": "2026-03-19 11:30",
                    "top_country": "DE",
                    "created_at": "2026-03-01 10:00",
                }
            ],
            "query": q,
            "filters": {"status": status_filter, "plan": plan_filter, "issue": issue_filter},
            "summary": {
                "total": 1,
                "active": 1,
                "blocked": 0,
                "with_devices": 1,
            },
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": 1,
                "total_pages": 1,
                "has_prev": False,
                "has_next": False,
                "from_item": 1,
                "to_item": 1,
            },
        }

    def test_dashboard_api_v2_users_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/users")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_users_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-users-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_users_payload", self.fake_users_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/users")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(set(payload["data"].keys()), {"items", "query", "filters", "summary", "pagination"})

    def test_dashboard_api_v2_users_returns_list_like_items_with_valid_session(self) -> None:
        token = "api-users-items-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_users_payload", self.fake_users_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/users")

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 1)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2UsersContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
