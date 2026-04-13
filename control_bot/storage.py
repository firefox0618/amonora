from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from typing import Any

from sqlalchemy import delete, select

from backend.core.database import async_session
from backend.core.models import (
    ControlAdminNotificationPreference,
    ControlBroadcastCampaign,
    ControlBroadcastDelivery,
    ControlMessageTemplate,
    ControlNotificationEvent,
    ControlTriggerDeliveryLog,
    ControlTriggerRule,
    User,
    VpnClient,
)
from backend.core.synthetic_users import real_user_sql_clause as shared_real_user_sql_clause
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_device_limit_for_user,
    get_access_status_from_user,
    utcnow,
)
from bot.utils.tariffs import PROMO_DATE_RANGE_LABEL, promo_tariff_offer_block
from control_bot.access import (
    CONTROL_ROLE_ADMIN,
    CONTROL_ROLE_OPERATOR,
    CONTROL_ROLE_OWNER,
    CONTROL_ROLE_SUPPORT_VIEW_ONLY,
    control_admins,
    control_role_for_telegram_id,
)
from dashboard.models import DashboardAdmin, DashboardSession, PaymentRecord

NOTIFICATION_CATEGORIES = [
    "payments",
    "users",
    "new_users",
    "trials",
    "access_keys",
    "support",
    "nodes",
    "security",
    "system",
]
LEGACY_NOTIFICATION_CATEGORY_MAP = {
    "access": "users",
    "panel_auth": "security",
    "errors": "system",
}
ROLE_DEFAULT_NOTIFICATION_PREFERENCES = {
    CONTROL_ROLE_OWNER: {category: True for category in NOTIFICATION_CATEGORIES},
    CONTROL_ROLE_ADMIN: {category: True for category in NOTIFICATION_CATEGORIES},
    CONTROL_ROLE_OPERATOR: {
        "payments": True,
        "users": True,
        "new_users": True,
        "trials": True,
        "access_keys": True,
        "support": True,
        "nodes": False,
        "security": True,
        "system": False,
    },
    CONTROL_ROLE_SUPPORT_VIEW_ONLY: {
        "payments": False,
        "users": True,
        "new_users": True,
        "trials": True,
        "access_keys": True,
        "support": True,
        "nodes": False,
        "security": False,
        "system": False,
    },
}
ROLE_MANDATORY_NOTIFICATION_CATEGORIES = {
    CONTROL_ROLE_OWNER: {"payments", "users", "nodes", "security", "system"},
    CONTROL_ROLE_ADMIN: {"payments", "users", "nodes", "security", "system"},
    CONTROL_ROLE_OPERATOR: {"payments", "users", "support", "security"},
    CONTROL_ROLE_SUPPORT_VIEW_ONLY: {"support"},
}

CAMPAIGN_SCOPE_ADMIN = "admin_push"
CAMPAIGN_SCOPE_USER = "user_broadcast"
CAMPAIGN_SCOPE_TRIGGER = "trigger"

CTA_ACTIONS = {
    "open_tariffs": "💳 Перейти к оплате",
    "open_devices": "📱 Открыть устройства",
    "start_trial": "🎁 Активировать пробный",
    "open_support": "🛟 Поддержка",
    "open_channel": "📡 Канал",
}


def _default_trigger_template_body(key: str) -> str:
    if key == "trial_ends_1d":
        return (
            "🎁 Пробный доступ заканчивается завтра.\n\n"
            "Откройте тарифы заранее, чтобы сохранить доступ после окончания пробного периода."
        )
    if key == "trial_ends_today":
        return (
            "⏳ Пробный доступ заканчивается сегодня.\n\n"
            "Продлите доступ сейчас, чтобы не потерять подключение после окончания пробного периода."
        )
    if key == "trial_expired_3d":
        return (
            "🔒 Пробный доступ уже завершился.\n\n"
            "Откройте тарифы, чтобы восстановить доступ сразу после оплаты."
        )
    raise KeyError(key)


_STALE_PROMO_TRIGGER_BODIES = {
    "trial_ends_1d": {
        (
            "🎁 Пробный доступ заканчивается завтра.\n\n"
            "До 31 марта 2026 включительно можно подключить тариф с бонусными месяцами:\n"
            "3 месяца — +1 месяц в подарок\n"
            "6 месяцев — +2 месяца в подарок\n"
            "12 месяцев — +3 месяца в подарок\n\n"
            "Откройте тарифы и зафиксируйте выгодные условия."
        ),
        (
            "🎁 Пробный доступ заканчивается завтра.\n\n"
            f"Только {PROMO_DATE_RANGE_LABEL} можно подключить тариф с бонусными месяцами:\n"
            f"{promo_tariff_offer_block()}\n\n"
            "Откройте тарифы и зафиксируйте выгодные условия."
        ),
    },
    "trial_ends_today": {
        (
            "⏳ Пробный доступ заканчивается сегодня.\n\n"
            "До 31 марта 2026 включительно действуют подарочные месяцы:\n"
            "3 месяца — +1 месяц\n"
            "6 месяцев — +2 месяца\n"
            "12 месяцев — +3 месяца\n\n"
            "Продлите доступ сейчас, чтобы не потерять подключение и забрать бонус."
        ),
        (
            "⏳ Пробный доступ заканчивается сегодня.\n\n"
            f"Только {PROMO_DATE_RANGE_LABEL} можно подключить тариф с подарочными месяцами:\n"
            f"{promo_tariff_offer_block(include_gift_wording=False)}\n\n"
            "Продлите доступ сейчас, чтобы не потерять подключение и забрать бонус."
        ),
    },
    "trial_expired_3d": {
        (
            "🔒 Пробный доступ уже завершился.\n\n"
            "До 31 марта 2026 включительно можно вернуться на выгодных условиях:\n"
            "3 месяца — +1 месяц в подарок\n"
            "6 месяцев — +2 месяца в подарок\n"
            "12 месяцев — +3 месяца в подарок\n\n"
            "Откройте тарифы, чтобы восстановить доступ сразу после оплаты."
        ),
        (
            "🔒 Пробный доступ уже завершился.\n\n"
            f"Акция с бонусными месяцами действует только {PROMO_DATE_RANGE_LABEL}:\n"
            f"{promo_tariff_offer_block()}\n\n"
            "Откройте тарифы, чтобы вернуть доступ сразу после оплаты."
        ),
    },
}

