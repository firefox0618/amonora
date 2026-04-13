import unittest

from sqlalchemy.dialects import postgresql

from ops import access_reminders, control_error_triggers


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


class OpsQueryHardeningTests(unittest.TestCase):
    def test_access_reminders_user_query_filters_real_trial_users_with_telegram(self) -> None:
        compiled = _compile(
            access_reminders._build_users_query(
                require_telegram=True,
                only_trial_users=True,
            )
        )

        self.assertIn("users.telegram_id is not null", compiled)
        self.assertIn("users.trial_expires_at is not null", compiled)
        self.assertIn("is_synthetic", compiled)
        self.assertIn("bridge_", compiled)

    def test_access_reminders_bridge_purge_query_targets_bridge_users_only(self) -> None:
        compiled = _compile(access_reminders._build_expired_bridge_users_query())

        self.assertIn("bridge_%", compiled)
        self.assertIn("users.subscription_expires_at is not null", compiled)

    def test_control_error_triggers_query_targets_repair_needed_real_users(self) -> None:
        compiled = _compile(control_error_triggers._build_repair_needed_users_query())

        self.assertIn("users.vpn_repair_needed is true", compiled)
        self.assertIn("users.telegram_id is not null", compiled)
        self.assertIn("is_synthetic", compiled)
