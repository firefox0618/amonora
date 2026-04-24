from __future__ import annotations

import json
from math import ceil

from backend.core.promo_codes import get_user_pending_discount
from bot.db import (
    get_active_device_slot_counts_for_users,
    get_user_balance_summary,
    get_user_by_telegram_id,
    get_user_referral_stats,
    get_user_vpn_clients,
    get_vpn_client_by_id,
)
from bot.public_subscription import (
    _normalize_device_type,
    _normalize_public_os_version,
    build_public_subscription_happ_wrapper_url,
    get_or_create_public_subscription_page_url_for_user,
    get_public_subscription_bound_devices_for_user,
)
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_access_status_from_user,
    get_device_limit_for_user,
    has_active_access_from_user,
    utcnow,
)
from bot.utils.subscription_accounting import (
    ADMIN_ACCESS_SOURCES,
    MANUAL_ACCESS_SOURCES,
    MANUAL_EXTENSION_SOURCES,
    humanize_extension_duration,
    load_subscription_payment_snapshot,
    manual_extension_days,
)

from bot.services.user.models import TestBonusSummary, TestUserSummary


def _format_status_label(user) -> str:
    return "✅ Подписка активна" if has_active_access_from_user(user) else "❌ Не активна"


def _format_expires_text(expires_at) -> str:
    if expires_at is None:
        return "—"
    return expires_at.strftime("%d.%m.%Y %H:%M")


def _format_days_left_text(expires_at) -> str:
    if expires_at is None:
        return "—"
    remaining_seconds = (expires_at - utcnow()).total_seconds()
    if remaining_seconds <= 0:
        return "0 дней"
    days_left = max(1, ceil(remaining_seconds / 86400))
    return f"{days_left} дн."


async def _subscription_billing_summary_for_user(user) -> tuple[str, str | None]:
    status = get_access_status_from_user(user)
    if status == "trial_active":
        return "Пробный период", None
    if status == "vip_active":
        return "Админ доступ", None
    if status != "paid_active":
        return "Без тарифа", None

    snapshot = await load_subscription_payment_snapshot(int(user.id))
    subscription_source = str(getattr(user, "subscription_source", "") or "").strip().lower()
    tariff_title = snapshot.latest_tariff_title
    if not tariff_title:
        if subscription_source in MANUAL_ACCESS_SOURCES:
            tariff_title = "Ручной доступ"
        elif subscription_source in ADMIN_ACCESS_SOURCES:
            tariff_title = "Админ доступ"
        else:
            tariff_title = "Платный доступ"

    manual_label: str | None = None
    if subscription_source in MANUAL_EXTENSION_SOURCES:
        extension_days = manual_extension_days(
            get_access_expires_at_from_user(user),
            snapshot.payment_only_expires_at,
        )
        if extension_days > 0:
            manual_label = humanize_extension_duration(extension_days)
    return tariff_title, manual_label


def _normalize_connection_uri(value: str | None) -> str | None:
    payload = str(value or "").strip()
    return payload or None


def _device_metadata(device) -> dict:
    raw_value = getattr(device, "client_data", None)
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _device_connection_uri(device, metadata: dict) -> str | None:
    if not metadata:
        return None
    if device.protocol == "trojan":
        return _normalize_connection_uri(metadata.get("connection_uri") or metadata.get("trojan_link"))
    return _normalize_connection_uri(metadata.get("connection_uri") or metadata.get("vless_link"))


def _device_display_row(device, metadata: dict) -> dict:
    device_name = str(metadata.get("device_name") or getattr(device, "email", f"Устройство #{device.id}"))
    country_name = str(metadata.get("country_name") or metadata.get("country_code") or "—")
    protocol = str(metadata.get("protocol") or getattr(device, "protocol", "vless")).upper()
    connection_uri = _device_connection_uri(device, metadata)
    device_type = _normalize_device_type(str(metadata.get("device_type") or "other").strip().lower()) or "other"
    device_model = str(
        metadata.get("device_model")
        or metadata.get("model")
        or metadata.get("hardware_model")
        or metadata.get("device_name")
        or getattr(device, "email", f"Устройство #{device.id}")
    )
    raw_os_version = (
        metadata.get("os_version")
        or metadata.get("platform_version")
        or metadata.get("system_version")
        or metadata.get("os_build")
    )
    os_version = str(
        _normalize_public_os_version(
            device_type=device_type,
            os_version=raw_os_version,
            user_agent=metadata.get("user_agent"),
        )
        or "—"
    )
    return {
        "kind": "vpn_client",
        "id": int(device.id),
        "title": device_name,
        "country_name": country_name,
        "protocol": protocol,
        "connection_uri": connection_uri,
        "device_type": device_type,
        "device_model": device_model,
        "os_version": os_version,
    }


