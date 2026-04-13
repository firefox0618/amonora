import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import dashboard.services as dashboard_services
from dashboard.services import get_support_tickets


class _FakeResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._scalar, list):
            return self._scalar
        return []


class _FakeUserSession:
    def __init__(self, users) -> None:
        self._users = users

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "FROM users" in text:
            return _FakeResult(self._users)
        raise AssertionError(f"unexpected query: {text}")


class DashboardSupportQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_filter_uses_active_ticket_slice_by_default(self) -> None:
        with (
            patch("dashboard.services.list_tickets", new=AsyncMock(return_value=[])) as list_mock,
        ):
            await get_support_tickets(filter_mode="queue", search="", admin=None)

        list_mock.assert_awaited_once_with("queue", admin_id=None, search="", exclude_synthetic=True)

    async def test_queue_search_can_find_closed_ticket_by_tg_id(self) -> None:
        tickets = [
            {
                "user_id": 1926159631,
                "username": "closed_user",
                "full_name": "Closed User",
                "status": "closed",
                "last_user_message_preview": "Нужна помощь",
            },
            {
                "user_id": 777,
                "username": "active_user",
                "full_name": "Active User",
                "status": "new",
                "last_user_message_preview": "Привет",
            },
        ]

        admin = SimpleNamespace(telegram_id=5511)
        with (
            patch("dashboard.services.list_tickets", new=AsyncMock(return_value=[tickets[0]])) as list_mock,
        ):
            result = await get_support_tickets(filter_mode="queue", search="1926159631", admin=admin)

        list_mock.assert_awaited_once_with("all", admin_id=5511, search="1926159631", exclude_synthetic=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
