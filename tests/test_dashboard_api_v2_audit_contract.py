import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2AuditContractSmokeTests(unittest.TestCase):
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

    async def fake_audit_payload(self, limit: int = 150):
        return {
            "summary": {
                "total": 2,
                "unique_actions": 2,
                "active_admins": 1,
                "target_types": 2,
                "latest_event_at": "2026-03-23 01:45",
            },
            "items": [
                {
                    "id": 11,
                    "action": "confirm_payment_record",
                    "target_type": "payment_record",
                    "target_id": "41",
                    "details_text": "Оплата подтверждена",
                    "created_at": "2026-03-23 01:45",
                    "admin_name": "Owner",
                }
            ],
            "top_actions": [{"action": "confirm_payment_record", "count": 1}],
            "top_admins": [{"name": "Owner", "count": 2}],
            "top_targets": [{"target_type": "payment_record", "count": 1}],
        }

    def test_dashboard_api_v2_audit_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/audit")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_audit_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-audit-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_audit_payload", self.fake_audit_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/audit?limit=120")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {"summary", "items", "top_actions", "top_admins", "top_targets"},
        )

    def test_dashboard_api_v2_audit_returns_list_like_items_with_valid_session(self) -> None:
        token = "api-audit-items-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_audit_payload", self.fake_audit_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/audit")

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 1)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2AuditContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
