import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardProviderPaymentSyncTests(unittest.TestCase):
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

    def test_dashboard_api_v2_payments_sync_calls_provider_sync(self) -> None:
        token = "provider-sync-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", AsyncMock(return_value={"records": [], "summary": {}, "finance": {"summary": {}, "dashboard": {"entries": [], "periods": [], "admins": [], "filters": {}, "recurring_rows": []}}, "tariffs": []})),
            patch.object(dashboard_main, "sync_payment_record_with_provider", AsyncMock(return_value={"provider_status": "CONFIRMED"})) as sync_mock,
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/payments/501/sync")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        sync_mock.assert_awaited_once()

    def test_dashboard_api_v2_payments_remind_calls_manual_reminder(self) -> None:
        token = "manual-remind-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", AsyncMock(return_value={"records": [], "summary": {}, "finance": {"summary": {}, "dashboard": {"entries": [], "periods": [], "admins": [], "filters": {}, "recurring_rows": []}}, "tariffs": []})),
            patch.object(dashboard_main, "send_manual_payment_reminder", AsyncMock(return_value={"record": {"id": 501}})) as remind_mock,
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/payments/501/remind")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        remind_mock.assert_awaited_once()


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardProviderPaymentSyncTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
