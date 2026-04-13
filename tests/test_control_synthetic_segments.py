import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import control_bot.storage as control_storage


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _SegmentSession:
    def __init__(self, user):
        self._user = user

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
        if "from vpn_clients" in text:
            if "from users" not in text or "is_synthetic" not in text:
                raise AssertionError(f"device count query lost real-user subquery: {statement}")
            return _FakeScalarResult([self._user.id])
        if "from users" in text:
            if "is_synthetic" not in text or "bridge_" not in text:
                raise AssertionError(f"segment users query lost synthetic filter: {statement}")
            return _FakeScalarResult([self._user])
        raise AssertionError(f"unexpected query: {statement}")


class ControlSyntheticSegmentsTests(unittest.IsolatedAsyncioTestCase):
    async def test_segment_users_all_reads_only_real_users(self) -> None:
        real_user = SimpleNamespace(
            id=42,
            telegram_id=420042,
            username="real_user",
            is_synthetic=False,
            created_at=datetime(2026, 4, 5, 10, 0, 0),
            last_activity_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=False,
            is_blocked=False,
        )

        with (
            patch.object(control_storage, "async_session", lambda: _SegmentSession(real_user)),
            patch("bot.db.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
        ):
            result = await control_storage.segment_users("all")

        self.assertEqual([user.id for user in result], [42])


if __name__ == "__main__":
    unittest.main()
