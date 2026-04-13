import unittest
from unittest.mock import AsyncMock, patch

import support_bot.storage as storage


class _ScalarOnlyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _ListResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return list(self._value)


class _DummySession:
    def __init__(self, values):
        self._values = list(values)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarOnlyResult(self._values.pop(0))

    async def commit(self):
        self.commits += 1


class _RecordingCountSession(_DummySession):
    def __init__(self, values):
        super().__init__(values)
        self.executed: list[str] = []

    async def execute(self, query):
        self.executed.append(str(query))
        return await super().execute(query)


class _RecordingListSession:
    def __init__(self, rows):
        self.rows = rows
        self.executed: list[str] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        self.executed.append(str(query))
        return _ListResult(self.rows)

    async def commit(self):
        self.commits += 1


class SupportStorageCountsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_ticket_counts_uses_sql_aggregates(self) -> None:
        session = _DummySession([10, 3, 4, 3, 2])

        with (
            patch.object(storage, "bootstrap_storage", new=AsyncMock()),
            patch.object(storage, "_prune_closed_tickets", new=AsyncMock()) as prune_mock,
            patch.object(storage, "async_session", return_value=session),
        ):
            counts = await storage.get_ticket_counts(admin_id=101)

        prune_mock.assert_awaited_once()
        self.assertEqual(session.commits, 1)
        self.assertEqual(
            counts,
            {
                "all": 10,
                "new": 3,
                "in_progress": 4,
                "closed": 3,
                "mine": 2,
            },
        )

    async def test_get_ticket_counts_exclude_synthetic_joins_users_and_uses_flag_filter(self) -> None:
        session = _RecordingCountSession([10, 3, 4, 3, 2])

        with (
            patch.object(storage, "bootstrap_storage", new=AsyncMock()),
            patch.object(storage, "_prune_closed_tickets", new=AsyncMock()),
            patch.object(storage, "async_session", return_value=session),
        ):
            await storage.get_ticket_counts(admin_id=101, exclude_synthetic=True)

        query_text = "\n".join(session.executed)
        self.assertIn("LEFT OUTER JOIN users ON users.telegram_id = support_tickets.user_id", query_text)
        self.assertIn("users.is_synthetic", query_text)
        self.assertIn("support_tickets.username", query_text)

    async def test_list_tickets_exclude_synthetic_joins_users_and_uses_flag_filter(self) -> None:
        session = _RecordingListSession([])

        with (
            patch.object(storage, "bootstrap_storage", new=AsyncMock()),
            patch.object(storage, "_prune_closed_tickets", new=AsyncMock()),
            patch.object(storage, "async_session", return_value=session),
        ):
            rows = await storage.list_tickets("all", exclude_synthetic=True)

        self.assertEqual(rows, [])
        query_text = "\n".join(session.executed)
        self.assertIn("LEFT OUTER JOIN users ON users.telegram_id = support_tickets.user_id", query_text)
        self.assertIn("users.is_synthetic", query_text)
        self.assertIn("support_tickets.username", query_text)


if __name__ == "__main__":
    unittest.main()
