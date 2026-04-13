import json
import unittest

from unittest.mock import patch

from bot.platega import PlategaClient, PlategaError


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    last_request: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, url: str, *, headers=None, json=None):
        FakeAsyncClient.last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }
        return FakeResponse(
            {
                "transactionId": "trx-001",
                "redirect": "https://pay.example/checkout",
                "status": "PENDING",
                "paymentMethod": 2,
                "expiresIn": "15m",
            }
        )


class FakeStringMethodAsyncClient(FakeAsyncClient):
    async def request(self, method: str, url: str, *, headers=None, json=None):
        FakeAsyncClient.last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }
        return FakeResponse(
            {
                "transactionId": "trx-002",
                "redirect": "https://pay.example/checkout-string",
                "status": "PENDING",
                "paymentMethod": "SBPQR",
                "expiresIn": "15m",
            }
        )


class PlategaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_payment_sends_expected_request_shape(self) -> None:
        client = PlategaClient(
            merchant_id="merchant-1",
            secret_key="secret-1",
            base_url="https://app.platega.io",
        )

        with patch("bot.platega.httpx.AsyncClient", FakeAsyncClient):
            payment = await client.create_payment(
                amount_rub=149,
                payment_method_id=PlategaClient.METHOD_SBP_QR,
                description="Amonora - 1 месяц",
                payload={"tariff_code": "1m", "user_id": 7},
                return_url="https://t.me/amonora_bot",
                failed_url="https://t.me/amonora_bot",
            )

        self.assertEqual(payment.transaction_id, "trx-001")
        self.assertEqual(payment.checkout_url, "https://pay.example/checkout")
        request = FakeAsyncClient.last_request
        self.assertIsNotNone(request)
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://app.platega.io/transaction/process")
        self.assertEqual(request["headers"]["X-MerchantId"], "merchant-1")
        self.assertEqual(request["headers"]["X-Secret"], "secret-1")
        self.assertEqual(request["json"]["paymentMethod"], PlategaClient.METHOD_SBP_QR)
        self.assertEqual(request["json"]["paymentDetails"]["amount"], 149.0)
        self.assertEqual(
            json.loads(request["json"]["payload"]),
            {"tariff_code": "1m", "user_id": 7},
        )

    async def test_create_payment_accepts_string_payment_method_in_response(self) -> None:
        client = PlategaClient(
            merchant_id="merchant-1",
            secret_key="secret-1",
            base_url="https://app.platega.io",
        )

        with patch("bot.platega.httpx.AsyncClient", FakeStringMethodAsyncClient):
            payment = await client.create_payment(
                amount_rub=149,
                payment_method_id=PlategaClient.METHOD_SBP_QR,
                description="Amonora - smoke",
                payload={"tariff_code": "1m", "user_id": 7},
            )

        self.assertEqual(payment.transaction_id, "trx-002")
        self.assertEqual(payment.payment_method_id, "SBPQR")

    def test_validate_callback_accepts_valid_headers_and_body(self) -> None:
        client = PlategaClient(merchant_id="merchant-1", secret_key="secret-1")
        payload = client.validate_callback(
            headers={"X-MerchantId": "merchant-1", "X-Secret": "secret-1"},
            body=json.dumps(
                {
                    "id": "trx-001",
                    "status": "CONFIRMED",
                    "paymentMethod": 2,
                    "amount": 149,
                    "currency": "RUB",
                }
            ).encode("utf-8"),
        )
        self.assertEqual(payload["id"], "trx-001")
        self.assertEqual(payload["status"], "CONFIRMED")

    def test_validate_callback_rejects_invalid_secret(self) -> None:
        client = PlategaClient(merchant_id="merchant-1", secret_key="secret-1")
        with self.assertRaisesRegex(PlategaError, "X-Secret"):
            client.validate_callback(
                headers={"X-MerchantId": "merchant-1", "X-Secret": "wrong"},
                body=b'{"id":"trx","status":"PENDING","paymentMethod":2}',
            )

    def test_parse_payload_requires_json_object(self) -> None:
        payload = PlategaClient.parse_payload('{"user_id":7,"tariff_code":"1m"}')
        self.assertEqual(payload["user_id"], 7)
        with self.assertRaises(PlategaError):
            PlategaClient.parse_payload("[1,2,3]")


if __name__ == "__main__":
    unittest.main()
