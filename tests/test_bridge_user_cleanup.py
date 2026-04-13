import os
import unittest

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


class _FakeExecuteResult:
    def __init__(self, scalar_value) -> None:
        self._scalar_value = scalar_value

    def scalar_one_or_none(self):
        return self._scalar_value


class _FakeSession:
    def __init__(self, user, *, has_devices: bool) -> None:
        self.user = user
        self.has_devices = has_devices
        self.executed = []
        self.deleted = []
        self.commits = 0

    async def execute(self, query):
        query_text = str(query)
        self.executed.append(query_text)
        if "FROM users" in query_text:
            return _FakeExecuteResult(self.user)
        if "FROM vpn_clients" in query_text:
            return _FakeExecuteResult(1 if self.has_devices else None)
        return _FakeExecuteResult(None)

    async def delete(self, user) -> None:
        self.deleted.append(user)

    async def commit(self) -> None:
        self.commits += 1


class _FakeSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class BridgeUserCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_bridge_user_nulls_delivery_links_before_delete(self) -> None:
        bridge_user = SimpleNamespace(id=133, username="bridge_cleanup_user")
        session = _FakeSession(bridge_user, has_devices=False)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", new=_FakeSessionFactory(session)),
        ):
            deleted = await bot_db.delete_landing_bridge_user_if_unused(133)

        self.assertTrue(deleted)
        self.assertEqual(session.deleted, [bridge_user])
        self.assertEqual(session.commits, 1)
        self.assertTrue(any("UPDATE control_broadcast_deliveries" in item for item in session.executed))
        self.assertTrue(any("UPDATE control_trigger_delivery_logs" in item for item in session.executed))

    async def test_delete_bridge_user_skips_when_devices_still_exist(self) -> None:
        bridge_user = SimpleNamespace(id=133, username="bridge_cleanup_user")
        session = _FakeSession(bridge_user, has_devices=True)

        with (
            patch.object(bot_db, "ensure_schema", new=AsyncMock()),
            patch.object(bot_db, "async_session", new=_FakeSessionFactory(session)),
        ):
            deleted = await bot_db.delete_landing_bridge_user_if_unused(133)

        self.assertFalse(deleted)
        self.assertEqual(session.deleted, [])
        self.assertEqual(session.commits, 0)
        self.assertFalse(any("UPDATE control_broadcast_deliveries" in item for item in session.executed))


if __name__ == "__main__":
    unittest.main()