TRIGGER_DEFAULTS = [
    {
        "key": "trial_ends_1d",
        "family": "trial",
        "title": "🎁 Окончание пробного периода — за 1 день",
        "description": "Напоминание за день до окончания пробного периода.",
        "enabled": False,
        "config": {"kind": "days_before", "days": 1, "send_hour": 10},
        "template_body": _default_trigger_template_body("trial_ends_1d"),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "trial_ends_today",
        "family": "trial",
        "title": "🎁 Окончание пробного периода — сегодня",
        "description": "Напоминание в день окончания пробного периода.",
        "enabled": False,
        "config": {"kind": "days_before", "days": 0, "send_hour": 9},
        "template_body": _default_trigger_template_body("trial_ends_today"),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "trial_active_2h",
        "family": "trial",
        "title": "🚀 Активный trial — через 2 часа",
        "description": "Follow-up для trial-пользователя, который уже дошёл до технического шага.",
        "enabled": True,
        "config": {"kind": "trial_hours_since_start", "hours": 2, "segment": "active"},
        "template_body": (
            "🔥 Видим, что ты уже начал настройку в Amonora Connect.\n\n"
            "Подключение уже идёт в правильную сторону — осталось закрепить результат и сохранить доступ после trial."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "trial_low_2h",
        "family": "trial",
        "title": "🧭 Trial без подключения — через 2 часа",
        "description": "Follow-up для trial-пользователя, который ещё не дошёл до технической настройки.",
        "enabled": True,
        "config": {"kind": "trial_hours_since_start", "hours": 2, "segment": "low"},
        "template_body": (
            "👀 Похоже, ты ещё не дошёл до подключения.\n\n"
            "Давай закончим настройку: открой устройства, создай первое подключение и получи ключ."
        ),
        "buttons": [{"action": "open_devices", "label": CTA_ACTIONS["open_devices"]}],
    },
    {
        "key": "trial_active_24h",
        "family": "trial",
        "title": "💎 Активный trial — через 24 часа",
        "description": "Дожим для активного trial-пользователя спустя сутки после старта.",
        "enabled": True,
        "config": {"kind": "trial_hours_since_start", "hours": 24, "segment": "active"},
        "template_body": (
            "💎 У тебя уже есть рабочая настройка в Amonora Connect.\n\n"
            "Сохрани доступ и стабильный режим до конца периода — продлить подписку можно прямо сейчас."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "trial_low_24h",
        "family": "trial",
        "title": "🛠 Trial без подключения — через 24 часа",
        "description": "Повторный follow-up, если за сутки trial-пользователь так и не дошёл до настройки.",
        "enabled": True,
        "config": {"kind": "trial_hours_since_start", "hours": 24, "segment": "low"},
        "template_body": (
            "⏳ Trial уже идёт, но устройство ещё не настроено.\n\n"
            "Доведи подключение до конца сейчас: открой устройства, создай первое подключение и получи ключ."
        ),
        "buttons": [{"action": "open_devices", "label": CTA_ACTIONS["open_devices"]}],
    },
    {
        "key": "trial_final_6h",
        "family": "trial",
        "title": "⚠️ До конца trial — 6 часов",
        "description": "Финальный follow-up перед окончанием пробного периода.",
        "enabled": True,
        "config": {"kind": "trial_hours_before_expiry", "hours": 6},
        "template_body": (
            "⚠️ Настройки уже адаптированы под тебя.\n\n"
            "До конца trial осталось меньше 6 часов. Если хочешь сохранить текущий режим и доступ, открой тарифы прямо сейчас."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "trial_expired_3d",
        "family": "trial",
        "title": "🎁 После окончания пробного периода — через 3 дня",
        "description": "Follow-up после окончания trial.",
        "enabled": True,
        "config": {"kind": "days_after_trial_expiry", "days": 3, "send_hour": 12},
        "template_body": _default_trigger_template_body("trial_expired_3d"),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "inactive_7d",
        "family": "inactive",
        "title": "⏳ Неактивность пользователя — 7 дней",
        "description": "Пользователь давно не открывал продуктовый контур.",
        "enabled": True,
        "config": {"kind": "inactive_days", "days": 7, "send_hour": 12},
        "template_body": (
            "⏳ Вы давно не заходили в Amonora Connect.\n\n"
            "Если нужна помощь или новый ключ, всё доступно прямо в боте."
        ),
        "buttons": [{"action": "open_support", "label": CTA_ACTIONS["open_support"]}],
    },
    {
        "key": "inactive_30d",
        "family": "inactive",
        "title": "⏳ Неактивность пользователя — 30 дней",
        "description": "Долгая неактивность пользователя.",
        "enabled": False,
        "config": {"kind": "inactive_days", "days": 30, "send_hour": 12},
        "template_body": (
            "⏳ Вы давно не пользовались Amonora Connect.\n\n"
            "Если хотите вернуться, бот поможет быстро восстановить доступ."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "start_no_action_1h",
        "family": "start_no_action",
        "title": "🚀 Старт без действий — через 1 час",
        "description": "Пользователь нажал /start, но не продолжил путь.",
        "enabled": True,
        "config": {"kind": "start_no_action_hours", "hours": 1},
        "template_body": (
            "🚀 Вы уже рядом с подключением.\n\n"
            "Откройте тарифы или активируйте пробный период прямо в боте."
        ),
        "buttons": [{"action": "start_trial", "label": CTA_ACTIONS["start_trial"]}],
    },
    {
        "key": "start_no_action_3h",
        "family": "start_no_action",
        "title": "🚀 Старт без действий — через 3 часа",
        "description": "Повторный follow-up для нового пользователя.",
        "enabled": True,
        "config": {"kind": "start_no_action_hours", "hours": 3},
        "template_body": (
            "🚀 Нужна помощь с первым подключением?\n\n"
            "В Amonora Connect всё можно сделать прямо в Telegram."
        ),
        "buttons": [{"action": "open_support", "label": CTA_ACTIONS["open_support"]}],
    },
    {
        "key": "subscription_expires_3d",
        "family": "subscription",
        "title": "💎 Окончание подписки — за 3 дня",
        "description": "Напоминание о скором завершении доступа.",
        "enabled": True,
        "config": {"kind": "days_before_access_expiry", "days": 3, "send_hour": 10},
        "template_body": (
            "💎 Ваш доступ в Amonora Connect заканчивается через 3 дня.\n\n"
            "Продлить подписку можно в пару нажатий."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "subscription_expires_today",
        "family": "subscription",
        "title": "💎 Окончание подписки — сегодня",
        "description": "Напоминание в день окончания доступа.",
        "enabled": True,
        "config": {"kind": "days_before_access_expiry", "days": 0, "send_hour": 9},
        "template_body": (
            "💎 Ваш доступ в Amonora Connect истекает сегодня.\n\n"
            "Продлите подписку, чтобы не терять рабочие устройства и ключи."
        ),
        "buttons": [{"action": "open_tariffs", "label": CTA_ACTIONS["open_tariffs"]}],
    },
    {
        "key": "device_limit_reached",
        "family": "devices",
        "title": "📱 Достигнут лимит устройств",
        "description": "У пользователя достигнут лимит устройств.",
        "enabled": False,
        "config": {"kind": "device_limit", "limit": 3},
        "template_body": (
            "📱 У вас достигнут лимит устройств в Amonora Connect.\n\n"
            "Если нужно подключить новое устройство, сначала отвяжите одно из текущих."
        ),
        "buttons": [{"action": "open_support", "label": CTA_ACTIONS["open_support"]}],
    },
    {
        "key": "access_issue",
        "family": "access_issue",
        "title": "🔌 Проблемы с доступом",
        "description": "У пользователя зафиксирована проблема с доступом или выдачей ключа.",
        "enabled": True,
        "config": {"kind": "access_issue"},
        "template_body": (
            "🔌 Мы заметили проблему с доступом к Amonora Connect.\n\n"
            "Откройте поддержку, если нужно ускорить проверку вручную."
        ),
        "buttons": [{"action": "open_support", "label": CTA_ACTIONS["open_support"]}],
    },
]

TRIAL_LEGACY_DISABLED_KEYS = {
    "trial_ends_1d",
    "trial_ends_today",
}


@dataclass(frozen=True)
class ControlAdminProfile:
    telegram_id: int
    role: str
    display_name: str
    username: str | None


def _json_load(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return value


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _preference_defaults_for_role(role: str | None) -> dict[str, bool]:
    defaults = ROLE_DEFAULT_NOTIFICATION_PREFERENCES.get(role or "", {})
    if defaults:
        return {category: bool(defaults.get(category, True)) for category in NOTIFICATION_CATEGORIES}
    return {category: True for category in NOTIFICATION_CATEGORIES}


def mandatory_notification_categories(role: str | None) -> set[str]:
    normalized_role = str(role or "").strip()
    categories = ROLE_MANDATORY_NOTIFICATION_CATEGORIES.get(normalized_role)
    if categories:
        return set(categories)
    return {"security"}


def is_notification_category_mandatory(role: str | None, category: str) -> bool:
    return category in mandatory_notification_categories(role)


def _category_enabled_map(
    rows: list[ControlAdminNotificationPreference],
    *,
    role: str | None = None,
) -> dict[str, bool]:
    mapping = _preference_defaults_for_role(role)
    for row in rows:
        normalized_category = LEGACY_NOTIFICATION_CATEGORY_MAP.get(row.category, row.category)
        if normalized_category not in NOTIFICATION_CATEGORIES:
            continue
        mapping[normalized_category] = bool(row.enabled)
    for category in mandatory_notification_categories(role):
        if category in NOTIFICATION_CATEGORIES:
            mapping[category] = True
    return mapping


async def list_control_admin_profiles() -> list[ControlAdminProfile]:
    configured = {row.telegram_id: row.role for row in control_admins()}
    async with async_session() as session:
        admins = list((await session.execute(select(DashboardAdmin))).scalars().all())

    dashboard_by_telegram = {int(row.telegram_id): row for row in admins if row.telegram_id is not None}
    result: list[ControlAdminProfile] = []
    for telegram_id, role in configured.items():
        dashboard_admin = dashboard_by_telegram.get(int(telegram_id))
        if dashboard_admin is not None:
            result.append(
                ControlAdminProfile(
                    telegram_id=int(telegram_id),
                    role=role,
                    display_name=dashboard_admin.display_name,
                    username=dashboard_admin.username,
                )
            )
            continue

        result.append(
            ControlAdminProfile(
                telegram_id=int(telegram_id),
                role=role,
                display_name=f"Admin {telegram_id}",
                username=None,
            )
        )
    return result


async def get_control_admin_profile(telegram_id: int) -> ControlAdminProfile | None:
    for row in await list_control_admin_profiles():
        if row.telegram_id == int(telegram_id):
            return row
    return None


async def get_notification_preferences(telegram_id: int) -> dict[str, bool]:
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(ControlAdminNotificationPreference).where(
                        ControlAdminNotificationPreference.telegram_id == int(telegram_id)
                    )
                )
            ).scalars().all()
        )
    return _category_enabled_map(rows, role=control_role_for_telegram_id(int(telegram_id)))


async def toggle_notification_preference(telegram_id: int, category: str) -> dict[str, bool]:
    if category not in NOTIFICATION_CATEGORIES:
        return await get_notification_preferences(telegram_id)
    role = control_role_for_telegram_id(int(telegram_id))
    if is_notification_category_mandatory(role, category):
        return await get_notification_preferences(telegram_id)

    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlAdminNotificationPreference).where(
                    ControlAdminNotificationPreference.telegram_id == int(telegram_id),
                    ControlAdminNotificationPreference.category == category,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ControlAdminNotificationPreference(
                telegram_id=int(telegram_id),
                category=category,
                enabled=False,
                updated_at=utcnow(),
            )
            session.add(row)
        else:
            row.enabled = not bool(row.enabled)
            row.updated_at = utcnow()
        await session.commit()
    return await get_notification_preferences(telegram_id)


async def set_notification_preference(telegram_id: int, category: str, enabled: bool) -> dict[str, bool]:
    if category not in NOTIFICATION_CATEGORIES:
        return await get_notification_preferences(telegram_id)
    role = control_role_for_telegram_id(int(telegram_id))
    if is_notification_category_mandatory(role, category):
        return await get_notification_preferences(telegram_id)

    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlAdminNotificationPreference).where(
                    ControlAdminNotificationPreference.telegram_id == int(telegram_id),
                    ControlAdminNotificationPreference.category == category,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ControlAdminNotificationPreference(
                telegram_id=int(telegram_id),
                category=category,
                enabled=bool(enabled),
                updated_at=utcnow(),
            )
            session.add(row)
        else:
            row.enabled = bool(enabled)
            row.updated_at = utcnow()
        await session.commit()
    return await get_notification_preferences(telegram_id)


async def list_notification_preference_rows() -> list[dict[str, Any]]:
    profiles = await list_control_admin_profiles()
    prefs_map = {profile.telegram_id: await get_notification_preferences(profile.telegram_id) for profile in profiles}
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        prefs = prefs_map[profile.telegram_id]
        rows.append(
            {
                "telegram_id": profile.telegram_id,
                "role": profile.role,
                "display_name": profile.display_name,
                "username": profile.username,
                "enabled_count": sum(1 for value in prefs.values() if value),
                "total_count": len(NOTIFICATION_CATEGORIES),
                "preferences": prefs,
            }
        )
    return rows


async def list_active_dashboard_sessions() -> list[dict[str, Any]]:
    now = utcnow()
    from dashboard.services import dashboard_settings

    idle_timeout = timedelta(minutes=max(dashboard_settings()["session_idle_minutes"], 1))
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DashboardSession, DashboardAdmin)
                    .join(DashboardAdmin, DashboardAdmin.id == DashboardSession.admin_id)
                )
            ).all()
        )

    active_rows: list[dict[str, Any]] = []
    for db_session, admin in rows:
        if db_session.expires_at <= now:
            continue
        if db_session.last_seen_at and db_session.last_seen_at <= now - idle_timeout:
            continue
        minutes_left = max(int((db_session.expires_at - now).total_seconds() // 60), 0)
        active_rows.append(
            {
                "session_id": db_session.id,
                "admin_id": admin.id,
                "username": admin.username,
                "display_name": admin.display_name,
                "telegram_id": admin.telegram_id,
                "ttl_minutes": minutes_left,
                "created_at": db_session.created_at,
                "last_seen_at": db_session.last_seen_at,
            }
        )
    active_rows.sort(key=lambda item: item["created_at"], reverse=True)
    return active_rows


async def terminate_all_dashboard_sessions() -> int:
    async with async_session() as session:
        result = await session.execute(select(DashboardSession.id))
        ids = list(result.scalars().all())
        if not ids:
            return 0
        await session.execute(delete(DashboardSession))
        await session.commit()
        return len(ids)


async def list_message_templates(scope: str | None = None) -> list[ControlMessageTemplate]:
    async with async_session() as session:
        query = select(ControlMessageTemplate).order_by(
            ControlMessageTemplate.is_builtin.desc(),
            ControlMessageTemplate.updated_at.desc(),
            ControlMessageTemplate.created_at.desc(),
        )
        if scope:
            query = query.where(ControlMessageTemplate.scope == scope)
        return list((await session.execute(query)).scalars().all())


async def get_message_template(template_id: int) -> ControlMessageTemplate | None:
    async with async_session() as session:
        return (
            await session.execute(
                select(ControlMessageTemplate).where(ControlMessageTemplate.id == int(template_id))
            )
        ).scalar_one_or_none()


async def save_message_template(
    *,
    scope: str,
    name: str,
    body: str,
    buttons: list[dict[str, str]] | None,
    created_by_telegram_id: int | None,
    template_id: int | None = None,
) -> ControlMessageTemplate:
    async with async_session() as session:
        if template_id is not None:
            row = (
                await session.execute(
                    select(ControlMessageTemplate).where(ControlMessageTemplate.id == int(template_id))
                )
            ).scalar_one()
            row.scope = scope
            row.name = name[:120]
            row.body = body
            row.buttons_json = _json_dump(buttons or [])
            row.updated_at = utcnow()
        else:
            row = ControlMessageTemplate(
                scope=scope[:50],
                name=name[:120],
                body=body,
                buttons_json=_json_dump(buttons or []),
                created_by_telegram_id=created_by_telegram_id,
                updated_at=utcnow(),
            )
            session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def delete_message_template(template_id: int) -> None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlMessageTemplate).where(ControlMessageTemplate.id == int(template_id))
            )
        ).scalar_one_or_none()
        if row is None or row.is_builtin:
            return
        await session.delete(row)
        await session.commit()


