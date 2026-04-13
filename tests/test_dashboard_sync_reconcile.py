import unittest

from unittest.mock import AsyncMock, patch

import dashboard.services as dashboard_services


class DashboardSyncReconcileTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_single_device_access_updates_inbound_after_xui_reconcile(self) -> None:
        device = type(
            "VpnClient",
            (),
            {
                "id": 15,
                "protocol": "vless",
                "client_uuid": "uuid-15",
                "xui_client_id": None,
                "email": "device@example.com",
                "client_data": '{"country_code":"de","provider_type":"xui","inbound_id":1}',
            },
        )()
        xui = type(
            "XuiClient",
            (),
            {
                "login": AsyncMock(return_value=True),
                "sync_vless_client_expiry": AsyncMock(return_value={"success": True, "inbound_id": 44, "recreated": True}),
                "close": AsyncMock(),
            },
        )()

        with (
            patch("dashboard.services.XUIClient", return_value=xui),
            patch("dashboard.services.update_vpn_client_metadata", new=AsyncMock()) as update_metadata_mock,
        ):
            result = await dashboard_services._sync_single_device_access(device, access_expires_at=None)

        self.assertEqual(result["status"], "success")
        update_metadata_mock.assert_awaited_once()
        self.assertEqual(update_metadata_mock.await_args.args[0], 15)
        self.assertEqual(update_metadata_mock.await_args.args[1]["inbound_id"], 44)


if __name__ == "__main__":
    unittest.main()
