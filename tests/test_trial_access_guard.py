import unittest

from datetime import timedelta
from types import SimpleNamespace

from bot.utils.access import can_activate_trial_from_user, has_active_trial_from_user, utcnow


class TrialAccessGuardTests(unittest.TestCase):
    def test_trial_cannot_activate_for_used_or_paid_user(self) -> None:
        now = utcnow()
        used_trial_user = SimpleNamespace(
            is_blocked=False,
            trial_used=True,
            trial_expires_at=None,
            subscription_status="inactive",
            subscription_expires_at=None,
        )
        paid_user = SimpleNamespace(
            is_blocked=False,
            trial_used=False,
            trial_expires_at=None,
            subscription_status="active",
            subscription_expires_at=now + timedelta(days=3),
        )

        self.assertFalse(can_activate_trial_from_user(used_trial_user))
        self.assertFalse(can_activate_trial_from_user(paid_user))

    def test_trial_is_not_active_when_channel_membership_paused(self) -> None:
        now = utcnow()
        paused_trial_user = SimpleNamespace(
            is_blocked=False,
            trial_used=True,
            trial_expires_at=now + timedelta(days=2),
            trial_channel_unsubscribed_at=now - timedelta(hours=1),
            subscription_status="inactive",
            subscription_expires_at=None,
        )

        self.assertFalse(has_active_trial_from_user(paused_trial_user))

    def test_trial_can_activate_only_for_clean_inactive_user(self) -> None:
        user = SimpleNamespace(
            is_blocked=False,
            trial_used=False,
            trial_expires_at=None,
            subscription_status="inactive",
            subscription_expires_at=None,
        )

        self.assertTrue(can_activate_trial_from_user(user))


if __name__ == "__main__":
    unittest.main()
