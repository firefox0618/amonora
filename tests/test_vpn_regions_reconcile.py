import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ops import vpn_regions


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeAsyncSession:
    def __init__(self, clients, users):
        self._clients = clients
        self._users = users

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "FROM vpn_clients" in text:
            return _FakeResult(self._clients)
        if "FROM users" in text:
            return _FakeResult(self._users)
        return _FakeResult([])


class VpnRegionsReconcileTests(unittest.IsolatedAsyncioTestCase):
    async def test_repair_missing_panel_client_recreates_active_vless_and_updates_metadata(self) -> None:
        user = SimpleNamespace(
            id=77,
            is_blocked=False,
            trial_expires_at=None,
            trial_used=True,
            subscription_status="active",
            subscription_source="telegram_stars",
            subscription_expires_at=datetime(2026, 4, 7, 12, 0, 0),
        )
        device = SimpleNamespace(
            id=91,
            protocol="vless",
            client_uuid="uuid-91",
            xui_client_id=None,
            email="device_91@example.com",
        )
        metadata = {
            "country_code": "de",
            "provider_type": "xui",
            "runtime_type": "xui",
            "inbound_id": 0,
        }
        fake_xui = SimpleNamespace(
            login=AsyncMock(return_value=True),
            sync_vless_client_expiry=AsyncMock(
                return_value={"success": True, "inbound_id": 443, "recreated": True}
            ),
            close=AsyncMock(),
        )

        with (
            patch("ops.vpn_regions.XUIClient", return_value=fake_xui),
            patch("ops.vpn_regions.update_vpn_client_metadata", new=AsyncMock()) as update_mock,
        ):
            result = await vpn_regions._repair_missing_panel_client(device, metadata=metadata, user=user)

        self.assertEqual(
            result,
            {
                "repaired": True,
                "country_code": "de",
                "inbound_id": 443,
                "recreated": True,
            },
        )
        update_mock.assert_awaited_once()
        self.assertEqual(update_mock.await_args.args[1]["inbound_id"], 443)

    async def test_reconcile_reports_retired_ee_device_in_dry_run(self) -> None:
        client = SimpleNamespace(
            id=17,
            user_id=77,
            protocol="vless",
            email="device_17@example.com",
            client_uuid="uuid-17",
            xui_client_id=None,
            client_data='{"country_code":"ee","provider_type":"retired","runtime_type":"retired"}',
        )
        user = SimpleNamespace(
            id=77,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 10, 8, 0, 0),
            trial_expires_at=None,
            trial_used=True,
            subscription_source="telegram_stars",
        )

        def _fake_session_factory():
            return _FakeAsyncSession([client], [user])

        with (
            patch("ops.vpn_regions.async_session", _fake_session_factory),
            patch("ops.vpn_regions._panel_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
            patch("ops.vpn_regions._xray_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
        ):
            report = await vpn_regions.reconcile_vpn_clients()

        self.assertEqual(report["total"], 1)
        self.assertEqual(report["results"][0]["result"], "checked")
        self.assertIn("retired_region_cleanup", report["results"][0]["issues"])
        self.assertEqual(report["retired_follow_up_users"], [77])

    async def test_reconcile_apply_cleans_retired_ee_device_and_emits_follow_up(self) -> None:
        client = SimpleNamespace(
            id=18,
            user_id=88,
            protocol="vless",
            email="device_18@example.com",
            client_uuid="uuid-18",
            xui_client_id=None,
            client_data='{"country_code":"ee","provider_type":"retired","runtime_type":"retired"}',
        )
        user = SimpleNamespace(
            id=88,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 10, 8, 0, 0),
            trial_expires_at=None,
            trial_used=True,
            subscription_source="telegram_stars",
        )

        def _fake_session_factory():
            return _FakeAsyncSession([client], [user])

        with (
            patch("ops.vpn_regions.async_session", _fake_session_factory),
            patch("ops.vpn_regions._panel_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
            patch("ops.vpn_regions._xray_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
            patch("ops.vpn_regions.delete_vpn_client_and_return", new=AsyncMock(return_value=client)) as delete_mock,
            patch("ops.vpn_regions.create_control_event", new=AsyncMock()) as control_mock,
        ):
            report = await vpn_regions.reconcile_vpn_clients(apply_changes=True, retire_ee_cleanup=True)

        delete_mock.assert_awaited_once_with(18)
        control_mock.assert_awaited_once()
        self.assertEqual(report["results"][0]["result"], "retired_region_cleanup")
        self.assertEqual(report["retired_follow_up_users"], [88])

    async def test_reconcile_normalizes_dk_metadata_and_marks_fixed(self) -> None:
        client = SimpleNamespace(
            id=27,
            user_id=91,
            protocol="vless",
            email="device_27@example.com",
            client_uuid="uuid-27",
            xui_client_id=None,
            client_data='{"country_code":"dk","provider_type":"xui","runtime_type":"xui","runtime_service_name":"3x-ui","anti_sharing_scope_label":"3x-ui limitIp"}',
        )
        user = SimpleNamespace(
            id=91,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 10, 8, 0, 0),
            trial_expires_at=None,
            trial_used=True,
            subscription_source="telegram_stars",
        )

        def _fake_session_factory():
            return _FakeAsyncSession([client], [user])

        fake_provisioner = SimpleNamespace(
            sync_vless_client=AsyncMock(),
        )

        with (
            patch("ops.vpn_regions.async_session", _fake_session_factory),
            patch("ops.vpn_regions._panel_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
            patch(
                "ops.vpn_regions._xray_inventory",
                new=AsyncMock(
                    return_value={
                        "entries": [{"country_code": "dk", "protocol": "vless", "email": "device_27@example.com", "client_uuid": "uuid-27", "managed": True}],
                        "by_email": {"device_27@example.com": {"country_code": "dk", "protocol": "vless", "email": "device_27@example.com", "client_uuid": "uuid-27", "managed": True}},
                        "by_uuid": {"uuid-27": {"country_code": "dk", "protocol": "vless", "email": "device_27@example.com", "client_uuid": "uuid-27", "managed": True}},
                    }
                ),
            ),
            patch("ops.vpn_regions.XrayCoreProvisioner", return_value=fake_provisioner),
            patch("ops.vpn_regions.update_vpn_client_metadata", new=AsyncMock()) as update_mock,
        ):
            report = await vpn_regions.reconcile_vpn_clients(apply_changes=True)

        self.assertEqual(report["results"][0]["result"], "metadata_fixed")
        fake_provisioner.sync_vless_client.assert_awaited_once()
        update_mock.assert_awaited_once()
        updated_metadata = update_mock.await_args.args[1]
        self.assertEqual(updated_metadata["provider_type"], "xray_core")
        self.assertEqual(updated_metadata["runtime_type"], "xray_core")
        self.assertEqual(updated_metadata["runtime_service_name"], "xray")

    async def test_reconcile_removes_orphan_xui_remote_when_apply_enabled(self) -> None:
        def _fake_session_factory():
            return _FakeAsyncSession([], [])

        orphan_entry = {
            "country_code": "de",
            "protocol": "vless",
            "email": "device_99@example.com",
            "client_uuid": "uuid-99",
            "managed": True,
            "inbound_id": 443,
        }

        with (
            patch("ops.vpn_regions.async_session", _fake_session_factory),
            patch(
                "ops.vpn_regions._panel_inventory",
                new=AsyncMock(return_value={"entries": [orphan_entry], "by_email": {"device_99@example.com": orphan_entry}, "by_uuid": {"uuid-99": orphan_entry}}),
            ),
            patch("ops.vpn_regions._xray_inventory", new=AsyncMock(return_value={"entries": [], "by_email": {}, "by_uuid": {}})),
            patch("ops.vpn_regions._delete_xui_remote", new=AsyncMock(return_value={"deleted": True})) as delete_mock,
        ):
            report = await vpn_regions.reconcile_vpn_clients(apply_changes=True)

        delete_mock.assert_awaited_once()
        self.assertEqual(report["results"][0]["result"], "remote_removed")


if __name__ == "__main__":
    unittest.main()
