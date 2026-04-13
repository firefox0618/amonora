import os
import unittest

from datetime import datetime, timedelta
from types import SimpleNamespace
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

import bot.db as bot_db
from bot.manual_payments import notify_support_admins_about_manual_payment
from control_bot.access import (
    CONTROL_ROLE_ADMIN,
    CONTROL_ROLE_OPERATOR,
    CONTROL_ROLE_OWNER,
    CONTROL_ROLE_SUPPORT_VIEW_ONLY,
    ControlAdmin,
)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None


class ManualPaymentHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_activate_paid_subscription_keeps_tariff_code_for_analytics(self) -> None:
        fixed_now = datetime(2026, 4, 6, 15, 10, 0)
        user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            subscription_started_at=None,
            subscription_expires_at=None,
            subscription_status="inactive",
            subscription_source=None,
            last_activity_at=None,
        )
        session = _FakeSession()

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", lambda: session),
            patch.object(bot_db, "_lock_user_row", new=AsyncMock(return_value=user)),
            patch.object(bot_db, "utcnow", return_value=fixed_now),
            patch.object(bot_db, "has_active_subscription_from_user", return_value=False),
            patch.object(bot_db, "mark_recent_campaign_conversion", new=AsyncMock()),
            patch.object(bot_db, "mark_recent_channel_post_conversion", new=AsyncMock()),
            patch.object(bot_db, "create_control_event", new=AsyncMock()),
            patch.object(bot_db, "safe_emit_analytics_event", new=AsyncMock()) as analytics_mock,
        ):
            updated_user = await bot_db.activate_paid_subscription(
                user_id=77,
                tariff_code="1m",
                payment_id="manual_184",
                duration_days=30,
                payment_source="sbp_manual",
            )

        self.assertIs(updated_user, user)
        self.assertEqual(user.subscription_status, "active")
        self.assertEqual(user.subscription_source, "sbp_manual")
        self.assertEqual(user.subscription_started_at, fixed_now)
        self.assertEqual(user.subscription_expires_at, fixed_now + timedelta(days=30))
        analytics_mock.assert_awaited_once()
        self.assertEqual(analytics_mock.await_args.kwargs["tariff_code"], "1m")

    async def test_notify_support_admins_about_manual_payment_targets_review_roles(self) -> None:
        record = SimpleNamespace(
            id=184,
            user_id=967,
            amount=149,
            currency="RUB",
            payment_method="sbp_manual",
            payment_status="awaiting_admin_review",
        )
        user = SimpleNamespace(id=967, telegram_id=8363687524, username="tester")

        with (
            patch("bot.manual_payments.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch("bot.manual_payments.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "bot.manual_payments.control_admins",
                return_value=[
                    ControlAdmin(telegram_id=1, role=CONTROL_ROLE_OWNER),
                    ControlAdmin(telegram_id=2, role=CONTROL_ROLE_ADMIN),
                    ControlAdmin(telegram_id=3, role=CONTROL_ROLE_OPERATOR),
                    ControlAdmin(telegram_id=4, role=CONTROL_ROLE_SUPPORT_VIEW_ONLY),
                ],
            ),
            patch("bot.manual_payments.create_control_event", new=AsyncMock()) as event_mock,
        ):
            await notify_support_admins_about_manual_payment(184)

        event_mock.assert_awaited_once()
        self.assertEqual(event_mock.await_args.kwargs["chat_ids"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
