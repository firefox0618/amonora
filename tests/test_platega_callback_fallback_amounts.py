import unittest

from unittest.mock import AsyncMock, patch

from bot.platega_flow import handle_platega_callback_payload


class PlategaCallbackFallbackAmountTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_fallback_uses_balance_aware_amounts_from_payload(self) -> None:
        fake_record = type("Record", (), {"id": 77})()

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=None)),
            patch("bot.platega_flow.create_external_payment_record", new=AsyncMock(return_value=fake_record)) as create_record,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock(return_value={"record": fake_record})),
        ):
            await handle_platega_callback_payload(
                {
                    "id": "trx-007",
                    "status": "PENDING",
                    "paymentMethod": 2,
                    "amount": 99,
                    "payload": '{"user_id":7,"telegram_id":7001,"tariff_code":"1m","payment_method":"sbp_platega","list_price_amount":149,"payable_amount":99,"balance_amount":50}',
                }
            )

        create_record.assert_awaited_once()
        kwargs = create_record.await_args.kwargs
        self.assertEqual(kwargs["amount"], 99)
        self.assertEqual(kwargs["list_price_amount"], 149)
        self.assertEqual(kwargs["balance_reserved_amount"], 50)


if __name__ == "__main__":
    unittest.main()
