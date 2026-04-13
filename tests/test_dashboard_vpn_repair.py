import unittest

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import dashboard.main as dashboard_main
import dashboard.services as dashboard_services
from dashboard.services import create_session, dashboard_settings, get_user_detail, repair_user_vpn_access, sync_user_access_state
from tests.test_dashboard_auth_session import FakeAsyncSession, MemoryStore
from bot.repair_reasons import MANUAL_REPAIR


class DashboardVpnRepairServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_user_access_state_uses_soft_sync_without_reissue(self) -> None:
        user = type("User", (), {"id": 120, "telegram_id": 991001, "username": "ruslan"})()
        admin = type("Admin", (), {"id": 601, "display_name": "Owner"})()
        expires_at = datetime(2026, 3, 23, 12, 0, 0)
        devices = [type("Device", (), {"id": 1})(), type("Device", (), {"id": 2})()]
        payments = [type("Payment", (), {"payment_status": "confirmed"})()]

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=devices)),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=payments)),
            patch(
                "dashboard.services.sync_user_clients_access",
                new=AsyncMock(
                    return_value={
                        "sync_failed": False,
                        "processed_devices": 2,
                        "successful_devices": 2,
                        "failed_devices": 0,
                        "results": [],
                    }
                ),
            ) as sync_mock,
            patch("dashboard.services._run_user_repair_operation", new=AsyncMock()) as destructive_mock,
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as repair_event_mock,
            patch("dashboard.services.create_control_event", new=AsyncMock()) as control_event_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            result = await sync_user_access_state(120, admin, "127.0.0.1")

        sync_mock.assert_awaited_once_with(120)
        destructive_mock.assert_not_awaited()
        clear_mock.assert_awaited_once_with(120)
        mark_mock.assert_not_awaited()
        repair_event_mock.assert_not_awaited()
        control_event_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()
        self.assertFalse(result["sync_failed"])
        self.assertEqual(result["reissued_devices"], 0)
        self.assertEqual(result["processed_devices"], 2)
        self.assertFalse(result["auto_retry_attempted"])
        self.assertFalse(result["auto_retry_succeeded"])

    async def test_repair_user_vpn_access_clears_marker_on_successful_sync(self) -> None:
        user = type("User", (), {"id": 77})()
        admin = type("Admin", (), {"id": 501})()
        expires_at = datetime(2026, 3, 19, 12, 0, 0)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[object()])),
            patch(
                "dashboard.services.sync_user_vpn_access_with_single_retry",
                new=AsyncMock(
                    return_value={
                        "sync_failed": False,
                        "auto_retry_attempted": False,
                        "auto_retry_succeeded": False,
                    }
                ),
            ) as sync_mock,
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as event_mock,
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await repair_user_vpn_access(77, admin, "127.0.0.1")

        self.assertEqual(result, {"sync_failed": False, "repair_needed": False, "reason": None})
        sync_mock.assert_awaited_once_with(77, expires_at)
        clear_mock.assert_awaited_once_with(77)
        event_mock.assert_awaited_once_with(77, "success", "manual_repair")
        mark_mock.assert_not_awaited()
        audit_mock.assert_awaited_once()

    async def test_repair_user_vpn_access_marks_manual_failure_when_sync_fails(self) -> None:
        user = type("User", (), {"id": 88})()
        admin = type("Admin", (), {"id": 502})()
        expires_at = datetime(2026, 3, 20, 8, 30, 0)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[object()])),
            patch(
                "dashboard.services.sync_user_vpn_access_with_single_retry",
                new=AsyncMock(
                    return_value={
                        "sync_failed": True,
                        "auto_retry_attempted": True,
                        "auto_retry_succeeded": False,
                    }
                ),
            ) as sync_mock,
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as event_mock,
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await repair_user_vpn_access(88, admin, "127.0.0.1")

        self.assertEqual(
            result,
            {"sync_failed": True, "repair_needed": True, "reason": "manual_repair_sync_failed"},
        )
        sync_mock.assert_awaited_once_with(88, expires_at)
        mark_mock.assert_awaited_once_with(88, "manual_repair_sync_failed")
        event_mock.assert_awaited_once_with(88, "failed", "manual_repair_sync_failed")
        clear_mock.assert_not_awaited()
        audit_mock.assert_awaited_once()

    async def test_repair_user_vpn_access_clears_marker_when_auto_retry_recovers(self) -> None:
        user = type("User", (), {"id": 90})()
        admin = type("Admin", (), {"id": 504})()
        expires_at = datetime(2026, 3, 20, 9, 0, 0)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[object()])),
            patch(
                "dashboard.services.sync_user_vpn_access_with_single_retry",
                new=AsyncMock(
                    return_value={
                        "sync_failed": False,
                        "auto_retry_attempted": True,
                        "auto_retry_succeeded": True,
                    }
                ),
            ) as sync_mock,
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as event_mock,
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await repair_user_vpn_access(90, admin, "127.0.0.1")

        self.assertEqual(result, {"sync_failed": False, "repair_needed": False, "reason": None})
        sync_mock.assert_awaited_once_with(90, expires_at)
        clear_mock.assert_awaited_once_with(90)
        event_mock.assert_awaited_once_with(90, "success", "manual_repair")
        mark_mock.assert_not_awaited()
        audit_mock.assert_awaited_once()

    async def test_repair_user_vpn_access_keeps_marker_when_no_devices_exist(self) -> None:
        user = type("User", (), {"id": 99})()
        admin = type("Admin", (), {"id": 503})()
        expires_at = datetime(2026, 3, 21, 18, 45, 0)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=expires_at)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch("dashboard.services.sync_user_vpn_access_with_single_retry", new=AsyncMock()) as sync_mock,
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as event_mock,
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await repair_user_vpn_access(99, admin, "127.0.0.1")

        self.assertEqual(
            result,
            {"sync_failed": True, "repair_needed": True, "reason": "manual_repair_no_devices"},
        )
        sync_mock.assert_not_awaited()
        mark_mock.assert_awaited_once_with(99, "manual_repair_no_devices")
        event_mock.assert_awaited_once_with(99, "skipped", "manual_repair_no_devices")
        clear_mock.assert_not_awaited()
        audit_mock.assert_awaited_once()

    async def test_get_user_detail_includes_recent_vpn_repair_events(self) -> None:
        user = type(
            "User",
            (),
            {
                "id": 111,
                "telegram_id": 123456,
                "username": "repair-user",
                "preferred_protocol": "vless",
                "is_blocked": False,
                "trial_used": False,
                "created_at": datetime(2026, 3, 20, 10, 0, 0),
                "vpn_repair_needed": True,
                "vpn_repair_reason": "manual_repair_failed",
                "vpn_repair_marked_at": datetime(2026, 3, 20, 10, 30, 0),
            },
        )()
        event = type(
            "VpnRepairEvent",
            (),
            {
                "result": "success",
                "reason": MANUAL_REPAIR,
                "created_at": datetime(2026, 3, 20, 10, 32, 0),
            },
        )()
        previous_event = type(
            "VpnRepairEvent",
            (),
            {
                "result": "failed",
                "reason": "manual_repair_failed",
                "created_at": datetime(2026, 3, 20, 10, 31, 0),
            },
        )()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={111: 0})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch("dashboard.services.list_vpn_repair_events", new=AsyncMock(return_value=[event, previous_event])),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_access_status_from_user", return_value="paid_active"),
            patch(
                "dashboard.services.get_access_expires_at_from_user",
                return_value=datetime(2026, 4, 20, 10, 0, 0),
            ),
        ):
            detail = await get_user_detail(111)

        assert detail is not None
        self.assertEqual(detail["vpn_repair_state"]["reason"], "manual_repair_sync_failed")
        self.assertEqual(detail["vpn_repair_state"]["reason_label"], "Manual repair sync failed")
        self.assertEqual(detail["vpn_repair_state"]["source"], "manual")
        self.assertEqual(detail["vpn_repair_state"]["source_label"], "Manual")
        self.assertEqual(detail["vpn_repair_events"][0]["result"], "success")
        self.assertEqual(detail["vpn_repair_events"][0]["outcome"], "success")
        self.assertEqual(detail["vpn_repair_events"][0]["outcome_label"], "Succeeded")
        self.assertEqual(detail["vpn_repair_events"][0]["source"], "manual")
        self.assertEqual(detail["vpn_repair_events"][0]["source_label"], "Manual")
        self.assertIsNone(detail["vpn_repair_events"][0]["reason"])
        self.assertIsNone(detail["vpn_repair_events"][0]["reason_label"])
        self.assertIn("2026-03-20", detail["vpn_repair_events"][0]["created_at"])
        self.assertEqual(detail["vpn_repair_events"][1]["reason"], "manual_repair_sync_failed")
        self.assertEqual(detail["vpn_repair_events"][1]["reason_label"], "Manual repair sync failed")

    async def test_get_user_detail_prefers_live_xui_ip_when_available(self) -> None:
        user = type(
            "User",
            (),
            {
                "id": 222,
                "telegram_id": 555000,
                "username": "live-ip-user",
                "preferred_protocol": "vless",
                "is_blocked": False,
                "trial_used": False,
                "created_at": datetime(2026, 3, 20, 10, 0, 0),
                "vpn_repair_needed": False,
                "vpn_repair_reason": None,
                "vpn_repair_marked_at": None,
                "last_activity_at": datetime(2026, 3, 20, 10, 40, 0),
            },
        )()
        device = type(
            "VpnClient",
            (),
            {
                "id": 10,
                "protocol": "vless",
                "created_at": datetime(2026, 3, 20, 10, 5, 0),
                "email": "device_222",
                "client_data": '{"country_code":"de","country_name":"Германия","device_name":"iPhone","ip_address":"10.0.0.1"}',
            },
        )()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={222: 0})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services.list_vpn_repair_events", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_access_status_from_user", return_value="paid_active"),
            patch("dashboard.services.get_access_expires_at_from_user", return_value=datetime(2026, 4, 20, 10, 0, 0)),
            patch(
                "dashboard.services._fetch_xui_live_device_ips",
                new=AsyncMock(
                    return_value={
                        "real_ip": "203.0.113.10",
                        "ip_history": "203.0.113.10",
                        "ip_source": "xui_client_ips",
                        "ip_source_label": "Живой IP из 3x-ui",
                        "ip_checked_at": "2026-03-20 12:40 UTC",
                    }
                ),
            ),
        ):
            detail = await get_user_detail(222)

        assert detail is not None
        self.assertEqual(detail["devices"][0]["metadata"]["ip_address"], "203.0.113.10")
        self.assertEqual(detail["devices"][0]["metadata"]["fallback_ip_address"], "10.0.0.1")
        self.assertEqual(detail["devices"][0]["metadata"]["ip_source"], "xui_client_ips")


