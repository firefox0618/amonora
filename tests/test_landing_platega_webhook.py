import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import landing.main as landing_main


class LandingPlategaWebhookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_cm = TestClient(landing_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)

    def test_platega_webhook_rejects_wrong_secret(self) -> None:
        response = self.client.post("/webhooks/platega/wrong")
        self.assertEqual(response.status_code, 404)

    def test_platega_webhook_accepts_valid_callback(self) -> None:
        fake_client = type(
            "FakePlategaClient",
            (),
            {
                "configured": True,
                "validate_callback": lambda self, headers, body: {
                    "id": "trx-001",
                    "status": "CONFIRMED",
                    "paymentMethod": 2,
                    "payload": '{"user_id":7,"tariff_code":"1m","payment_method":"sbp_platega"}',
                },
            },
        )()
        handler = AsyncMock(
            return_value={
                "record": type("Record", (), {"id": 501, "payment_status": "confirmed"})(),
                "provider_status": "CONFIRMED",
                "just_confirmed": True,
                "provider_sync_problem": None,
            }
        )
        fake_bot = type("FakeBot", (), {"session": type("Session", (), {"close": AsyncMock()})()})()
        with (
            patch.object(landing_main, "platega_client", fake_client),
            patch.object(landing_main.config, "platega_webhook_secret", "test-secret"),
            patch.object(landing_main, "handle_platega_callback_payload", handler),
            patch.object(landing_main, "Bot", return_value=fake_bot),
        ):
            response = self.client.post(
                "/webhooks/platega/test-secret",
                json={"id": "trx-001"},
                headers={"X-MerchantId": "merchant-1", "X-Secret": "secret-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["record_id"], 501)
        self.assertTrue(response.headers.get("X-Request-ID"))
        handler.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
