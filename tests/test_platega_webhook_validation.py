import json
import unittest
from datetime import datetime, timedelta, timezone

from bot.platega import PlategaClient, PlategaError


class PlategaWebhookValidationTests(unittest.TestCase):
    def _headers(self) -> dict[str, str]:
        return {
            "X-MerchantId": "merchant-1",
            "X-Secret": "secret-1",
        }

    def _body(self, *, updated_at: str) -> bytes:
        return json.dumps(
            {
                "id": "trx-1",
                "status": "CONFIRMED",
                "paymentMethod": "2",
                "updatedAt": updated_at,
            },
            ensure_ascii=False,
        ).encode("utf-8")

    def test_validate_callback_accepts_recent_timestamp(self) -> None:
        client = PlategaClient(
            merchant_id="merchant-1",
            secret_key="secret-1",
            base_url="https://example.com",
            webhook_max_age_seconds=900,
        )
        updated_at = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")

        payload = client.validate_callback(headers=self._headers(), body=self._body(updated_at=updated_at))

        self.assertEqual(payload["id"], "trx-1")
        self.assertTrue(payload["_callback_hash"])

    def test_validate_callback_rejects_old_timestamp(self) -> None:
        client = PlategaClient(
            merchant_id="merchant-1",
            secret_key="secret-1",
            base_url="https://example.com",
            webhook_max_age_seconds=900,
        )
        updated_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

        with self.assertRaises(PlategaError):
            client.validate_callback(headers=self._headers(), body=self._body(updated_at=updated_at))


if __name__ == "__main__":
    unittest.main()