def _public_subscription_device_row(device: dict) -> dict:
    device_title = str(device.get("title") or device.get("device_model") or f"Happ #{device.get('id') or '?'}").strip()
    return {
        "kind": "public_slot",
        "id": int(device.get("id") or 0),
        "title": device_title or f"Happ #{device.get('id') or '?'}",
        "country_name": "Единая ссылка",
        "protocol": "SUB",
        "connection_uri": None,
        "device_type": str(device.get("device_type") or "other").strip().lower() or "other",
        "device_model": str(device.get("device_model") or device_title or "Happ device").strip() or "Happ device",
        "os_version": str(device.get("os_version") or "—").strip() or "—",
    }


async def _load_test_user_summary(telegram_id: int) -> TestUserSummary:
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return TestUserSummary(
            telegram_id=int(telegram_id),
            access_active=False,
            status_label="❌ Не активна",
            days_left_text="—",
            expires_text="—",
            balance_rub=0,
            tariff_title="Без тарифа",
            devices_count=0,
            device_limit=1,
            devices=(),
            single_connection_uri=None,
        )

    expires_at = get_access_expires_at_from_user(user)
    tariff_title, manual_extension_label = await _subscription_billing_summary_for_user(user)
    subscription_page_url: str | None = None
    happ_subscription_url: str | None = None
    try:
        subscription_page_url = await get_or_create_public_subscription_page_url_for_user(int(user.id))
        if subscription_page_url:
            happ_subscription_url = build_public_subscription_happ_wrapper_url(subscription_page_url)
    except Exception:
        subscription_page_url = None
        happ_subscription_url = None
    active_slot_counts = await get_active_device_slot_counts_for_users([int(user.id)])
    setattr(user, "active_device_slot_addons", int(active_slot_counts.get(int(user.id), 0)))
    device_limit = get_device_limit_for_user(user)
    balance_summary = await get_user_balance_summary(int(user.id))
    raw_vpn_devices = await get_user_vpn_clients(int(user.id))
    raw_vpn_devices = sorted(
        raw_vpn_devices,
        key=lambda item: (
            str(getattr(item, "created_at", "") or ""),
            int(getattr(item, "id", 0)),
        ),
    )
    vpn_devices = tuple(_device_display_row(device, _device_metadata(device)) for device in raw_vpn_devices)
    public_devices = tuple(
        _public_subscription_device_row(device)
        for device in await get_public_subscription_bound_devices_for_user(int(user.id))
    )
    devices = vpn_devices + public_devices
    single_connection_uri = devices[0]["connection_uri"] if len(devices) == 1 else None
    return TestUserSummary(
        telegram_id=int(telegram_id),
        access_active=has_active_access_from_user(user),
        status_label=_format_status_label(user),
        days_left_text=_format_days_left_text(expires_at),
        expires_text=_format_expires_text(expires_at),
        balance_rub=int(balance_summary.get("balance_available_rub", 0) or 0),
        tariff_title=tariff_title,
        devices_count=len(devices),
        device_limit=int(device_limit),
        devices=devices,
        single_connection_uri=single_connection_uri,
        subscription_page_url=subscription_page_url,
        happ_subscription_url=happ_subscription_url,
        manual_extension_label=manual_extension_label,
    )


async def _load_bonus_summary(telegram_id: int) -> TestBonusSummary:
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return TestBonusSummary(
            referral_link="Ссылка появится после активации аккаунта",
            invited_count=0,
            paid_count=0,
            earned_total_rub=0,
            balance_available_rub=0,
        )
    stats = await get_user_referral_stats(int(user.id))
    referral_link = str(stats.get("ref_link") or "").strip() or "Ссылка появится после активации аккаунта"
    return TestBonusSummary(
        referral_link=referral_link,
        invited_count=int(stats.get("invited_count", 0) or 0),
        paid_count=int(stats.get("paid_count", 0) or 0),
        earned_total_rub=int(stats.get("total_earned_rub", 0) or 0),
        balance_available_rub=int(stats.get("balance_available_rub", 0) or 0),
    )


def _subscription_connection_uri(summary: TestUserSummary) -> str | None:
    if summary.subscription_page_url:
        return summary.subscription_page_url
    if summary.single_connection_uri:
        return summary.single_connection_uri
    for device in summary.devices:
        connection_uri = str(device.get("connection_uri") or "").strip()
        if connection_uri:
            return connection_uri
    return None


async def _get_owned_test_device_for_telegram(telegram_id: int, device_id: int):
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return None, None
    device = await get_vpn_client_by_id(int(device_id))
    if device is None or int(device.user_id) != int(user.id):
        return user, None
    return user, device


async def _load_pending_discount_payload(user_id: int) -> dict | None:
    redemption = await get_user_pending_discount(int(user_id))
    if redemption is None:
        return None
    discount_percent = max(int(getattr(redemption, "discount_percent", 0) or 0), 0)
    if discount_percent <= 0:
        return None
    return {
        "redemption_id": int(redemption.id),
        "discount_percent": discount_percent,
    }
