import json
import unittest

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.models import DashboardAdmin, DashboardAuditLog, DashboardLoginCode, DashboardSession
from dashboard.security import hash_password, hash_token, utcnow
from dashboard.services import create_session, get_admin_by_session, get_dashboard_auth_lockout_state


TEST_USERNAME = "test_dashboard_auth_followup_admin"
TEST_PASSWORD = "test-dashboard-followup-pass"
TEST_DISPLAY_NAME = "Dashboard Auth Followup"
TEST_TELEGRAM_ID = 9900012355


class FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
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
            id=17,
            username=TEST_USERNAME,
            display_name=TEST_DISPLAY_NAME,
            role="owner",
            telegram_id=TEST_TELEGRAM_ID,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
        )
        self.sessions: dict[str, DashboardSession] = {}
        self.login_codes: dict[str, DashboardLoginCode] = {}
        self.audit_logs: list[DashboardAuditLog] = []
        self._next_session_id = 1
        self._next_login_code_id = 1


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

        if "DELETE FROM dashboard_sessions" in text:
            if "id_1" in params:
                doomed = next((row for row in self.store.sessions.values() if row.id == params["id_1"]), None)
                if doomed is not None:
                    self.store.sessions.pop(doomed.token_hash, None)
            elif "token_hash_1" in params:
                self.store.sessions.pop(params["token_hash_1"], None)
            elif "admin_id_1" in params:
                self.store.sessions = {
                    key: value
                    for key, value in self.store.sessions.items()
                    if value.admin_id != params["admin_id_1"]
                }
            return FakeResult(None)

        if "DELETE FROM dashboard_login_codes" in text:
            if "id_1" in params:
                doomed = next((row for row in self.store.login_codes.values() if row.id == params["id_1"]), None)
                if doomed is not None:
                    self.store.login_codes.pop(doomed.username, None)
            elif "username_1" in params:
                self.store.login_codes.pop(params["username_1"], None)
            elif "expires_at_1" in params:
                cutoff = params["expires_at_1"]
                self.store.login_codes = {
                    key: value
                    for key, value in self.store.login_codes.items()
                    if value.expires_at > cutoff
                }
            return FakeResult(None)

        if "FROM dashboard_admins" in text:
            if "id_1" in params:
                return FakeResult(self.store.admin if self.store.admin.id == params["id_1"] else None)
            if "username_1" in params:
                return FakeResult(self.store.admin if self.store.admin.username == params["username_1"] else None)
            return FakeResult(None)

        if "FROM dashboard_sessions" in text:
            if "token_hash_1" in params:
                return FakeResult(self.store.sessions.get(params["token_hash_1"]))
            return FakeResult(None)

        if "FROM dashboard_login_codes" in text:
            if "username_1" in params:
                return FakeResult(self.store.login_codes.get(params["username_1"]))
            if "expires_at_1" in params:
                rows = [row for row in self.store.login_codes.values() if row.expires_at <= params["expires_at_1"]]
                return FakeResult(rows)
            return FakeResult(None)

        return FakeResult(None)

    async def commit(self) -> None:
        for obj in self.added:
            if isinstance(obj, DashboardSession):
                if obj.id is None:
                    obj.id = self.store._next_session_id
                    self.store._next_session_id += 1
                self.store.sessions[obj.token_hash] = obj
            elif isinstance(obj, DashboardLoginCode):
                if obj.id is None:
                    obj.id = self.store._next_login_code_id
                    self.store._next_login_code_id += 1
                self.store.login_codes[obj.username] = obj
            elif isinstance(obj, DashboardAuditLog):
                self.store.audit_logs.append(obj)
        self.added.clear()

    async def refresh(self, obj) -> None:
        if isinstance(obj, DashboardSession) and obj.id is None:
            obj.id = self.store._next_session_id
            self.store._next_session_id += 1
        if isinstance(obj, DashboardLoginCode) and obj.id is None:
            obj.id = self.store._next_login_code_id
            self.store._next_login_code_id += 1


class _AggregateResult:
    def __init__(self, row) -> None:
        self._row = row

    def one(self):
        return self._row


class _LockoutSession:
    def __init__(self, username_row, ip_row) -> None:
        self._rows = [username_row, ip_row]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        if "FROM dashboard_auth_lockout_states" in str(statement):
            return FakeResult(None)
        return _AggregateResult(self._rows.pop(0))


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


class DashboardAuthAuditFollowupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()
        dashboard_main._PENDING_CODES.clear()
        dashboard_main._AUTH_RATE_LIMITS.clear()

    def fake_session_factory(self):
        return FakeAsyncSession(self.store)

    def make_request(self, *, method: str = "POST", origin: str | None = None, host: str = "testserver", cookies: dict | None = None):
        headers = {"host": host}
        if origin:
            headers["origin"] = origin
        return SimpleNamespace(
            method=method,
            headers=headers,
            client=SimpleNamespace(host="127.0.0.1"),
            url=SimpleNamespace(netloc=host),
            cookies=cookies or {},
        )

    def test_get_admin_by_session_removes_session_for_inactive_admin(self) -> None:
        token = "inactive-admin-session"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            _run_async(create_session(self.store.admin.id, token))
            self.store.admin.is_active = False
            admin = _run_async(get_admin_by_session(token))

        self.assertIsNone(admin)
        self.assertNotIn(hash_token(token), self.store.sessions)

    def test_legacy_login_invalid_credentials_writes_auth_audit(self) -> None:
        request = self.make_request()
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.login_action(request, "missing-admin", TEST_PASSWORD))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_request_code_invalid_credentials" for log in self.store.audit_logs))

    def test_v2_request_code_rate_limit_writes_auth_audit(self) -> None:
        request = self.make_request()
        payload = dashboard_main.V2LoginRequest(username=TEST_USERNAME, password=TEST_PASSWORD)
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=True)),
        ):
            response = _run_async(dashboard_main.v2_auth_request_code(request, payload))

        self.assertEqual(response.status_code, 429)
        self.assertTrue(any(log.action == "auth_request_code_rate_limited_v2" for log in self.store.audit_logs))

    def test_legacy_request_code_rate_limit_writes_auth_audit(self) -> None:
        request = self.make_request()
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=True)),
        ):
            response = _run_async(dashboard_main.login_action(request, TEST_USERNAME, TEST_PASSWORD))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_request_code_rate_limited" for log in self.store.audit_logs))

    def test_legacy_request_code_lockout_writes_auth_audit(self) -> None:
        request = self.make_request()
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=False)),
            patch.object(dashboard_main, "get_dashboard_auth_lockout_state", new=AsyncMock(return_value={"locked": True, "retry_after_seconds": 120})),
        ):
            response = _run_async(dashboard_main.login_action(request, TEST_USERNAME, TEST_PASSWORD))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_request_code_lockout" for log in self.store.audit_logs))

    def test_v2_verify_missing_code_writes_auth_audit(self) -> None:
        request = self.make_request()
        payload = dashboard_main.V2VerifyRequest(username=TEST_USERNAME, code="123456")
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.v2_auth_verify(request, payload))

        self.assertEqual(response.status_code, 401)
        self.assertTrue(any(log.action == "auth_verify_code_missing_v2" for log in self.store.audit_logs))

    def test_v2_request_code_lockout_writes_auth_audit(self) -> None:
        request = self.make_request()
        payload = dashboard_main.V2LoginRequest(username=TEST_USERNAME, password=TEST_PASSWORD)
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=False)),
            patch.object(dashboard_main, "get_dashboard_auth_lockout_state", new=AsyncMock(return_value={"locked": True, "retry_after_seconds": 120})),
        ):
            response = _run_async(dashboard_main.v2_auth_request_code(request, payload))

        self.assertEqual(response.status_code, 429)
        self.assertTrue(any(log.action == "auth_request_code_lockout_v2" for log in self.store.audit_logs))

    def test_legacy_verify_missing_code_writes_auth_audit(self) -> None:
        request = self.make_request()
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.verify_action(request, TEST_USERNAME, "123456"))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_verify_code_missing" for log in self.store.audit_logs))

    def test_auth_lockout_uses_ip_failures_when_username_failures_are_low(self) -> None:
        now = utcnow()
        session = _LockoutSession(
            username_row=(1, now - timedelta(seconds=5)),
            ip_row=(12, now - timedelta(seconds=5)),
        )

        with patch.object(dashboard_services, "async_session", return_value=session):
            state = _run_async(
                get_dashboard_auth_lockout_state(
                    "request_code",
                    TEST_USERNAME,
                    ip_address="203.0.113.77",
                    now_utc=now,
                )
        )

        self.assertTrue(state["locked"])
        self.assertGreaterEqual(int(state["failure_count"]), 12)
        self.assertGreater(int(state["retry_after_seconds"]), 0)

    def test_legacy_verify_lockout_writes_auth_audit(self) -> None:
        request = self.make_request()
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=False)),
            patch.object(dashboard_main, "get_dashboard_auth_lockout_state", new=AsyncMock(return_value={"locked": True, "retry_after_seconds": 120})),
        ):
            response = _run_async(dashboard_main.verify_action(request, TEST_USERNAME, "123456"))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_verify_lockout" for log in self.store.audit_logs))

    def test_v2_verify_lockout_writes_auth_audit(self) -> None:
        request = self.make_request()
        payload = dashboard_main.V2VerifyRequest(username=TEST_USERNAME, code="123456")
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "_hit_dashboard_auth_rate_limit", new=AsyncMock(return_value=False)),
            patch.object(dashboard_main, "get_dashboard_auth_lockout_state", new=AsyncMock(return_value={"locked": True, "retry_after_seconds": 120})),
        ):
            response = _run_async(dashboard_main.v2_auth_verify(request, payload))

        self.assertEqual(response.status_code, 429)
        self.assertTrue(any(log.action == "auth_verify_lockout_v2" for log in self.store.audit_logs))

    def test_v2_verify_invalid_code_writes_auth_audit(self) -> None:
        request = self.make_request()
        username = TEST_USERNAME
        dashboard_main._PENDING_CODES[username] = {
            "code_hash": dashboard_main._hash_login_code("123456"),
            "admin_id": self.store.admin.id,
            "telegram_id": self.store.admin.telegram_id,
            "message_id": 1,
            "bot_key": "control",
            "attempts": 0,
            "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(minutes=5),
        }
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.v2_auth_verify(request, dashboard_main.V2VerifyRequest(username=username, code="000000")))

        self.assertEqual(response.status_code, 401)
        self.assertTrue(any(log.action == "auth_verify_invalid_code_v2" for log in self.store.audit_logs))

    def test_legacy_verify_invalid_code_writes_auth_audit(self) -> None:
        request = self.make_request()
        username = TEST_USERNAME
        dashboard_main._PENDING_CODES[username] = {
            "code_hash": dashboard_main._hash_login_code("123456"),
            "admin_id": self.store.admin.id,
            "telegram_id": self.store.admin.telegram_id,
            "message_id": 1,
            "bot_key": "control",
            "attempts": 0,
            "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(minutes=5),
        }
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.verify_action(request, username, "000000"))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_verify_invalid_code" for log in self.store.audit_logs))

    def test_v2_verify_success_writes_auth_audit(self) -> None:
        request = self.make_request()
        username = TEST_USERNAME
        dashboard_main._PENDING_CODES[username] = {
            "code_hash": dashboard_main._hash_login_code("123456"),
            "admin_id": self.store.admin.id,
            "telegram_id": self.store.admin.telegram_id,
            "message_id": 1,
            "bot_key": "control",
            "attempts": 0,
            "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(minutes=5),
        }
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.v2_auth_verify(request, dashboard_main.V2VerifyRequest(username=username, code="123456")))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(log.action == "auth_verify_success_v2" for log in self.store.audit_logs))

    def test_legacy_verify_success_writes_auth_audit(self) -> None:
        request = self.make_request()
        username = TEST_USERNAME
        dashboard_main._PENDING_CODES[username] = {
            "code_hash": dashboard_main._hash_login_code("123456"),
            "admin_id": self.store.admin.id,
            "telegram_id": self.store.admin.telegram_id,
            "message_id": 1,
            "bot_key": "control",
            "attempts": 0,
            "created_at": utcnow(),
            "expires_at": utcnow() + timedelta(minutes=5),
        }
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = _run_async(dashboard_main.verify_action(request, username, "123456"))

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_verify_success" for log in self.store.audit_logs))

    def test_request_login_code_audit_contains_delivery_details(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "send_panel_auth_code", new=AsyncMock(return_value=(77, "control"))),
        ):
            _run_async(dashboard_main._request_dashboard_login_code(self.store.admin, "request_login_code", "127.0.0.1"))

        payload = json.loads(self.store.audit_logs[-1].details_text)
        self.assertEqual(payload["admin"]["username"], TEST_USERNAME)
        self.assertEqual(payload["delivery"]["bot_key"], "control")
        self.assertEqual(payload["delivery"]["message_id"], 77)

    def test_logout_audit_contains_session_fingerprint(self) -> None:
        token = "logout-audit-session"
        request = self.make_request(cookies={dashboard_services.dashboard_settings()["cookie_name"]: token})
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            _run_async(create_session(self.store.admin.id, token))
            response = _run_async(dashboard_main.logout(request, self.store.admin))

        self.assertEqual(response.status_code, 303)
        payload = json.loads(self.store.audit_logs[-1].details_text)
        self.assertEqual(payload["admin"]["username"], TEST_USERNAME)
        self.assertEqual(payload["session"]["fingerprint"], hash_token(token)[:16])
        self.assertTrue(payload["session"]["had_cookie"])

    def test_notification_preference_audit_contains_before_after(self) -> None:
        request = self.make_request()
        payload = dashboard_main.V2NotificationPreferenceRequest(
            telegram_id=TEST_TELEGRAM_ID,
            category="payments",
            enabled=False,
        )
        before = {"payments": True, "incidents": True}
        after = {"payments": False, "incidents": True}
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "get_notification_preferences", new=AsyncMock(return_value=before)),
            patch.object(dashboard_main, "set_notification_preference", new=AsyncMock(return_value=after)),
            patch.object(dashboard_main, "_invalidate_v2_cache", new=AsyncMock()),
            patch.object(dashboard_main, "get_v2_settings_payload", new=AsyncMock(return_value={})),
        ):
            response = _run_async(dashboard_main.v2_settings_notifications(request, payload, self.store.admin))

        self.assertEqual(response.status_code, 200)
        details = json.loads(self.store.audit_logs[-1].details_text)
        self.assertEqual(details["before"]["enabled"], True)
        self.assertEqual(details["after"]["enabled"], False)
        self.assertEqual(details["admin"]["username"], TEST_USERNAME)


if __name__ == "__main__":
    unittest.main()
