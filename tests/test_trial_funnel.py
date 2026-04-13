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
os.environ.setdefault("CHANNEL_ID", "1")

from bot import db as bot_db
from bot.utils.access import TRIAL_ACTIVITY_LEVEL_ACTIVE, TRIAL_ACTIVITY_LEVEL_LOW


class _FakeExecuteResult:
    def __init__(self, user) -> None:
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, user) -> None:
        self.user = user
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _query):
        return _FakeExecuteResult(self.user)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _user):
        self.refreshes += 1


class _FakeSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TrialFunnelDbTests(unittest.IsolatedAsyncioTestCase):
    async def test_activate_trial_sets_low_activity_defaults(self) -> None:
        now = datetime(2026, 4, 3, 9, 0, 0)
        user = SimpleNamespace(
            id=77,
            telegram_id=1010,
            trial_used=False,
            trial_started_at=None,
            trial_expires_at=None,
            trial_channel_unsubscribed_at=None,
            trial_activity_level=None,
            trial_engaged_at=datetime(2026, 4, 1, 9, 0, 0),
            last_activity_at=None,
            subscription_expires_at=None,
            subscription_status="inactive",
            is_blocked=False,
        )
        session = _FakeSession(user)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", new=_FakeSessionFactory(session)),
            patch.object(bot_db, "can_activate_trial_from_user", return_value=True),
            patch.object(bot_db, "utcnow", return_value=now),
            patch.object(bot_db, "mark_recent_campaign_conversion", new=AsyncMock()),
            patch.object(bot_db, "mark_recent_channel_post_conversion", new=AsyncMock()),
            patch.object(bot_db, "create_control_event", new=AsyncMock()),
        ):
            updated_user = await bot_db.activate_trial(77)

        self.assertIs(updated_user, user)
        self.assertTrue(user.trial_used)
        self.assertEqual(user.trial_started_at, now)
        self.assertEqual(user.trial_expires_at, now + timedelta(days=bot_db.config.trial_days))
        self.assertEqual(user.trial_activity_level, TRIAL_ACTIVITY_LEVEL_LOW)
        self.assertIsNone(user.trial_engaged_at)
        self.assertEqual(user.last_activity_at, now)

    async def test_mark_trial_technical_engagement_sets_active_once(self) -> None:
        now = datetime(2026, 4, 3, 11, 30, 0)
        user = SimpleNamespace(
            id=88,
            telegram_id=2020,
            trial_used=True,
            trial_started_at=now - timedelta(hours=1),
            trial_expires_at=now + timedelta(days=2),
            trial_channel_unsubscribed_at=None,
            trial_activity_level=TRIAL_ACTIVITY_LEVEL_LOW,
            trial_engaged_at=None,
            last_activity_at=now - timedelta(hours=1),
            subscription_expires_at=None,
            subscription_status="inactive",
            is_blocked=False,
        )
        session = _FakeSession(user)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", new=_FakeSessionFactory(session)),
            patch.object(bot_db, "utcnow", return_value=now),
        ):
            updated_user = await bot_db.mark_trial_technical_engagement(88)
            again_user = await bot_db.mark_trial_technical_engagement(88, engaged_at=now + timedelta(hours=1))

        self.assertIs(updated_user, user)
        self.assertIs(again_user, user)
        self.assertEqual(user.trial_activity_level, TRIAL_ACTIVITY_LEVEL_ACTIVE)
        self.assertEqual(user.trial_engaged_at, now)
        self.assertEqual(user.last_activity_at, now + timedelta(hours=1))
        self.assertEqual(session.commits, 2)
        self.assertEqual(session.refreshes, 2)


if __name__ == "__main__":
    unittest.main()
