import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

import landing.main as landing_main


class LandingPublicSurfaceHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_cm = TestClient(landing_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)

    def test_manual_page_has_cookie_controls(self) -> None:
        response = self.client.get("/manual")

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-cookie-banner', response.text)
        self.assertIn('data-cookie-modal', response.text)

    def test_legacy_crypto_pay_webhook_disabled_by_default(self) -> None:
        with patch.object(landing_main.config, "enable_legacy_crypto_pay_webhook", False):
            response = self.client.post("/webhooks/crypto-pay/test-secret")

        self.assertEqual(response.status_code, 410)


if __name__ == "__main__":
    unittest.main()
