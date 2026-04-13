import unittest

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.models import DashboardAdmin, DashboardAuditLog, DashboardAuthLockoutState
from dashboard.security import hash_password, utcnow
from dashboard.services import (
    clear_dashboard_auth_failures,
    get_dashboard_auth_lockout_state,
    record_dashboard_auth_failure,
)


TEST_USERNAME = "test_dashboard_auth_lockout_admin"
TEST_PASSWORD = "test-dashboard-lockout-pass"
TEST_TELEGRAM_ID = 9900012399


class FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def one(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._scalar, list):
            return self._scalar
        return []


class MemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.admin = DashboardAdmin(
            id=27,
            username=TEST_USERNAME,
            display_name="Dashboard Lockout Admin",
            role="owner",
            telegram_id=TEST_TELEGRAM_ID,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
        )
        self.audit_logs: list[DashboardAuditLog] = []
        self.auth_lockouts: dict[tuple[str, str, str], DashboardAuthLockoutState] = {}
        self._next_lockout_id = 1


class FakeAsyncSession:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def execute(self, statement):
        text = str(statement)
        params = statement.compile().params

        if "FROM dashboard_auth_lockout_states" in text:
            key = (
                params.get("scope_1"),
                params.get("identity_type_1"),
                params.get("identity_value_1"),
            )
            return FakeResult(self.store.auth_lockouts.get(key))

        return FakeResult(None)

    async def commit(self) -> None:
        for obj in self.added:
            if isinstance(obj, DashboardAuthLockoutState):
                if obj.id is None:
                    obj.id = self.store._next_lockout_id
                    self.store._next_lockout_id += 1
                key = (obj.scope, obj.identity_type, obj.identity_value)
                self.store.auth_lockouts[key] = obj
            elif isinstance(obj, DashboardAuditLog):
                self.store.audit_logs.append(obj)
        self.added.clear()


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


class DashboardAuthLockoutStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()
        dashboard_main._PENDING_CODES.clear()
        dashboard_main._AUTH_RATE_LIMITS.clear()

    def fake_session_factory(self):
        return FakeAsyncSession(self.store)

    def make_request(self):
        return SimpleNamespace(
            method="POST",
            headers={"host": "testserver"},
            client=SimpleNamespace(host="127.0.0.1"),
            url=SimpleNamespace(netloc="testserver"),
            cookies={},
        )

    def test_record_dashboard_auth_failure_locks_and_clear_resets(self) -> None:
        now = utcnow()
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            for step in range(dashboard_services.DASHBOARD_AUTH_LOCKOUT_THRESHOLD):
                state = _run_async(
                    record_dashboard_auth_failure(
                        "request_code",
                        TEST_USERNAME,
                        ip_address="203.0.113.10",
                        now_utc=now + timedelta(seconds=step),
                    )
                )
            self.assertTrue(state["locked"])
            locked_state = _run_async(
                get_dashboard_auth_lockout_state(
                    "request_code",
                    TEST_USERNAME,
                    ip_address="203.0.113.10",
                    now_utc=now + timedelta(seconds=step),
                )
            )
            self.assertTrue(locked_state["locked"])
            _run_async(
                clear_dashboard_auth_failures(
                    "request_code",
                    TEST_USERNAME,
                    ip_address="203.0.113.10",
                    now_utc=now + timedelta(seconds=step + 1),
                )
            )
            cleared_state = _run_async(
                get_dashboard_auth_lockout_state(
                    "request_code",
                    TEST_USERNAME,
                    ip_address="203.0.113.10",
                    now_utc=now + timedelta(seconds=step + 1),
                )
            )

        self.assertFalse(cleared_state["locked"])
        self.assertEqual(int(cleared_state["failure_count"]), 0)

    def test_legacy_login_uses_persistent_lockout_after_repeated_invalid_credentials(self) -> None:
        request = self.make_request()
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=False)),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=None)),
        ):
            for _ in range(dashboard_services.DASHBOARD_AUTH_LOCKOUT_THRESHOLD):
                response = _run_async(dashboard_main.login_action(request, TEST_USERNAME, "wrong"))
                self.assertEqual(response.status_code, 303)
            locked_response = _run_async(dashboard_main.login_action(request, TEST_USERNAME, "wrong"))

        self.assertEqual(locked_response.status_code, 303)
        self.assertTrue(any(log.action == "auth_request_code_lockout" for log in self.store.audit_logs))

    def test_verify_success_clears_verify_scope_failures(self) -> None:
        request = self.make_request()
        now = utcnow()
        dashboard_main._PENDING_CODES[TEST_USERNAME] = {
            "code_hash": dashboard_main._hash_login_code("123456"),
            "admin_id": self.store.admin.id,
            "telegram_id": self.store.admin.telegram_id,
            "message_id": 1,
            "bot_key": "control",
            "attempts": 0,
            "created_at": now,
            "expires_at": now + timedelta(minutes=5),
        }

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "create_session", new=AsyncMock(return_value=None)),
            patch.object(dashboard_main, "delete_dashboard_login_code", new=AsyncMock(return_value=None)),
        ):
            for step in range(3):
                _run_async(
                    record_dashboard_auth_failure(
                        "verify_code",
                        TEST_USERNAME,
                        ip_address="127.0.0.1",
                        now_utc=now + timedelta(seconds=step),
                    )
                )
            response = _run_async(dashboard_main.verify_action(request, TEST_USERNAME, "123456"))
            state = _run_async(
                get_dashboard_auth_lockout_state(
                    "verify_code",
                    TEST_USERNAME,
                    ip_address="127.0.0.1",
                    now_utc=now + timedelta(seconds=5),
                )
            )

        self.assertEqual(response.status_code, 303)
        self.assertFalse(state["locked"])
        self.assertEqual(int(state["failure_count"]), 0)


if __name__ == "__main__":
    unittest.main()