class DashboardVpnRepairApiTests(unittest.TestCase):
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

    def test_dashboard_api_v2_repair_vpn_returns_401_without_session(self) -> None:
        with patch.object(dashboard_services, "async_session", self.fake_session_factory):
            response = self.client.post("/dashboard/api/v2/users/101/repair-vpn")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_dashboard_api_v2_repair_vpn_returns_sync_result_with_valid_session(self) -> None:
        token = "api-repair-vpn-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(
                dashboard_main,
                "repair_user_vpn_access",
                new=AsyncMock(return_value={"sync_failed": False, "repair_needed": False, "reason": None}),
            ) as repair_mock,
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/users/101/repair-vpn")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["data"],
            {"sync_failed": False, "repair_needed": False, "reason": None},
        )
        repair_mock.assert_awaited_once()

    def test_dashboard_api_v2_sync_returns_soft_sync_result_with_valid_session(self) -> None:
        token = "api-sync-token"
        with (
            patch.object(dashboard_services, "async_session", self.fake_session_factory),
            patch.object(
                dashboard_main,
                "sync_user_access_state",
                new=AsyncMock(
                    return_value={
                        "sync_failed": False,
                        "repair_needed": False,
                        "reason": None,
                        "processed_devices": 2,
                        "successful_devices": 2,
                        "failed_devices": 0,
                        "reissued_devices": 0,
                        "results": [],
                    }
                ),
            ) as sync_mock,
        ):
            self._run(create_session(self.store.admin.id, token))
            self.set_session_cookie(token)
            response = self.client.post("/dashboard/api/v2/users/101/sync")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["reissued_devices"], 0)
        self.assertEqual(payload["data"]["processed_devices"], 2)
        sync_mock.assert_awaited_once()


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


DashboardVpnRepairApiTests._run = staticmethod(_run_async)


if __name__ == "__main__":
    unittest.main()
