import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2SupportContractSmokeTests(unittest.TestCase):
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

    async def fake_support_payload(self, filter_mode="all", q="", ticket_id=None, admin=None):
        return {
            "tickets": [
                {
                    "user_id": 5001,
                    "username": "alice",
                    "status": "new",
                    "last_user_message_preview": "Help me",
                }
            ],
            "counts": {
                "all": 1,
                "new": 1,
                "in_progress": 0,
                "closed": 0,
                "mine": 0,
            },
            "filter_mode": filter_mode,
            "query": q,
            "selected_ticket": None,
            "admin_choices": [{"id": 7, "display_name": "Owner"}],
        }

    def test_dashboard_api_v2_support_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/support")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_support_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-support-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_support_payload", self.fake_support_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/support")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {"tickets", "counts", "filter_mode", "query", "selected_ticket", "admin_choices"},
        )

    def test_dashboard_api_v2_support_returns_list_like_tickets_with_valid_session(self) -> None:
        token = "api-support-items-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_support_payload", self.fake_support_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/support")

        self.assertEqual(response.status_code, 200)
        tickets = response.json()["data"]["tickets"]
        self.assertIsInstance(tickets, list)
        self.assertEqual(len(tickets), 1)

    def test_dashboard_api_v2_support_reply_returns_json_error_when_delivery_fails(self) -> None:
        token = "api-support-reply-error-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(
                dashboard_main,
                "send_support_reply",
                AsyncMock(side_effect=ValueError("Не удалось доставить ответ: пользователь заблокировал support-бота.")),
            ),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post(
                "/dashboard/api/v2/support/5001/reply",
                json={"message": "Проверка"},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("заблокировал support-бота", payload["error"])


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2SupportContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
