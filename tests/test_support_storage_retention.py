import unittest

from support_bot import storage


class _DummySession:
    def __init__(self) -> None:
        self.execute_calls = 0

    async def execute(self, _query):
        self.execute_calls += 1
        raise AssertionError("execute should not be called when retention pruning is disabled")


class SupportStorageRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ticket_lock_is_scoped_per_user_id(self) -> None:
        self.assertIs(storage._ticket_lock(101), storage._ticket_lock(101))
        self.assertIsNot(storage._ticket_lock(101), storage._ticket_lock(202))

    async def test_trim_messages_keeps_full_history(self) -> None:
        session = _DummySession()

        await storage._trim_messages(session, 101)

        self.assertEqual(session.execute_calls, 0)

    async def test_prune_closed_tickets_keeps_archival_history(self) -> None:
        session = _DummySession()

        await storage._prune_closed_tickets(session)

        self.assertEqual(session.execute_calls, 0)


if __name__ == "__main__":
    unittest.main()
