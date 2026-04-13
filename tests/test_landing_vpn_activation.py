import unittest

from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
