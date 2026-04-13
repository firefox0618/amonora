from dataclasses import dataclass
from datetime import timedelta

from bot.config import config
from bot.utils.access import get_access_status_from_user, utcnow


@dataclass
class DummyUser:
    telegram_id: int | None = None
    trial_expires_at: object = None
    trial_used: bool = False
    trial_channel_unsubscribed_at: object = None
    subscription_expires_at: object = None
    subscription_status: str = "inactive"
    subscription_source: str | None = None
    is_blocked: bool = False


def main() -> None:
    now = utcnow()

    trial_user = DummyUser(trial_expires_at=now + timedelta(days=1), trial_used=True)
    assert get_access_status_from_user(trial_user) == "trial_active"

    paused_trial_user = DummyUser(
        trial_expires_at=now + timedelta(days=1),
        trial_used=True,
        trial_channel_unsubscribed_at=now - timedelta(hours=2),
    )
    assert get_access_status_from_user(paused_trial_user) == "expired"

    paid_user = DummyUser(
        subscription_expires_at=now + timedelta(days=5),
        subscription_status="active",
        subscription_source="telegram_stars",
    )
    assert get_access_status_from_user(paid_user) == "paid_active"

    vip_user = DummyUser(
        subscription_expires_at=now + timedelta(days=10),
        subscription_status="active",
        subscription_source="manual_vip",
    )
    assert get_access_status_from_user(vip_user) == "vip_active"

    admin_user = DummyUser(telegram_id=config.admin_ids[0])
    assert get_access_status_from_user(admin_user) == "vip_active"

    blocked_user = DummyUser(
        telegram_id=config.admin_ids[0],
        trial_expires_at=now + timedelta(days=1),
        subscription_expires_at=now + timedelta(days=1),
        subscription_status="active",
        is_blocked=True,
    )
    assert get_access_status_from_user(blocked_user) == "blocked"

    expired_user = DummyUser(
        trial_expires_at=now - timedelta(days=1),
        trial_used=True,
        subscription_expires_at=now - timedelta(days=1),
        subscription_status="inactive",
    )
    assert get_access_status_from_user(expired_user) == "expired"

    print("Access logic tests passed")


if __name__ == "__main__":
    main()
