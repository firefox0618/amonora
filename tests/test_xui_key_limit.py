import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from bot.vpn_api import XUIClient, XUI_SINGLE_DEVICE_LIMIT_IP


class _DummyResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self.status_code = 200
        self._payload = payload or {"success": True, "obj": None}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _RecordingHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.post_responses: list[_DummyResponse] = []

    async def post(self, url: str, *, json=None, data=None):
        self.calls.append({"url": url, "json": json, "data": data})
        if self.post_responses:
            return self.post_responses.pop(0)
        return _DummyResponse()

    async def aclose(self) -> None:
        return None


class XUIKeyLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_vless_client_sets_single_ip_limit(self) -> None:
        client = XUIClient(base_url="https://panel.example", username="user", password="pass")
        recorder = _RecordingHttpClient()
        client.client = recorder

        await client.add_vless_client(
            inbound_id=42,
            email="device@example",
            client_uuid="uuid-1",
            expiry_time_ms=1234567890,
        )

        payload = recorder.calls[0]["json"]
        settings = json.loads(payload["settings"])
        self.assertEqual(settings["clients"][0]["limitIp"], XUI_SINGLE_DEVICE_LIMIT_IP)
        self.assertEqual(settings["clients"][0]["id"], "uuid-1")

    async def test_update_vless_client_keeps_single_ip_limit(self) -> None:
        client = XUIClient(base_url="https://panel.example", username="user", password="pass")
        recorder = _RecordingHttpClient()
        client.client = recorder

        await client.update_vless_client(
            inbound_id=42,
            client_uuid="uuid-2",
            email="device@example",
            expiry_time_ms=1234567890,
            enable=False,
        )

        payload = recorder.calls[0]["json"]
        settings = json.loads(payload["settings"])
        self.assertEqual(settings["clients"][0]["limitIp"], XUI_SINGLE_DEVICE_LIMIT_IP)
        self.assertFalse(settings["clients"][0]["enable"])

    async def test_sync_trojan_client_expiry_upgrades_existing_client_limit(self) -> None:
        client = XUIClient(base_url="https://panel.example", username="user", password="pass")
        access_expires_at = datetime.now(UTC) + timedelta(days=2)
        client.list_inbounds = AsyncMock(
            return_value=[
                {
                    "id": 8443,
                    "settings": json.dumps(
                        {
                            "clients": [
                                {
                                    "password": "trojan-secret",
                                    "email": "device@example",
                                    "limitIp": 0,
                                    "enable": True,
                                    "expiryTime": 0,
                                }
                            ]
                        }
                    ),
                }
            ]
        )
        captured: dict[str, dict] = {}

        async def _capture_update(inbound: dict, settings: dict) -> dict:
            captured["settings"] = settings
            return {"success": True}

        client.update_inbound_settings = _capture_update

        await client.sync_trojan_client_expiry(
            inbound_id=8443,
            client_uuid="trojan-secret",
            email="device@example",
            access_expires_at=access_expires_at,
        )

        updated_client = captured["settings"]["clients"][0]
        self.assertEqual(updated_client["limitIp"], XUI_SINGLE_DEVICE_LIMIT_IP)
        self.assertTrue(updated_client["enable"])
        self.assertEqual(updated_client["expiryTime"], int(access_expires_at.timestamp() * 1000))

    async def test_get_client_ips_uses_post_endpoint_and_parses_response(self) -> None:
        client = XUIClient(base_url="https://panel.example", username="user", password="pass")
        recorder = _RecordingHttpClient()
        recorder.post_responses.append(_DummyResponse({"success": True, "obj": "1.1.1.1, 2.2.2.2"}))
        client.client = recorder

        ips = await client.get_client_ips("device@example")

        self.assertEqual(ips, ["1.1.1.1", "2.2.2.2"])
        self.assertTrue(recorder.calls[0]["url"].endswith("/panel/api/inbounds/clientIps/device%40example"))

    async def test_get_client_ips_returns_empty_for_no_record(self) -> None:
        client = XUIClient(base_url="https://panel.example", username="user", password="pass")
        recorder = _RecordingHttpClient()
        recorder.post_responses.append(_DummyResponse({"success": True, "obj": "No IP Record"}))
        client.client = recorder

        ips = await client.get_client_ips("device@example")

        self.assertEqual(ips, [])


if __name__ == "__main__":
    unittest.main()
