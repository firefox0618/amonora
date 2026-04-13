import unittest

from types import SimpleNamespace
from unittest.mock import patch

import dashboard.services as dashboard_services


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _AssertingUserSession:
    def __init__(self, users) -> None:
        self._users = users

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        compiled = statement.compile()
        params = compiled.params
        user_id_keys = params.get("id_1", [])
        telegram_id_keys = params.get("telegram_id_1", [])
        self._assert_no_big_telegram_ids_in_user_id_keys(user_id_keys)
        self._assert_big_telegram_ids_stay_in_telegram_keys(telegram_id_keys)
        return _FakeResult(self._users)

    @staticmethod
    def _assert_no_big_telegram_ids_in_user_id_keys(user_id_keys):
        assert all(int(item) <= 2_147_483_647 for item in user_id_keys), user_id_keys

    @staticmethod
    def _assert_big_telegram_ids_stay_in_telegram_keys(telegram_id_keys):
        assert 5_429_984_787 in [int(item) for item in telegram_id_keys], telegram_id_keys


class DashboardSupportTicketKeyHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_support_user_lookup_keeps_big_telegram_ids_out_of_user_id_filter(self) -> None:
        users = [SimpleNamespace(id=18, telegram_id=5_429_984_787, username="real_user")]
        with patch.object(dashboard_services, "async_session", return_value=_AssertingUserSession(users)):
            mapping = await dashboard_services._support_users_by_ticket_keys({18, 5_429_984_787})

        self.assertIn(18, mapping)
        self.assertIn(5_429_984_787, mapping)


if __name__ == "__main__":
    unittest.main()