async def ensure_default_trigger_rules() -> list[ControlTriggerRule]:
    async with async_session() as session:
        existing = {
            row.key: row
            for row in list((await session.execute(select(ControlTriggerRule))).scalars().all())
        }
        changed = False
        for item in TRIGGER_DEFAULTS:
            row = existing.get(item["key"])
            if row is None:
                row = ControlTriggerRule(
                    key=item["key"],
                    family=item["family"],
                    title=item["title"],
                    description=item["description"],
                    enabled=item["enabled"],
                    config_json=_json_dump(item["config"]),
                    template_body=item["template_body"],
                    buttons_json=_json_dump(item["buttons"]),
                    updated_at=utcnow(),
                )
                session.add(row)
                changed = True
                continue
            if item["key"] in TRIAL_LEGACY_DISABLED_KEYS and row.enabled:
                row.enabled = False
                row.updated_at = utcnow()
                changed = True
            stale_bodies = _STALE_PROMO_TRIGGER_BODIES.get(item["key"])
            if stale_bodies and str(row.template_body or "") in stale_bodies:
                row.template_body = item["template_body"]
                row.updated_at = utcnow()
                changed = True
        if changed:
            await session.commit()
        return list((await session.execute(select(ControlTriggerRule).order_by(ControlTriggerRule.family.asc(), ControlTriggerRule.id.asc()))).scalars().all())


