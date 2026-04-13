import tempfile
import unittest

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import dashboard.services as dashboard_services
import dashboard.v2_data as dashboard_v2_data


class _FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._scalar, list):
            return self._scalar
        return []


class _FakeMetricsSession:
    def __init__(self, *, users, clients, payments, audits) -> None:
        self._users = users
        self._clients = clients
        self._payments = payments
        self._audits = audits

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "FROM vpn_clients" in text:
            return _FakeResult(self._clients)
        if "FROM payment_records" in text:
            return _FakeResult(self._payments)
        if "FROM users" in text:
            return _FakeResult(self._users)
        if "FROM dashboard_audit_logs" in text:
            return _FakeResult(self._audits)
        raise AssertionError(f"unexpected query: {text}")


class DashboardSyntheticFilterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 4, 3, 18, 0, 0)
        self.real_user = SimpleNamespace(
            id=1,
            telegram_id=1001,
            username="alice",
            is_synthetic=False,
            subscription_expires_at=self.now + timedelta(days=30),
            trial_expires_at=None,
            trial_used=False,
            trial_started_at=None,
            subscription_status="active",
            is_blocked=False,
            preferred_protocol="vless",
            created_at=self.now - timedelta(days=2),
        )
        self.synthetic_user = SimpleNamespace(
            id=2,
            telegram_id=1002,
            username="operator_fixture",
            is_synthetic=True,
            subscription_expires_at=self.now + timedelta(days=30),
            trial_expires_at=None,
            trial_used=False,
            trial_started_at=None,
            subscription_status="active",
            is_blocked=False,
            preferred_protocol="vless",
            created_at=self.now - timedelta(days=1),
        )
        self.real_client = SimpleNamespace(
            id=11,
            user_id=1,
            protocol="vless",
            email="device_real_1",
            client_data='{"country_code":"de"}',
            created_at=self.now - timedelta(days=1),
        )
        self.synthetic_client = SimpleNamespace(
            id=12,
            user_id=2,
            protocol="vless",
            email="device_synth_1",
            client_data='{"country_code":"de"}',
            created_at=self.now - timedelta(days=1),
        )
        self.real_payment = SimpleNamespace(
            id=21,
            user_id=1,
            payment_status="confirmed",
            payment_method="sbp_platega",
            amount=149,
            confirmed_at=self.now - timedelta(hours=2),
            created_at=self.now - timedelta(hours=3),
        )
        self.synthetic_payment = SimpleNamespace(
            id=22,
            user_id=2,
            payment_status="confirmed",
            payment_method="sbp_platega",
            amount=999,
            confirmed_at=self.now - timedelta(hours=2),
            created_at=self.now - timedelta(hours=3),
        )

    def _fake_session_factory(self):
        return _FakeMetricsSession(
            users=[self.real_user, self.synthetic_user],
            clients=[self.real_client, self.synthetic_client],
            payments=[self.real_payment, self.synthetic_payment],
            audits=[],
        )

    async def test_get_users_hides_synthetic_users_from_default_list(self) -> None:
        with patch.object(dashboard_services, "async_session", self._fake_session_factory):
            rows = await dashboard_services.get_users()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)

    async def test_overview_metrics_excludes_synthetic_users_devices_and_payments(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self._fake_session_factory),
            patch.object(dashboard_services, "get_support_dashboard_counts", new=AsyncMock(return_value={"new": 0, "in_progress": 0, "closed": 0, "all": 0, "mine": 0})),
            patch.object(dashboard_services, "get_service_statuses", new=AsyncMock(return_value={})),
            patch.object(dashboard_services, "get_server_snapshots", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "utcnow", return_value=self.now),
        ):
            metrics = await dashboard_services.overview_metrics(force_refresh=True)

        self.assertEqual(metrics["total_users"], 1)
        self.assertEqual(metrics["active_access"], 1)
        self.assertEqual(metrics["total_devices"], 1)
        self.assertEqual(metrics["payment_counts"]["confirmed"], 1)
        self.assertEqual(metrics["payment_counts"]["revenue_30d"], 149)

    async def test_overview_metrics_uses_filtered_support_counts_instead_of_raw_ticket_counts(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self._fake_session_factory),
            patch.object(dashboard_services, "get_support_dashboard_counts", new=AsyncMock(return_value={"new": 1, "in_progress": 0, "closed": 0, "all": 1, "mine": 0})) as counts_mock,
            patch.object(dashboard_services, "get_ticket_counts", new=AsyncMock(side_effect=AssertionError("raw support counts should not be used"))),
            patch.object(dashboard_services, "get_service_statuses", new=AsyncMock(return_value={})),
            patch.object(dashboard_services, "get_server_snapshots", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "utcnow", return_value=self.now),
        ):
            metrics = await dashboard_services.overview_metrics(force_refresh=True)

        counts_mock.assert_awaited_once()
        self.assertEqual(metrics["support_counts"]["new"], 1)

    async def test_operations_report_excludes_synthetic_users_from_summary(self) -> None:
        admin = SimpleNamespace(id=7)
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_root = Path(tmpdir)
            generated_root = docs_root / "generated"
            with (
                patch.object(dashboard_services, "async_session", self._fake_session_factory),
                patch.object(dashboard_services, "get_ticket_counts", new=AsyncMock(return_value={"new": 0, "in_progress": 0, "closed": 0})),
                patch.object(dashboard_services, "get_service_statuses", new=AsyncMock(return_value={})),
                patch.object(dashboard_services, "get_server_snapshots", new=AsyncMock(return_value=[])),
                patch.object(dashboard_services, "utcnow", return_value=self.now),
                patch.object(dashboard_services, "DOCS_ROOT", docs_root),
                patch.object(dashboard_services, "GENERATED_DOCS_ROOT", generated_root),
                patch.object(dashboard_services, "invalidate_docs_cache"),
                patch.object(dashboard_services, "create_audit_log", new=AsyncMock()),
            ):
                report = await dashboard_services.generate_operations_report(admin, "127.0.0.1")

            report_text = (docs_root / report["slug"]).read_text(encoding="utf-8")

        self.assertIn("| Всего пользователей | 1 |", report_text)
        self.assertIn("| Всего устройств | 1 |", report_text)
        self.assertIn("| Подтверждённые платежи | 1 |", report_text)

    async def test_get_payment_records_hides_synthetic_payment_rows(self) -> None:
        def filtered_payment_session_factory():
            return _FakeMetricsSession(
                users=[self.real_user, self.synthetic_user],
                clients=[self.real_client, self.synthetic_client],
                payments=[self.real_payment],
                audits=[],
            )

        with patch.object(dashboard_services, "async_session", filtered_payment_session_factory):
            rows = await dashboard_services.get_payment_records()

        self.assertEqual([item.id for item in rows], [21])

    async def test_finance_payment_records_map_excludes_synthetic_linked_payments(self) -> None:
        entry_real = SimpleNamespace(source_type="payment_record", source_id="21")
        entry_synth = SimpleNamespace(source_type="payment_record", source_id="22")

        with patch.object(dashboard_services, "async_session", self._fake_session_factory):
            mapping = await dashboard_services._finance_payment_records_map([entry_real, entry_synth])

        self.assertEqual(sorted(mapping.keys()), ["21"])

    async def test_get_support_tickets_hides_synthetic_ticket_rows(self) -> None:
        tickets = [
            {
                "user_id": 1001,
                "username": "alice",
                "full_name": "Alice",
                "status": "new",
                "last_user_message_preview": "real",
                "assigned_admin_id": None,
            }
        ]
        list_tickets_mock = AsyncMock(return_value=tickets)
        with (
            patch.object(dashboard_services, "async_session", self._fake_session_factory),
            patch.object(dashboard_services, "list_tickets", new=list_tickets_mock),
        ):
            rows = await dashboard_services.get_support_tickets(filter_mode="all")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], 1001)
        list_tickets_mock.assert_awaited_once_with(
            "all",
            admin_id=None,
            search="",
            exclude_synthetic=True,
        )

    async def test_get_support_dashboard_counts_excludes_synthetic_tickets(self) -> None:
        counts_payload = {"all": 1, "new": 1, "in_progress": 0, "closed": 0, "mine": 0}
        get_counts_mock = AsyncMock(return_value=counts_payload)
        with (
            patch.object(dashboard_services, "async_session", self._fake_session_factory),
            patch.object(dashboard_services, "get_ticket_counts", new=get_counts_mock),
        ):
            counts = await dashboard_services.get_support_dashboard_counts()

        self.assertEqual(counts["all"], 1)
        self.assertEqual(counts["new"], 1)
        self.assertEqual(counts["closed"], 0)
        get_counts_mock.assert_awaited_once_with(admin_id=None, exclude_synthetic=True)

    async def test_get_support_ticket_detail_returns_none_for_synthetic_user(self) -> None:
        ticket = {
            "user_id": 1002,
            "username": "operator_fixture",
            "full_name": "Synthetic",
            "status": "new",
            "last_user_message_preview": "synthetic",
        }
        with (
            patch.object(dashboard_services, "get_ticket", new=AsyncMock(return_value=ticket)),
            patch.object(dashboard_services, "get_history", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=None)),
            patch.object(dashboard_services, "get_user_by_telegram_id", new=AsyncMock(return_value=self.synthetic_user)),
        ):
            detail = await dashboard_services.get_support_ticket_detail(1002)

        self.assertIsNone(detail)

    async def test_v2_load_users_clients_payments_filters_synthetic_rows(self) -> None:
        with patch.object(dashboard_v2_data, "async_session", self._fake_session_factory):
            users, clients, payments = await dashboard_v2_data._load_users_clients_payments()

        self.assertEqual([user.id for user in users], [1])
        self.assertEqual([client.id for client in clients], [11])
        self.assertEqual([payment.id for payment in payments], [21])

    async def test_get_user_detail_returns_none_for_synthetic_user(self) -> None:
        with patch.object(dashboard_services, "get_user_by_id", new=AsyncMock(return_value=self.synthetic_user)):
            detail = await dashboard_services.get_user_detail(2)

        self.assertIsNone(detail)

    async def test_get_vpn_overview_excludes_synthetic_devices(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self._fake_session_factory),
            patch.object(dashboard_services, "utcnow", return_value=self.now),
        ):
            overview = await dashboard_services.get_vpn_overview()

        self.assertEqual(overview["summary"]["total_devices"], 1)
        self.assertEqual(len(overview["items"]), 1)
        self.assertEqual(overview["items"][0]["id"], 11)


if __name__ == "__main__":
    unittest.main()
