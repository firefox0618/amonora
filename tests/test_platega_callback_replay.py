import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.platega import PlategaError
from bot.platega_flow import _platega_callback_event_key, _set_non_confirmed_status, handle_platega_callback_payload


class FakeSyncSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refresh_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj) -> None:
        self.refresh_calls += 1


class PlategaCallbackReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_callback_replay_is_noop_after_effect_applied(self) -> None:
        record = SimpleNamespace(
            id=91,
            payment_method="sbp_platega",
            user_id=7,
            tariff_code="1m",
            amount=149,
            currency="RUB",
            metadata_json='{"provider_callback_hash":"same-hash","provider_last_callback_status":"CONFIRMED","effect_applied_at":"2026-04-04T00:10:00"}',
        )
        payload = {
            "id": "trx-91",
            "status": "CONFIRMED",
            "paymentMethod": "2",
            "amount": 149,
            "currency": "RUB",
            "payload": '{"user_id":7,"telegram_id":7001,"tariff_code":"1m","payment_method":"sbp_platega"}',
            "_callback_hash": "same-hash",
        }

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch("bot.platega_flow._mark_platega_callback_seen", new=AsyncMock()) as mark_seen_mock,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock()) as sync_mock,
        ):
            result = await handle_platega_callback_payload(payload, notify_user=True, bot=object())

        mark_seen_mock.assert_awaited_once_with(
            record,
            payload=payload,
            parsed_payload={"user_id": 7, "telegram_id": 7001, "tariff_code": "1m", "payment_method": "sbp_platega"},
        )
        sync_mock.assert_not_awaited()
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["provider_status"], "CONFIRMED")
        self.assertIs(result["record"], record)

    async def test_callback_history_replay_is_noop_even_if_last_callback_changed(self) -> None:
        record = SimpleNamespace(
            id=92,
            payment_method="sbp_platega",
            user_id=7,
            tariff_code="1m",
            amount=149,
            currency="RUB",
            metadata_json=(
                '{"provider_callback_hash":"other-hash",'
                '"provider_last_callback_status":"PENDING",'
                '"effect_applied_at":"2026-04-04T00:10:00",'
                '"provider_callback_signatures":["same-hash:CONFIRMED","other-hash:PENDING"]}'
            ),
        )
        payload = {
            "id": "trx-92",
            "status": "CONFIRMED",
            "paymentMethod": "2",
            "amount": 149,
            "currency": "RUB",
            "payload": '{"user_id":7,"telegram_id":7001,"tariff_code":"1m","payment_method":"sbp_platega"}',
            "_callback_hash": "same-hash",
        }

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch("bot.platega_flow._mark_platega_callback_seen", new=AsyncMock()) as mark_seen_mock,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock()) as sync_mock,
        ):
            result = await handle_platega_callback_payload(payload, notify_user=True, bot=object())

        mark_seen_mock.assert_awaited_once_with(
            record,
            payload=payload,
            parsed_payload={"user_id": 7, "telegram_id": 7001, "tariff_code": "1m", "payment_method": "sbp_platega"},
        )
        sync_mock.assert_not_awaited()
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["provider_status"], "CONFIRMED")

    async def test_repeated_terminal_non_confirmed_callback_is_noop(self) -> None:
        record = SimpleNamespace(
            id=93,
            payment_method="sbp_platega",
            user_id=7,
            tariff_code="1m",
            amount=149,
            currency="RUB",
            metadata_json='{"provider_callback_signatures":["pending-hash:PENDING"],"provider_last_callback_status":"PENDING"}',
        )
        payload = {
            "id": "trx-93",
            "status": "PENDING",
            "paymentMethod": "2",
            "amount": 149,
            "currency": "RUB",
            "payload": '{"user_id":7,"telegram_id":7001,"tariff_code":"1m","payment_method":"sbp_platega"}',
            "_callback_hash": "pending-hash",
        }

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch("bot.platega_flow._mark_platega_callback_seen", new=AsyncMock()) as mark_seen_mock,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock()) as sync_mock,
        ):
            result = await handle_platega_callback_payload(payload, notify_user=False, bot=None)

        mark_seen_mock.assert_awaited_once_with(
            record,
            payload=payload,
            parsed_payload={"user_id": 7, "telegram_id": 7001, "tariff_code": "1m", "payment_method": "sbp_platega"},
        )
        sync_mock.assert_not_awaited()
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["provider_status"], "PENDING")

    async def test_semantic_callback_replay_is_noop_even_with_different_raw_hash(self) -> None:
        parsed_payload = {"user_id": 7, "telegram_id": 7001, "tariff_code": "1m", "payment_method": "sbp_platega"}
        payload = {
            "id": "trx-94",
            "status": "CONFIRMED",
            "paymentMethod": "2",
            "amount": 149,
            "payload": json.dumps(parsed_payload, ensure_ascii=False),
            "_callback_hash": "new-hash",
        }
        event_key = _platega_callback_event_key(payload, parsed_payload)
        record = SimpleNamespace(
            id=94,
            payment_method="sbp_platega",
            user_id=7,
            tariff_code="1m",
            amount=149,
            currency="RUB",
            metadata_json=json.dumps(
                {
                    "effect_applied_at": "2026-04-04T00:10:00",
                    "provider_callback_event_keys": [event_key],
                    "provider_last_callback_status": "CONFIRMED",
                },
                ensure_ascii=False,
            ),
        )

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch("bot.platega_flow._mark_platega_callback_seen", new=AsyncMock()) as mark_seen_mock,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock()) as sync_mock,
        ):
            result = await handle_platega_callback_payload(payload, notify_user=True, bot=object())

        mark_seen_mock.assert_awaited_once_with(record, payload=payload, parsed_payload=parsed_payload)
        sync_mock.assert_not_awaited()
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["provider_status"], "CONFIRMED")

    async def test_existing_record_mismatch_is_rejected_and_reported(self) -> None:
        parsed_payload = {"user_id": 7, "telegram_id": 7001, "tariff_code": "1m", "payment_method": "sbp_platega"}
        payload = {
            "id": "trx-95",
            "status": "CONFIRMED",
            "paymentMethod": "2",
            "amount": 999,
            "currency": "RUB",
            "payload": json.dumps(parsed_payload, ensure_ascii=False),
            "_callback_hash": "mismatch-hash",
        }
        record = SimpleNamespace(
            id=95,
            payment_method="sbp_platega",
            user_id=7,
            tariff_code="1m",
            amount=149,
            currency="RUB",
            metadata_json="{}",
        )

        with (
            patch("bot.platega_flow.get_tariff", return_value=type("Tariff", (), {"code": "1m", "title": "1 month", "rub_price": 149, "duration_days": 30})()),
            patch("bot.platega_flow.get_payment_record_by_external_id", new=AsyncMock(return_value=record)),
            patch("bot.platega_flow.create_control_event", new=AsyncMock()) as control_mock,
            patch("bot.platega_flow._mark_platega_callback_seen", new=AsyncMock()) as mark_seen_mock,
            patch("bot.platega_flow.sync_platega_record", new=AsyncMock()) as sync_mock,
        ):
            with self.assertRaises(PlategaError):
                await handle_platega_callback_payload(payload, notify_user=False, bot=None)

        control_mock.assert_awaited_once()
        mark_seen_mock.assert_not_awaited()
        sync_mock.assert_not_awaited()


class PlategaRecordSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_non_confirmed_status_releases_reserved_balance_for_expired_provider_payment(self) -> None:
        record = SimpleNamespace(
            id=96,
            user_id=7,
            tariff_code="1m",
            payment_method="sbp_platega",
            payment_status="pending",
            balance_reserved_amount=50,
            expires_at=None,
            metadata_json="{}",
            note=None,
        )
        session = FakeSyncSession()
        fixed_now = datetime(2026, 4, 6, 10, 30, 0)

        async def release_reserved_balance(mock_session, mock_record, *, reason: str) -> int:
            self.assertIs(mock_session, session)
            self.assertIs(mock_record, record)
            self.assertEqual(reason, "payment_expired")
            mock_record.balance_reserved_amount = 0
            return 50

        with (
            patch("bot.platega_flow._release_reserved_balance_for_record", new=AsyncMock(side_effect=release_reserved_balance)) as release_mock,
            patch("bot.platega_flow.safe_emit_analytics_event", new=AsyncMock()) as analytics_mock,
            patch("bot.platega_flow.utcnow", return_value=fixed_now),
        ):
            updated = await _set_non_confirmed_status(
                session,
                record,
                normalized_status="expired",
                provider_payload={"status": "CANCELED", "id": "trx-96"},
            )

        self.assertIs(updated, record)
        self.assertEqual(record.payment_status, "expired")
        self.assertEqual(record.balance_reserved_amount, 0)
        self.assertEqual(record.expires_at, fixed_now)
        self.assertEqual(json.loads(record.metadata_json)["provider_status"], "CANCELED")
        self.assertEqual(session.commit_calls, 1)
        self.assertEqual(session.refresh_calls, 1)
        release_mock.assert_awaited_once()
        analytics_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
