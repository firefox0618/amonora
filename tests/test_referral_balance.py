import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot.db as bot_db
from bot.handlers import tariffs as tariff_handlers
from dashboard.models import PaymentRecord


class FakeCountResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self):
        return self.value


class FakeListResult:
    def __init__(self, values) -> None:
        self.values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self.values)

    def first(self):
        return self.values[0] if self.values else None


class FakeUserResult:
    def __init__(self, user) -> None:
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class FakeSession:
    def __init__(self, *, count_value: int = 0, user=None, queued_results=None) -> None:
        self.count_value = count_value
        self.user = user
        self.added = []
        self.queued_results = list(queued_results or [])
        self.commit_calls = 0
        self.refresh_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def execute(self, statement):
        if self.queued_results:
            return self.queued_results.pop(0)
        text = str(statement)
        if "count" in text.lower() or "sum(" in text.lower():
            return FakeCountResult(self.count_value)
        return FakeUserResult(self.user)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj) -> None:
        self.refresh_calls += 1


class DummyMessage:
    def __init__(self) -> None:
        self.edits = []

    async def edit_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, "kwargs": kwargs})

    async def answer(self, text: str) -> None:
        self.edits.append({"answer": text})


class ReferralBalanceHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_migrate_referral_balance_credits_historical_paid_referrals_once(self) -> None:
        user = SimpleNamespace(id=11, balance_rub=0, balance_reserved_rub=0, referral_balance_migrated_at=None)
        referred_1 = SimpleNamespace(id=101, referral_bonus_granted=True, created_at=datetime(2026, 3, 18, 9, 0, 0))
        referred_2 = SimpleNamespace(id=102, referral_bonus_granted=False, created_at=datetime(2026, 3, 19, 9, 0, 0))
        session = FakeSession(
            queued_results=[
                FakeListResult([referred_1, referred_2]),
                FakeCountResult(0),
            ]
        )

        with patch.object(bot_db, "utcnow", return_value=datetime(2026, 3, 21, 10, 0, 0)):
            credited = await bot_db._migrate_referral_balance_if_needed(session, user)

        self.assertEqual(credited, 100)
        self.assertEqual(user.balance_rub, 100)
        self.assertIsNotNone(user.referral_balance_migrated_at)
        self.assertTrue(referred_2.referral_bonus_granted)
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.added[0].amount, 100)
        self.assertEqual(session.added[0].direction, "credit")
        self.assertEqual(session.added[0].reason, "referral_migration")

    async def test_migrate_referral_balance_backfills_legacy_invites_before_existing_cutoff(self) -> None:
        cutoff = datetime(2026, 3, 21, 16, 11, 0)
        user = SimpleNamespace(id=18, balance_rub=0, balance_reserved_rub=0, referral_balance_migrated_at=cutoff)
        legacy_invited = SimpleNamespace(id=17, referral_bonus_granted=False, created_at=datetime(2026, 3, 16, 14, 58, 33))
        session = FakeSession(
            queued_results=[
                FakeListResult([legacy_invited]),
                FakeCountResult(0),
            ]
        )

        credited = await bot_db._migrate_referral_balance_if_needed(session, user)

        self.assertEqual(credited, 50)
        self.assertEqual(user.balance_rub, 50)
        self.assertTrue(legacy_invited.referral_bonus_granted)
        self.assertEqual(session.added[0].reason, "referral_migration")

    async def test_migrate_referral_balance_backfills_missing_delta_after_old_partial_credit(self) -> None:
        user = SimpleNamespace(id=17, balance_rub=50, balance_reserved_rub=0, referral_balance_migrated_at=datetime(2026, 3, 20, 12, 0, 0))
        referred_1 = SimpleNamespace(id=201, referral_bonus_granted=True, created_at=datetime(2026, 3, 18, 12, 0, 0))
        referred_2 = SimpleNamespace(id=202, referral_bonus_granted=False, created_at=datetime(2026, 3, 21, 13, 0, 0))
        session = FakeSession(
            queued_results=[
                FakeListResult([referred_1, referred_2]),
                FakeCountResult(50),
            ]
        )

        credited = await bot_db._migrate_referral_balance_if_needed(session, user)

        self.assertEqual(credited, 50)
        self.assertEqual(user.balance_rub, 100)
        self.assertTrue(referred_2.referral_bonus_granted)
        self.assertEqual(session.added[0].reason, "referral_backfill")

    async def test_first_migration_does_not_treat_post_rollout_invite_as_legacy(self) -> None:
        user = SimpleNamespace(id=31, balance_rub=0, balance_reserved_rub=0, referral_balance_migrated_at=None)
        modern_invited = SimpleNamespace(id=301, referral_bonus_granted=False, created_at=datetime(2026, 3, 22, 9, 0, 0))
        session = FakeSession(
            queued_results=[
                FakeListResult([modern_invited]),
                FakeCountResult(0),
            ]
        )

        credited = await bot_db._migrate_referral_balance_if_needed(session, user)

        self.assertEqual(credited, 0)
        self.assertEqual(user.balance_rub, 0)
        self.assertEqual(user.referral_balance_migrated_at, bot_db.REFERRAL_BALANCE_LEGACY_CUTOFF)
        self.assertFalse(modern_invited.referral_bonus_granted)
        self.assertEqual(len(session.added), 0)

    async def test_process_referral_reward_for_monthly_payment_uses_new_default_50_rub(self) -> None:
        payment = PaymentRecord(
            id=601,
            user_id=302,
            external_payment_id="ref-601",
            tariff_code="1m",
            payment_method="sbp_manual",
            payment_status="confirmed",
            amount=149,
            list_price_amount=149,
            balance_reserved_amount=0,
            balance_applied_amount=0,
            currency="RUB",
            duration_days=30,
        )
        referrer = SimpleNamespace(
            id=32,
            telegram_id=3200,
            balance_rub=0,
            balance_reserved_rub=0,
            referral_bonus_granted=False,
            referral_balance_migrated_at=None,
        )
        modern_invited = SimpleNamespace(
            id=302,
            telegram_id=3020,
            referred_by_user_id=32,
            balance_rub=0,
            balance_reserved_rub=0,
            referral_bonus_granted=False,
            created_at=datetime(2026, 3, 22, 9, 0, 0),
        )
        session = FakeSession(
            queued_results=[
                FakeUserResult(payment),
                FakeUserResult(None),
                FakeUserResult(None),
                FakeListResult([payment]),
                FakeListResult([modern_invited]),
                FakeCountResult(0),
            ]
        )

        async def fake_lock_user_row(_session, user_id):
            return {32: referrer, 302: modern_invited}.get(user_id)

        async def fake_credit_user_balance(_session, user, *, amount: int, **kwargs):
            user.balance_rub = int(getattr(user, "balance_rub", 0) or 0) + amount
            return amount

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: session),
            patch.object(bot_db, "_lock_user_row", new=AsyncMock(side_effect=fake_lock_user_row)),
            patch.object(bot_db, "_ensure_ref_code", new=AsyncMock()),
            patch.object(bot_db, "_ensure_referral_row", new=AsyncMock()),
            patch.object(bot_db, "_credit_user_balance", new=AsyncMock(side_effect=fake_credit_user_balance)),
            patch.object(bot_db, "create_control_event", new=AsyncMock()),
        ):
            outcome = await bot_db.process_referral_reward_for_payment(payment.id)

        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.bonus_referrer_rub, 50)
        self.assertEqual(outcome.referrer_balance_rub, 50)
        self.assertEqual(referrer.balance_rub, 50)
        self.assertEqual(modern_invited.balance_rub, 50)
        self.assertEqual(referrer.referral_balance_migrated_at, bot_db.REFERRAL_BALANCE_LEGACY_CUTOFF)
        self.assertTrue(modern_invited.referral_bonus_granted)

    async def test_grant_referral_bonus_if_needed_credits_paid_referral_only_once(self) -> None:
        referrer = SimpleNamespace(id=11, balance_rub=120)
        payment = SimpleNamespace(id=501)
        session = FakeSession(
            queued_results=[
                FakeListResult([payment]),
            ]
        )

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: session),
            patch.object(
                bot_db,
                "process_referral_reward_for_payment",
                new=AsyncMock(
                    return_value=bot_db.ReferralRewardOutcome(
                        applied=True,
                        referrer_user_id=11,
                        invited_user_id=77,
                        referrer_telegram_id=1111,
                        invited_telegram_id=2222,
                        bonus_referrer_rub=50,
                        bonus_invited_rub=50,
                        referrer_balance_rub=120,
                        invited_balance_rub=50,
                        tariff_code="3m",
                        tariff_title="3 месяца",
                    )
                ),
            ),
            patch.object(bot_db, "get_user_by_id", new=AsyncMock(return_value=referrer)),
        ):
            bonus_applied, returned_referrer = await bot_db.grant_referral_bonus_if_needed(77)

        self.assertTrue(bonus_applied)
        self.assertIs(returned_referrer, referrer)
        self.assertEqual(session.commit_calls, 0)

    async def test_reserve_release_and_apply_balance_update_user_and_record(self) -> None:
        user = SimpleNamespace(id=22, balance_rub=100, balance_reserved_rub=0)
        record = PaymentRecord(
            id=5,
            user_id=22,
            external_payment_id="manual-5",
            tariff_code="1m",
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            amount=49,
            list_price_amount=149,
            balance_reserved_amount=100,
            balance_applied_amount=0,
            currency="RUB",
            duration_days=30,
        )
        session = FakeSession(user=user)

        reserved = await bot_db._reserve_user_balance(
            session,
            user,
            amount=100,
            reason="payment_reserved",
            reference_type="payment_record",
            reference_id="5",
        )
        self.assertEqual(reserved, 100)
        self.assertEqual(user.balance_reserved_rub, 100)

        released = await bot_db._release_reserved_balance_for_record(session, record, reason="payment_cancelled")
        self.assertEqual(released, 100)
        self.assertEqual(record.balance_reserved_amount, 0)
        self.assertEqual(user.balance_reserved_rub, 0)

        user.balance_reserved_rub = 100
        record.balance_reserved_amount = 100
        applied = await bot_db._apply_reserved_balance_for_record(session, record, reason="payment_confirmed")
        self.assertEqual(applied, 100)
        self.assertEqual(record.balance_reserved_amount, 0)
        self.assertEqual(record.balance_applied_amount, 100)
        self.assertEqual(user.balance_rub, 0)
        self.assertEqual(user.balance_reserved_rub, 0)

    async def test_finish_balance_only_payment_uses_balance_breakdown_and_notifies_referrer(self) -> None:
        dummy_record = PaymentRecord(
            id=41,
            user_id=99,
            external_payment_id="balance_41",
            tariff_code="1m",
            payment_method="balance_rub",
            payment_status="confirmed",
            amount=0,
            list_price_amount=149,
            balance_reserved_amount=0,
            balance_applied_amount=149,
            currency="RUB",
            duration_days=30,
        )
        payment_result = {
            "tariff": SimpleNamespace(title="1 месяц"),
            "expires_text": "2026-04-20 12:00:00",
            "sync_failed": False,
            "list_price_amount": 149,
            "balance_applied_amount": 149,
            "paid_amount": 0,
        }
        tariff = SimpleNamespace(code="1m", title="1 месяц", duration_days=30)
        message = DummyMessage()
        bot = object()

        with (
            patch.object(tariff_handlers, "create_balance_only_payment_record", new=AsyncMock(return_value=dummy_record)),
            patch.object(tariff_handlers, "finalize_subscription_payment", new=AsyncMock(return_value=payment_result)),
            patch.object(tariff_handlers, "notify_referral_bonus", new=AsyncMock(return_value=True)) as notify_mock,
        ):
            result = await tariff_handlers._finish_balance_only_payment(
                message,
                user_id=99,
                tariff=tariff,
                bot=bot,
            )

        self.assertTrue(result)
        self.assertEqual(len(message.edits), 1)
        self.assertIn("Списано с Баланса", message.edits[0]["text"])
        notify_mock.assert_awaited_once_with(bot, payment_record_id=41)


if __name__ == "__main__":
    unittest.main()