async def list_trigger_rules() -> list[ControlTriggerRule]:
    await ensure_default_trigger_rules()
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ControlTriggerRule).order_by(ControlTriggerRule.family.asc(), ControlTriggerRule.title.asc())
                )
            ).scalars().all()
        )


async def get_trigger_rule(rule_id: int) -> ControlTriggerRule | None:
    await ensure_default_trigger_rules()
    async with async_session() as session:
        return (
            await session.execute(select(ControlTriggerRule).where(ControlTriggerRule.id == int(rule_id)))
        ).scalar_one_or_none()


async def update_trigger_rule(
    rule_id: int,
    *,
    enabled: bool | None = None,
    template_body: str | None = None,
    buttons: list[dict[str, str]] | None = None,
    config: dict[str, Any] | None = None,
) -> ControlTriggerRule | None:
    async with async_session() as session:
        row = (
            await session.execute(select(ControlTriggerRule).where(ControlTriggerRule.id == int(rule_id)))
        ).scalar_one_or_none()
        if row is None:
            return None
        if enabled is not None:
            row.enabled = bool(enabled)
        if template_body is not None:
            row.template_body = template_body
        if buttons is not None:
            row.buttons_json = _json_dump(buttons)
        if config is not None:
            row.config_json = _json_dump(config)
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return row


