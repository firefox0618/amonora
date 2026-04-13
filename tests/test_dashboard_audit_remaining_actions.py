import json
import tempfile
import unittest

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.models import DashboardAdmin, DashboardRolePermissionOverride, ManagedServer
from dashboard.services import (
    repair_user_vpn_access,
    server_health_check,
    service_action,
    sync_user_access_state,
    update_role_permission_override,
    update_tariffs,
)
from tests.test_dashboard_acr_second_pass import _DummySession, _ScalarResult


class _RoleOverrideSession:
    def __init__(self, row):
        self.row = row
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarResult(self.row)

    def add(self, _obj):
        return None

    async def commit(self):
        self.commits += 1


class _ServerLookupSession:
    def __init__(self, server):
        self.server = server

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarResult(self.server)


class _AvatarSession:
    def __init__(self, admin):
        self.admin = admin
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _model, _admin_id):
        return self.admin

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


class DashboardRemainingAuditTests(unittest.IsolatedAsyncioTestCase):
    def _audit_payload(self, audit_mock: AsyncMock) -> dict:
        self.assertTrue(audit_mock.await_args_list)
        details = audit_mock.await_args_list[-1].args[4]
        self.assertIsInstance(details, str)
        return json.loads(details)

    async def test_update_role_permission_override_audit_contains_before_after(self) -> None:
        row = DashboardRolePermissionOverride(
            role="support_admin",
            permission="manage_support",
            enabled=False,
            updated_at=datetime(2026, 4, 3, 10, 0, 0),
        )
        actor = SimpleNamespace(id=9)

        with (
            patch("dashboard.services.async_session", return_value=_RoleOverrideSession(row)),
            patch("dashboard.services.refresh_role_permission_overrides_cache", new=AsyncMock()),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await update_role_permission_override(
                "support_admin",
                "manage_support",
                True,
                actor,
                "127.0.0.1",
            )

        self.assertTrue(result["enabled"])
        payload = self._audit_payload(audit_mock)
        self.assertFalse(payload["before"]["enabled"])
        self.assertTrue(payload["after"]["enabled"])

    async def test_update_role_permission_override_rejects_permission_outside_role_allowlist(self) -> None:
        actor = SimpleNamespace(id=9)

        with self.assertRaisesRegex(ValueError, "нельзя менять для выбранной роли"):
            await update_role_permission_override(
                "support_admin",
                "manage_users",
                True,
                actor,
                "127.0.0.1",
            )

    async def test_update_tariffs_audit_contains_before_after_and_services(self) -> None:
        admin = SimpleNamespace(id=1)
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("TARIFF_1M=149\nTARIFF_3M=399\n", encoding="utf-8")

            with (
                patch("dashboard.services.ENV_PATH", env_path),
                patch("dashboard.services._system_command", new=AsyncMock(return_value=(0, "ok"))),
                patch("dashboard.services.invalidate_runtime_cache"),
                patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            ):
                await update_tariffs({"TARIFF_1M": 199, "TARIFF_6M": 799}, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["TARIFF_1M"], "149")
        self.assertIsNone(payload["before"]["TARIFF_6M"])
        self.assertEqual(payload["after"]["TARIFF_1M"], 199)
        self.assertEqual(payload["after"]["TARIFF_6M"], 799)
        self.assertEqual(payload["affected_services"], ["amonora-bot.service", "amonora-landing.service"])

    async def test_repair_user_vpn_access_audit_contains_before_after_reason(self) -> None:
        before_user = SimpleNamespace(
            id=41,
            username="repair-user",
            is_blocked=False,
            balance_rub=0,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=True,
            trial_activity_level="active",
            vpn_repair_needed=False,
            vpn_repair_reason=None,
            last_activity_at=None,
        )
        after_user = SimpleNamespace(**{**before_user.__dict__, "vpn_repair_needed": True, "vpn_repair_reason": "manual_repair_no_access"})
        admin = SimpleNamespace(id=3)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=before_user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock(return_value=after_user)),
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await repair_user_vpn_access(41, admin, "127.0.0.1")

        self.assertTrue(result["sync_failed"])
        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["username"], "repair-user")
        self.assertTrue(payload["after"]["vpn_repair_needed"])
        self.assertEqual(payload["reason"], "manual_repair_no_access")

    async def test_sync_user_access_state_audit_contains_before_after_and_mode(self) -> None:
        before_user = SimpleNamespace(
            id=77,
            telegram_id=990077,
            username="sync-user",
            is_blocked=False,
            balance_rub=0,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=True,
            trial_activity_level="active",
            vpn_repair_needed=True,
            vpn_repair_reason="manual_repair_sync_failed",
            last_activity_at=None,
        )
        after_user = SimpleNamespace(**{**before_user.__dict__, "vpn_repair_needed": False, "vpn_repair_reason": None})
        admin = SimpleNamespace(id=5, display_name="Owner")
        payments = [SimpleNamespace(payment_status="confirmed")]
        devices = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=before_user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 4, 3, 12, 0, 0))),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=payments)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=devices)),
            patch(
                "dashboard.services.sync_user_clients_access",
                new=AsyncMock(return_value={"sync_failed": False, "processed_devices": 2, "successful_devices": 2, "failed_devices": 0, "results": []}),
            ),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock(return_value=after_user)),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            result = await sync_user_access_state(77, admin, "127.0.0.1")

        self.assertFalse(result["sync_failed"])
        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["mode"], "soft_sync")
        self.assertEqual(payload["operation_state"], "success")
        self.assertTrue(payload["before"]["vpn_repair_needed"])
        self.assertFalse(payload["after"]["vpn_repair_needed"])

    async def test_service_action_refresh_audit_contains_after_status(self) -> None:
        admin = SimpleNamespace(id=11)

        with (
            patch("dashboard.services._system_command", new=AsyncMock(return_value=(0, "active\n"))),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await service_action("refresh", "amonora-bot.service", admin, "127.0.0.1")

        self.assertEqual(result["status"], "active")
        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["after"]["status"], "active")

    async def test_server_health_check_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=12)
        server = ManagedServer(id=9, name="Germany-1", host="srv", public_ip="1.1.1.1", country_code="DE", country_name="Germany", provider="xui", status="active")
        snapshot = {"id": 9, "status": "healthy", "overall_state": "healthy", "country_code": "de"}

        with (
            patch("dashboard.services.async_session", return_value=_ServerLookupSession(server)),
            patch("dashboard.services.get_server_snapshots", new=AsyncMock(return_value=[snapshot])),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await server_health_check(9, admin, "127.0.0.1")

        self.assertEqual(result["status"], "healthy")
        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["name"], "Germany-1")
        self.assertEqual(payload["after"]["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
