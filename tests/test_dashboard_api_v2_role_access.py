import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore


class DashboardApiV2RoleAccessSmokeTests(unittest.TestCase):
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
        self.store.admin.role = "support_admin"
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
            "items": [],
            "query": q,
            "filters": {"status": status_filter, "plan": plan_filter, "issue": issue_filter},
            "summary": {"total": 0, "active": 0, "blocked": 0, "with_devices": 0},
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": 0,
                "total_pages": 1,
                "has_prev": False,
                "has_next": False,
                "from_item": 0,
                "to_item": 0,
            },
        }

    async def fake_payments_payload(
        self,
        record_id=None,
        period_key=None,
        search="",
        status_filter="all",
        method_filter="all",
        issue_filter="all",
        admin=None,
    ):
        return {
            "summary": {"mrr": 0, "new_subscriptions": 0, "refunds": 0, "failed_payments": 0, "manual_queue": 0},
            "records": [],
            "selected_record": None,
            "payment_mix": [],
            "finance": {
                "summary": {"income": 0, "expense": 0, "net": 0},
                "dashboard": {"entries": [], "selected_entry": None, "recurring_rows": [], "admins": [], "filters": {"period_key": "month"}},
            },
            "tariffs": [],
        }

    async def fake_support_payload(self, filter_mode: str = "all", q: str = "", ticket_id=None, admin=None):
        return {"tickets": [], "counts": {"all": 0}, "filter_mode": filter_mode, "query": q, "selected_ticket": None, "admin_choices": []}

    async def fake_campaign_analytics_payload(self, search: str = ""):
        return {
            "summary": {
                "total_campaigns": 1,
                "total_transitions": 12,
                "total_bot_starts": 5,
                "total_paid": 2,
                "overall_conversion_rate": 16.67,
            },
            "query": search,
            "campaigns": [],
        }

    def _authenticate(self) -> None:
        token = "role-access-token"
        self._run(create_session(self.store.admin.id, token))
        self.set_session_cookie(token)

    def test_support_admin_can_open_support_but_not_users_or_payments(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_users_payload", self.fake_users_payload),
            patch.object(dashboard_main, "get_v2_payments_payload", self.fake_payments_payload),
            patch.object(dashboard_main, "get_v2_campaign_analytics_payload", self.fake_campaign_analytics_payload),
            patch.object(dashboard_main, "get_v2_support_payload", self.fake_support_payload),
        ):
            self._authenticate()
            users_response = self.client.get("/dashboard/api/v2/users")
            payments_response = self.client.get("/dashboard/api/v2/payments")
            analytics_response = self.client.get("/dashboard/api/v2/analytics/campaigns")
            support_response = self.client.get("/dashboard/api/v2/support")

        self.assertEqual(users_response.status_code, 403)
        self.assertEqual(payments_response.status_code, 403)
        self.assertEqual(analytics_response.status_code, 403)
        self.assertEqual(support_response.status_code, 200)

    def test_support_admin_cannot_open_server_traffic_settings_or_finance_surfaces(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            servers_response = self.client.get("/dashboard/api/v2/servers")
            traffic_response = self.client.get("/dashboard/api/v2/traffic")
            settings_response = self.client.get("/dashboard/api/v2/settings")
            finance_response = self.client.get("/dashboard/api/v2/finance")

        self.assertEqual(servers_response.status_code, 403)
        self.assertEqual(traffic_response.status_code, 403)
        self.assertEqual(settings_response.status_code, 403)
        self.assertEqual(finance_response.status_code, 403)

    def test_support_admin_cannot_create_or_confirm_payments(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            create_response = self.client.post(
                "/dashboard/api/v2/payments",
                json={
                    "user_id": 44,
                    "payment_method": "manual_sbp",
                    "tariff_code": "1m",
                    "payment_status": "awaiting_admin_review",
                    "reference": "support-admin-test",
                    "note": "",
                },
            )
            confirm_response = self.client.post("/dashboard/api/v2/payments/73/confirm")

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(confirm_response.status_code, 403)

    def test_support_admin_cannot_change_env(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            response = self.client.post(
                "/dashboard/api/v2/settings/env",
                json={"key": "SAFE_KEY", "value": "value"},
            )

        self.assertEqual(response.status_code, 403)

    def test_support_admin_cannot_create_finance_or_read_legacy_server_snapshots(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            finance_response = self.client.post(
                "/dashboard/finance/create",
                data={
                    "entry_type": "expense",
                    "category": "operations",
                    "amount": 100,
                    "note": "",
                    "related_server": "",
                    "status": "draft",
                    "counterparty_admin_id": "",
                    "occurred_at": "",
                },
                follow_redirects=False,
            )
            snapshots_response = self.client.get("/dashboard/api/servers/snapshots")

        self.assertEqual(finance_response.status_code, 303)
        self.assertIn("/payments?error=", finance_response.headers.get("location", ""))
        self.assertEqual(snapshots_response.status_code, 403)

    def test_support_admin_cannot_delete_payments_or_users(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            payment_response = self.client.post("/dashboard/api/v2/payments/73/delete")
            user_response = self.client.post("/dashboard/api/v2/users/44/delete")

        self.assertEqual(payment_response.status_code, 403)
        self.assertEqual(user_response.status_code, 403)

    def test_tech_admin_cannot_delete_users(self) -> None:
        self.store.admin.role = "tech_admin"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._authenticate()
            user_response = self.client.post("/dashboard/api/v2/users/44/delete")

        self.assertEqual(user_response.status_code, 403)

    def test_tech_admin_can_open_finance_tab_and_read_payments_payload(self) -> None:
        self.store.admin.role = "tech_admin"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", self.fake_payments_payload),
            patch.object(dashboard_main, "get_v2_campaign_analytics_payload", self.fake_campaign_analytics_payload),
        ):
            self._authenticate()
            session_response = self.client.get("/dashboard/api/v2/session")
            payments_response = self.client.get("/dashboard/api/v2/payments")
            analytics_response = self.client.get("/dashboard/api/v2/analytics/campaigns")

        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(payments_response.status_code, 200)
        self.assertEqual(analytics_response.status_code, 200)
        navigation = session_response.json()["data"]["navigation"]
        self.assertTrue(any(item["key"] == "payments" for item in navigation))
        self.assertTrue(any(item["key"] == "analytics" for item in navigation))

    def test_tech_admin_without_manage_services_cannot_run_settings_service_action(self) -> None:
        self.store.admin.role = "tech_admin"

        def fake_role_has_permission(role: str, permission: str) -> bool:
            if permission == "manage_services":
                return False
            return dashboard_services.role_has_permission(role, permission)

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "role_has_permission", side_effect=fake_role_has_permission),
        ):
            self._authenticate()
            response = self.client.post(
                "/dashboard/api/v2/settings/services/action",
                json={"service_name": "amonora-dashboard.service", "action": "restart"},
            )

        self.assertEqual(response.status_code, 403)

    def test_tech_admin_without_manage_docs_cannot_generate_docs_report(self) -> None:
        self.store.admin.role = "tech_admin"

        def fake_role_has_permission(role: str, permission: str) -> bool:
            if permission == "manage_docs":
                return False
            return dashboard_services.role_has_permission(role, permission)

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "role_has_permission", side_effect=fake_role_has_permission),
        ):
            self._authenticate()
            response = self.client.post("/dashboard/api/v2/settings/docs/report")

        self.assertEqual(response.status_code, 403)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2RoleAccessSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
