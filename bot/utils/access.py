from datetime import datetime, timezone

from bot.config import config
from bot.utils.device_slots import DEFAULT_DEVICE_LIMIT, effective_device_limit_for_user


VIP_SUBSCRIPTION_SOURCES = {
    "dashboard_vip",
    "manual_vip",
    "vip",
    "vip_free",
    "complimentary",
}

ADMIN_DEVICE_LIMIT = 30
PERSONAL_DEVICE_LIMITS: dict[int, int] = {
    417561011: 20,  # @s_ufa
}
TRIAL_ACTIVITY_LEVEL_LOW = "low"
TRIAL_ACTIVITY_LEVEL_ACTIVE = "active"


def _complimentary_admin_ids() -> set[int]:
    return set(config.admin_ids) | set(config.support_admin_ids)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def has_admin_complimentary_access_from_user(user) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    return getattr(user, "telegram_id", None) in _complimentary_admin_ids()


def is_admin_telegram_id(telegram_id: int | None) -> bool:
    return telegram_id in _complimentary_admin_ids()


def get_device_limit_for_telegram_id(telegram_id: int | None) -> int:
    return ADMIN_DEVICE_LIMIT if is_admin_telegram_id(telegram_id) else DEFAULT_DEVICE_LIMIT


def get_device_limit_for_user(user) -> int:
    telegram_id = getattr(user, "telegram_id", None)
    personal_limit = PERSONAL_DEVICE_LIMITS.get(int(telegram_id)) if telegram_id is not None else None
    if personal_limit is not None:
        return max(int(personal_limit), 1)

    base_limit = get_device_limit_for_telegram_id(telegram_id)
    if base_limit == ADMIN_DEVICE_LIMIT:
        return base_limit
    return effective_device_limit_for_user(user, base_limit=base_limit)


def has_trial_window_from_user(user) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    trial_expires_at = getattr(user, "trial_expires_at", None)
    return bool(trial_expires_at and trial_expires_at > utcnow())


def get_trial_activity_level_from_user(user) -> str:
    raw_value = str(getattr(user, "trial_activity_level", "") or "").strip().lower()
    if raw_value == TRIAL_ACTIVITY_LEVEL_ACTIVE:
        return TRIAL_ACTIVITY_LEVEL_ACTIVE
    return TRIAL_ACTIVITY_LEVEL_LOW


def trial_is_paused_by_channel_from_user(user) -> bool:
    if not has_trial_window_from_user(user):
        return False
    if has_active_subscription_from_user(user):
        return False
    return getattr(user, "trial_channel_unsubscribed_at", None) is not None


def has_active_trial_from_user(user) -> bool:
    return has_trial_window_from_user(user) and not trial_is_paused_by_channel_from_user(user)


def has_active_subscription_from_user(user) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    subscription_expires_at = getattr(user, "subscription_expires_at", None)
    return subscription_expires_at is not None and subscription_expires_at > utcnow()


def has_active_access_from_user(user) -> bool:
    return (
        has_admin_complimentary_access_from_user(user)
        or has_active_subscription_from_user(user)
        or has_active_trial_from_user(user)
    )


def can_activate_trial_from_user(user) -> bool:
    if user is None or getattr(user, "is_blocked", False):
        return False
    if getattr(user, "trial_used", False):
        return False
    if getattr(user, "subscription_expires_at", None) is not None:
        return False
    return not has_active_access_from_user(user)


def has_vip_access_from_user(user) -> bool:
    return has_admin_complimentary_access_from_user(user) or (
        has_active_subscription_from_user(user) and (getattr(user, "subscription_source", None) or "") in VIP_SUBSCRIPTION_SOURCES
    )


def get_access_expires_at_from_user(user):
    if has_active_subscription_from_user(user):
        return user.subscription_expires_at
    if has_active_trial_from_user(user):
        return user.trial_expires_at
    return None


def get_access_status_from_user(user) -> str:
    if getattr(user, "is_blocked", False):
        return "blocked"
    if has_vip_access_from_user(user):
        return "vip_active"
    if has_active_subscription_from_user(user):
        return "paid_active"
    if has_active_trial_from_user(user):
        return "trial_active"
    if getattr(user, "trial_used", False) or getattr(user, "subscription_expires_at", None) is not None:
        return "expired"
    return "inactive"