async def toggle_trigger_rule(rule_id: int) -> ControlTriggerRule | None:
    row = await get_trigger_rule(rule_id)
    if row is None:
        return None
    return await update_trigger_rule(rule_id, enabled=not bool(row.enabled))


async def list_trigger_rules_grouped() -> dict[str, list[ControlTriggerRule]]:
    grouped: dict[str, list[ControlTriggerRule]] = defaultdict(list)
    for row in await list_trigger_rules():
        grouped[row.family].append(row)
    return dict(grouped)


async def create_broadcast_campaign(
    *,
    scope: str,
    name: str | None,
    audience_key: str | None,
    message_body: str,
    buttons: list[dict[str, str]] | None,
    metadata: dict[str, Any] | None,
    created_by_telegram_id: int | None,
    priority_label: str | None = None,
    scheduled_at=None,
    template_id: int | None = None,
    trigger_rule_id: int | None = None,
    is_test: bool = False,
    status: str = "queued",
) -> ControlBroadcastCampaign:
    async with async_session() as session:
        row = ControlBroadcastCampaign(
            scope=scope[:50],
            name=name[:150] if name else None,
            status=status[:50],
            audience_key=audience_key[:100] if audience_key else None,
            priority_label=priority_label[:50] if priority_label else None,
            message_body=message_body,
            buttons_json=_json_dump(buttons or []),
            metadata_json=_json_dump(metadata or {}),
            created_by_telegram_id=created_by_telegram_id,
            template_id=template_id,
            trigger_rule_id=trigger_rule_id,
            is_test=is_test,
            scheduled_at=scheduled_at,
            updated_at=utcnow(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def update_broadcast_campaign(
    campaign_id: int,
    **changes,
) -> ControlBroadcastCampaign | None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlBroadcastCampaign).where(ControlBroadcastCampaign.id == int(campaign_id))
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        for key, value in changes.items():
            if key == "buttons":
                row.buttons_json = _json_dump(value or [])
            elif key == "metadata":
                row.metadata_json = _json_dump(value or {})
            elif hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return row


async def get_broadcast_campaign(campaign_id: int) -> ControlBroadcastCampaign | None:
    async with async_session() as session:
        return (
            await session.execute(
                select(ControlBroadcastCampaign).where(ControlBroadcastCampaign.id == int(campaign_id))
            )
        ).scalar_one_or_none()


async def list_recent_broadcast_campaigns(scope: str | None = None, limit: int = 12) -> list[ControlBroadcastCampaign]:
    async with async_session() as session:
        query = select(ControlBroadcastCampaign).order_by(ControlBroadcastCampaign.created_at.desc()).limit(limit)
        if scope:
            query = query.where(ControlBroadcastCampaign.scope == scope)
        return list((await session.execute(query)).scalars().all())


async def list_broadcast_deliveries(campaign_id: int) -> list[ControlBroadcastDelivery]:
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ControlBroadcastDelivery)
                    .where(ControlBroadcastDelivery.campaign_id == int(campaign_id))
                    .order_by(ControlBroadcastDelivery.created_at.asc())
                )
            ).scalars().all()
        )


