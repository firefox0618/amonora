import unittest
from unittest.mock import patch

from control_bot.access import CONTROL_ROLE_ADMIN, control_admins, control_allowed_telegram_ids


class ControlAccessTests(unittest.TestCase):
    def test_control_access_falls_back_to_admin_ids_when_control_lists_are_empty(self) -> None:
        with (
            patch("control_bot.access.config.control_owner_ids", []),
            patch("control_bot.access.config.control_admin_ids", []),
            patch("control_bot.access.config.control_operator_ids", []),
            patch("control_bot.access.config.control_support_view_only_ids", []),
            patch("control_bot.access.config.control_allowed_telegram_ids", []),
            patch("control_bot.access.config.admin_ids", [7650618403, 548589949]),
            patch("control_bot.access.config.support_admin_ids", [548589949, 5487345316]),
        ):
            admins = control_admins()
            allowed_ids = control_allowed_telegram_ids()

        self.assertEqual([item.telegram_id for item in admins], [7650618403, 548589949, 5487345316])
        self.assertTrue(all(item.role == CONTROL_ROLE_ADMIN for item in admins))
        self.assertEqual(allowed_ids, [7650618403, 548589949, 5487345316])


if __name__ == "__main__":
    unittest.main()
