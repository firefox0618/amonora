from __future__ import annotations

from math import ceil

from backend.core.promo_codes import get_user_pending_discount
from bot.db import (
    get_active_device_slot_counts_for_users,
    get_user_balance_summary,
    get_user_by_telegram_id,
    get_user_referral_stats,
    get_vpn_client_by_id,
)
from bot.public_subscription import (
    build_public_subscription_happ_wrapper_url,
    get_account_devices_for_user,
    get_or_create_public_subscription_page_url_for_user,
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
    devices = tuple(await get_account_devices_for_user(int(user.id)))
    single_connection_uri = devices[0].get("connection_uri") if len(devices) == 1 else None
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