async def create_broadcast_deliveries(
    campaign_id: int,
    *,
    recipients: list[dict[str, Any]],
    bot_key: str,
    cta_action: str | None,
) -> list[ControlBroadcastDelivery]:
    async with async_session() as session:
        rows: list[ControlBroadcastDelivery] = []
        for recipient in recipients:
            row = ControlBroadcastDelivery(
                campaign_id=int(campaign_id),
                user_id=recipient.get("user_id"),
                telegram_id=int(recipient["telegram_id"]),
                bot_key=bot_key[:20],
                status="queued",
                cta_action=cta_action[:50] if cta_action else None,
            )
            rows.append(row)
            session.add(row)
        await session.commit()
        for row in rows:
            await session.refresh(row)
        return rows


async def update_delivery_status(
    delivery_id: int,
    *,
    status: str,
    error_text: str | None = None,
    clicked: bool = False,
    converted: bool = False,
) -> ControlBroadcastDelivery | None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlBroadcastDelivery).where(ControlBroadcastDelivery.id == int(delivery_id))
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.status = status[:30]
        if status == "sent":
            row.sent_at = utcnow()
        if error_text is not None:
            row.error_text = error_text
        if clicked and row.clicked_at is None:
            row.clicked_at = utcnow()
        if converted and row.converted_at is None:
            row.converted_at = utcnow()
        await session.commit()
        await session.refresh(row)
        await recalculate_broadcast_campaign(row.campaign_id)
        return row


async def mark_delivery_clicked(delivery_id: int) -> ControlBroadcastDelivery | None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlBroadcastDelivery).where(ControlBroadcastDelivery.id == int(delivery_id))
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.clicked_at is None:
            row.clicked_at = utcnow()
            await session.commit()
            await session.refresh(row)
        campaign_id = int(row.campaign_id)
    await recalculate_broadcast_campaign(campaign_id)
    return row


async def get_delivery(delivery_id: int) -> ControlBroadcastDelivery | None:
    async with async_session() as session:
        return (
            await session.execute(
                select(ControlBroadcastDelivery).where(ControlBroadcastDelivery.id == int(delivery_id))
            )
        ).scalar_one_or_none()


