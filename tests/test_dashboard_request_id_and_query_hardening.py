import unittest

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.responses import Response
from starlette.requests import Request

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
import dashboard.v2_data as dashboard_v2_data
import control_bot.dispatcher as control_dispatcher


class _AuditWriteSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, item) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.committed = True


class _MetricsNoAuditQuerySession:
    def __init__(self, *, users, clients, payments) -> None:
        self._users = users
        self._clients = clients
        self._payments = payments

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "FROM dashboard_audit_logs" in text:
            raise AssertionError("overview_metrics should not full-scan dashboard_audit_logs anymore")
        if "FROM vpn_clients" in text:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._clients))
        if "FROM payment_records" in text:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._payments))
        if "FROM users" in text:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._users))
        raise AssertionError(f"unexpected query: {text}")


class _TrafficWindowSession:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self.executed.append(text)
        if "FROM dashboard_audit_logs" in text:
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [datetime(2026, 4, 3, 11, 0, 0)])
            )
        if "FROM support_ticket_messages" in text:
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [datetime(2026, 4, 3, 12, 0, 0)])
            )
        raise AssertionError(f"unexpected query: {text}")


class _RepairCountSession:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self.executed.append(text)
        return SimpleNamespace(all=lambda: [(1, 3), (2, 1)])


class _PaymentFilterSession:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self.executed.append(text)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))


class _UsersLookupSession:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self.executed.append(text)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))


class DashboardRequestIdAndQueryHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_audit_log_includes_request_id_from_context(self) -> None:
        session = _AuditWriteSession()
        token = dashboard_services.set_current_audit_request_id("req-test-123")
        try:
            with patch.object(dashboard_services, "async_session", return_value=session):
                await dashboard_services.create_audit_log(1, "demo_action", "user", "42", "{}", "127.0.0.1")
        finally:
            dashboard_services.reset_current_audit_request_id(token)

        self.assertTrue(session.committed)
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.added[0].request_id, "req-test-123")

    async def test_dashboard_request_id_middleware_sets_response_header(self) -> None:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/dashboard/api/v2/session",
            "raw_path": b"/dashboard/api/v2/session",
            "query_string": b"",
            "headers": [(b"host", b"localhost"), (b"x-request-id", b"req-from-client")],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 80),
            "scheme": "http",
        }
        request = Request(scope)

        async def call_next(incoming_request):
            self.assertEqual(incoming_request.state.request_id, "req-from-client")
            self.assertEqual(dashboard_services.get_current_audit_request_id(), "req-from-client")
            return Response("ok", media_type="text/plain")

        response = await dashboard_main.dashboard_request_id_middleware(request, call_next)

        self.assertEqual(response.headers.get("X-Request-ID"), "req-from-client")
        self.assertIsNone(dashboard_services.get_current_audit_request_id())

    async def test_dashboard_control_event_includes_request_id_from_context(self) -> None:
        token = dashboard_services.set_current_audit_request_id("req-control-123")
        try:
            with patch.object(dashboard_services, "_create_control_event", new=AsyncMock()) as control_event_mock:
                await dashboard_services.create_control_event(
                    category="users",
                    severity="INFO",
                    event_type="demo_event",
                    title="Demo",
                    message="demo",
                )
        finally:
            dashboard_services.reset_current_audit_request_id(token)

        control_event_mock.assert_awaited_once()
        self.assertEqual(control_event_mock.await_args.kwargs.get("request_id"), "req-control-123")

    def test_control_event_payload_includes_request_id_when_column_is_present(self) -> None:
        event = SimpleNamespace(payload_json='{"user_id": 42}', request_id="req-ctrl-1")

        payload = control_dispatcher.event_payload(event)

        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["request_id"], "req-ctrl-1")

    async def test_dashboard_request_id_middleware_blocks_cross_site_unsafe_dashboard_request(self) -> None:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/dashboard/api/v2/auth/logout",
            "raw_path": b"/dashboard/api/v2/auth/logout",
            "query_string": b"",
            "headers": [
                (b"host", b"panel.example"),
                (b"origin", b"https://evil.example"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("panel.example", 443),
            "scheme": "https",
        }
        request = Request(scope)

        async def call_next(_incoming_request):
            raise AssertionError("cross-site request should be rejected before reaching the handler")

        response = await dashboard_main.dashboard_request_id_middleware(request, call_next)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("content-type"), "application/json")

    async def test_dashboard_request_id_middleware_accepts_forwarded_host_for_same_origin_proxy(self) -> None:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/dashboard/api/v2/payments/176/reject",
            "raw_path": b"/dashboard/api/v2/payments/176/reject",
            "query_string": b"",
            "headers": [
                (b"host", b"127.0.0.1:8088"),
                (b"x-forwarded-host", b"amonoraconnect.com"),
                (b"x-forwarded-proto", b"https"),
                (b"origin", b"https://amonoraconnect.com"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8088),
            "scheme": "http",
        }
        request = Request(scope)

        async def call_next(_incoming_request):
            return Response("ok", media_type="text/plain")

        response = await dashboard_main.dashboard_request_id_middleware(request, call_next)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"ok")

    async def test_overview_metrics_uses_recent_audit_helper_instead_of_full_scan(self) -> None:
        now = datetime(2026, 4, 3, 18, 0, 0)
        real_user = SimpleNamespace(
            id=1,
            telegram_id=1001,
            username="alice",
            subscription_expires_at=now + timedelta(days=10),
            trial_expires_at=None,
            trial_used=False,
            trial_started_at=None,
            subscription_status="active",
            is_blocked=False,
            preferred_protocol="vless",
            created_at=now - timedelta(days=1),
        )
        client = SimpleNamespace(
            id=11,
            user_id=1,
            protocol="vless",
            client_data='{"country_code":"de"}',
            created_at=now - timedelta(hours=5),
        )
        payment = SimpleNamespace(
            id=21,
            user_id=1,
            payment_status="confirmed",
            payment_method="sbp_platega",
            amount=149,
            confirmed_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=3),
        )
        session = _MetricsNoAuditQuerySession(users=[real_user], clients=[client], payments=[payment])

        with (
            patch.object(dashboard_services, "async_session", return_value=session),
            patch.object(dashboard_services, "recent_audit_logs", new=AsyncMock(return_value=[])) as recent_audits_mock,
            patch.object(dashboard_services, "get_support_dashboard_counts", new=AsyncMock(return_value={"new": 0, "in_progress": 0, "closed": 0, "all": 0, "mine": 0})),
            patch.object(dashboard_services, "get_service_statuses", new=AsyncMock(return_value={})),
            patch.object(dashboard_services, "get_server_snapshots", new=AsyncMock(return_value=[])),
            patch.object(dashboard_services, "utcnow", return_value=now),
        ):
            metrics = await dashboard_services.overview_metrics(force_refresh=True)

        recent_audits_mock.assert_awaited_once_with(8)
        self.assertEqual(metrics["total_users"], 1)
        self.assertEqual(metrics["recent_audit"], [])

    async def test_v2_overview_reuses_region_metrics_rows_for_overview_metrics(self) -> None:
        region_metrics = {
            "users": [
                SimpleNamespace(
                    id=1,
                    username="alice",
                    telegram_id=1001,
                    created_at=datetime(2026, 4, 2, 18, 0, 0),
                    is_blocked=False,
                )
            ],
            "clients": [],
            "payments": [],
            "region_stats": {},
            "real_user_count": 1,
            "trial_active_count": 0,
            "paid_active_count": 0,
            "inactive_count": 1,
            "trial_used_count": 0,
            "plan_counts": {},
        }
        metrics_mock = AsyncMock(
            return_value={
                "servers": [],
                "payment_counts": {"revenue_30d": 0, "pending": 0, "open_manual": 0},
                "support_counts": {"new": 0, "in_progress": 0},
                "recent_audit": [],
                "alerts": [],
                "service_statuses": {},
                "backup_status": {"status": "healthy", "backup_stale": False, "last_backup_at": "2026-04-03 10:00"},
                "restore_validation_status": {"status": "healthy", "restore_validation_stale": False},
            }
        )

        with (
            patch.object(dashboard_v2_data, "_collect_region_and_plan_metrics", new=AsyncMock(return_value=region_metrics)),
            patch.object(dashboard_v2_data, "overview_metrics", metrics_mock),
            patch.object(dashboard_v2_data, "_load_failed_repair_counts_for_users", new=AsyncMock(return_value={})),
            patch.object(dashboard_v2_data, "_get_admin_lookup", new=AsyncMock(return_value={})),
            patch.object(dashboard_v2_data, "get_support_tickets", new=AsyncMock(return_value=[])),
            patch.object(dashboard_v2_data, "recent_audit_logs", new=AsyncMock(return_value=[])),
            patch.object(dashboard_v2_data, "utcnow", return_value=datetime(2026, 4, 3, 18, 0, 0)),
            patch.object(dashboard_v2_data, "dashboard_local_date", side_effect=lambda value: value.date() if value else None),
        ):
            payload = await dashboard_v2_data.get_v2_overview_payload()

        metrics_mock.assert_awaited_once_with(source_rows=region_metrics)
        self.assertIn("kpis", payload)

    async def test_v2_traffic_payload_queries_only_recent_audit_and_support_timestamps(self) -> None:
        session = _TrafficWindowSession()
        region_metrics = {
            "clients": [],
            "users": [],
            "payments": [],
            "region_stats": {},
        }

        with (
            patch.object(dashboard_v2_data, "async_session", return_value=session),
            patch.object(dashboard_v2_data, "_collect_region_and_plan_metrics", new=AsyncMock(return_value=region_metrics)),
            patch.object(dashboard_v2_data, "get_server_snapshots", new=AsyncMock(return_value=[])),
            patch.object(dashboard_v2_data, "ensure_current_traffic_baseline", new=AsyncMock(return_value={})),
            patch.object(dashboard_v2_data, "apply_traffic_baseline_to_snapshots", return_value=([], {})),
            patch.object(dashboard_v2_data, "utcnow", return_value=datetime(2026, 4, 3, 18, 0, 0)),
        ):
            payload = await dashboard_v2_data.get_v2_traffic_payload(force_refresh=True)

        self.assertEqual(len(payload["peak_hours"]), 24)
        self.assertTrue(any("FROM dashboard_audit_logs" in text and "created_at >=" in text for text in session.executed))
        self.assertTrue(any("FROM support_ticket_messages" in text and "created_at >=" in text for text in session.executed))

    async def test_load_failed_repair_counts_for_users_uses_grouped_query(self) -> None:
        session = _RepairCountSession()

        with patch.object(dashboard_v2_data, "async_session", return_value=session):
            mapping = await dashboard_v2_data._load_failed_repair_counts_for_users([1, 2, 2])

        self.assertEqual(mapping, {1: 3, 2: 1})
        self.assertTrue(any("GROUP BY vpn_repair_events.user_id" in text for text in session.executed))

    async def test_restore_validation_status_prefers_machine_readable_json_signal(self) -> None:
        with TemporaryDirectory() as tmpdir:
            status_path = Path(tmpdir) / "restore-proof.json"
            status_path.write_text(
                '{"status":"healthy","last_restore_validation_at":"2026-04-03T11:00:00Z","validated_public_tables":42,"proof_kind":"temporary_database_restore","proof_status":"verified","proof_scope":["core_pg"]}',
                encoding="utf-8",
            )
            with (
                patch.object(dashboard_services, "RESTORE_PROOF_STATUS_PATH", status_path),
                patch.object(dashboard_services, "RESTORE_VALIDATION_STATUS_PATH", Path(tmpdir) / "restore-validation.json"),
            ):
                payload = dashboard_services._build_restore_validation_status(now=datetime(2026, 4, 3, 18, 0, 0))

        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["signal_source"], "machine-readable restore proof status")
        self.assertFalse(payload["restore_validation_stale"])

    async def test_get_payment_records_pushes_filters_into_sql(self) -> None:
        session = _PaymentFilterSession()

        with patch.object(dashboard_services, "async_session", return_value=session):
            await dashboard_services.get_payment_records(
                search="alice",
                status_filter="confirmed",
                method_filter="sbp_manual",
                issue_filter="problem",
            )

        query_text = "\n".join(session.executed)
        self.assertIn("LEFT OUTER JOIN users ON users.id = payment_records.user_id", query_text)
        self.assertIn("lower(coalesce(payment_records.payment_status", query_text)
        self.assertIn("lower(coalesce(payment_records.payment_method", query_text)
        self.assertIn("payment_records.payment_status IN", query_text)
        self.assertIn("coalesce(users.username", query_text)
        self.assertEqual(len(session.executed), 1)

    async def test_v2_users_lookup_limits_query_to_requested_real_users(self) -> None:
        session = _UsersLookupSession()

        with patch.object(dashboard_v2_data, "async_session", return_value=session):
            await dashboard_v2_data._get_users_lookup({7, 8})

        query_text = "\n".join(session.executed)
        self.assertIn("FROM users", query_text)
        self.assertIn("users.id IN", query_text)
        self.assertIn("users.is_synthetic", query_text)


if __name__ == "__main__":
    unittest.main()
