import os
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

from bot import payment_flow
from bot.utils.referrals import ReferralRewardOutcome
from bot.utils.texts import referral_reward_invited_text, referral_reward_referrer_text


class ReferralNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_referral_reward_delivery_sends_both_user_notifications_and_logs_once(self) -> None:
        outcome = ReferralRewardOutcome(
            applied=True,
            referrer_user_id=11,
            invited_user_id=22,
            referrer_telegram_id=1111,
            invited_telegram_id=2222,
            bonus_referrer_rub=50,
            bonus_invited_rub=50,
            referrer_balance_rub=150,
            invited_balance_rub=50,
            tariff_code="3m",
            tariff_title="3 месяца",
        )

        with (
            patch.object(payment_flow, "process_referral_reward_for_payment", new=AsyncMock(return_value=outcome)),
            patch.object(payment_flow, "send_user_message_and_refresh_home", new=AsyncMock(return_value=True)) as send_mock,
            patch.object(payment_flow, "_send_referral_push_notification", new=AsyncMock(return_value=False)) as push_mock,
            patch.object(payment_flow, "_log_referral_notification_delivery", new=AsyncMock()) as log_mock,
        ):
            applied = await payment_flow.notify_referral_bonus(bot=None, payment_record_id=701)

        self.assertTrue(applied)
        self.assertEqual(send_mock.await_count, 2)
        send_mock.assert_any_await(1111, referral_reward_referrer_text(bonus_rub=50, balance_rub=150, tariff_title="3 месяца"))
        send_mock.assert_any_await(2222, referral_reward_invited_text(bonus_rub=50, balance_rub=50, tariff_title="3 месяца"))
        self.assertEqual(push_mock.await_count, 2)
        log_mock.assert_awaited_once()

    async def test_referral_reward_delivery_skips_duplicate_reward_without_notifications(self) -> None:
        outcome = ReferralRewardOutcome(
            applied=False,
            referrer_user_id=11,
            invited_user_id=22,
            referrer_telegram_id=1111,
            invited_telegram_id=2222,
            bonus_referrer_rub=50,
            bonus_invited_rub=50,
            referrer_balance_rub=150,
            invited_balance_rub=50,
            tariff_code="3m",
            tariff_title="3 месяца",
        )

        with (
            patch.object(payment_flow, "process_referral_reward_for_payment", new=AsyncMock(return_value=outcome)),
            patch.object(payment_flow, "send_user_message_and_refresh_home", new=AsyncMock()) as send_mock,
            patch.object(payment_flow, "_send_referral_push_notification", new=AsyncMock()) as push_mock,
            patch.object(payment_flow, "_log_referral_notification_delivery", new=AsyncMock()) as log_mock,
        ):
            applied = await payment_flow.notify_referral_bonus(bot=None, payment_record_id=702)

        self.assertFalse(applied)
        send_mock.assert_not_awaited()
        push_mock.assert_not_awaited()
        log_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