async def recalculate_broadcast_campaign(campaign_id: int) -> ControlBroadcastCampaign | None:
    async with async_session() as session:
        campaign = (
            await session.execute(
                select(ControlBroadcastCampaign).where(ControlBroadcastCampaign.id == int(campaign_id))
            )
        ).scalar_one_or_none()
        if campaign is None:
            return None
        deliveries = list(
            (
                await session.execute(
                    select(ControlBroadcastDelivery).where(ControlBroadcastDelivery.campaign_id == campaign.id)
                )
            ).scalars().all()
        )
        campaign.target_count = len(deliveries)
        campaign.sent_count = sum(1 for row in deliveries if row.status == "sent")
        campaign.failed_count = sum(1 for row in deliveries if row.status == "failed")
        campaign.clicked_count = sum(1 for row in deliveries if row.clicked_at is not None)
        campaign.converted_count = sum(1 for row in deliveries if row.converted_at is not None)
        if deliveries and all(row.status in {"sent", "failed", "skipped"} for row in deliveries):
            campaign.status = "completed"
            if campaign.completed_at is None:
                campaign.completed_at = utcnow()
        campaign.updated_at = utcnow()
        await session.commit()
        await session.refresh(campaign)
        return campaign


async def list_pending_broadcast_campaigns() -> list[ControlBroadcastCampaign]:
    now = utcnow()
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ControlBroadcastCampaign).where(
                        ControlBroadcastCampaign.status.in_(["queued", "scheduled", "processing"]),
                    )
                )
            ).scalars().all()
        )


async def list_trigger_delivery_logs_for_user(user_id: int, rule_key: str) -> list[ControlTriggerDeliveryLog]:
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ControlTriggerDeliveryLog)
                    .join(ControlTriggerRule, ControlTriggerRule.id == ControlTriggerDeliveryLog.trigger_rule_id)
                    .where(
                        ControlTriggerDeliveryLog.user_id == int(user_id),
                        ControlTriggerRule.key == rule_key,
                    )
                    .order_by(ControlTriggerDeliveryLog.sent_at.desc())
                )
            ).scalars().all()
        )


async def register_trigger_delivery_log(
    *,
    trigger_rule_id: int | None,
    campaign_id: int | None,
    user_id: int | None,
    telegram_id: int | None,
    event_key: str,
    dedupe_key: str | None,
    result: str,
) -> ControlTriggerDeliveryLog:
    async with async_session() as session:
        row = ControlTriggerDeliveryLog(
            trigger_rule_id=trigger_rule_id,
            campaign_id=campaign_id,
            user_id=user_id,
            telegram_id=telegram_id,
            event_key=event_key[:120],
            dedupe_key=dedupe_key[:255] if dedupe_key else None,
            result=result[:30],
            sent_at=utcnow(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def has_trigger_delivery(dedupe_key: str) -> bool:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ControlTriggerDeliveryLog.id).where(ControlTriggerDeliveryLog.dedupe_key == dedupe_key)
            )
        ).scalar_one_or_none()
    return row is not None


def _segment_users_base_query():
    return select(User).where(shared_real_user_sql_clause(User)).order_by(User.created_at.desc())


def _segment_user_device_count_query():
    return select(VpnClient.user_id).where(
        VpnClient.user_id.in_(select(User.id).where(shared_real_user_sql_clause(User)))
    )


async def segment_users(audience_key: str) -> list[User]:
    from bot.db import get_active_device_slot_counts_for_users

    now = utcnow()
    async with async_session() as session:
        users = list((await session.execute(_segment_users_base_query())).scalars().all())
        device_rows = list((await session.execute(_segment_user_device_count_query())).scalars().all())
    device_counts: dict[int, int] = defaultdict(int)
    for user_id in device_rows:
        if user_id is not None:
            device_counts[int(user_id)] += 1
    extra_slot_counts = await get_active_device_slot_counts_for_users([user.id for user in users])

    result: list[User] = []
    for user in users:
        setattr(user, "active_device_slot_addons", int(extra_slot_counts.get(int(user.id), 0)))
        status = get_access_status_from_user(user)
        access_expires_at = get_access_expires_at_from_user(user)
        last_activity = getattr(user, "last_activity_at", None) or user.created_at
        if audience_key == "all":
            result.append(user)
        elif audience_key == "trial_active" and status == "trial_active":
            result.append(user)
        elif audience_key == "paid_active" and status in {"paid_active", "vip_active"}:
            result.append(user)
        elif audience_key == "expired" and status == "expired":
            result.append(user)
        elif audience_key == "inactive_30d" and last_activity <= now - timedelta(days=30):
            result.append(user)
        elif audience_key == "inactive_7d" and last_activity <= now - timedelta(days=7):
            result.append(user)
        elif audience_key == "new_7d" and user.created_at >= now - timedelta(days=7):
            result.append(user)
        elif audience_key == "expiring_today" and access_expires_at is not None and access_expires_at.date() == now.date():
            result.append(user)
        elif audience_key == "expiring_tomorrow" and access_expires_at is not None and access_expires_at.date() == (now + timedelta(days=1)).date():
            result.append(user)
        elif audience_key == "expiring_3d" and access_expires_at is not None and access_expires_at.date() == (now + timedelta(days=3)).date():
            result.append(user)
        elif audience_key == "expiring_7d" and access_expires_at is not None and access_expires_at.date() == (now + timedelta(days=7)).date():
            result.append(user)
        elif audience_key == "device_limit_reached" and device_counts.get(int(user.id), 0) >= get_device_limit_for_user(user):
            result.append(user)
        elif audience_key == "access_issue" and bool(getattr(user, "vpn_repair_needed", False)):
            result.append(user)
    return result


