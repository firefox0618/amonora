import unittest

from types import SimpleNamespace

import ops.access_reminders as access_reminders
import ops.control_error_triggers as control_error_triggers


class OpsSyntheticFiltersTests(unittest.TestCase):
    def test_access_reminders_treats_bridge_users_as_synthetic(self) -> None:
        user = SimpleNamespace(username="bridge_test_user")

        self.assertTrue(access_reminders._is_synthetic_user(user))

    def test_access_reminders_treats_flagged_users_as_synthetic(self) -> None:
        user = SimpleNamespace(username="ordinary_user", is_synthetic=True)

        self.assertTrue(access_reminders._is_synthetic_user(user))

    def test_control_error_triggers_treats_bridge_users_as_synthetic(self) -> None:
        user = SimpleNamespace(username="bridge_test_user")

        self.assertTrue(control_error_triggers._is_synthetic_user(user))

    def test_control_error_triggers_treats_flagged_users_as_synthetic(self) -> None:
        user = SimpleNamespace(username="ordinary_user", is_synthetic=True)

        self.assertTrue(control_error_triggers._is_synthetic_user(user))


if __name__ == "__main__":
    unittest.main()
