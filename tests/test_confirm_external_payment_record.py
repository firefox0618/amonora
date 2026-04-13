import unittest

from datetime import datetime
from unittest.mock import AsyncMock, patch

import bot.db as bot_db
from dashboard.models import PaymentRecord


def build_record(
    *,
    payment_method: str = "crypto_bot",
    external_payment_id: str = "ext-001",
    payment_status: str = "pending",
    note: str | None = None,
    confirmed_at: datetime | None = None,
) -> PaymentRecord:
    return PaymentRecord(
        id=1,
        user_id=77,
        external_payment_id=external_payment_id,
        tariff_code="1m",
        payment_method=payment_method,
        payment_status=payment_status,
        amount=149,
        currency="RUB",
        duration_days=30,
        note=note,
        confirmed_at=confirmed_at,
    )


class FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeAsyncSession:
    def __init__(self, record: PaymentRecord | None) -> None:
        self.record = record
        self.commit_calls = 0
        self.refresh_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        params = statement.compile().params

        if "FROM payment_records" in text:
            if self.record is None:
                return FakeResult(None)
            if (
                params.get("payment_method_1") == self.record.payment_method
                and params.get("external_payment_id_1") == self.record.external_payment_id
            ):
                return FakeResult(self.record)
            return FakeResult(None)

        return FakeResult(None)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj) -> None:
        if obj is self.record:
            self.refresh_calls += 1


class ConfirmExternalPaymentRecordIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_external_payment_record_first_confirm_marks_record_confirmed(self) -> None:
        record = build_record(payment_status="pending")
        fake_session = FakeAsyncSession(record)
        fixed_now = datetime(2026, 3, 19, 18, 0, 0)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: fake_session),
            patch.object(bot_db, "utcnow", return_value=fixed_now),
        ):
            updated, just_confirmed = await bot_db.confirm_external_payment_record(
                payment_method="crypto_bot",
                external_payment_id="ext-001",
            )

        self.assertIs(updated, record)
        self.assertTrue(just_confirmed)
        self.assertEqual(record.payment_status, "confirmed")
        self.assertEqual(record.confirmed_at, fixed_now)
        self.assertEqual(fake_session.commit_calls, 1)
        self.assertEqual(fake_session.refresh_calls, 1)

    async def test_confirm_external_payment_record_duplicate_confirm_returns_false_and_keeps_confirmed_at(self) -> None:
        original_confirmed_at = datetime(2026, 3, 18, 12, 30, 0)
        record = build_record(payment_status="confirmed", confirmed_at=original_confirmed_at)
        fake_session = FakeAsyncSession(record)
        later_now = datetime(2026, 3, 19, 20, 0, 0)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: fake_session),
            patch.object(bot_db, "utcnow", return_value=later_now),
        ):
            updated, just_confirmed = await bot_db.confirm_external_payment_record(
                payment_method="crypto_bot",
                external_payment_id="ext-001",
            )

        self.assertIs(updated, record)
        self.assertFalse(just_confirmed)
        self.assertEqual(record.payment_status, "confirmed")
        self.assertEqual(record.confirmed_at, original_confirmed_at)
        self.assertEqual(fake_session.commit_calls, 1)
        self.assertEqual(fake_session.refresh_calls, 1)

    async def test_confirm_external_payment_record_missing_record_returns_none_false(self) -> None:
        fake_session = FakeAsyncSession(None)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: fake_session),
        ):
            updated, just_confirmed = await bot_db.confirm_external_payment_record(
                payment_method="crypto_bot",
                external_payment_id="missing-id",
            )

        self.assertIsNone(updated)
        self.assertFalse(just_confirmed)
        self.assertEqual(fake_session.commit_calls, 0)
        self.assertEqual(fake_session.refresh_calls, 0)

    async def test_confirm_external_payment_record_first_confirm_updates_note_when_provided(self) -> None:
        record = build_record(payment_status="pending", note="old note")
        fake_session = FakeAsyncSession(record)
        fixed_now = datetime(2026, 3, 19, 21, 0, 0)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: fake_session),
            patch.object(bot_db, "utcnow", return_value=fixed_now),
        ):
            updated, just_confirmed = await bot_db.confirm_external_payment_record(
                payment_method="crypto_bot",
                external_payment_id="ext-001",
                note="new payload snapshot",
            )

        self.assertIs(updated, record)
        self.assertTrue(just_confirmed)
        self.assertEqual(record.note, "new payload snapshot")
        self.assertEqual(record.confirmed_at, fixed_now)

    async def test_confirm_external_payment_record_duplicate_confirm_can_still_update_note(self) -> None:
        original_confirmed_at = datetime(2026, 3, 18, 9, 15, 0)
        record = build_record(
            payment_status="confirmed",
            note="old note",
            confirmed_at=original_confirmed_at,
        )
        fake_session = FakeAsyncSession(record)
        later_now = datetime(2026, 3, 19, 22, 0, 0)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: fake_session),
            patch.object(bot_db, "utcnow", return_value=later_now),
        ):
            updated, just_confirmed = await bot_db.confirm_external_payment_record(
                payment_method="crypto_bot",
                external_payment_id="ext-001",
                note="new duplicate note",
            )

        self.assertIs(updated, record)
        self.assertFalse(just_confirmed)
        self.assertEqual(record.payment_status, "confirmed")
        self.assertEqual(record.confirmed_at, original_confirmed_at)
        self.assertEqual(record.note, "new duplicate note")


if __name__ == "__main__":
    unittest.main()
