import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.models import DashboardAdmin
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardPaymentCacheIsolationTests(unittest.TestCase):
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

    def test_payments_cache_isolated_per_admin(self) -> None:
        async def fake_payload(record_id=None, period_key=None, admin=None):
            return {
                "summary": {},
                "records": [],
                "selected_record": None,
                "payment_mix": [],
                "finance": {
                    "summary": {"admin_id": admin.id},
                    "dashboard": {"entries": [], "selected_entry": None, "periods": [], "admins": [], "filters": {}, "recurring_rows": []},
                },
                "tariffs": [],
            }

        token_one = "payments-cache-admin-1"
        token_two = "payments-cache-admin-2"
        admin_two = DashboardAdmin(
            id=9,
            username="cache_second_admin",
            display_name="Cache Second Admin",
            role="owner",
            telegram_id=990009,
            password_hash=self.store.admin.password_hash,
            is_active=True,
        )

        payload_mock = AsyncMock(side_effect=fake_payload)

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", payload_mock),
        ):
            self._run(create_session(self.store.admin.id, token_one))
            self.set_session_cookie(token_one)
            first = self.client.get("/dashboard/api/v2/finance")

            self.client.cookies.clear()
            self.store.admin = admin_two
            self._run(create_session(self.store.admin.id, token_two))
            self.set_session_cookie(token_two)
            second = self.client.get("/dashboard/api/v2/finance")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["summary"]["admin_id"], 7)
        self.assertEqual(second.json()["data"]["summary"]["admin_id"], 9)
        self.assertEqual(payload_mock.await_count, 2)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardPaymentCacheIsolationTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
