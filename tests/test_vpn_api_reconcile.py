import unittest

from datetime import datetime
from unittest.mock import AsyncMock

from bot.vpn_api import XUIClient


class XuiSyncReconcileTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_vless_client_expiry_recreates_missing_client_when_access_is_active(self) -> None:
        client = XUIClient(base_url="https://panel.example")
        client.resolve_client_inbound_id = AsyncMock(return_value=None)
        client.find_inbound = AsyncMock(return_value={"id": 44})
        client.add_vless_client = AsyncMock(return_value={"success": True, "msg": "created", "obj": None})
        try:
            result = await client.sync_vless_client_expiry(
                inbound_id=1,
                client_uuid="uuid-1",
                email="user@example.com",
                access_expires_at=datetime(2026, 4, 6, 12, 0, 0),
            )
        finally:
            await client.close()

        self.assertTrue(result["success"])
        self.assertTrue(result["recreated"])
        self.assertEqual(result["inbound_id"], 44)
        client.add_vless_client.assert_awaited_once()

    async def test_sync_trojan_client_expiry_treats_missing_disabled_client_as_converged(self) -> None:
        client = XUIClient(base_url="https://panel.example")
        client.list_inbounds = AsyncMock(return_value=[])
        client.find_inbound = AsyncMock()
        client.add_trojan_client = AsyncMock()
        try:
            result = await client.sync_trojan_client_expiry(
                inbound_id=9,
                client_uuid="uuid-2",
                email="user@example.com",
                access_expires_at=None,
            )
        finally:
            await client.close()

        self.assertTrue(result["success"])
        self.assertFalse(result["recreated"])
        self.assertEqual(result["inbound_id"], 9)
        client.find_inbound.assert_not_called()
        client.add_trojan_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
