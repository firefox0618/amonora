import json
import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.models import FinanceEntry, ManagedServer
from dashboard.services import (
    approve_finance_entry,
    cancel_finance_entry,
    create_finance_entry,
    create_managed_server,
    delete_finance_entry,
    service_action,
    update_server_status,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _SessionWithValue:
    def __init__(self, value):
        self._value = value
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, _query):
        return _ScalarResult(self._value)

    async def commit(self):
        return None

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 901
        return None

    async def delete(self, _obj):
        return None


class DashboardFinanceServerAuditTests(unittest.IsolatedAsyncioTestCase):
    def _audit_payload(self, audit_mock: AsyncMock) -> dict:
        details = audit_mock.await_args_list[-1].args[4]
        self.assertIsInstance(details, str)
        return json.loads(details)

    async def test_create_finance_entry_audit_contains_after_snapshot(self) -> None:
        admin = SimpleNamespace(id=1, role="owner")
        session = _SessionWithValue(None)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services._get_active_dashboard_admins", new=AsyncMock(return_value=[])),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await create_finance_entry("income", "subscription", 500, "note", "DE-1", admin, "127.0.0.1", status="posted")

        payload = self._audit_payload(audit_mock)
        self.assertIsNone(payload["before"])
        self.assertEqual(payload["after"]["entry_type"], "income")
        self.assertEqual(payload["after"]["status"], "posted")

    async def test_approve_finance_entry_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=1)
        entry = FinanceEntry(
            id=77,
            entry_type="income",
            category="subscription",
            amount=500,
            currency="RUB",
            status="draft",
            occurred_at=datetime(2026, 4, 3, 10, 0, 0),
        )
        session = _SessionWithValue(entry)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services._get_active_dashboard_admins", new=AsyncMock(return_value=[])),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await approve_finance_entry(77, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["status"], "draft")
        self.assertEqual(payload["after"]["status"], "posted")

    async def test_cancel_finance_entry_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=1)
        entry = FinanceEntry(
            id=78,
            entry_type="expense",
            category="ops",
            amount=300,
            currency="RUB",
            status="draft",
            occurred_at=datetime(2026, 4, 3, 10, 0, 0),
        )
        session = _SessionWithValue(entry)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services._get_active_dashboard_admins", new=AsyncMock(return_value=[])),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await cancel_finance_entry(78, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["status"], "draft")
        self.assertEqual(payload["after"]["status"], "cancelled")

    async def test_delete_finance_entry_audit_contains_before_and_null_after(self) -> None:
        admin = SimpleNamespace(id=1)
        entry = FinanceEntry(
            id=79,
            entry_type="expense",
            category="ops",
            amount=300,
            currency="RUB",
            status="draft",
            occurred_at=datetime(2026, 4, 3, 10, 0, 0),
        )
        session = _SessionWithValue(entry)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await delete_finance_entry(79, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["status"], "draft")
        self.assertIsNone(payload["after"])

    async def test_service_action_audit_contains_before_and_after_status(self) -> None:
        admin = SimpleNamespace(id=1)

        with (
            patch("dashboard.services._system_command", new=AsyncMock(side_effect=[(0, "inactive"), (0, ""), (0, "active")])),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await service_action("restart", "amonora-dashboard.service", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["action"], "restart")
        self.assertEqual(payload["before_status"], "inactive")
        self.assertEqual(payload["after_status"], "active")

    async def test_create_managed_server_audit_contains_after_snapshot(self) -> None:
        admin = SimpleNamespace(id=1)
        session = _SessionWithValue(None)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await create_managed_server("DE-1", "10.0.0.1", "1.1.1.1", "DE", "Germany", "hetzner", "active", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertIsNone(payload["before"])
        self.assertEqual(payload["after"]["name"], "DE-1")
        self.assertEqual(payload["after"]["status"], "active")

    async def test_update_server_status_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=1)
        server = ManagedServer(
            id=55,
            name="DE-1",
            host="10.0.0.1",
            public_ip="1.1.1.1",
            country_code="DE",
            country_name="Germany",
            provider="hetzner",
            status="active",
            is_local=False,
        )
        session = _SessionWithValue(server)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await update_server_status(55, "maintenance", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["status"], "active")
        self.assertEqual(payload["after"]["status"], "maintenance")


if __name__ == "__main__":
    unittest.main()
