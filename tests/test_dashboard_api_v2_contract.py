import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings
from tests.test_dashboard_auth_session import MemoryStore, FakeAsyncSession


class DashboardApiV2ContractSmokeTests(unittest.TestCase):
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

    async def fake_overview_payload(self):
        return {
            "kpis": {
                "total_users": 12,
                "active_users": 9,
                "active_connections": 7,
                "monthly_revenue": 15500,
                "servers_online": 2,
            },
            "user_distribution": {
                "trial_active": 2,
                "paid_active": 7,
                "inactive": 3,
                "trial_used": 4,
                "plans": [{"label": "1 month", "count": 5}],
            },
            "charts": {
                "traffic": [{"label": "today", "traffic": 10, "rx": 6, "tx": 4}],
                "user_activity": [{"date": "2026-03-19", "users": 9, "revenue": 15500}],
                "server_load": [{"label": "de-1", "cpu": 20, "ram": 30, "disk": 40, "connections": 7}],
            },
            "rail": {
                "alerts": [{"title": "Notice", "text": "All good", "href": "/servers", "action": "Open"}],
                "recent_payments": [],
                "recent_activity": [],
            },
            "system_alerts": {
                "backup": {
                    "last_backup_at": "2026-03-19 12:00",
                    "backup_stale": False,
                    "status": "healthy",
                    "priority": "low",
                    "age_hours": 2.5,
                    "stale_definition_hours": 24,
                    "sources": [
                        {
                            "key": "core",
                            "label": "Core PG",
                            "last_backup_at": "2026-03-19 12:00",
                            "backup_stale": False,
                            "status": "healthy",
                            "age_hours": 2.5,
                            "recent_files": 2,
                        }
                    ],
                },
                "restore": {
                    "last_restore_validation_at": "2026-03-19 20:40",
                    "restore_validation_stale": False,
                    "status": "healthy",
                    "priority": "low",
                    "age_days": 1.0,
                    "stale_definition_days": 30,
                    "signal_source": "documentation task results",
                },
                "support": {
                    "open_tickets": 5,
                    "new_tickets": 2,
                    "is_escalated": True,
                    "priority": "high",
                    "oldest_open_tickets": [
                        {
                            "user_id": 5001,
                            "username": "alice",
                            "status": "new",
                            "created_at": "2026-03-19 09:00",
                            "updated_at": "2026-03-19 10:00",
                            "preview": "Payment not confirmed",
                            "priority": "high",
                            "age_hours": 33.0,
                            "is_escalated": True,
                            "href": "/support?ticket_id=5001",
                        }
                    ],
                    "status": "warning",
                },
                "payments": {
                    "pending_confirmations": 2,
                    "open_manual_requests": 3,
                    "stale_pending_confirmations": 1,
                    "stale_definition_hours": 12,
                    "is_escalated": True,
                    "priority": "high",
                    "oldest_pending_manual_payments": [
                        {
                            "record_id": 41,
                            "user_id": 99,
                            "username": "alice",
                            "telegram_id": 123456,
                            "created_at": "2026-03-19 11:55",
                            "age_hours": 14,
                            "is_stale": True,
                            "is_escalated": True,
                            "priority": "high",
                            "href": "/payments?record_id=41",
                            "user_href": "/users?user_id=99",
                        }
                    ],
                    "status": "warning",
                },
            },
            "attention": {
                "repair_needed_users": [
                    {
                        "user_id": 99,
                        "username": "alice",
                        "telegram_id": 123456,
                        "reason": "manual_repair_sync_failed",
                        "reason_label": "Manual repair sync failed",
                        "marked_at": "2026-03-19 12:00",
                        "marked_age_hours": 8.0,
                        "access_status": "paid_active",
                        "devices_count": 1,
                        "failed_repair_attempts": 2,
                        "has_repeated_failures": True,
                        "is_escalated": True,
                        "is_payment_related": True,
                        "priority": "high",
                        "can_repair": True,
                        "repair_block_reason": None,
                        "href": "/users?user_id=99",
                    }
                ],
                "payment_related_users": [
                    {
                        "user_id": 99,
                        "username": "alice",
                        "telegram_id": 123456,
                        "reason": "post_payment_sync_failed",
                        "reason_label": "Post-payment VPN sync failed",
                        "marked_at": "2026-03-19 12:00",
                        "marked_age_hours": 8.0,
                        "failed_repair_attempts": 2,
                        "has_repeated_failures": True,
                        "is_escalated": True,
                        "is_payment_related": True,
                        "priority": "high",
                        "href": "/users?user_id=99",
                    }
                ],
                "summary": {
                    "repair_needed": 1,
                    "repeated_failed_repairs": 1,
                    "payment_related_repairs": 1,
                    "high_priority_repairs": 1,
                    "escalated_repairs": 1,
                },
            },
            "health": {"status": "ok"},
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
            "summary": {
                "mrr": 15500,
                "new_subscriptions": 3,
                "refunds": 0,
                "failed_payments": 1,
                "manual_queue": 2,
            },
            "records": [
                {
                    "id": 41,
                    "user_id": 99,
                    "username": "alice",
                    "telegram_id": 123456,
                    "tariff_code": "monthly",
                    "payment_method": "stars",
                    "payment_method_label": "Telegram Stars",
                    "payment_status": "confirmed",
                    "payment_status_label": "Confirmed",
                    "amount": 299,
                    "currency": "RUB",
                    "duration_days": 30,
                    "reviewed_at": "2026-03-19T12:00:00",
                    "expires_at": "2026-04-18T12:00:00",
                    "confirmed_at": "2026-03-19T12:00:00",
                    "created_at": "2026-03-19T11:55:00",
                    "is_reviewable": False,
                    "is_waiting_user": False,
                }
            ],
            "selected_record": {
                "id": 41,
                "user_id": 99,
                "username": "alice",
                "telegram_id": 123456,
                "tariff_code": "monthly",
                "payment_method": "stars",
                "payment_method_label": "Telegram Stars",
                "payment_status": "confirmed",
                "payment_status_label": "Confirmed",
                "amount": 299,
                "currency": "RUB",
                "duration_days": 30,
                "reviewed_at": "2026-03-19T12:00:00",
                "expires_at": "2026-04-18T12:00:00",
                "confirmed_at": "2026-03-19T12:00:00",
                "created_at": "2026-03-19T11:55:00",
                "is_reviewable": False,
                "is_waiting_user": False,
                "linked_user_context": {
                    "user_id": 99,
                    "username": "alice",
                    "telegram_id": 123456,
                    "access_status": "paid_active",
                    "access_expires_at": "2026-04-18 12:00",
                    "devices_count": 1,
                    "vpn_repair_needed": True,
                    "vpn_repair_reason": "post_payment_sync_failed",
                    "vpn_repair_reason_label": "Post-payment VPN sync failed",
                    "vpn_repair_source": "post_payment",
                    "vpn_repair_source_label": "Post-payment",
                    "repair_action": {
                        "can_repair": True,
                        "blocked_reason": None,
                    },
                    "user_issue_summary": {
                        "has_issue": True,
                        "access_status": "paid_active",
                        "devices_count": 1,
                        "vpn_repair_needed": True,
                        "vpn_repair_reason": "post_payment_sync_failed",
                        "vpn_repair_reason_label": "Post-payment VPN sync failed",
                        "vpn_repair_source": "post_payment",
                        "vpn_repair_source_label": "Post-payment",
                        "last_repair_result": "skipped",
                        "last_repair_outcome": "skipped",
                        "last_repair_outcome_label": "Skipped",
                        "last_repair_source": "manual",
                        "last_repair_source_label": "Manual",
                        "last_repair_reason": "manual_repair_sync_failed",
                        "last_repair_reason_label": "Manual repair sync failed",
                        "last_repair_at": "2026-03-19 12:05",
                        "can_repair": True,
                        "repair_block_reason": None,
                    },
                    "support_ticket_open": True,
                    "support_status": "В работе",
                    "user_href": "/users?user_id=99",
                    "support_href": "/support?ticket_id=99",
                },
            },
            "payment_mix": [{"method": "stars", "count": 1}],
            "finance": {
                "summary": {"income": 15500},
                "dashboard": {
                    "summary": {"income": 15500},
                    "entries": [],
                    "selected_entry": None,
                    "periods": ["2026-03"],
                    "admins": [],
                    "filters": {},
                    "recurring_rows": [],
                },
            },
            "tariffs": [{"code": "monthly", "label": "1 month"}],
        }

    def test_dashboard_api_v2_overview_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/overview")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_overview_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-overview-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_overview_payload", self.fake_overview_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {"kpis", "user_distribution", "charts", "rail", "system_alerts", "attention", "health"},
        )

    def test_dashboard_api_v2_payments_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/payments")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_payments_returns_expected_shape_with_valid_session(self) -> None:
        token = "api-payments-contract-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", self.fake_payments_payload),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/payments")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            set(payload["data"].keys()),
            {"summary", "records", "selected_record", "payment_mix", "finance", "tariffs"},
        )
        self.assertIsInstance(payload["data"]["records"], list)
        self.assertEqual(payload["data"]["selected_record"]["linked_user_context"]["vpn_repair_source"], "post_payment")
        self.assertEqual(
            payload["data"]["selected_record"]["linked_user_context"]["user_issue_summary"]["last_repair_outcome"],
            "skipped",
        )

    def test_dashboard_api_v2_user_delete_rejects_get(self) -> None:
        token = "api-user-delete-method-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/users/99/delete")

        self.assertEqual(response.status_code, 405)

    def test_dashboard_api_v2_payment_delete_rejects_get(self) -> None:
        token = "api-payment-delete-method-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/payments/41/delete")

        self.assertEqual(response.status_code, 405)

    def test_dashboard_api_v2_finance_delete_rejects_get(self) -> None:
        token = "api-finance-delete-method-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/finance/7/delete")

        self.assertEqual(response.status_code, 405)

    def test_owner_can_reject_confirm_and_update_payment_status(self) -> None:
        token = "api-payment-owner-actions-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_v2_payments_payload", self.fake_payments_payload),
            patch.object(dashboard_main, "confirm_payment_record", new=AsyncMock()) as confirm_mock,
            patch.object(dashboard_main, "reject_payment_record", new=AsyncMock()) as reject_mock,
            patch.object(
                dashboard_main,
                "set_payment_record_status",
                new=AsyncMock(return_value=SimpleNamespace(id=41, payment_status="expired")),
            ) as status_mock,
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            confirm_response = self.client.post("/dashboard/api/v2/payments/41/confirm")
            reject_response = self.client.post(
                "/dashboard/api/v2/payments/41/reject",
                json={"reason": "bad proof"},
            )
            status_response = self.client.post(
                "/dashboard/api/v2/payments/41/status",
                json={"payment_status": "expired", "reason": "timeout"},
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        confirm_mock.assert_awaited_once()
        reject_mock.assert_awaited_once()
        status_mock.assert_awaited_once()


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardApiV2ContractSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
