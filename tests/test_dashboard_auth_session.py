import unittest

from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.models import DashboardAdmin, DashboardAuditLog, DashboardLoginCode, DashboardSession
from dashboard.security import hash_password, hash_token, utcnow
from dashboard.services import (
    create_session,
    dashboard_settings,
    delete_session,
    get_admin_by_session,
    verify_admin_credentials,
)


TEST_USERNAME = "test_dashboard_auth_session_admin"
TEST_PASSWORD = "test-dashboard-pass-010"
TEST_DISPLAY_NAME = "Dashboard Auth Session Test"
TEST_TELEGRAM_ID = 9900012345


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
            id=7,
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
        self.commit_calls = 0

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
            if "token_hash_1" in params:
                self.store.sessions.pop(params["token_hash_1"], None)
            elif "id_1" in params:
                session = next(
                    (item for item in self.store.sessions.values() if item.id == params["id_1"]),
                    None,
                )
                if session is not None:
                    self.store.sessions.pop(session.token_hash, None)
            elif "admin_id_1" in params:
                self.store.sessions = {
                    key: value
                    for key, value in self.store.sessions.items()
                    if value.admin_id != params["admin_id_1"]
                }
            return FakeResult(None)

        if "DELETE FROM dashboard_login_codes" in text:
            if "id_1" in params:
                row = next((item for item in self.store.login_codes.values() if item.id == params["id_1"]), None)
                if row is not None:
                    self.store.login_codes.pop(row.username, None)
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

        if "DELETE FROM dashboard_audit_logs" in text:
            self.store.audit_logs.clear()
            return FakeResult(None)

        if "FROM dashboard_admins" in text:
            if "username_1" in params:
                admin = self.store.admin if self.store.admin.username == params["username_1"] else None
                return FakeResult(admin)
            if "id_1" in params:
                admin = self.store.admin if self.store.admin.id == params["id_1"] else None
                return FakeResult(admin)
            return FakeResult(None)

        if "FROM dashboard_sessions" in text:
            if "token_hash_1" in params:
                return FakeResult(self.store.sessions.get(params["token_hash_1"]))
            return FakeResult(None)

        if "FROM dashboard_login_codes" in text:
            if "username_1" in params:
                return FakeResult(self.store.login_codes.get(params["username_1"]))
            if "expires_at_1" in params:
                rows = [item for item in self.store.login_codes.values() if item.expires_at <= params["expires_at_1"]]
                return FakeResult(rows)
            return FakeResult(None)

        return FakeResult(None)

    async def commit(self) -> None:
        self.commit_calls += 1
        for obj in self.added:
            if isinstance(obj, DashboardSession):
                if obj.id is None:
                    obj.id = self.store._next_session_id
                    self.store._next_session_id += 1
                self.store.sessions[obj.token_hash] = obj
            elif isinstance(obj, DashboardAuditLog):
                self.store.audit_logs.append(obj)
            elif isinstance(obj, DashboardLoginCode):
                if obj.id is None:
                    obj.id = self.store._next_login_code_id
                    self.store._next_login_code_id += 1
                self.store.login_codes[obj.username] = obj
        self.added.clear()

    async def refresh(self, obj) -> None:
        if isinstance(obj, DashboardSession) and obj.id is None:
            obj.id = self.store._next_session_id
            self.store._next_session_id += 1
        if isinstance(obj, DashboardLoginCode) and obj.id is None:
            obj.id = self.store._next_login_code_id
            self.store._next_login_code_id += 1


class DashboardAuthSessionSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = MemoryStore()
        cls.startup_handlers = list(dashboard_main.app.router.on_startup)
        dashboard_main.app.router.on_startup.clear()
        cls.original_lifespan_context = dashboard_main.app.router.lifespan_context

        @asynccontextmanager
        async def _test_lifespan(app):
            yield

        dashboard_main.app.router.lifespan_context = _test_lifespan
        cls.client_cm = TestClient(dashboard_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        dashboard_main.app.router.lifespan_context = cls.original_lifespan_context
        dashboard_main.app.router.on_startup[:] = cls.startup_handlers

    def setUp(self) -> None:
        self.store.reset()
        self.client.cookies.clear()
        dashboard_main._PENDING_CODES.clear()
        dashboard_main._AUTH_RATE_LIMITS.clear()

    def fake_session_factory(self):
        return FakeAsyncSession(self.store)

    def set_session_cookie(self, token: str) -> None:
        self.client.cookies.set(dashboard_settings()["cookie_name"], token)

    def test_verify_admin_credentials_returns_admin_for_valid_credentials(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            admin = self._run(verify_admin_credentials(TEST_USERNAME, TEST_PASSWORD))
        self.assertIsNotNone(admin)
        self.assertEqual(admin.username, TEST_USERNAME)

    def test_verify_admin_credentials_returns_none_for_invalid_login(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            admin = self._run(verify_admin_credentials("missing-admin", TEST_PASSWORD))
        self.assertIsNone(admin)

    def test_verify_admin_credentials_returns_none_for_invalid_password(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            admin = self._run(verify_admin_credentials(TEST_USERNAME, "wrong-password"))
        self.assertIsNone(admin)

    def test_create_session_persists_session_for_admin(self) -> None:
        token = "session-create-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))

        stored = self.store.sessions.get(hash_token(token))
        self.assertIsNotNone(stored)
        self.assertEqual(stored.admin_id, self.store.admin.id)
        self.assertIsNotNone(self.store.admin.last_login_at)

    def test_get_admin_by_session_returns_admin_for_valid_session(self) -> None:
        token = "session-valid-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            admin = self._run(get_admin_by_session(token))

        self.assertIsNotNone(admin)
        self.assertEqual(admin.username, TEST_USERNAME)

    def test_get_admin_by_session_returns_none_for_unknown_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            admin = self._run(get_admin_by_session("unknown-token"))
        self.assertIsNone(admin)

    def test_get_admin_by_session_returns_none_for_expired_session(self) -> None:
        token = "session-expired-token"
        token_hash = hash_token(token)
        self.store.sessions[token_hash] = DashboardSession(
            id=1,
            admin_id=self.store.admin.id,
            token_hash=token_hash,
            expires_at=utcnow() - timedelta(minutes=5),
            last_seen_at=utcnow() - timedelta(minutes=10),
        )

        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            admin = self._run(get_admin_by_session(token))

        self.assertIsNone(admin)
        self.assertNotIn(token_hash, self.store.sessions)

    def test_get_admin_by_session_removes_session_for_inactive_admin(self) -> None:
        token = "session-inactive-admin-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.store.admin.is_active = False
            admin = self._run(get_admin_by_session(token))

        self.assertIsNone(admin)
        self.assertNotIn(hash_token(token), self.store.sessions)

    def test_delete_session_removes_existing_session(self) -> None:
        token = "session-delete-token"
        token_hash = hash_token(token)
        self.store.sessions[token_hash] = DashboardSession(
            id=1,
            admin_id=self.store.admin.id,
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(hours=1),
            last_seen_at=utcnow(),
        )

        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(delete_session(token))

        self.assertNotIn(token_hash, self.store.sessions)

    def test_delete_session_makes_session_unresolvable(self) -> None:
        token = "session-delete-and-resolve-token"
        token_hash = hash_token(token)
        self.store.sessions[token_hash] = DashboardSession(
            id=1,
            admin_id=self.store.admin.id,
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(hours=1),
            last_seen_at=utcnow(),
        )

        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(delete_session(token))
            admin = self._run(get_admin_by_session(token))

        self.assertIsNone(admin)

    def test_dashboard_api_v2_session_returns_401_without_cookie(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.get("/dashboard/api/v2/session")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_session_returns_admin_payload_for_valid_session_cookie(self) -> None:
        token = "api-valid-session-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/session")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["admin"]["username"], TEST_USERNAME)

    def test_dashboard_api_v2_session_hides_missing_avatar_file(self) -> None:
        token = "api-missing-avatar-token"
        self.store.admin.avatar_path = "/dashboard/static/avatars/admin-1-missing.png"
        missing_target = Path(dashboard_main.BASE_DIR / "static" / "avatars" / "admin-1-missing.png")

        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch("dashboard.v2_data.ADMIN_AVATAR_ROOT", missing_target.parent),
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.get("/dashboard/api/v2/session")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIsNone(payload["admin"]["avatar_url"])
        self.assertIsNone(payload["profile"]["avatar_url"])

    def test_dashboard_api_v2_logout_clears_session_for_valid_cookie(self) -> None:
        token = "api-logout-session-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertNotIn(hash_token(token), self.store.sessions)
        self.assertTrue(any(log.action == "logout_v2" for log in self.store.audit_logs))

    def test_dashboard_api_v2_logout_rejects_cross_site_origin(self) -> None:
        token = "api-logout-cross-site-token"
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post(
                "/dashboard/api/v2/auth/logout",
                headers={"origin": "https://evil.example"},
            )

        self.assertEqual(response.status_code, 403)

    def test_legacy_login_rejects_cross_site_origin(self) -> None:
        response = self.client.post(
            "/login",
            data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            headers={"origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_legacy_verify_rejects_cross_site_origin(self) -> None:
        response = self.client.post(
            "/verify",
            data={"username": TEST_USERNAME, "code": "123456"},
            headers={"origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_api_v2_logout_is_safe_without_session_cookie(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.post("/dashboard/api/v2/auth/logout")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_request_code_points_to_control_bot(self) -> None:
        request_code_mock = AsyncMock()
        with (
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "_request_dashboard_login_code", request_code_mock),
        ):
            response = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["delivery"]["bot"], "@amonora_control_bot")
        self.assertEqual(payload["notice"], "Код отправлен в @amonora_control_bot")
        request_code_mock.assert_awaited_once()

    def test_dashboard_api_v2_request_code_rejects_cross_site_origin(self) -> None:
        response = self.client.post(
            "/dashboard/api/v2/auth/request-code",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            headers={"origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_api_v2_verify_uses_durable_login_code_when_memory_cache_is_empty(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "generate_code", return_value="123456"),
            patch.object(dashboard_main, "send_panel_auth_code", new=AsyncMock(return_value=(555, "control"))),
        ):
            request_response = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            self.assertEqual(request_response.status_code, 200)

            dashboard_main._PENDING_CODES.clear()
            verify_response = self.client.post(
                "/dashboard/api/v2/auth/verify",
                json={"username": TEST_USERNAME, "code": "123456"},
            )

        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["ok"])
        self.assertFalse(self.store.login_codes)

    def test_dashboard_api_v2_verify_rejects_cross_site_origin(self) -> None:
        response = self.client.post(
            "/dashboard/api/v2/auth/verify",
            json={"username": TEST_USERNAME, "code": "123456"},
            headers={"origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_api_v2_request_code_has_server_side_cooldown(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "generate_code", return_value="123456"),
            patch.object(dashboard_main, "send_panel_auth_code", new=AsyncMock(return_value=(555, "control"))),
        ):
            first = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            second = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_legacy_login_invalid_credentials_writes_auth_audit(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.post(
                "/login",
                data={"username": "missing-admin", "password": TEST_PASSWORD},
            )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(any(log.action == "auth_request_code_invalid_credentials" for log in self.store.audit_logs))

    def test_dashboard_api_v2_request_code_rate_limit_writes_auth_audit(self) -> None:
        request_code_mock = AsyncMock()
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "_request_dashboard_login_code", request_code_mock),
        ):
            for _ in range(dashboard_main.AUTH_REQUEST_LIMIT):
                response = self.client.post(
                    "/dashboard/api/v2/auth/request-code",
                    json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
                )
                self.assertEqual(response.status_code, 200)
            limited = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )

        self.assertEqual(limited.status_code, 429)
        self.assertTrue(any(log.action == "auth_request_code_rate_limited_v2" for log in self.store.audit_logs))

    def test_dashboard_api_v2_verify_missing_code_writes_auth_audit(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.post(
                "/dashboard/api/v2/auth/verify",
                json={"username": TEST_USERNAME, "code": "123456"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertTrue(any(log.action == "auth_verify_code_missing_v2" for log in self.store.audit_logs))

    def test_dashboard_api_v2_verify_invalid_code_writes_auth_audit(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "generate_code", return_value="123456"),
            patch.object(dashboard_main, "send_panel_auth_code", new=AsyncMock(return_value=(555, "control"))),
        ):
            request_response = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            self.assertEqual(request_response.status_code, 200)
            response = self.client.post(
                "/dashboard/api/v2/auth/verify",
                json={"username": TEST_USERNAME, "code": "000000"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertTrue(any(log.action == "auth_verify_invalid_code_v2" for log in self.store.audit_logs))

    def test_dashboard_api_v2_verify_success_writes_auth_audit(self) -> None:
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(dashboard_main, "verify_admin_credentials", new=AsyncMock(return_value=self.store.admin)),
            patch.object(dashboard_main, "generate_code", return_value="123456"),
            patch.object(dashboard_main, "send_panel_auth_code", new=AsyncMock(return_value=(555, "control"))),
        ):
            request_response = self.client.post(
                "/dashboard/api/v2/auth/request-code",
                json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            )
            self.assertEqual(request_response.status_code, 200)
            response = self.client.post(
                "/dashboard/api/v2/auth/verify",
                json={"username": TEST_USERNAME, "code": "123456"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(log.action == "auth_verify_success_v2" for log in self.store.audit_logs))

    def test_auth_rate_limit_applies_per_username_even_from_different_ips(self) -> None:
        request_a = SimpleNamespace(client=SimpleNamespace(host="198.51.100.10"), headers={})
        request_b = SimpleNamespace(client=SimpleNamespace(host="198.51.100.11"), headers={})

        first = self._run(
            dashboard_main._hit_dashboard_auth_rate_limit(
                "request_code",
                request_a,
                TEST_USERNAME,
                limit=1,
                window_seconds=300,
            )
        )
        second = self._run(
            dashboard_main._hit_dashboard_auth_rate_limit(
                "request_code",
                request_b,
                TEST_USERNAME,
                limit=1,
                window_seconds=300,
            )
        )

        self.assertFalse(first)
        self.assertTrue(second)

    def test_client_ip_prefers_forwarded_ip_for_local_proxy_peer(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"cf-connecting-ip": "198.51.100.77"},
        )

        result = dashboard_main._client_ip(request)

        self.assertEqual(result, "198.51.100.77")

    def test_client_ip_prefers_dedicated_proxy_header_for_local_proxy_peer(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-amonora-client-ip": "203.0.113.14"},
        )

        result = dashboard_main._client_ip(request)

        self.assertEqual(result, "203.0.113.14")

    def test_client_ip_ignores_spoofed_forwarded_header_from_untrusted_peer(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.15"),
            headers={"x-amonora-client-ip": "203.0.113.14"},
        )

        result = dashboard_main._client_ip(request)

        self.assertEqual(result, "198.51.100.15")

def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardAuthSessionSmokeTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
