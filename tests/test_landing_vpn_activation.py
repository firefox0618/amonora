import unittest

from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import landing.main as landing_main


class LandingVpnActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_cm = TestClient(landing_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)

    def test_vpn_activate_returns_gone_for_legacy_path(self) -> None:
        response = self.client.post(
            "/vpn/activate",
            json={"key": "vless://legacy", "device_fingerprint": "device-1"},
        )

        self.assertEqual(response.status_code, 410)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "gone")
        self.assertIn("retired", payload["message"].lower())


class LandingBridgeAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_issue_bridge_vless_key_uses_local_region_health_checker(self) -> None:
        class FakeProvisioner:
            def __init__(self, country_code: str) -> None:
                self.country_code = country_code

            async def health_check(self) -> bool:
                return self.country_code == "dk"

            async def provision_vless_client(self, **kwargs):
                return SimpleNamespace(
                    vpn_client_id=77,
                    metadata={
                        "vless_link": "vless://bridge",
                        "provider_type": "fake",
                    },
                )

            async def close(self) -> None:
                return None

        update_mock = AsyncMock()
        with (
            patch.object(landing_main, "get_vless_provisioner", side_effect=lambda country_code: FakeProvisioner(country_code)),
            patch.object(landing_main, "update_vpn_client_metadata", new=update_mock),
        ):
            payload = await landing_main._issue_bridge_vless_key(
                user_id=42,
                access_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            )

        self.assertEqual(payload["country_code"], "dk")
        self.assertEqual(payload["metadata"]["vless_link"], "vless://bridge")
        update_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
