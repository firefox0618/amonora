import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.models import ManagedServer, PaymentRecord
from dashboard.services import (
    confirm_payment_record,
    create_payment_record,
    dashboard_server_state,
    migrate_server_region_access,
    run_server_action,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return []


class _DummySession:
    def __init__(self, execute_results=None):
        self._execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.refreshes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, _query):
        return self._execute_results.pop(0)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1
        if getattr(obj, "id", None) is None:
            obj.id = 901


class DashboardAcrSecondPassTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_payment_record_rejects_confirmed_non_manual_status(self) -> None:
        admin = SimpleNamespace(id=7, display_name="Owner")
        session = _DummySession(execute_results=[_ScalarResult(44)])

        with (
            patch("dashboard.services._get_runtime_tariff", return_value=SimpleNamespace(code="1m", rub_price=149, duration_days=30)),
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch("dashboard.services._finalize_confirmed_payment_access", new=AsyncMock(return_value={"sync_failed": False})) as finalize_mock,
            patch("dashboard.services.sync_income_entry_for_payment_record", new=AsyncMock()) as income_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            with self.assertRaisesRegex(ValueError, "нельзя создавать сразу из панели"):
                await create_payment_record(
                    44,
                    "telegram_stars",
                    "1m",
                    "confirmed",
                    "stars-901",
                    "ok",
                    admin,
                    "127.0.0.1",
                )

        self.assertEqual(session.commits, 0)
        finalize_mock.assert_not_awaited()
        income_mock.assert_not_awaited()

    async def test_create_payment_record_reuses_semantic_open_intent_instead_of_creating_duplicate(self) -> None:
        admin = SimpleNamespace(id=7, display_name="Owner")
        session = _DummySession(execute_results=[_ScalarResult(44)])
        open_record = SimpleNamespace(id=901)

        with (
            patch("dashboard.services._get_runtime_tariff", return_value=SimpleNamespace(code="1m", rub_price=149, duration_days=30)),
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.get_open_payment_intent_for_user", new=AsyncMock(return_value=open_record)),
            patch("dashboard.services.create_manual_payment_record", new=AsyncMock()) as create_manual_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            with self.assertRaisesRegex(ValueError, "уже есть открытый платёж #901"):
                await create_payment_record(
                    44,
                    "sbp_manual",
                    "1m",
                    "awaiting_user_payment",
                    "",
                    "",
                    admin,
                    "127.0.0.1",
                )

        create_manual_mock.assert_not_awaited()
        self.assertEqual(session.commits, 0)

    async def test_confirm_payment_record_non_manual_uses_finalize_flow(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Manager")
        db_record = PaymentRecord(
            id=73,
            user_id=51,
            payment_method="telegram_stars",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        refreshed_record = PaymentRecord(
            id=73,
            user_id=51,
            payment_method="telegram_stars",
            payment_status="confirmed",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        session = _DummySession(execute_results=[_ScalarResult(db_record)])

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[db_record, refreshed_record, refreshed_record])),
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services._finalize_confirmed_payment_access", new=AsyncMock(return_value={"sync_failed": False})) as finalize_mock,
            patch("dashboard.services.sync_income_entry_for_payment_record", new=AsyncMock()) as income_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            await confirm_payment_record(73, admin, "127.0.0.1")

        self.assertEqual(db_record.payment_status, "confirmed")
        self.assertIsInstance(db_record.confirmed_at, datetime)
        finalize_mock.assert_awaited_once_with(refreshed_record, payment_source="dashboard_telegram_stars")
        income_mock.assert_awaited_once_with(73)

    async def test_migrate_server_region_access_skips_unbound_devices_and_avoids_maintenance(self) -> None:
        admin = SimpleNamespace(id=2, display_name="Tech Admin")
        source = ManagedServer(id=1, name="Germany-1", country_code="DE")
        target = ManagedServer(id=2, name="Estonia-1", country_code="EE")
        bound_device = SimpleNamespace(id=10, protocol="vless")
        unbound_device = SimpleNamespace(id=11, protocol="vless")
        session = _DummySession(
            execute_results=[
                _ScalarResult(source),
                _ScalarResult(target),
                _ScalarResult([bound_device, unbound_device]),
            ]
        )

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch(
                "dashboard.services._device_metadata",
                side_effect=[
                    {"managed_server_id": 1, "country_code": "DE"},
                    {"country_code": "DE"},
                ],
            ),
            patch("dashboard.services.region_supports_protocol", return_value=True),
            patch("dashboard.services._reissue_existing_device", new=AsyncMock()) as reissue_mock,
            patch("dashboard.services.update_server_status", new=AsyncMock()) as maintenance_mock,
            patch("dashboard.services.create_control_event", new=AsyncMock()) as event_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            result = await migrate_server_region_access(1, 2, admin, "127.0.0.1")

        reissue_mock.assert_awaited_once_with(bound_device, target_country_code="ee")
        maintenance_mock.assert_not_awaited()
        event_mock.assert_awaited_once()
        self.assertEqual(result["migrated_devices"], 1)
        self.assertEqual(result["skipped_devices"], 1)
        self.assertEqual(result["unbound_devices"], 1)
        self.assertTrue(result["requires_manual_review"])

    async def test_run_server_action_refresh_alias_uses_health_check(self) -> None:
        admin = SimpleNamespace(id=3)

        with patch("dashboard.services.server_health_check", new=AsyncMock(return_value={"id": 4, "status": "healthy"})) as health_mock:
            result = await run_server_action(4, "refresh", admin, "127.0.0.1")

        health_mock.assert_awaited_once_with(4, admin, "127.0.0.1")
        self.assertEqual(result["action"], "refresh")
        self.assertEqual(result["snapshot"]["id"], 4)

    def test_dashboard_server_state_distinguishes_monitoring_gap_from_real_down(self) -> None:
        state = dashboard_server_state(
            {
                "status": "active",
                "overall_state": "healthy",
                "host_status": "error",
                "ssh_status": "error",
                "country_code": "de",
                "xui_status": "ok",
                "xui_service_status": "active",
            }
        )

        self.assertEqual(state["code"], "degradation")
        self.assertEqual(state["label"], "Деградация мониторинга")

    def test_dashboard_server_state_ignores_xui_panel_noise_when_runtime_service_is_active(self) -> None:
        state = dashboard_server_state(
            {
                "status": "active",
                "overall_state": "healthy",
                "host_status": "ok",
                "ssh_status": "active",
                "country_code": "de",
                "xui_status": "error",
                "xui_service_status": "active",
            }
        )

        self.assertEqual(state["code"], "active")
        self.assertEqual(state["label"], "Активна")

    def test_dashboard_server_state_ignores_legacy_estonia_runtime_after_awg_cutover(self) -> None:
        state = dashboard_server_state(
            {
                "status": "active",
                "overall_state": "healthy",
                "host_status": "ok",
                "ssh_status": "active",
                "country_code": "ee",
                "xui_status": "error",
                "xui_service_status": "failed",
                "xray_service_status": "inactive",
            }
        )

        self.assertEqual(state["code"], "active")
        self.assertEqual(state["label"], "Активна")


if __name__ == "__main__":
    unittest.main()