async def segment_counts() -> dict[str, int]:
    keys = [
        "all",
        "trial_active",
        "paid_active",
        "expired",
        "inactive_30d",
        "inactive_7d",
        "new_7d",
        "expiring_today",
        "expiring_tomorrow",
        "expiring_3d",
        "expiring_7d",
        "device_limit_reached",
        "access_issue",
    ]
    return {key: len(await segment_users(key)) for key in keys}


async def build_campaign_recipients(audience_key: str, *, test_telegram_id: int | None = None) -> list[dict[str, Any]]:
    if test_telegram_id is not None:
        return [{"user_id": None, "telegram_id": int(test_telegram_id)}]

    users = await segment_users(audience_key)
    return [
        {
            "user_id": user.id,
            "telegram_id": int(user.telegram_id),
        }
        for user in users
    ]


async def render_template_body(body: str, user_id: int | None, telegram_id: int) -> str:
    user = None
    device_count = 0
    if user_id is not None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.id == int(user_id)))
            ).scalar_one_or_none()
            if user is not None:
                device_count = len(
                    list(
                        (
                            await session.execute(
                                select(VpnClient.id).where(VpnClient.user_id == int(user_id))
                            )
                        ).scalars().all()
                    )
                )

    values = {
        "first_name": user.username or f"user_{telegram_id}" if user is not None else f"user_{telegram_id}",
        "username": f"@{user.username}" if user is not None and user.username else "—",
        "telegram_id": telegram_id,
        "access_expires_at": escape(
            get_access_expires_at_from_user(user).strftime("%Y-%m-%d %H:%M")
            if user is not None and get_access_expires_at_from_user(user) is not None
            else "—"
        ),
        "trial_expires_at": escape(
            user.trial_expires_at.strftime("%Y-%m-%d %H:%M") if user is not None and user.trial_expires_at else "—"
        ),
        "balance_rub": int(getattr(user, "balance_rub", 0)) if user is not None else 0,
        "device_count": device_count,
        "protocol": escape(getattr(user, "preferred_protocol", "vless").upper() if user is not None else "VLESS"),
    }
    safe_values = defaultdict(str, values)
    return body.format_map(safe_values)


async def list_recent_user_events(limit: int = 10) -> list[ControlNotificationEvent]:
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(ControlNotificationEvent)
                    .where(ControlNotificationEvent.category.in_(["users", "access"]))
                    .order_by(ControlNotificationEvent.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )


async def mark_recent_campaign_conversion(user_id: int, *, reason: str) -> int:
    async with async_session() as session:
        deliveries = list(
            (
                await session.execute(
                    select(ControlBroadcastDelivery)
                    .join(ControlBroadcastCampaign, ControlBroadcastCampaign.id == ControlBroadcastDelivery.campaign_id)
                    .where(
                        ControlBroadcastDelivery.user_id == int(user_id),
                        ControlBroadcastDelivery.sent_at.is_not(None),
                        ControlBroadcastDelivery.converted_at.is_(None),
                        ControlBroadcastCampaign.scope.in_([CAMPAIGN_SCOPE_USER, CAMPAIGN_SCOPE_TRIGGER]),
                    )
                    .order_by(ControlBroadcastDelivery.sent_at.desc())
                    .limit(5)
                )
            ).scalars().all()
        )
        changed_campaign_ids: set[int] = set()
        now = utcnow()
        for row in deliveries:
            if row.sent_at is None or row.sent_at < now - timedelta(days=7):
                continue
            row.converted_at = now
            if row.error_text:
                row.error_text = f"{row.error_text}\nconversion:{reason}"
            else:
                row.error_text = f"conversion:{reason}"
            changed_campaign_ids.add(int(row.campaign_id))
        await session.commit()
    for campaign_id in changed_campaign_ids:
        await recalculate_broadcast_campaign(campaign_id)
    return len(changed_campaign_ids)


def serialize_template_buttons(template: ControlMessageTemplate | ControlTriggerRule | ControlBroadcastCampaign | None) -> list[dict[str, str]]:
    if template is None:
        return []
    return _json_load(getattr(template, "buttons_json", None), []) or []


def serialize_campaign_metadata(campaign: ControlBroadcastCampaign | None) -> dict[str, Any]:
    if campaign is None:
        return {}
    return _json_load(campaign.metadata_json, {}) or {}


def priority_label(role: str) -> str:
    return {
        CONTROL_ROLE_OWNER: "owner",
        CONTROL_ROLE_ADMIN: "admin",
        CONTROL_ROLE_OPERATOR: "operator",
        CONTROL_ROLE_SUPPORT_VIEW_ONLY: "support-view-only",
    }.get(role, role)
