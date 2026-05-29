import unittest

from datetime import datetime
from unittest.mock import AsyncMock

from bot.vpn_api import XUIClient


class XuiSyncReconcileTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_uses_csrf_token_when_panel_requires_base_path(self) -> None:
        class DummyResponse:
            def __init__(self, *, status_code: int = 200, text: str = "") -> None:
                self.status_code = status_code
                self.text = text

            def raise_for_status(self) -> None:
                return None

        class DummyClient:
            def __init__(self) -> None:
                self.post_headers = None

            async def get(self, url: str) -> DummyResponse:
                self.get_url = url
                return DummyResponse(
                    text=(
                        '<meta name="csrf-token" content="csrf-123">'
                        '<meta name="base-path" content="/panel-path/">'
                    )
                )

            async def post(self, url: str, *, headers=None, data=None) -> DummyResponse:
                self.post_url = url
                self.post_headers = headers or {}
                self.post_data = data or {}
                return DummyResponse(status_code=200)

            async def aclose(self) -> None:
                return None

        client = XUIClient(base_url="https://panel.example")
        client.client = DummyClient()
        try:
            login_ok = await client.login()
        finally:
            await client.close()

        self.assertTrue(login_ok)
        self.assertEqual(client.client.post_url, "https://panel.example/login")
        self.assertEqual(client.client.post_headers["X-CSRF-Token"], "csrf-123")
        self.assertEqual(client.client.post_headers["Referer"], "https://panel.example/panel-path/")
        self.assertEqual(
            client.client.post_data,
            {"username": client.username, "password": client.password},
        )

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

    async def test_add_vless_client_falls_back_to_clients_api_on_404(self) -> None:
        class DummyResponse:
            def __init__(self, *, status_code: int, payload: dict | None = None) -> None:
                self.status_code = status_code
                self._payload = payload or {}
                self.request = None

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError("boom", request=self.request, response=self)

            def json(self) -> dict:
                return dict(self._payload)

        class DummyClient:
            def __init__(self) -> None:
                self.calls = []

            async def get(self, url: str) -> DummyResponse:
                return DummyResponse(status_code=404)

            async def post(self, url: str, *, headers=None, data=None, json=None) -> DummyResponse:
                self.calls.append({"url": url, "json": json, "data": data, "headers": headers})
                if url.endswith("/panel/api/inbounds/addClient"):
                    return DummyResponse(status_code=404)
                return DummyResponse(status_code=200, payload={"success": True, "obj": None})

            async def aclose(self) -> None:
                return None

        import httpx

        client = XUIClient(base_url="https://panel.example")
        client.client = DummyClient()
        try:
            result = await client.add_vless_client(
                inbound_id=44,
                email="user@example.com",
                client_uuid="uuid-1",
                expiry_time_ms=123456,
            )
        finally:
            await client.close()

        self.assertTrue(result["success"])
        self.assertEqual(client.client.calls[0]["url"], "https://panel.example/panel/api/inbounds/addClient")
        self.assertEqual(client.client.calls[1]["url"], "https://panel.example/panel/api/clients/add")
        self.assertEqual(client.client.calls[1]["json"]["inboundIds"], [44])


if __name__ == "__main__":
    unittest.main()
