from __future__ import annotations

import calendar
from datetime import datetime

from bot.config import config


DEVICE_SLOT_PRODUCT_TYPE = "device_slot_addon"
DEVICE_SLOT_TARIFF_CODE = "device_slot_addon"
DEFAULT_DEVICE_LIMIT = 3
MAX_DEVICE_LIMIT = 8
DEVICE_SLOT_DURATION_DAYS = 30


def device_slot_unit_price_rub() -> int:
    return max(int(getattr(config, "device_slot_unit_price_rub", 49) or 49), 1)


def device_slot_max_extra_slots() -> int:
    configured = max(int(getattr(config, "device_slot_max_extra_slots", 5) or 5), 0)
    return min(configured, max(MAX_DEVICE_LIMIT - DEFAULT_DEVICE_LIMIT, 0))


def clamp_device_slot_count(slots_count: int) -> int:
    return min(max(int(slots_count), 0), device_slot_max_extra_slots())


def active_extra_device_slots_from_user(user) -> int:
    return clamp_device_slot_count(int(getattr(user, "active_device_slot_addons", 0) or 0))


def effective_device_limit_for_user(user, *, base_limit: int) -> int:
    return min(int(base_limit) + active_extra_device_slots_from_user(user), MAX_DEVICE_LIMIT)


def remaining_device_slot_capacity(user, *, base_limit: int) -> int:
    current_limit = effective_device_limit_for_user(user, base_limit=base_limit)
    return max(MAX_DEVICE_LIMIT - current_limit, 0)


def device_slot_title(slots_count: int = 1) -> str:
    safe_slots = max(int(slots_count), 1)
    return f"+{safe_slots} устройство" if safe_slots == 1 else f"+{safe_slots} устройства"


def device_slot_display_title(slots_count: int = 1) -> str:
    return f"{device_slot_title(slots_count)} на 1 месяц"


def is_device_slot_product(*, product_type: str | None = None, tariff_code: str | None = None) -> bool:
    return str(product_type or "").strip().lower() == DEVICE_SLOT_PRODUCT_TYPE or str(tariff_code or "").strip().lower() == DEVICE_SLOT_TARIFF_CODE


def payment_product_type(metadata: dict | None = None, *, tariff_code: str | None = None) -> str:
    payload = metadata if isinstance(metadata, dict) else {}
    explicit = str(payload.get("product_type") or "").strip().lower()
    if explicit:
        return explicit
    if is_device_slot_product(tariff_code=tariff_code):
        return DEVICE_SLOT_PRODUCT_TYPE
    return "subscription"


def device_slot_duration_days(expires_at: datetime | None, *, now: datetime | None = None) -> int:
    if expires_at is None:
        return 0
    current = now or datetime.utcnow()
    if expires_at <= current:
        return 0
    return max((expires_at - current).days, 0)


def add_device_slot_month(start_at: datetime) -> datetime:
    safe_start = start_at or datetime.utcnow()
    year = safe_start.year
    month = safe_start.month + 1
    if month > 12:
        month = 1
        year += 1
    day = min(safe_start.day, calendar.monthrange(year, month)[1])
    return safe_start.replace(year=year, month=month, day=day)
