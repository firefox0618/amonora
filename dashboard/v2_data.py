from __future__ import annotations

import json
import math
import re

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import String, cast, func, or_, select

from backend.core.database import async_session
from backend.core.models import (
    AnalyticsDailyStageCount,
    ChannelContentItem,
    PromoCodeRedemption,
    PublicSubscriptionRoute,
    SupportTicketMessage,
    User,
    VpnClient,
    VpnRepairEvent,
)
from backend.core.promo_codes import list_promo_codes, promo_kind_label
from backend.core.synthetic_users import is_synthetic_user as shared_is_synthetic_user
from bot.config import config
from bot.db import get_active_device_slot_counts_for_users, get_active_device_slot_entitlements_for_user
from bot.manual_payments import payment_status_label
from bot.platega_flow import PLATEGA_PAYMENT_METHODS, sync_platega_record_by_id
from bot.repair_reasons import (
    is_payment_related_repair_reason,
    normalize_repair_reason,
    repair_reason_label,
)
from bot.utils.access import get_access_expires_at_from_user, get_access_status_from_user, get_device_limit_for_user
from bot.utils.device_slots import DEFAULT_DEVICE_LIMIT
from bot.utils.regions import get_country_name, normalize_country_code
from bot.utils.texts import manual_payment_method_label
from control_bot.channel_content import (
    CHANNEL_CONTENT_TYPE_OFFER,
    build_channel_cta_url,
    channel_content_status_label,
)
from control_bot.dispatcher import CATEGORY_LABELS
from control_bot.storage import NOTIFICATION_CATEGORIES, is_notification_category_mandatory, list_notification_preference_rows
from dashboard.models import DashboardAdmin, DashboardAuditLog, PaymentRecord
from dashboard.services import (
    ADMIN_AVATAR_ROOT,
    ROLE_NAMES,
    ROLE_PERMISSIONS,
    _real_user_ids_subquery,
    _real_user_sql_clause,
    _can_send_manual_payment_reminder,
    apply_traffic_baseline_to_snapshots,
    dashboard_day_start,
    dashboard_local_date,
    ensure_current_traffic_baseline,
    editable_permission_roles,
    editable_permissions_for_role,
    dashboard_server_state,
    dashboard_settings,
    dashboard_user_status,
    documentation_settings,
    get_role_permission_matrix_snapshot,
    format_dashboard_datetime,
    get_channel_subscription_statuses,
    get_finance_dashboard,
    get_finance_summary,
    get_managed_servers,
    get_documentation_page,
    get_payment_focus,
    get_payment_record_by_id,
    get_payment_records,
    get_runtime_tariffs,
    get_runtime_tariffs_list,
    get_server_snapshot_by_id,
    get_server_snapshots,
    get_service_statuses,
    get_support_admin_choices,
    get_support_dashboard_counts,
    get_support_ticket_detail,
    get_support_tickets,
    get_user_balance_history,
    get_user_detail,
    get_users,
    get_vpn_overview,
    overview_metrics,
    payment_status_is_open,
    read_masked_env,
    recent_audit_logs,
    role_has_any_permission,
    role_has_permission,
    service_logs,
    summarize_server_snapshots,
    utcnow,
)
from dashboard.finance import payment_method_counts_as_revenue


MANUAL_PAYMENT_STALE_HOURS = 12
REPAIR_ESCALATION_HOURS = 6
SUPPORT_ESCALATION_HOURS = 24
ACTIVE_ACCESS_STATUSES = {"paid_active", "trial_active", "vip_active"}
MANUAL_PAYMENT_METHODS = {"sbp_manual", "crypto_manual"}
PROVIDER_SYNC_PAYMENT_METHODS = set(PLATEGA_PAYMENT_METHODS)
AUTO_PROVIDER_SYNC_STATUSES = {"pending", "awaiting_user_payment"}
AUTO_PROVIDER_SYNC_INTERVAL_SECONDS = 10
AUTO_PROVIDER_SYNC_LIMIT = 4
ADMIN_AVATAR_PREFIX = "/dashboard/static/avatars/"
CAMPAIGN_ANALYTICS_SOURCE_MODE = "last"
CAMPAIGN_ANALYTICS_EVENT_LINK_TOUCHED = "link_touched"
CAMPAIGN_ANALYTICS_EVENT_BOT_START = "bot_start"
CAMPAIGN_ANALYTICS_EVENT_TRIAL_STARTED = "trial_started"
CAMPAIGN_ANALYTICS_EVENT_CONFIG_ISSUED = "config_issued"
CAMPAIGN_ANALYTICS_EVENT_PAYMENT_SUCCESS = "payment_success"
CAMPAIGN_ANALYTICS_EVENT_SUBSCRIPTION_RENEWED = "subscription_renewed"
CAMPAIGN_ANALYTICS_EVENT_ORDER = (
    CAMPAIGN_ANALYTICS_EVENT_LINK_TOUCHED,
    CAMPAIGN_ANALYTICS_EVENT_BOT_START,
    CAMPAIGN_ANALYTICS_EVENT_TRIAL_STARTED,
    CAMPAIGN_ANALYTICS_EVENT_CONFIG_ISSUED,
    CAMPAIGN_ANALYTICS_EVENT_PAYMENT_SUCCESS,
    CAMPAIGN_ANALYTICS_EVENT_SUBSCRIPTION_RENEWED,
)

AUDIT_ACTION_LABELS = {
    "grant_trial": "Выдал пробный доступ",
    "extend_subscription": "продление",
    "clear_user_access": "Снял доступ",
    "set_user_block_state": "Изменил блокировку пользователя",
    "set_user_preferred_protocol": "Изменил протокол пользователя",
    "create_device": "Создал устройство",
    "delete_device": "Удалил устройство",
    "delete_user": "удаление пользователя",
    "sync_user_access": "Запустил синхронизацию",
    "deep_repair_user_access": "Запустил глубокий ремонт",
    "confirm_payment_record": "Подтвердил платёж",
    "reject_payment_record": "Отклонил платёж",
    "set_payment_record_status": "Изменил статус платежа",
    "sync_payment_record_provider": "Синхронизировал платёж с провайдером",
    "delete_payment_record": "Удалил платёж",
    "assign_support_ticket": "Взял обращение",
    "transfer_support_ticket": "Передал обращение",
    "close_support_ticket": "Закрыл обращение",
    "support_reply": "Ответил в поддержке",
    "server_restart": "Перезапустил ноду",
    "server_health_check": "Проверил ноду",
    "server_maintenance": "Перевёл ноду в обслуживание",
    "server_migrate": "Запустил миграцию ноды",
    "update_env_value": "Изменил переменную окружения",
    "update_tariffs": "Обновил тарифы",
    "update_admin_access": "Изменил доступ администратора",
    "update_notification_preference": "Изменил уведомления",
    "update_role_permission_override": "Изменил разрешение роли",
    "reset_traffic_baseline": "Сбросил накопленный трафик",
    "auto_reset_traffic_baseline": "Автоматически сбросил накопленный трафик",
    "login_code_requested": "Выдача кода",
    "request_login_code_v2": "Выдача кода",
    "login_v2": "Вошёл в панель",
    "logout_v2": "выход",
    "block_user": "блокировка доступа",
    "unblock_user": "разблокировка доступа",
    "server_watchdog_down": "оффлайн",
    "server_watchdog_recovered": "восстановлен",
    "server_watchdog_overloaded": "Нода перегружена, нужно снять часть нагрузки",
    "remove_user_tariff": "Снял тариф пользователя",
}

PERMISSION_LABELS = {
    "manage_users": "Управление пользователями",
    "delete_users": "Удаление пользователей",
    "manage_payments": "Управление платежами",
    "manage_support": "Работа с поддержкой",
    "manage_servers": "Просмотр и настройка нод",
    "manage_server_actions": "Действия с нодами",
    "manage_finance": "Управление финансами",
    "approve_finance": "Проведение финансовых записей",
    "run_sync": "Запуск синхронизации",
    "run_deep_repair": "Запуск глубокого ремонта",
    "clear_access": "Снятие доступа",
    "manage_services": "Управление сервисами",
    "manage_docs": "Управление документацией",
    "delete_payments": "Удаление платежей",
    "delete_finance": "Удаление финансовых записей",
}

AUDIT_DISPLAY_DIFF_LABELS = {
    "status": "Статус",
    "payment_status": "Статус",
    "assigned_admin_name": "Ответственный",
    "rejection_reason": "Причина",
}

AUDIT_PAYMENT_STATUS_LABELS = {
    "awaiting_admin_review": "Ожидает проверку",
    "awaiting_user_payment": "Ожидает оплату",
    "pending": "В обработке",
    "confirmed": "Подтверждён",
    "rejected": "Отклонён",
    "expired": "Истёк",
    "disputed": "Спор",
    "error": "Ошибка",
}

AUDIT_SUPPORT_STATUS_LABELS = {
    "new": "Новый",
    "in_progress": "В работе",
    "closed": "Закрыто",
}

AUDIT_SUMMARY_DIFF_KEYS = (
    "payment_status",
    "status",
    "assigned_admin_name",
)

AUDIT_SUMMARY_NOISY_KEYS = {
    "id",
    "user_id",
    "updated_at",
    "created_at",
    "closed_at",
    "expires_at",
    "confirmed_at",
    "reviewed_at",
    "messages_count",
}


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 3)


def _repair_priority(*, is_payment_related: bool) -> str:
    return "high" if is_payment_related else "medium"


def _backup_priority(block: dict) -> str:
    if block.get("last_backup_at") == "—":
        return "high"
    if block.get("backup_stale"):
        return "medium"
    return "low"


def _restore_priority(block: dict) -> str:
    if block.get("status") == "unknown":
        return "medium"
    if block.get("restore_validation_stale"):
        return "medium"
    return "low"


def _support_priority(*, open_tickets: int) -> str:
    return "medium" if open_tickets > 0 else "low"


def _payments_priority(*, pending_confirmations: int, stale_pending_confirmations: int) -> str:
    if stale_pending_confirmations > 0:
        return "high"
    if pending_confirmations > 0:
        return "medium"
    return "low"


def _repair_action_guard(access_status: str, devices_count: int) -> tuple[bool, str | None]:
    if access_status not in ACTIVE_ACCESS_STATUSES:
        return False, "manual_repair_no_access"
    if devices_count <= 0:
        return False, "manual_repair_no_devices"
    return True, None

def _format_datetime(value: datetime | None) -> str:
    return format_dashboard_datetime(value)


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _trim_audit_text(value: str | None, limit: int = 96) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _build_campaign_stats_payload(stage_counts: dict[str, int] | None) -> dict[str, int | float]:
    counts = dict(stage_counts or {})
    transitions = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_LINK_TOUCHED, 0) or 0)
    bot_starts = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_BOT_START, 0) or 0)
    trial_started = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_TRIAL_STARTED, 0) or 0)
    key_issued = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_CONFIG_ISSUED, 0) or 0)
    paid = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_PAYMENT_SUCCESS, 0) or 0)
    renewed = int(counts.get(CAMPAIGN_ANALYTICS_EVENT_SUBSCRIPTION_RENEWED, 0) or 0)
    conversion_rate = round((paid / transitions) * 100, 2) if transitions > 0 else 0.0
    return {
        "transitions": transitions,
        "bot_starts": bot_starts,
        "trial_started": trial_started,
        "key_issued": key_issued,
        "paid": paid,
        "renewed": renewed,
        "conversion_rate": conversion_rate,
    }


def _build_campaign_funnel(stats: dict[str, int | float]) -> list[dict[str, int | float | str]]:
    transitions = int(stats.get("transitions", 0) or 0)
    base = transitions or 1
    funnel = [
        {"stage": "Переход по ссылке", "count": transitions, "rate": 100.0 if transitions else 0.0},
        {"stage": "Нажали Start", "count": int(stats.get("bot_starts", 0) or 0), "rate": 0.0},
        {"stage": "Начали пробный период", "count": int(stats.get("trial_started", 0) or 0), "rate": 0.0},
        {"stage": "Получили ключ", "count": int(stats.get("key_issued", 0) or 0), "rate": 0.0},
        {"stage": "Оплатили", "count": int(stats.get("paid", 0) or 0), "rate": 0.0},
        {"stage": "Продлили", "count": int(stats.get("renewed", 0) or 0), "rate": 0.0},
    ]
    for index in range(1, len(funnel)):
        funnel[index]["rate"] = round((int(funnel[index]["count"]) / base) * 100, 2)
    return funnel


def _resolve_campaign_period(
    *,
    period_key: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, object]:
    today_local = dashboard_local_date(utcnow()) or utcnow().date()
    normalized_key = str(period_key or "").strip().lower() or "30d"

    if normalized_key == "7d":
        start_date = today_local - timedelta(days=6)
        end_date = today_local
        label = "Последние 7 дней"
        return {
            "key": "7d",
            "label": label,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "date_from": start_date,
            "date_to": end_date,
        }

    if normalized_key == "this_month":
        start_date = today_local.replace(day=1)
        end_date = today_local
        label = "Текущий месяц"
        return {
            "key": "this_month",
            "label": label,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "date_from": start_date,
            "date_to": end_date,
        }

    if normalized_key == "last_month":
        current_month_start = today_local.replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end
        label = "Прошлый месяц"
        return {
            "key": "last_month",
            "label": label,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "date_from": start_date,
            "date_to": end_date,
        }

    if normalized_key == "custom":
        custom_from = str(date_from or "").strip()
        custom_to = str(date_to or "").strip()
        if custom_from and custom_to:
            try:
                start_date = date.fromisoformat(custom_from)
                end_date = date.fromisoformat(custom_to)
            except ValueError:
                start_date = None
                end_date = None
            if start_date is not None and end_date is not None and start_date <= end_date:
                return {
                    "key": "custom",
                    "label": "Выбранный диапазон",
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "date_from": start_date,
                    "date_to": end_date,
                }

    start_date = today_local - timedelta(days=29)
    end_date = today_local
    return {
        "key": "30d",
        "label": "Последние 30 дней",
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "date_from": start_date,
        "date_to": end_date,
    }


def _serialize_campaign_row(item: ChannelContentItem, stage_counts: dict[str, int] | None = None) -> dict[str, object]:
    token = str(item.deep_link_token or "").strip().lower()
    stats = _build_campaign_stats_payload(stage_counts)
    return {
        "id": int(item.id),
        "token": token,
        "name": str(item.topic_brief or "").strip() or f"Кампания #{int(item.id)}",
        "tracking_url": build_channel_cta_url(token),
        "created_at": item.created_at,
        "status": str(item.status or "").strip().lower() or "queued",
        "status_label": channel_content_status_label(item.status),
        "cta_label": str(item.cta_label or "").strip() or "Подключиться",
        "stats": stats,
    }


async def _load_campaign_offer_items(search: str = "") -> list[ChannelContentItem]:
    query = (
        select(ChannelContentItem)
        .where(ChannelContentItem.content_type == CHANNEL_CONTENT_TYPE_OFFER)
        .order_by(ChannelContentItem.created_at.desc(), ChannelContentItem.id.desc())
        .limit(100)
    )
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                ChannelContentItem.topic_brief.ilike(pattern),
                ChannelContentItem.deep_link_token.ilike(pattern),
                ChannelContentItem.cta_label.ilike(pattern),
            )
        )
    async with async_session() as session:
        return list((await session.execute(query)).scalars().all())


async def _load_campaign_stage_counts(
    tokens: list[str],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, dict[str, int]]:
    normalized_tokens = sorted({str(token or "").strip().lower() for token in tokens if str(token or "").strip()})
    if not normalized_tokens:
        return {}
    date_from_value = date_from
    date_to_value = date_to
    if date_from_value is not None and date_to_value is not None and date_from_value > date_to_value:
        date_from_value, date_to_value = date_to_value, date_from_value
    async with async_session() as session:
        query = (
            select(
                AnalyticsDailyStageCount.source_key,
                AnalyticsDailyStageCount.event_name,
                func.sum(AnalyticsDailyStageCount.users_count),
            )
            .where(
                AnalyticsDailyStageCount.source_mode == CAMPAIGN_ANALYTICS_SOURCE_MODE,
                AnalyticsDailyStageCount.source_key.in_(normalized_tokens),
                AnalyticsDailyStageCount.event_name.in_(CAMPAIGN_ANALYTICS_EVENT_ORDER),
            )
            .group_by(AnalyticsDailyStageCount.source_key, AnalyticsDailyStageCount.event_name)
        )
        if date_from_value is not None:
            query = query.where(AnalyticsDailyStageCount.bucket_date >= date_from_value)
        if date_to_value is not None:
            query = query.where(AnalyticsDailyStageCount.bucket_date <= date_to_value)
        rows = (
            await session.execute(query)
        ).all()

    stage_map: dict[str, dict[str, int]] = defaultdict(dict)
    for source_key, event_name, total in rows:
        token = str(source_key or "").strip().lower()
        event = str(event_name or "").strip().lower()
        if not token or not event:
            continue
        stage_map[token][event] = int(total or 0)
    return stage_map


def _audit_status_label(key: str, value, action: str | None) -> str | None:
    if value in (None, ""):
        return None
    if key == "payment_status":
        return AUDIT_PAYMENT_STATUS_LABELS.get(str(value), str(value))
    if key == "status":
        if action in {"assign_support_ticket", "transfer_support_ticket", "close_support_ticket", "support_reply"}:
            return AUDIT_SUPPORT_STATUS_LABELS.get(str(value), str(value))
        if str(value) in AUDIT_SUPPORT_STATUS_LABELS:
            return AUDIT_SUPPORT_STATUS_LABELS[str(value)]
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return _trim_audit_text(str(value), limit=48)


def _format_audit_diff(label: str, before, after, action: str | None) -> str | None:
    before_label = _audit_status_label(label, before, action) if label in {"payment_status", "status"} else _audit_status_label("", before, action)
    after_label = _audit_status_label(label, after, action) if label in {"payment_status", "status"} else _audit_status_label("", after, action)
    if before_label == after_label:
        return None
    display_label = AUDIT_DISPLAY_DIFF_LABELS.get(label, label.replace("_", " ").capitalize())
    if before_label and after_label:
        return f"{display_label}: {before_label} → {after_label}"
    if after_label:
        return f"{display_label}: {after_label}"
    if before_label:
        return f"{display_label}: {before_label}"
    return None


def _summarize_audit_payload(action: str | None, details_text: str | None) -> tuple[str | None, str | None]:
    raw_text = details_text.strip() if isinstance(details_text, str) else None
    if not raw_text:
        return None, None
    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError):
        return _trim_audit_text(raw_text), raw_text
    if not isinstance(payload, dict):
        return _trim_audit_text(raw_text), raw_text

    before = payload.get("before") if isinstance(payload.get("before"), dict) else {}
    after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
    parts: list[str] = []

    for key in AUDIT_SUMMARY_DIFF_KEYS:
        diff = _format_audit_diff(key, before.get(key), after.get(key), action)
        if diff:
            parts.append(diff)

    if not parts and before and after:
        for key in sorted(set(before) | set(after)):
            if key in AUDIT_SUMMARY_NOISY_KEYS or key in AUDIT_SUMMARY_DIFF_KEYS:
                continue
            diff = _format_audit_diff(key, before.get(key), after.get(key), action)
            if diff:
                parts.append(diff)
            if len(parts) >= 2:
                break

    reason = _trim_audit_text(
        payload.get("reason")
        or payload.get("rejection_reason")
        or after.get("rejection_reason")
        or after.get("note")
        or payload.get("note"),
        limit=72,
    )
    if reason and not any(part.startswith("Причина:") for part in parts):
        parts.append(f"Причина: {reason}")

    if payload.get("user_notified") is True:
        parts.append("Пользователь уведомлён")

    if parts:
        return " · ".join(parts[:3]), raw_text
    return "Подробности в записи", raw_text


def _format_throughput_label(value: float) -> str:
    numeric = float(value or 0)
    if numeric <= 0:
        return "0 Мбит/с"
    if numeric < 0.1:
        return "< 0.1 Мбит/с"
    if numeric >= 1000:
        return f"{numeric / 1000:.2f} Гбит/с"
    if numeric >= 10:
        return f"{numeric:.1f} Мбит/с"
    return f"{numeric:.2f} Мбит/с"


def _available_payment_status_actions(record: PaymentRecord) -> list[str]:
    status = str(record.payment_status or "").strip().lower()
    method = str(record.payment_method or "").strip().lower()

    if status == "confirmed":
        return []

    if method in PROVIDER_SYNC_PAYMENT_METHODS:
        return []

    if method in MANUAL_PAYMENT_METHODS:
        if status == "awaiting_admin_review":
            return ["confirmed", "rejected", "expired", "disputed", "error"]
        if status == "awaiting_user_payment":
            return ["expired", "disputed", "error"]
        if status in {"rejected", "expired", "disputed", "error"}:
            return ["disputed", "error", "expired"]
        return []

    if status in {"pending", "awaiting_user_payment", "awaiting_admin_review"}:
        return ["confirmed", "expired", "disputed", "error"]
    if status in {"rejected", "expired", "disputed", "error"}:
        return ["disputed", "error", "expired"]
    return []


def _payment_age_hours(created_at: datetime, now: datetime) -> int:
    return max(0, int((now - created_at).total_seconds() // 3600))


def _payment_revenue_moment(record: PaymentRecord) -> datetime | None:
    return record.confirmed_at or record.created_at


def _ticket_sort_timestamp(ticket: dict) -> datetime:
    for key in ("created_at", "updated_at"):
        raw = ticket.get(key)
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
    return datetime.max


def _provider_sync_stamp(record: PaymentRecord) -> datetime | None:
    if not getattr(record, "metadata_json", None):
        return None
    try:
        metadata = json.loads(record.metadata_json)
    except json.JSONDecodeError:
        return None
    raw = metadata.get("last_synced_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _provider_sync_due(record: PaymentRecord, now: datetime) -> bool:
    if record.payment_method not in PROVIDER_SYNC_PAYMENT_METHODS:
        return False
    if str(record.payment_status or "").strip().lower() not in AUTO_PROVIDER_SYNC_STATUSES:
        return False
    last_sync = _provider_sync_stamp(record)
    if last_sync is None:
        return True
    return (now - last_sync).total_seconds() >= AUTO_PROVIDER_SYNC_INTERVAL_SECONDS


def _sort_payments_latest_first(payments: list[PaymentRecord]) -> list[PaymentRecord]:
    return sorted(
        payments,
        key=lambda record: (
            -(record.created_at.timestamp() if record.created_at else 0.0),
            -int(getattr(record, "id", 0) or 0),
        ),
    )


async def _refresh_provider_payment_records(
    payments: list[PaymentRecord],
    *,
    selected_record_id: int | None = None,
) -> list[PaymentRecord]:
    now = utcnow()
    candidates = [record for record in payments if _provider_sync_due(record, now)]
    if not candidates:
        return payments

    candidates.sort(
        key=lambda record: (
            0 if selected_record_id is not None and record.id == selected_record_id else 1,
            -(record.created_at.timestamp() if record.created_at else 0.0),
        )
    )
    synced_any = False
    for record in candidates[:AUTO_PROVIDER_SYNC_LIMIT]:
        try:
            await sync_platega_record_by_id(record.id, notify_user=False)
            synced_any = True
        except Exception:
            continue
    if not synced_any:
        return payments
    return await get_payment_records()


def _is_synthetic_user(user: User) -> bool:
    return shared_is_synthetic_user(user)


def _build_tariff_title_map() -> dict[str, str]:
    return {str(item["code"]): str(item["title"]) for item in get_runtime_tariffs_list()}


def _latest_confirmed_tariff_by_user(payments: list[PaymentRecord]) -> dict[int, str]:
    mapping: dict[int, tuple[datetime, str]] = {}
    for record in payments:
        if record.user_id is None or record.payment_status != "confirmed" or not record.tariff_code:
            continue
        current = mapping.get(record.user_id)
        if current is None or record.created_at > current[0]:
            mapping[record.user_id] = (record.created_at, record.tariff_code)
    return {user_id: tariff_code for user_id, (_, tariff_code) in mapping.items()}


def _plan_label_for_user(user: User, latest_tariffs: dict[int, str] | None = None) -> str:
    status = get_access_status_from_user(user)
    if status == "trial_active":
        return "Пробный период"
    if status == "vip_active":
        return "Админ доступ"
    if status == "paid_active":
        tariff_titles = _build_tariff_title_map()
        tariff_code = latest_tariffs.get(user.id) if latest_tariffs else None
        return tariff_titles.get(str(tariff_code), "Платный доступ")
    if getattr(user, "trial_used", False):
        return "Пробный уже был"
    return "Без тарифа"


def _plan_code_for_user(user: User, latest_tariffs: dict[int, str] | None = None) -> str | None:
    if latest_tariffs:
        return latest_tariffs.get(user.id)
    return None


def _plan_bucket_for_label(plan_label: str) -> str:
    normalized = str(plan_label or "").strip().lower()
    if "проб" in normalized:
        return "trial"
    if "без" in normalized:
        return "none"
    return "paid"


PLAN_DISPLAY_ORDER = {
    "1 месяц": 0,
    "3 месяца": 1,
    "6 месяцев": 2,
    "12 месяцев": 3,
    "Пробный период": 4,
    "Админ доступ": 5,
    "Пробный уже был": 6,
    "Без тарифа": 7,
}


def _ordered_plan_rows(plan_counts: Counter[str]) -> list[dict]:
    rows = [{"label": label, "count": count} for label, count in plan_counts.items()]
    rows.sort(key=lambda item: (PLAN_DISPLAY_ORDER.get(item["label"], 99), item["label"]))
    return rows


def _build_repair_attention_payload(
    users: list[User],
    failed_repair_counts: dict[int, int] | None = None,
    device_counts: dict[int, int] | None = None,
) -> dict:
    now = utcnow()
    repair_needed_users = []
    repair_candidates = [item for item in users if getattr(item, "vpn_repair_needed", False) and not _is_synthetic_user(item)]
    for user in repair_candidates:
        failed_attempts = int(failed_repair_counts.get(user.id, 0))
        is_payment_related = is_payment_related_repair_reason(getattr(user, "vpn_repair_reason", None))
        access_status = get_access_status_from_user(user)
        devices_count = int((device_counts or {}).get(user.id, 0))
        can_repair, repair_block_reason = _repair_action_guard(access_status, devices_count)
        marked_at_raw = getattr(user, "vpn_repair_marked_at", None)
        marked_age_hours = _payment_age_hours(marked_at_raw, now) if isinstance(marked_at_raw, datetime) else None
        is_escalated = bool(marked_age_hours is not None and marked_age_hours >= REPAIR_ESCALATION_HOURS)
        priority = "high" if is_escalated else _repair_priority(is_payment_related=is_payment_related)
        repair_needed_users.append(
            {
                "user_id": user.id,
                "username": user.username or "—",
                "telegram_id": user.telegram_id,
                "reason": normalize_repair_reason(getattr(user, "vpn_repair_reason", None)),
                "reason_label": repair_reason_label(getattr(user, "vpn_repair_reason", None)),
                "marked_at": _format_datetime(marked_at_raw),
                "marked_age_hours": marked_age_hours,
                "access_status": access_status,
                "devices_count": devices_count,
                "failed_repair_attempts": failed_attempts,
                "has_repeated_failures": failed_attempts >= 2,
                "is_payment_related": is_payment_related,
                "priority": priority,
                "is_escalated": is_escalated,
                "can_repair": can_repair,
                "repair_block_reason": repair_block_reason,
                "href": f"/users?user_id={user.id}",
            }
        )

    repair_needed_users.sort(
        key=lambda item: (
            _priority_rank(item["priority"]),
            item["marked_at"],
        ),
        reverse=False,
    )
    payment_related_users = [item for item in repair_needed_users if item["is_payment_related"]]

    return {
        "repair_needed_users": repair_needed_users[:5],
        "payment_related_users": payment_related_users[:5],
        "summary": {
            "repair_needed": len(repair_needed_users),
            "repeated_failed_repairs": sum(1 for item in repair_needed_users if item["has_repeated_failures"]),
            "payment_related_repairs": len(payment_related_users),
            "high_priority_repairs": sum(1 for item in repair_needed_users if item["priority"] == "high"),
            "escalated_repairs": sum(1 for item in repair_needed_users if item["is_escalated"]),
        },
    }


async def _load_failed_repair_counts_for_users(user_ids: list[int]) -> dict[int, int]:
    normalized_user_ids = sorted({int(user_id) for user_id in user_ids if int(user_id) > 0})
    if not normalized_user_ids:
        return {}
    async with async_session() as session:
        rows = (
            await session.execute(
                select(VpnRepairEvent.user_id, func.count(VpnRepairEvent.id))
                .where(
                    VpnRepairEvent.user_id.in_(normalized_user_ids),
                    VpnRepairEvent.result == "failed",
                )
                .group_by(VpnRepairEvent.user_id)
            )
        ).all()
    return {int(user_id): int(count or 0) for user_id, count in rows}


def _build_pending_manual_payment_attention(
    payments: list[PaymentRecord],
    users_lookup: dict[int, User],
    now: datetime,
) -> list[dict]:
    pending_manual = sorted(
        [row for row in payments if row.payment_status == "awaiting_admin_review"],
        key=lambda row: row.created_at,
    )
    rows = []
    for record in pending_manual[:5]:
        user = users_lookup.get(record.user_id) if record.user_id is not None else None
        age_hours = _payment_age_hours(record.created_at, now)
        rows.append(
            {
                "record_id": record.id,
                "user_id": record.user_id,
                "username": user.username if user and user.username else "—",
                "telegram_id": user.telegram_id if user else None,
                "created_at": _format_datetime(record.created_at),
                "age_hours": age_hours,
                "is_stale": age_hours >= MANUAL_PAYMENT_STALE_HOURS,
                "priority": "high" if age_hours >= MANUAL_PAYMENT_STALE_HOURS else "medium",
                "is_escalated": age_hours >= MANUAL_PAYMENT_STALE_HOURS,
                "href": f"/payments?record_id={record.id}",
                "user_href": f"/users?user_id={record.user_id}" if record.user_id is not None else None,
            }
        )
    return rows


def _build_support_attention(tickets: list[dict]) -> list[dict]:
    open_tickets = [ticket for ticket in tickets if ticket.get("status") in {"new", "in_progress"}]
    oldest_open = sorted(open_tickets, key=_ticket_sort_timestamp)[:3]
    rows = []
    for ticket in oldest_open:
        created_at = _ticket_sort_timestamp(ticket)
        age_hours = _payment_age_hours(created_at, utcnow()) if created_at != datetime.max else None
        is_escalated = bool(age_hours is not None and age_hours >= SUPPORT_ESCALATION_HOURS)
        rows.append(
            {
                "user_id": int(ticket["user_id"]),
                "username": str(ticket.get("username") or ticket.get("full_name") or "—"),
                "status": str(ticket.get("status") or "new"),
                "created_at": str(ticket.get("created_at") or "—"),
                "updated_at": str(ticket.get("updated_at") or "—"),
                "preview": str(ticket.get("last_user_message_preview") or ticket.get("last_message_preview") or "—"),
                "priority": "high" if is_escalated else "medium",
                "age_hours": age_hours,
                "is_escalated": is_escalated,
                "href": f"/support?ticket_id={ticket['user_id']}",
            }
        )
    return rows


async def _build_selected_support_user_context(ticket_detail: dict | None, *, admin: DashboardAdmin | None = None) -> dict | None:
    if not ticket_detail:
        return None

    user = ticket_detail.get("user")
    user_id = int(getattr(user, "id", 0) or 0) if user is not None else 0
    if user is None or user_id <= 0:
        return None

    detail = await get_user_detail(user_id)
    if detail is None:
        return None

    payments = ticket_detail.get("payments") or []
    latest_payment = payments[0] if payments else None
    access_status = detail["status"]
    devices_count = len(detail.get("devices", []))
    max_devices = get_device_limit_for_user(user)
    vpn_repair_needed = bool(detail["vpn_repair_state"]["repair_needed"])
    vpn_repair_reason = normalize_repair_reason(detail["vpn_repair_state"].get("reason"))
    vpn_repair_reason_label = repair_reason_label(detail["vpn_repair_state"].get("reason"))
    can_repair, repair_block_reason = _repair_action_guard(access_status, devices_count)
    dashboard_status = dashboard_user_status(user, latest_payment_status=latest_payment.get("payment_status") if latest_payment else None)

    return {
        "user_id": user_id,
        "username": user.username or "—",
        "telegram_id": user.telegram_id,
        "plan_label": _plan_label_for_user(user),
        "trial_used": bool(getattr(user, "trial_used", False)),
        "can_grant_trial": not bool(getattr(user, "trial_used", False)) and access_status not in ACTIVE_ACCESS_STATUSES,
        "can_extend_access": True,
        "access_status": access_status,
        "status_state": dashboard_status["code"],
        "status_label": dashboard_status["label"],
        "access_expires_at": detail["access_expires_at"],
        "devices_count": devices_count,
        "max_devices": max_devices,
        "vpn_repair_needed": vpn_repair_needed,
        "vpn_repair_reason": vpn_repair_reason,
        "vpn_repair_reason_label": vpn_repair_reason_label,
        "repair_action": {
            "can_repair": can_repair,
            "blocked_reason": repair_block_reason,
        },
        "sync_action": {
            "can_sync": can_repair,
            "blocked_reason": repair_block_reason,
        },
        "deep_repair_action": {
            "can_deep_repair": len(detail.get("devices", [])) > 0 and access_status in ACTIVE_ACCESS_STATUSES,
            "blocked_reason": None if len(detail.get("devices", [])) > 0 and access_status in ACTIVE_ACCESS_STATUSES else repair_block_reason,
        },
        "support_ticket_open": detail.get("support_ticket") is not None,
        "support_status": detail.get("support_ticket", {}).get("status_label") if detail.get("support_ticket") else None,
        "user_href": f"/users?user_id={user_id}",
        "latest_payment_href": (
            f"/payments?record_id={latest_payment['id']}"
            if latest_payment and latest_payment.get("id") and admin is not None and role_has_permission(admin.role, "manage_payments")
            else None
        ),
    }


async def _build_selected_payment_user_context(payment: dict | None) -> dict | None:
    if payment is None or payment.get("user_id") is None:
        return None

    user_id = int(payment["user_id"])
    detail = await get_user_detail(user_id)
    if detail is None:
        return None

    user = detail["user"]
    support_ticket = detail.get("support_ticket")
    repair_events = detail.get("vpn_repair_events") or []
    last_repair_event = repair_events[0] if repair_events else None
    access_status = detail["status"]
    devices_count = len(detail.get("devices", []))
    max_devices = get_device_limit_for_user(user)
    vpn_repair_needed = bool(detail["vpn_repair_state"]["repair_needed"])
    vpn_repair_reason = normalize_repair_reason(detail["vpn_repair_state"].get("reason"))
    vpn_repair_reason_label = repair_reason_label(detail["vpn_repair_state"].get("reason"))
    vpn_repair_source = detail["vpn_repair_state"].get("source")
    vpn_repair_source_label = detail["vpn_repair_state"].get("source_label")
    dashboard_status = dashboard_user_status(user, latest_payment_status=payment.get("payment_status"))
    issue_summary = {
        "has_issue": vpn_repair_needed or devices_count == 0 or access_status not in {"paid_active", "trial_active", "vip_active"},
        "access_status": access_status,
        "devices_count": devices_count,
        "max_devices": max_devices,
        "vpn_repair_needed": vpn_repair_needed,
        "vpn_repair_reason": vpn_repair_reason,
        "vpn_repair_reason_label": vpn_repair_reason_label,
        "vpn_repair_source": vpn_repair_source,
        "vpn_repair_source_label": vpn_repair_source_label,
        "last_repair_result": last_repair_event.get("result") if last_repair_event else None,
        "last_repair_outcome": last_repair_event.get("outcome") if last_repair_event else None,
        "last_repair_outcome_label": last_repair_event.get("outcome_label") if last_repair_event else None,
        "last_repair_source": last_repair_event.get("source") if last_repair_event else None,
        "last_repair_source_label": last_repair_event.get("source_label") if last_repair_event else None,
        "last_repair_reason": last_repair_event.get("reason") if last_repair_event else None,
        "last_repair_reason_label": last_repair_event.get("reason_label") if last_repair_event else None,
        "last_repair_at": last_repair_event.get("created_at") if last_repair_event else None,
    }
    can_repair, repair_block_reason = _repair_action_guard(access_status, devices_count)
    issue_summary["can_repair"] = can_repair
    issue_summary["repair_block_reason"] = repair_block_reason
    return {
        "user_id": user.id,
        "username": user.username or "—",
        "telegram_id": user.telegram_id,
        "access_status": access_status,
        "status_state": dashboard_status["code"],
        "status_label": dashboard_status["label"],
        "access_expires_at": detail["access_expires_at"],
        "devices_count": devices_count,
        "vpn_repair_needed": vpn_repair_needed,
        "vpn_repair_reason": vpn_repair_reason,
        "vpn_repair_reason_label": vpn_repair_reason_label,
        "vpn_repair_source": vpn_repair_source,
        "vpn_repair_source_label": vpn_repair_source_label,
        "repair_action": {
            "can_repair": can_repair,
            "blocked_reason": repair_block_reason,
        },
        "user_issue_summary": issue_summary,
        "support_ticket_open": support_ticket is not None,
        "support_status": support_ticket.get("status_label") if support_ticket else None,
        "user_href": f"/users?user_id={user.id}",
        "support_href": f"/support?ticket_id={user.telegram_id}" if support_ticket else None,
    }


async def _load_users_clients_payments() -> tuple[list[User], list[VpnClient], list[PaymentRecord]]:
    async with async_session() as session:
        users = list((await session.execute(select(User).where(_real_user_sql_clause()))).scalars().all())
        clients = list(
            (
                await session.execute(
                    select(VpnClient).where(VpnClient.user_id.in_(_real_user_ids_subquery()))
                )
            ).scalars().all()
        )
        payments = list(
            (
                await session.execute(
                    select(PaymentRecord).where(
                        or_(
                            PaymentRecord.user_id.is_(None),
                            PaymentRecord.user_id.in_(_real_user_ids_subquery()),
                        )
                    )
                )
            ).scalars().all()
        )
    real_users = [user for user in users if not _is_synthetic_user(user)]
    real_user_ids = {int(user.id) for user in real_users}
    real_clients = [client for client in clients if int(getattr(client, "user_id", 0) or 0) in real_user_ids]
    real_payments = [
        payment
        for payment in payments
        if payment.user_id is None or int(getattr(payment, "user_id", 0) or 0) in real_user_ids
    ]
    real_payments = _sort_payments_latest_first(real_payments)
    return real_users, real_clients, real_payments


async def _collect_region_and_plan_metrics() -> dict:
    users, clients, payments = await _load_users_clients_payments()
    tariff_map = _latest_confirmed_tariff_by_user(payments)
    real_users = [user for user in users if not _is_synthetic_user(user)]
    user_lookup = {user.id: user for user in users}
    region_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total_devices": 0, "active_devices": 0, "users": 0, "active_users": 0})
    region_user_sets: dict[str, set[int]] = defaultdict(set)
    region_active_user_sets: dict[str, set[int]] = defaultdict(set)
    default_plan_labels = [str(item["title"]) for item in get_runtime_tariffs_list()]
    default_plan_labels.extend(["Пробный доступ", "Платный доступ", "Без тарифа"])
    plan_counts: Counter[str] = Counter({label: 0 for label in default_plan_labels})

    for user in real_users:
        plan_counts[_plan_label_for_user(user, tariff_map)] += 1

    for client in clients:
        user = user_lookup.get(client.user_id)
        if user is None or _is_synthetic_user(user):
            continue
        country_code = normalize_country_code(json.loads(client.client_data).get("country_code") if client.client_data else "de")
        region_stats[country_code]["total_devices"] += 1
        region_user_sets[country_code].add(user.id)
        if get_access_status_from_user(user) in {"paid_active", "trial_active"} and not getattr(user, "is_blocked", False):
            region_stats[country_code]["active_devices"] += 1
            region_active_user_sets[country_code].add(user.id)

    for country_code, user_ids in region_user_sets.items():
        region_stats[country_code]["users"] = len(user_ids)
    for country_code, user_ids in region_active_user_sets.items():
        region_stats[country_code]["active_users"] = len(user_ids)

    return {
        "users": users,
        "clients": clients,
        "payments": payments,
        "latest_tariffs": tariff_map,
        "plan_counts": plan_counts,
        "region_stats": region_stats,
        "real_user_count": len(real_users),
        "trial_active_count": sum(1 for user in real_users if get_access_status_from_user(user) == "trial_active"),
        "paid_active_count": sum(1 for user in real_users if get_access_status_from_user(user) == "paid_active"),
        "inactive_count": sum(1 for user in real_users if get_access_status_from_user(user) == "inactive"),
        "trial_used_count": sum(1 for user in real_users if get_access_status_from_user(user) != "trial_active" and getattr(user, "trial_used", False)),
    }


def _build_v2_users_base_query(search: str = ""):
    normalized_search = str(search or "").strip().lower()
    query = select(User).where(_real_user_sql_clause()).order_by(User.created_at.desc())
    if not normalized_search:
        return query

    search_pattern = f"%{normalized_search}%"
    tariff_match = (
        select(PaymentRecord.id)
        .where(
            PaymentRecord.user_id == User.id,
            PaymentRecord.payment_status == "confirmed",
            func.lower(func.coalesce(PaymentRecord.tariff_code, "")).like(search_pattern),
        )
        .limit(1)
        .exists()
    )
    return query.where(
        or_(
            cast(User.id, String).like(search_pattern),
            cast(User.telegram_id, String).like(search_pattern),
            func.lower(func.coalesce(User.username, "")).like(search_pattern),
            tariff_match,
        )
    )


def _build_v2_user_device_stats_query(user_ids: list[int] | set[int] | tuple[int, ...]):
    normalized_ids = sorted({int(item) for item in user_ids if item is not None})
    return (
        select(
            VpnClient.user_id.label("user_id"),
            func.count(VpnClient.id).label("devices_count"),
            func.max(VpnClient.created_at).label("last_device_created"),
        )
        .where(VpnClient.user_id.in_(normalized_ids))
        .group_by(VpnClient.user_id)
    )


def _build_v2_user_country_rows_query(user_ids: list[int] | set[int] | tuple[int, ...]):
    normalized_ids = sorted({int(item) for item in user_ids if item is not None})
    return select(
        VpnClient.user_id.label("user_id"),
        VpnClient.client_data.label("client_data"),
    ).where(VpnClient.user_id.in_(normalized_ids))


def _build_v2_user_payment_count_query(user_ids: list[int] | set[int] | tuple[int, ...]):
    normalized_ids = sorted({int(item) for item in user_ids if item is not None})
    return (
        select(
            PaymentRecord.user_id.label("user_id"),
            func.count(PaymentRecord.id).label("payment_count"),
        )
        .where(PaymentRecord.user_id.in_(normalized_ids))
        .group_by(PaymentRecord.user_id)
    )


def _build_v2_user_latest_payment_status_query(user_ids: list[int] | set[int] | tuple[int, ...]):
    normalized_ids = sorted({int(item) for item in user_ids if item is not None})
    latest_status = (
        select(
            PaymentRecord.user_id.label("user_id"),
            PaymentRecord.payment_status.label("payment_status"),
            func.row_number()
            .over(
                partition_by=PaymentRecord.user_id,
                order_by=(PaymentRecord.created_at.desc(), PaymentRecord.id.desc()),
            )
            .label("row_number"),
        )
        .where(PaymentRecord.user_id.in_(normalized_ids))
        .subquery()
    )
    return select(latest_status.c.user_id, latest_status.c.payment_status).where(latest_status.c.row_number == 1)


def _build_v2_user_latest_confirmed_tariff_query(user_ids: list[int] | set[int] | tuple[int, ...]):
    normalized_ids = sorted({int(item) for item in user_ids if item is not None})
    latest_tariff = (
        select(
            PaymentRecord.user_id.label("user_id"),
            PaymentRecord.tariff_code.label("tariff_code"),
            func.row_number()
            .over(
                partition_by=PaymentRecord.user_id,
                order_by=(PaymentRecord.created_at.desc(), PaymentRecord.id.desc()),
            )
            .label("row_number"),
        )
        .where(
            PaymentRecord.user_id.in_(normalized_ids),
            PaymentRecord.payment_status == "confirmed",
            PaymentRecord.tariff_code.is_not(None),
        )
        .subquery()
    )
    return select(latest_tariff.c.user_id, latest_tariff.c.tariff_code).where(latest_tariff.c.row_number == 1)


def _admin_payload(admin: DashboardAdmin) -> dict:
    initials = "".join(part[:1].upper() for part in admin.display_name.split()[:2]).strip() or admin.username[:1].upper()
    avatar_url = _resolved_admin_avatar_url(admin.avatar_path)
    return {
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name,
        "initials": initials,
        "role": admin.role,
        "role_name": ROLE_NAMES.get(admin.role, admin.role),
        "telegram_id": admin.telegram_id,
        "avatar_url": avatar_url,
        "last_login_at": _format_datetime(admin.last_login_at),
        "permissions": {
            "can_manage_users": role_has_permission(admin.role, "manage_users"),
            "can_delete_users": role_has_permission(admin.role, "delete_users"),
            "can_manage_servers": role_has_permission(admin.role, "manage_servers"),
            "can_manage_server_actions": role_has_permission(admin.role, "manage_server_actions"),
            "can_manage_payments": role_has_permission(admin.role, "manage_payments"),
            "can_delete_payments": role_has_permission(admin.role, "delete_payments"),
            "can_manage_finance": role_has_permission(admin.role, "manage_finance"),
            "can_manage_support": role_has_permission(admin.role, "manage_support"),
            "can_approve_finance": role_has_permission(admin.role, "approve_finance"),
            "can_delete_finance": role_has_permission(admin.role, "delete_finance"),
            "can_run_sync": role_has_permission(admin.role, "run_sync"),
            "can_run_deep_repair": role_has_permission(admin.role, "run_deep_repair"),
            "can_clear_access": role_has_permission(admin.role, "clear_access"),
            "can_manage_services": role_has_permission(admin.role, "manage_services"),
            "can_manage_docs": role_has_permission(admin.role, "manage_docs"),
        },
    }


def _resolved_admin_avatar_url(avatar_path: str | None) -> str | None:
    normalized = str(avatar_path or "").strip()
    if not normalized:
        return None
    if not normalized.startswith(ADMIN_AVATAR_PREFIX):
        return normalized
    filename = normalized.removeprefix(ADMIN_AVATAR_PREFIX).strip()
    if not filename:
        return None
    target = Path(ADMIN_AVATAR_ROOT) / filename
    return normalized if target.exists() else None


def _serialize_payment_record(record: PaymentRecord, users: dict[int, User] | None = None) -> dict:
    metadata = {}
    if getattr(record, "metadata_json", None):
        try:
            metadata = json.loads(record.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    user = users.get(record.user_id) if users and record.user_id is not None else None
    tariff_label = metadata.get("product_title") or metadata.get("tariff_title") or record.tariff_code or "—"
    return {
        "id": record.id,
        "user_id": record.user_id,
        "username": user.username if user and user.username else "—",
        "telegram_id": user.telegram_id if user else None,
        "tariff_code": record.tariff_code or "—",
        "tariff_label": tariff_label,
        "payment_method": record.payment_method,
        "payment_method_label": {
            "telegram_stars": "Telegram Stars",
            "crypto_bot": "Crypto Bot",
            "sbp_platega": "СБП (Platega)",
            "crypto_platega": "Криптовалюта (Platega)",
        }.get(record.payment_method, manual_payment_method_label(record.payment_method)),
        "payment_status": record.payment_status,
        "payment_status_label": payment_status_label(record.payment_status),
        "amount": record.amount,
        "currency": record.currency,
        "duration_days": record.duration_days,
        "reference": record.reference,
        "note": record.note,
        "reviewed_by_actor_name": record.reviewed_by_actor_name,
        "reviewed_at": _format_datetime(record.reviewed_at),
        "rejection_reason": record.rejection_reason,
        "expires_at": _format_datetime(record.expires_at),
        "confirmed_at": _format_datetime(record.confirmed_at),
        "created_at": _format_datetime(record.created_at),
        "is_reviewable": record.payment_status == "awaiting_admin_review",
        "is_waiting_user": record.payment_status in {"awaiting_user_payment", "pending"},
        "can_send_reminder": _can_send_manual_payment_reminder(record),
        "is_problem": record.payment_status in {"rejected", "expired", "disputed", "error"},
        "provider_name": metadata.get("provider_name") if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
        "provider_transaction_id": record.external_payment_id if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
        "provider_status": metadata.get("provider_status") if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
        "checkout_url": metadata.get("checkout_url") if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
        "last_provider_sync_at": metadata.get("last_synced_at") if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
        "can_sync_provider": bool(record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS and record.external_payment_id),
        "provider_sync_problem": metadata.get("provider_sync_problem") if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS else None,
    }


def _serialize_audit_log(item: DashboardAuditLog, admin_lookup: dict[int, DashboardAdmin]) -> dict:
    admin = admin_lookup.get(item.admin_id) if item.admin_id else None
    details_text, raw_details_text = _summarize_audit_payload(item.action, item.details_text)
    return {
        "id": item.id,
        "action": item.action,
        "action_label": AUDIT_ACTION_LABELS.get(item.action, str(item.action or "system_event").replace("_", " ")),
        "target_type": item.target_type,
        "target_id": item.target_id,
        "details_text": details_text,
        "raw_details_text": raw_details_text,
        "request_id": getattr(item, "request_id", None),
        "created_at": _format_datetime(item.created_at),
        "admin_name": admin.display_name if admin else "System",
    }


def _serialize_server(snapshot: dict) -> dict:
    rx_mbps = float(snapshot.get("network_rx_mbps") or snapshot.get("rx_mbps") or 0)
    tx_mbps = float(snapshot.get("network_tx_mbps") or snapshot.get("tx_mbps") or 0)
    total_mbps = round(rx_mbps + tx_mbps, 2)
    total_transfer_gb = round(float(snapshot.get("network_sent_gb") or 0) + float(snapshot.get("network_recv_gb") or 0), 2)
    server_state = dashboard_server_state(snapshot)
    return {
        "id": snapshot.get("id"),
        "name": snapshot.get("name"),
        "country_code": snapshot.get("country_code"),
        "country_name": snapshot.get("country_name"),
        "status": snapshot.get("status"),
        "status_label": server_state["label"],
        "status_state": server_state["code"],
        "public_ip": snapshot.get("public_ip"),
        "provider": snapshot.get("provider"),
        "host": snapshot.get("host"),
        "cpu_percent": snapshot.get("cpu_percent") or 0,
        "memory_used_percent": snapshot.get("memory_used_percent") or 0,
        "disk_used_percent": snapshot.get("disk_used_percent") or 0,
        "xui_clients": snapshot.get("xui_clients") or 0,
        "panel_clients": snapshot.get("xui_clients") or 0,
        "active_devices": snapshot.get("active_devices") or 0,
        "total_devices": snapshot.get("total_devices") or 0,
        "active_users": snapshot.get("active_users") or 0,
        "network_rx_mbps": round(rx_mbps, 2),
        "network_tx_mbps": round(tx_mbps, 2),
        "total_network_mbps": total_mbps,
        "total_transfer_gb": total_transfer_gb,
        "ping_ms": snapshot.get("ping_ms"),
        "ping_label": snapshot.get("ping_label") or "—",
        "uptime": snapshot.get("uptime") or "—",
        "overall_state": snapshot.get("overall_state") or "unknown",
        "status_message": snapshot.get("status_message") or "—",
        "service_pills": snapshot.get("service_pills") or [],
        "load": snapshot.get("load") or "—",
    }


def _serialize_finance_entry(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "entry_type": entry["entry_type"],
        "entry_type_label": entry["entry_type_label"],
        "status": entry["status"],
        "status_label": entry["status_label"],
        "category": entry["category"],
        "amount": entry["amount"],
        "currency": entry["currency"],
        "signed_amount": entry["signed_amount"],
        "note": entry["note"],
        "related_server": entry["related_server"],
        "source_type": entry["source_type"],
        "source_id": entry["source_id"],
        "period_key": entry["period_key"],
        "occurred_at": entry["occurred_at"],
        "approved_at": entry["approved_at"],
        "created_by_name": entry["created_by_name"],
        "counterparty_name": entry["counterparty_name"],
        "approved_by_name": entry["approved_by_name"],
        "is_recurring": entry["is_recurring"],
    }


async def _get_admin_lookup() -> dict[int, DashboardAdmin]:
    async with async_session() as session:
        rows = list((await session.execute(select(DashboardAdmin))).scalars().all())
    return {row.id: row for row in rows}


async def _get_users_lookup(user_ids: list[int] | set[int] | tuple[int, ...] | None = None) -> dict[int, User]:
    normalized_ids = sorted({int(item) for item in (user_ids or []) if item is not None})
    if user_ids is not None and not normalized_ids:
        return {}
    async with async_session() as session:
        query = select(User).where(_real_user_sql_clause())
        if normalized_ids:
            query = query.where(User.id.in_(normalized_ids))
        rows = list((await session.execute(query)).scalars().all())
    return {row.id: row for row in rows}


async def get_v2_session_payload(admin: DashboardAdmin) -> dict:
    avatar_url = _resolved_admin_avatar_url(admin.avatar_path)
    navigation = [
        {"key": "overview", "label": "Панель управления", "href": "/overview"},
        {"key": "users", "label": "Пользователи", "href": "/users"},
        {"key": "servers", "label": "Серверы", "href": "/servers"},
        {"key": "traffic", "label": "Трафик", "href": "/traffic"},
        {"key": "payments", "label": "Финансы", "href": "/payments"},
        {"key": "analytics", "label": "Аналитика", "href": "/analytics"},
        {"key": "campaigns", "label": "Кампании", "href": "/campaigns"},
        {"key": "taskboard", "label": "Задачи", "href": "/taskboard"},
        {"key": "promocodes", "label": "Промокоды", "href": "/promocodes"},
        {"key": "support", "label": "Поддержка", "href": "/support"},
        {"key": "knowledge", "label": "База знаний", "href": "/knowledge"},
        {"key": "audit", "label": "Аудит", "href": "/audit"},
        {"key": "settings", "label": "Настройки", "href": "/settings"},
    ]
    navigation_requirements = {
        "users": ("manage_users",),
        "servers": ("manage_servers",),
        "traffic": ("manage_servers",),
        "payments": ("manage_payments", "manage_finance", "approve_finance"),
        "analytics": ("manage_payments",),
        "promocodes": ("manage_payments",),
        "support": ("manage_support",),
        "knowledge": ("manage_docs",),
        "campaigns": ("manage_campaigns",),
        "taskboard": ("manage_tasks",),
        "settings": ("manage_services", "manage_docs"),
    }
    return {
        "admin": _admin_payload(admin),
        "settings": dashboard_settings(),
        "product": {
            "name": "Amonora",
            "title": "Amonora Панель управления",
        },
        "profile": {
            "telegram_id": admin.telegram_id,
            "avatar_url": avatar_url,
            "last_login_at": _format_datetime(admin.last_login_at),
            "session_idle_minutes": dashboard_settings()["session_idle_minutes"],
            "session_hours": dashboard_settings()["session_hours"],
        },
        "navigation": [
            item
            for item in navigation
            if role_has_any_permission(admin.role, *navigation_requirements.get(item["key"], ()))
            or item["key"] in {"overview", "audit"}
        ],
    }


async def get_v2_overview_payload() -> dict:
    region_metrics = await _collect_region_and_plan_metrics()
    metrics = await overview_metrics(source_rows=region_metrics)
    users_lookup = {user.id: user for user in region_metrics["users"]}
    repair_candidate_ids = [
        int(user.id)
        for user in region_metrics["users"]
        if getattr(user, "vpn_repair_needed", False) and not _is_synthetic_user(user)
    ]
    failed_repair_counts = await _load_failed_repair_counts_for_users(repair_candidate_ids)
    admins_lookup = await _get_admin_lookup()
    payments = region_metrics["payments"]
    confirmed = [row for row in payments if row.payment_status == "confirmed"]
    revenue_confirmed = [row for row in confirmed if payment_method_counts_as_revenue(row.payment_method)]
    revenue_confirmed = [row for row in confirmed if payment_method_counts_as_revenue(row.payment_method)]
    now = utcnow()
    pending_manual_payments = [row for row in payments if row.payment_status == "awaiting_admin_review"]
    support_tickets = await get_support_tickets("all")
    stale_pending_confirmations = sum(
        1 for row in pending_manual_payments if row.created_at <= now - timedelta(hours=MANUAL_PAYMENT_STALE_HOURS)
    )
    oldest_pending_manual_payments = _build_pending_manual_payment_attention(payments, users_lookup, now)
    support_attention = _build_support_attention(support_tickets)
    recent_payments = [_serialize_payment_record(row, users_lookup) for row in payments[:6]]
    recent_activity = [_serialize_audit_log(row, admins_lookup) for row in await recent_audit_logs(8)]
    today_local = dashboard_local_date(now) or now.date()
    start = today_local - timedelta(days=13)
    activity_buckets = {start + timedelta(days=index): 0 for index in range(14)}
    revenue_buckets = {start + timedelta(days=index): 0 for index in range(14)}

    for user in users_lookup.values():
        if _is_synthetic_user(user):
            continue
        created = dashboard_local_date(user.created_at)
        if created in activity_buckets:
            activity_buckets[created] += 1

    for payment in revenue_confirmed:
        revenue_moment = _payment_revenue_moment(payment)
        revenue_date = dashboard_local_date(revenue_moment)
        if revenue_date in revenue_buckets:
            revenue_buckets[revenue_date] += payment.amount

    snapshots = []
    for item in metrics["servers"]:
        region = region_metrics["region_stats"].get(item.get("country_code") or "", {})
        snapshots.append(
            _serialize_server(
                {
                    **item,
                    "active_devices": region.get("active_devices", 0),
                    "total_devices": region.get("total_devices", 0),
                    "active_users": region.get("active_users", 0),
                }
            )
        )
    traffic_chart = [
        {
            "label": item["name"],
            "traffic": item["total_network_mbps"],
            "rx": item["network_rx_mbps"],
            "tx": item["network_tx_mbps"],
            "connections": item["active_devices"],
        }
        for item in snapshots
    ]
    server_load_chart = [
        {
            "label": item["name"],
            "cpu": item["cpu_percent"],
            "ram": item["memory_used_percent"],
            "disk": item["disk_used_percent"],
            "connections": item["active_devices"],
        }
        for item in snapshots
    ]
    user_activity_chart = [
        {"date": day.strftime("%d %b"), "users": count, "revenue": revenue_buckets[day]}
        for day, count in activity_buckets.items()
    ]
    repair_attention = _build_repair_attention_payload(
        region_metrics["users"],
        failed_repair_counts,
        Counter(client.user_id for client in region_metrics["clients"]),
    )
    node_issues = [
        {
            "server_id": item["id"],
            "name": item["name"],
            "status": item["status"],
            "status_label": item["status_label"],
            "status_state": item["status_state"],
            "overall_state": item["overall_state"],
            "cpu_percent": item["cpu_percent"],
            "memory_used_percent": item["memory_used_percent"],
            "disk_used_percent": item["disk_used_percent"],
            "href": f"/servers?server_id={item['id']}",
        }
        for item in snapshots
        if item["status_state"] in {"degradation", "down", "maintenance"} or item["overall_state"] in {"warning", "critical"}
    ]
    new_users_7d = sum(
        1
        for user in users_lookup.values()
        if not _is_synthetic_user(user) and user.created_at >= now - timedelta(days=7)
    )
    new_users_24h = sum(
        1
        for user in users_lookup.values()
        if not _is_synthetic_user(user) and user.created_at >= now - timedelta(days=1)
    )
    today_start = dashboard_day_start(now)
    revenue_today = sum(
        row.amount
        for row in revenue_confirmed
        if (revenue_moment := _payment_revenue_moment(row)) is not None and revenue_moment >= today_start
    )

    return {
        "priority": _backup_priority(metrics["backup_status"]),
        "kpis": {
            "total_users": region_metrics["real_user_count"],
            "active_users": region_metrics["paid_active_count"] + region_metrics["trial_active_count"],
            "paid_users": region_metrics["paid_active_count"],
            "trial_users": region_metrics["trial_active_count"],
            "active_connections": sum(values["active_devices"] for values in region_metrics["region_stats"].values()),
            "monthly_revenue": metrics["payment_counts"]["revenue_30d"],
            "daily_revenue": revenue_today,
            "new_users": new_users_7d,
            "new_users_24h": new_users_24h,
            "devices_total": sum(values["total_devices"] for values in region_metrics["region_stats"].values()),
            "servers_online": sum(1 for row in snapshots if row["status"] == "active"),
        },
        "user_distribution": {
            "trial_active": region_metrics["trial_active_count"],
            "paid_active": region_metrics["paid_active_count"],
            "inactive": region_metrics["inactive_count"],
            "trial_used": region_metrics["trial_used_count"],
            "plans": _ordered_plan_rows(region_metrics["plan_counts"]),
        },
        "charts": {
            "traffic": traffic_chart,
            "user_activity": user_activity_chart,
            "server_load": server_load_chart,
        },
        "rail": {
            "alerts": metrics["alerts"],
            "recent_payments": recent_payments,
            "recent_activity": recent_activity,
        },
        "system_alerts": {
            "backup": {
                **metrics["backup_status"],
                "priority": _backup_priority(metrics["backup_status"]),
            },
            "restore": {
                **metrics["restore_validation_status"],
                "priority": _restore_priority(metrics["restore_validation_status"]),
            },
            "support": {
                "open_tickets": int(metrics["support_counts"].get("new", 0)) + int(metrics["support_counts"].get("in_progress", 0)),
                "new_tickets": int(metrics["support_counts"].get("new", 0)),
                "oldest_open_tickets": support_attention,
                "priority": "high"
                if any(item["is_escalated"] for item in support_attention)
                else _support_priority(
                    open_tickets=int(metrics["support_counts"].get("new", 0)) + int(metrics["support_counts"].get("in_progress", 0))
                ),
                "is_escalated": any(item["is_escalated"] for item in support_attention),
                "status": "warning"
                if int(metrics["support_counts"].get("new", 0)) + int(metrics["support_counts"].get("in_progress", 0)) > 0
                else "healthy",
            },
            "payments": {
                "pending_confirmations": int(metrics["payment_counts"].get("pending", 0)),
                "open_manual_requests": int(metrics["payment_counts"].get("open_manual", 0)),
                "stale_pending_confirmations": stale_pending_confirmations,
                "stale_definition_hours": MANUAL_PAYMENT_STALE_HOURS,
                "oldest_pending_manual_payments": oldest_pending_manual_payments,
                "priority": "high"
                if any(item["is_escalated"] for item in oldest_pending_manual_payments)
                else _payments_priority(
                    pending_confirmations=int(metrics["payment_counts"].get("pending", 0)),
                    stale_pending_confirmations=stale_pending_confirmations,
                ),
                "is_escalated": any(item["is_escalated"] for item in oldest_pending_manual_payments),
                "status": "warning"
                if int(metrics["payment_counts"].get("pending", 0)) > 0 or stale_pending_confirmations > 0
                else "healthy",
            },
            "nodes": {
                "issues": len(node_issues),
                "degraded": sum(1 for item in snapshots if item["status_state"] == "degradation"),
                "down": sum(1 for item in snapshots if item["status_state"] == "down"),
                "maintenance": sum(1 for item in snapshots if item["status_state"] == "maintenance"),
                "items": node_issues[:5],
                "priority": "high" if any(item["status_state"] == "down" for item in node_issues) else ("medium" if node_issues else "low"),
                "status": "warning" if node_issues else "healthy",
            },
        },
        "attention": {
            **repair_attention,
            "summary": {
                **repair_attention["summary"],
                "sync_errors": sum(
                    1
                    for item in repair_attention["repair_needed_users"]
                    if item.get("reason") and "sync" in str(item["reason"])
                ),
                "node_issues": len(node_issues),
            },
        },
        "health": {
            "support_counts": metrics["support_counts"],
            "service_statuses": metrics["service_statuses"],
            "server_summary": summarize_server_snapshots(metrics["servers"]),
        },
    }


def _matches_user_dashboard_filters(row: dict, *, status_filter: str, plan_filter: str, issue_filter: str) -> bool:
    if status_filter != "all" and row.get("status_state") != status_filter:
        return False
    if plan_filter != "all":
        plan_bucket = str(row.get("plan_bucket") or "paid")
        plan_code = str(row.get("plan_code") or "")
        if plan_filter == "trial" and plan_bucket != "trial":
            return False
        if plan_filter == "paid" and plan_bucket != "paid":
            return False
        if plan_filter == "none" and plan_bucket != "none":
            return False
        if plan_filter in {"1m", "3m", "6m", "12m"} and plan_code != plan_filter:
            return False
    if issue_filter != "all":
        status_state = str(row.get("status_state") or "")
        if issue_filter == "repair" and status_state not in {"repair_needed", "sync_error"}:
            return False
        if issue_filter == "payment" and status_state != "awaiting_payment":
            return False
        if issue_filter == "blocked" and status_state != "blocked":
            return False
    return True


async def get_v2_users_payload(
    search: str = "",
    *,
    status_filter: str = "all",
    plan_filter: str = "all",
    issue_filter: str = "all",
    page: int = 1,
    page_size: int = 100,
) -> dict:
    query = search.strip().lower()
    async with async_session() as session:
        all_users = list((await session.execute(_build_v2_users_base_query(query))).scalars().all())

    all_users = sorted([item for item in all_users if not _is_synthetic_user(item)], key=lambda item: item.created_at, reverse=True)
    user_ids = [int(user.id) for user in all_users]
    device_counts: dict[int, int] = {}
    last_device_created: dict[int, datetime] = {}
    country_counts: dict[int, Counter] = defaultdict(Counter)
    payment_counts: dict[int, int] = {}
    latest_payment_status: dict[int, str] = {}
    latest_tariffs: dict[int, str] = {}
    public_slot_stats: dict[int, dict[int, dict[str, object]]] = defaultdict(dict)

    if user_ids:
        async with async_session() as session:
            device_stat_rows = (await session.execute(_build_v2_user_device_stats_query(user_ids))).all()
            country_rows = (await session.execute(_build_v2_user_country_rows_query(user_ids))).all()
            payment_count_rows = (await session.execute(_build_v2_user_payment_count_query(user_ids))).all()
            latest_payment_rows = (await session.execute(_build_v2_user_latest_payment_status_query(user_ids))).all()
            latest_tariff_rows = (await session.execute(_build_v2_user_latest_confirmed_tariff_query(user_ids))).all()
            public_route_rows = (
                await session.execute(
                    select(
                        PublicSubscriptionRoute.user_id,
                        PublicSubscriptionRoute.country_code,
                        PublicSubscriptionRoute.slot_index,
                        PublicSubscriptionRoute.client_data,
                    )
                    .where(
                        PublicSubscriptionRoute.user_id.in_(user_ids),
                        PublicSubscriptionRoute.status == "active",
                    )
                    .order_by(
                        PublicSubscriptionRoute.user_id.asc(),
                        PublicSubscriptionRoute.slot_index.asc(),
                        PublicSubscriptionRoute.country_code.asc(),
                    )
                )
            ).all()

        for user_id, devices_count, last_created_at in device_stat_rows:
            normalized_user_id = int(user_id)
            device_counts[normalized_user_id] = int(devices_count or 0)
            if isinstance(last_created_at, datetime):
                last_device_created[normalized_user_id] = last_created_at
        for user_id, raw_client_data in country_rows:
            try:
                metadata = json.loads(raw_client_data or "{}")
            except json.JSONDecodeError:
                metadata = {}
            country = normalize_country_code(metadata.get("country_code"))
            country_counts[int(user_id)][country] += 1
        for user_id, payment_count in payment_count_rows:
            payment_counts[int(user_id)] = int(payment_count or 0)
        for user_id, payment_status in latest_payment_rows:
            latest_payment_status[int(user_id)] = str(payment_status or "")
        for user_id, tariff_code in latest_tariff_rows:
            if tariff_code:
                latest_tariffs[int(user_id)] = str(tariff_code)
        for user_id, country_code, slot_index, raw_client_data in public_route_rows:
            normalized_user_id = int(user_id)
            normalized_slot_index = max(int(slot_index or 1), 1)
            slot_stat = public_slot_stats[normalized_user_id].setdefault(
                normalized_slot_index,
                {"bound": False, "countries": set()},
            )
            safe_country = normalize_country_code(country_code)
            if safe_country:
                slot_stat["countries"].add(safe_country)
            try:
                metadata = json.loads(raw_client_data or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if str(metadata.get("feed_device_fingerprint_hash") or "").strip():
                slot_stat["bound"] = True
            fallback_country = normalize_country_code(metadata.get("country_code"))
            if fallback_country:
                slot_stat["countries"].add(fallback_country)
        for normalized_user_id, slot_rows in public_slot_stats.items():
            bound_slots = [item for item in slot_rows.values() if bool(item.get("bound"))]
            if bound_slots:
                device_counts[normalized_user_id] = int(device_counts.get(normalized_user_id, 0) or 0) + len(bound_slots)
            for slot_stat in bound_slots:
                for country_code in sorted(slot_stat.get("countries") or []):
                    country_counts[normalized_user_id][str(country_code)] += 1

    extra_slot_counts = await get_active_device_slot_counts_for_users([user.id for user in all_users])
    filtered_users: list[User] = []
    for user in all_users:
        setattr(user, "active_device_slot_addons", int(extra_slot_counts.get(user.id, 0)))
        filtered_users.append(user)

    channel_statuses = await get_channel_subscription_statuses([user.telegram_id for user in filtered_users])
    rows = []
    for user in filtered_users:
        current_device_count = int(device_counts.get(user.id, 0) or 0)
        current_payment_count = int(payment_counts.get(user.id, 0) or 0)
        plan_label = _plan_label_for_user(user, latest_tariffs)
        plan_code = _plan_code_for_user(user, latest_tariffs)
        top_country = country_counts[user.id].most_common(1)[0][0] if country_counts[user.id] else None
        countries = [get_country_name(code) for code, _count in country_counts[user.id].most_common()]
        dashboard_status = dashboard_user_status(user, latest_payment_status=latest_payment_status.get(user.id))
        telegram_id_key = int(user.telegram_id) if user.telegram_id is not None else 0
        channel_subscription = channel_statuses.get(
            telegram_id_key,
            {"status": "unknown", "label": "Не проверено", "checked_at": None},
        )
        rows.append(
            {
                "id": user.id,
                "username": user.username or "—",
                "telegram_id": user.telegram_id,
                "plan": plan_label,
                "plan_code": plan_code,
                "plan_bucket": _plan_bucket_for_label(plan_label),
                "preferred_protocol": user.preferred_protocol,
                "devices": current_device_count,
                "payments": current_payment_count,
                "status": get_access_status_from_user(user),
                "status_state": dashboard_status["code"],
                "status_label": dashboard_status["label"],
                "is_blocked": user.is_blocked,
                "access_expires_at": _format_datetime(get_access_expires_at_from_user(user)),
                "last_device_at": _format_datetime(last_device_created.get(user.id)),
                "top_country": get_country_name(top_country) if top_country else "—",
                "countries": countries,
                "countries_label": ", ".join(countries[:2]) if countries else "—",
                "created_at": _format_datetime(user.created_at),
                "balance_rub": int(getattr(user, "balance_rub", 0) or 0),
                "base_device_limit": DEFAULT_DEVICE_LIMIT,
                "extra_device_slots_active": int(getattr(user, "active_device_slot_addons", 0) or 0),
                "extra_device_slots_max": int(getattr(config, "device_slot_max_extra_slots", 5) or 5),
                "max_devices": get_device_limit_for_user(user),
                "device_limit_reached": current_device_count >= get_device_limit_for_user(user),
                "channel_subscription_status": channel_subscription["status"],
                "channel_subscription_label": channel_subscription["label"],
                "channel_subscription_checked_at": channel_subscription.get("checked_at"),
            }
        )

    filtered_rows = [
        row
        for row in rows
        if _matches_user_dashboard_filters(
            row,
            status_filter=status_filter,
            plan_filter=plan_filter,
            issue_filter=issue_filter,
        )
    ]
    safe_page_size = min(max(int(page_size or 100), 20), 200)
    total_items = len(filtered_rows)
    total_pages = max(1, math.ceil(total_items / safe_page_size)) if total_items else 1
    safe_page = min(max(int(page or 1), 1), total_pages)
    start_index = (safe_page - 1) * safe_page_size
    end_index = start_index + safe_page_size
    page_items = filtered_rows[start_index:end_index]

    return {
        "items": page_items,
        "query": search,
        "filters": {
            "status": status_filter,
            "plan": plan_filter,
            "issue": issue_filter,
        },
        "summary": {
            "total": len(filtered_rows),
            "active": sum(1 for row in filtered_rows if row["status"] in {"paid_active", "trial_active"}),
            "blocked": sum(1 for row in filtered_rows if row["is_blocked"]),
            "with_devices": sum(1 for row in filtered_rows if row["devices"] > 0),
            "trial": sum(1 for row in filtered_rows if row["status_state"] == "trial"),
            "waiting_payment": sum(1 for row in filtered_rows if row["status_state"] == "awaiting_payment"),
            "needs_repair": sum(1 for row in filtered_rows if row["status_state"] in {"sync_error", "repair_needed"}),
            "no_access": sum(1 for row in filtered_rows if row["status_state"] == "no_access"),
        },
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": safe_page > 1,
            "has_next": safe_page < total_pages,
            "from_item": start_index + 1 if page_items else 0,
            "to_item": start_index + len(page_items),
        },
    }


async def get_v2_user_detail_payload(user_id: int) -> dict | None:
    detail = await get_user_detail(user_id)
    if detail is None:
        return None
    user = detail["user"]
    extra_slot_counts = await get_active_device_slot_counts_for_users([user.id])
    setattr(user, "active_device_slot_addons", int(extra_slot_counts.get(user.id, 0)))
    active_entitlements = await get_active_device_slot_entitlements_for_user(user.id)
    next_device_slot_expires_at = active_entitlements[0].expires_at if active_entitlements else None
    telegram_id_key = int(user.telegram_id) if user.telegram_id is not None else 0
    channel_subscription = (
        await get_channel_subscription_statuses([user.telegram_id], force_refresh=True)
    ).get(
        telegram_id_key,
        {"status": "unknown", "label": "Не проверено", "checked_at": None},
    )
    payments = await get_payment_records(user_id=user.id)
    latest_tariffs = _latest_confirmed_tariff_by_user(payments)
    serialized_payments = [_serialize_payment_record(record, {user.id: user}) for record in payments]
    balance_history = await get_user_balance_history(user.id, limit=12)
    dashboard_status = dashboard_user_status(user, latest_payment_status=payments[0].payment_status if payments else None)
    can_repair, repair_block_reason = _repair_action_guard(detail["status"], len(detail["devices"]))
    device_countries: list[str] = []
    latest_ip = "—"
    latest_ip_source = ""
    for device in detail["devices"]:
        metadata = device.get("metadata") or {}
        country_name = str(metadata.get("country_name") or "—").strip()
        if country_name and country_name != "—" and country_name not in device_countries:
            device_countries.append(country_name)
        ip_candidate = str(metadata.get("ip_address") or "—").strip()
        if latest_ip == "—" and ip_candidate and ip_candidate != "—":
            latest_ip = ip_candidate
            latest_ip_source = str(metadata.get("ip_source_label") or "—").strip()
    plan_label = _plan_label_for_user(user, latest_tariffs)
    return {
        "user": {
            "id": user.id,
            "username": user.username or "—",
            "telegram_id": user.telegram_id,
            "plan_label": plan_label,
            "plan_code": _plan_code_for_user(user, latest_tariffs),
            "plan_bucket": _plan_bucket_for_label(plan_label),
            "status": detail["status"],
            "status_state": dashboard_status["code"],
            "status_label": dashboard_status["label"],
            "preferred_protocol": user.preferred_protocol,
            "is_blocked": user.is_blocked,
            "trial_used": user.trial_used,
            "access_expires_at": detail["access_expires_at"],
            "created_at": _format_datetime(user.created_at),
            "subscription_started_at": _format_datetime(getattr(user, "subscription_started_at", None)),
            "balance_rub": int(getattr(user, "balance_rub", 0) or 0),
            "balance_reserved_rub": int(getattr(user, "balance_reserved_rub", 0) or 0),
            "balance_available_rub": max(
                int(getattr(user, "balance_rub", 0) or 0) - int(getattr(user, "balance_reserved_rub", 0) or 0),
                0,
            ),
            "base_device_limit": DEFAULT_DEVICE_LIMIT,
            "extra_device_slots_active": int(getattr(user, "active_device_slot_addons", 0) or 0),
            "extra_device_slots_max": int(getattr(config, "device_slot_max_extra_slots", 5) or 5),
            "next_device_slot_expires_at": _format_datetime(next_device_slot_expires_at),
            "max_devices": get_device_limit_for_user(user),
            "devices_count": len(detail["devices"]),
            "payments_count": len(payments),
            "countries": device_countries,
            "countries_label": ", ".join(device_countries[:2]) if device_countries else "—",
            "last_known_ip": latest_ip,
            "last_known_ip_source_label": latest_ip_source,
            "channel_subscription_status": channel_subscription["status"],
            "channel_subscription_label": channel_subscription["label"],
            "channel_subscription_checked_at": channel_subscription.get("checked_at"),
            "subscription_link_url": detail.get("subscription_link_url"),
            "subscription_link_token": detail.get("subscription_link_token"),
            "subscription_link_last_viewed_at": detail.get("subscription_link_last_viewed_at"),
            "subscription_link_last_feed_accessed_at": detail.get("subscription_link_last_feed_accessed_at"),
        },
        "vpn_repair_state": detail["vpn_repair_state"],
        "repair_action": {
            "can_repair": can_repair,
            "blocked_reason": repair_block_reason,
        },
        "sync_action": {
            "can_sync": can_repair,
            "blocked_reason": repair_block_reason,
        },
        "deep_repair_action": {
            "can_deep_repair": len(detail["devices"]) > 0 and detail["status"] in ACTIVE_ACCESS_STATUSES,
            "blocked_reason": None if len(detail["devices"]) > 0 and detail["status"] in ACTIVE_ACCESS_STATUSES else repair_block_reason,
        },
        "vpn_repair_events": detail.get("vpn_repair_events", []),
        "devices": detail["devices"],
        "payments": serialized_payments,
        "balance_history": balance_history,
        "payment_counts": detail["payment_counts"],
        "support_ticket": detail["support_ticket"],
        "support_history": detail["support_history"],
        "tariffs": get_runtime_tariffs_list(),
    }


async def get_v2_servers_payload(server_id: int | None = None, force_refresh: bool = False) -> dict:
    region_metrics = await _collect_region_and_plan_metrics()
    snapshots = [
        _serialize_server(
            {
                **item,
                "active_devices": region_metrics["region_stats"].get(item.get("country_code") or "", {}).get("active_devices", 0),
                "total_devices": region_metrics["region_stats"].get(item.get("country_code") or "", {}).get("total_devices", 0),
                "active_users": region_metrics["region_stats"].get(item.get("country_code") or "", {}).get("active_users", 0),
            }
        )
        for item in await get_server_snapshots(force_refresh=force_refresh)
    ]
    selected = None
    if server_id is not None:
        target = await get_server_snapshot_by_id(server_id)
        if target:
            region = region_metrics["region_stats"].get(target.get("country_code") or "", {})
            selected = _serialize_server(
                {
                    **target,
                    "active_devices": region.get("active_devices", 0),
                    "total_devices": region.get("total_devices", 0),
                    "active_users": region.get("active_users", 0),
                }
            )
    vpn = await get_vpn_overview()
    managed_servers = [
        {
            "id": row.id,
            "name": row.name,
            "country_name": row.country_name,
            "country_code": row.country_code,
            "host": row.host,
            "public_ip": row.public_ip,
            "provider": row.provider,
            "status": row.status,
        }
        for row in await get_managed_servers()
    ]
    if selected is not None:
        selected = {
            **selected,
            "available_actions": ["restart", "health_check", "maintenance", "migrate"],
            "migration_targets": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "country_name": item["country_name"],
                    "country_code": item["country_code"],
                    "status": item["status"],
                }
                for item in managed_servers
                if int(item["id"]) != int(selected["id"])
            ],
        }
    return {
        "summary": {
            **summarize_server_snapshots(await get_server_snapshots(force_refresh=force_refresh)),
            "active_devices": sum(item["active_devices"] for item in snapshots),
            "total_devices": sum(item["total_devices"] for item in snapshots),
            "degradation": sum(1 for item in snapshots if item["status_state"] == "degradation"),
            "down": sum(1 for item in snapshots if item["status_state"] == "down"),
        },
        "nodes": snapshots,
        "selected_node": selected,
        "vpn_summary": vpn["summary"],
        "managed_servers": managed_servers,
    }


async def get_v2_traffic_payload(force_refresh: bool = False) -> dict:
    region_metrics = await _collect_region_and_plan_metrics()
    snapshots = []
    for item in await get_server_snapshots(force_refresh=force_refresh):
        region = region_metrics["region_stats"].get(item.get("country_code") or "", {})
        snapshots.append(
            _serialize_server(
                {
                    **item,
                    "active_devices": region.get("active_devices", 0),
                    "total_devices": region.get("total_devices", 0),
                    "active_users": region.get("active_users", 0),
                }
            )
        )
    traffic_baseline = await ensure_current_traffic_baseline(snapshots)
    snapshots, traffic_baseline = apply_traffic_baseline_to_snapshots(snapshots)
    cutoff = utcnow() - timedelta(hours=24)

    async with async_session() as session:
        audits = list(
            (
                await session.execute(
                    select(DashboardAuditLog.created_at).where(DashboardAuditLog.created_at >= cutoff)
                )
            ).scalars().all()
        )
        support_messages = list(
            (
                await session.execute(
                    select(SupportTicketMessage.created_at).where(SupportTicketMessage.created_at >= cutoff)
                )
            ).scalars().all()
        )

    hourly_counter = [0] * 24
    for client in region_metrics["clients"]:
        if client.created_at >= cutoff:
            hourly_counter[client.created_at.hour] += 2
    for user in region_metrics["users"]:
        if _is_synthetic_user(user):
            continue
        if user.created_at >= cutoff:
            hourly_counter[user.created_at.hour] += 1
    for payment in region_metrics["payments"]:
        if payment.created_at >= cutoff:
            hourly_counter[payment.created_at.hour] += 2
    for audit_created_at in audits:
        if audit_created_at is not None:
            hourly_counter[audit_created_at.hour] += 1
    for message_created_at in support_messages:
        if message_created_at is not None:
            hourly_counter[message_created_at.hour] += 1

    region_rows = [
        {"region": get_country_name(code), "connections": values["active_devices"]}
        for code, values in sorted(region_metrics["region_stats"].items())
    ] or [{"region": "Германия", "connections": 0}, {"region": "Эстония", "connections": 0}]

    server_rows = [
        {
            "server": item["name"],
            "traffic": item["total_network_mbps"],
            "rx": item["network_rx_mbps"],
            "tx": item["network_tx_mbps"],
            "connections": item["active_devices"],
            "country": item["country_name"],
            "transfer_gb": item["total_transfer_gb"],
        }
        for item in snapshots
    ]

    top_countries = sorted(
        [
            {"country": get_country_name(code), "connections": values["active_devices"]}
            for code, values in region_metrics["region_stats"].items()
        ],
        key=lambda item: item["connections"],
        reverse=True,
    )[:5]
    total_bandwidth = round(sum(item["total_network_mbps"] for item in snapshots), 2)
    total_transfer_gb = round(sum(item["total_transfer_gb"] for item in snapshots), 2)
    protocol_counter = Counter(client.protocol for client in region_metrics["clients"])

    return {
        "overview": {
            "current_bandwidth": total_bandwidth,
            "current_bandwidth_label": _format_throughput_label(total_bandwidth),
            "total_transfer_gb": total_transfer_gb,
            "regions_online": sum(1 for row in region_rows if row["connections"] > 0),
            "servers_reporting": len(snapshots),
            "active_connections": sum(values["active_devices"] for values in region_metrics["region_stats"].values()),
            "period_label": "Последние 24 часа",
            "peak_hours_label": "Операционная активность control-plane за последние 24 часа",
            "baseline_reset_at": traffic_baseline.get("reset_at") if isinstance(traffic_baseline, dict) else None,
        },
        "bandwidth_by_server": server_rows,
        "load_by_server": [
            {
                "server": item["name"],
                "cpu": item["cpu_percent"],
                "ram": item["memory_used_percent"],
                "disk": item["disk_used_percent"],
            }
            for item in snapshots
        ],
        "connections_by_region": region_rows,
        "peak_hours": [{"hour": f"{hour:02d}:00", "activity": value} for hour, value in enumerate(hourly_counter)],
        "top_countries": top_countries,
        "traffic_mix": [
            {"label": item["name"], "value": item["total_transfer_gb"] or item["active_devices"] or item["total_network_mbps"] or 0}
            for item in snapshots
        ],
        "protocol_mix": [
            {"label": "VLESS" if protocol == "vless" else "Trojan + TLS", "value": count}
            for protocol, count in sorted(protocol_counter.items())
        ],
    }


async def get_v2_payments_payload(
    record_id: int | None = None,
    period_key: str | None = None,
    *,
    search: str = "",
    status_filter: str = "all",
    method_filter: str = "all",
    issue_filter: str = "all",
    admin: DashboardAdmin | None = None,
) -> dict:
    payments = await get_payment_records(
        search=search,
        status_filter=status_filter,
        method_filter=method_filter,
        issue_filter=issue_filter,
    )
    payments = await _refresh_provider_payment_records(payments, selected_record_id=record_id)
    selected_record_model = next((row for row in payments if row.id == record_id), None) if record_id is not None else None
    if record_id is not None and selected_record_model is None:
        selected_record_model = await get_payment_record_by_id(record_id)
    payment_user_ids = {
        int(record.user_id)
        for record in payments
        if getattr(record, "user_id", None) is not None
    }
    if selected_record_model is not None and getattr(selected_record_model, "user_id", None) is not None:
        payment_user_ids.add(int(selected_record_model.user_id))
    users_lookup = await _get_users_lookup(sorted(payment_user_ids))
    serialized_payments = [_serialize_payment_record(record, users_lookup) for record in payments]
    finance = await get_finance_dashboard(period_key=period_key)
    now = utcnow()
    selected_payment = None
    if record_id is not None:
        selected_payment = next((item for item in serialized_payments if item["id"] == record_id), None)
        if selected_payment is None:
            if selected_record_model is not None:
                selected_payment = _serialize_payment_record(selected_record_model, users_lookup)
    if selected_payment is None and serialized_payments:
        selected_payment = serialized_payments[0]
    if selected_payment is not None:
        selected_record_model = next((row for row in payments if row.id == selected_payment["id"]), None) or selected_record_model
        selected_payment = {
            **selected_payment,
            "linked_user_context": await _build_selected_payment_user_context(selected_payment),
            "available_status_actions": _available_payment_status_actions(selected_record_model) if selected_record_model is not None else [],
        }
    linked_finance_entry = None
    if selected_payment is not None:
        linked_finance_entry = next(
            (
                item
                for item in finance["entries"]
                if item.get("source_type") == "payment_record" and int(item.get("source_id") or 0) == int(selected_payment["id"])
            ),
            None,
        )
        if linked_finance_entry is None and finance.get("selected_entry") is not None:
            selected_entry = finance["selected_entry"]
            if selected_entry.get("source_type") == "payment_record" and int(selected_entry.get("source_id") or 0) == int(selected_payment["id"]):
                linked_finance_entry = selected_entry

    confirmed = [row for row in payments if row.payment_status == "confirmed"]
    revenue_confirmed = [row for row in confirmed if payment_method_counts_as_revenue(row.payment_method)]
    failed = [row for row in payments if row.payment_status == "rejected"]
    manual_queue = [row for row in payments if row.payment_status == "awaiting_admin_review"]
    waiting_user_payment = [row for row in payments if row.payment_status in {"awaiting_user_payment", "pending"}]
    expired_records = [row for row in payments if row.payment_status == "expired"]
    disputed_records = [row for row in payments if row.payment_status == "disputed"]
    error_records = [row for row in payments if row.payment_status == "error"]
    new_subscriptions = sum(1 for row in revenue_confirmed if (row.confirmed_at or row.created_at) >= now - timedelta(days=30))
    payment_methods = Counter(row.payment_method for row in payments)

    can_manage_finance = admin is None or role_has_permission(admin.role, "manage_finance") or role_has_permission(admin.role, "approve_finance")

    return _json_safe({
        "summary": {
            "mrr": sum(row.amount for row in revenue_confirmed if (row.confirmed_at or row.created_at) >= now - timedelta(days=30)),
            "new_subscriptions": new_subscriptions,
            "refunds": 0,
            "failed_payments": len(failed),
            "manual_queue": len(manual_queue),
            "awaiting_payment": len(waiting_user_payment),
            "confirmed": len(confirmed),
            "expired": len(expired_records),
            "disputed": len(disputed_records),
            "error": len(error_records),
            "problem_records": len(failed) + len(expired_records) + len(disputed_records) + len(error_records),
        },
        "records": serialized_payments,
        "selected_record": selected_payment,
        "filters": {
            "search": search,
            "status": status_filter,
            "method": method_filter,
            "issue": issue_filter,
            "period_key": period_key or "",
        },
        "payment_mix": [{"method": key, "count": value} for key, value in payment_methods.items()],
        "finance": {
            "summary": await get_finance_summary(period_key=period_key),
            "dashboard": {
                **finance,
                "entries": [_serialize_finance_entry(item) for item in finance["entries"]] if can_manage_finance else [],
                "selected_entry": (
                    _serialize_finance_entry(linked_finance_entry)
                    if can_manage_finance and linked_finance_entry
                    else (_serialize_finance_entry(finance["selected_entry"]) if can_manage_finance and finance["selected_entry"] else None)
                ),
                "recurring_rows": [_serialize_finance_entry(item) for item in finance["recurring_rows"]] if can_manage_finance else [],
                "admins": finance["admins"] if can_manage_finance else [],
            },
        },
        "tariffs": get_runtime_tariffs_list(),
    })


async def get_v2_promocodes_payload(*, search: str = "", kind_filter: str = "all", status_filter: str = "all") -> dict:
    codes = await list_promo_codes(search=search, kind_filter=kind_filter, status_filter=status_filter)
    admin_lookup = await _get_admin_lookup()
    buyer_ids = [int(code.buyer_user_id) for code in codes if getattr(code, "buyer_user_id", None) is not None]
    buyers = await _get_users_lookup(buyer_ids)

    serialized = []
    active = 0
    discount_count = 0
    days_count = 0
    gift_count = 0
    pending_discount_redemptions = 0

    async with async_session() as session:
        pending_discount_redemptions = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(PromoCodeRedemption)
                    .where(PromoCodeRedemption.status == "pending_discount")
                )
            ).scalar()
            or 0
        )

    for row in codes:
        normalized_kind = str(row.kind or "").strip().lower()
        status = str(row.status or "").strip().lower()
        if status == "active":
            active += 1
        if normalized_kind == "discount_percent":
            discount_count += 1
        elif normalized_kind == "gift_days":
            gift_count += 1
        else:
            days_count += 1
        buyer = buyers.get(int(row.buyer_user_id)) if getattr(row, "buyer_user_id", None) is not None else None
        admin = admin_lookup.get(int(row.created_by_admin_id)) if getattr(row, "created_by_admin_id", None) is not None else None
        serialized.append(
            {
                "id": int(row.id),
                "code": str(row.code or ""),
                "kind": normalized_kind,
                "kind_label": promo_kind_label(normalized_kind),
                "title": str(row.title or "").strip() or "—",
                "description": str(row.description or "").strip() or "—",
                "discount_percent": int(row.discount_percent or 0) if row.discount_percent is not None else None,
                "grant_days": int(row.grant_days or 0),
                "max_redemptions": int(row.max_redemptions or 0),
                "redeemed_count": int(row.redeemed_count or 0),
                "remaining_redemptions": max(int(row.max_redemptions or 0) - int(row.redeemed_count or 0), 0),
                "status": status,
                "status_label": {
                    "active": "Активен",
                    "inactive": "Отключён",
                    "exhausted": "Исчерпан",
                }.get(status, "Неизвестно"),
                "created_by_name": admin.display_name if admin is not None else "Система",
                "buyer_label": (
                    f"@{buyer.username}" if buyer is not None and getattr(buyer, "username", None) else (
                        str(getattr(buyer, "telegram_id", "—")) if buyer is not None else "—"
                    )
                ),
                "buyer_user_id": int(row.buyer_user_id) if row.buyer_user_id is not None else None,
                "payment_record_id": int(row.payment_record_id) if row.payment_record_id is not None else None,
                "expires_at": _format_datetime(row.expires_at),
                "created_at": _format_datetime(row.created_at),
            }
        )

    return {
        "summary": {
            "total": len(serialized),
            "active": active,
            "discounts": discount_count,
            "days": days_count,
            "gift": gift_count,
            "pending_discount_redemptions": pending_discount_redemptions,
        },
        "filters": {
            "search": search,
            "kind": kind_filter,
            "status": status_filter,
        },
        "codes": serialized,
    }


async def get_v2_campaign_analytics_payload(
    *,
    search: str = "",
    period_key: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    period = _resolve_campaign_period(period_key=period_key, date_from=date_from, date_to=date_to)
    items = await _load_campaign_offer_items(search)
    stage_map = await _load_campaign_stage_counts(
        [str(item.deep_link_token or "") for item in items],
        date_from=period["date_from"],
        date_to=period["date_to"],
    )
    campaigns = [_serialize_campaign_row(item, stage_map.get(str(item.deep_link_token or "").strip().lower(), {})) for item in items]

    summary = {
        "total_campaigns": len(campaigns),
        "total_transitions": sum(int(item["stats"]["transitions"]) for item in campaigns),
        "total_bot_starts": sum(int(item["stats"]["bot_starts"]) for item in campaigns),
        "total_trial_started": sum(int(item["stats"]["trial_started"]) for item in campaigns),
        "total_key_issued": sum(int(item["stats"]["key_issued"]) for item in campaigns),
        "total_paid": sum(int(item["stats"]["paid"]) for item in campaigns),
        "total_renewed": sum(int(item["stats"]["renewed"]) for item in campaigns),
    }
    total_transitions = int(summary["total_transitions"] or 0)
    summary["overall_conversion_rate"] = round((int(summary["total_paid"]) / total_transitions) * 100, 2) if total_transitions > 0 else 0.0

    return {
        "summary": summary,
        "query": search,
        "period": {
            "key": period["key"],
            "label": period["label"],
            "start": period["start"],
            "end": period["end"],
            "presets": ["7d", "30d", "this_month", "last_month", "custom"],
        },
        "campaigns": campaigns,
    }


async def get_v2_campaign_analytics_detail_payload(
    campaign_id: int,
    *,
    period_key: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict | None:
    async with async_session() as session:
        item = (
            await session.execute(
                select(ChannelContentItem).where(
                    ChannelContentItem.id == int(campaign_id),
                    ChannelContentItem.content_type == CHANNEL_CONTENT_TYPE_OFFER,
                )
            )
        ).scalar_one_or_none()
    if item is None:
        return None

    token = str(item.deep_link_token or "").strip().lower()
    period = _resolve_campaign_period(period_key=period_key, date_from=date_from, date_to=date_to)
    stage_map = await _load_campaign_stage_counts([token], date_from=period["date_from"], date_to=period["date_to"])
    payload = _serialize_campaign_row(item, stage_map.get(token, {}))
    payload["funnel"] = _build_campaign_funnel(payload["stats"])
    payload["period"] = {
        "key": period["key"],
        "label": period["label"],
        "start": period["start"],
        "end": period["end"],
    }
    return payload


async def get_v2_support_payload(filter_mode: str = "all", search: str = "", ticket_id: int | None = None, admin: DashboardAdmin | None = None) -> dict:
    tickets = await get_support_tickets(filter_mode, search, admin)
    counts = await get_support_dashboard_counts(admin)
    selected_ticket_id = ticket_id
    selected = await get_support_ticket_detail(selected_ticket_id) if selected_ticket_id is not None else None
    selected_payload = None
    if selected is not None:
        selected_payload = {
            **selected,
            "linked_user_context": await _build_selected_support_user_context(selected, admin=admin),
        }
    return {
        "tickets": tickets,
        "counts": counts,
        "filter_mode": filter_mode,
        "query": search,
        "selected_ticket": selected_payload,
        "admin_choices": await get_support_admin_choices(admin),
    }


async def get_v2_notifications_payload() -> dict:
    overview = await get_v2_overview_payload()
    alerts = overview["rail"]["alerts"][:6]
    recent_payments = overview["rail"]["recent_payments"][:5]
    support_counts = overview["health"]["support_counts"]
    support_tickets = await get_support_tickets("new")
    items = [
        {
            "id": f"alert-{index}",
            "kind": "alert",
            "title": alert["title"],
            "text": alert["text"],
            "href": alert["href"],
            "meta": alert["action"],
        }
        for index, alert in enumerate(alerts, start=1)
    ]
    items.extend(
        {
            "id": f"payment-{payment['id']}",
            "kind": "payment",
            "title": f"Платёж #{payment['id']}",
            "text": f"{payment['username']} · {payment['payment_method_label']}",
            "href": f"/payments?record_id={payment['id']}",
            "meta": payment["payment_status_label"],
        }
        for payment in recent_payments
    )
    items.extend(
        {
            "id": f"support-{ticket['user_id']}",
            "kind": "support",
            "title": f"Обращение от {ticket.get('username') or ticket.get('full_name') or ticket['user_id']}",
            "text": ticket.get("last_user_message_preview") or "Новое сообщение клиента",
            "href": f"/support?ticket_id={ticket['user_id']}",
            "meta": str(ticket.get("status") or "new"),
        }
        for ticket in support_tickets[:5]
    )
    unread = max(
        len(items),
        len(alerts) + int(support_counts.get("new", 0)) + int(support_counts.get("in_progress", 0)),
    )
    return {
        "alerts": alerts,
        "recent_payments": recent_payments,
        "support_counts": support_counts,
        "unread": unread,
        "items": items[:10],
    }


async def get_v2_search_payload(query: str, admin: DashboardAdmin | None = None) -> dict:
    needle = query.strip().lower()
    if len(needle) < 2:
        return {"query": query, "sections": []}

    users_payload = await get_v2_users_payload(query)
    user_items = [
        {
            "id": f"user-{item['id']}",
            "title": item["username"],
            "subtitle": f"User · {item['plan']} · ID {item['telegram_id']}",
            "href": f"/users?user_id={item['id']}&q={query}",
            "tag": item["status"],
        }
        for item in users_payload["items"][:5]
    ]

    server_items = []
    if admin is None or role_has_permission(admin.role, "manage_servers"):
        for node in [_serialize_server(item) for item in await get_server_snapshots()]:
            haystack = " ".join(
                [
                    str(node.get("name") or ""),
                    str(node.get("public_ip") or ""),
                    str(node.get("country_name") or ""),
                    str(node.get("host") or ""),
                ]
            ).lower()
            if needle not in haystack:
                continue
            server_items.append(
                {
                    "id": f"server-{node['id']}",
                    "title": node["name"],
                    "subtitle": f"Server · {node['country_name']} · {node['public_ip']}",
                    "href": f"/servers?server_id={node['id']}",
                    "tag": node["status"],
                }
            )
        server_items = server_items[:5]

    payment_rows = await get_payment_records(search=needle)
    payment_user_ids = sorted(
        {
            int(record.user_id)
            for record in payment_rows
            if getattr(record, "user_id", None) is not None
        }
    )
    users_lookup = await _get_users_lookup(payment_user_ids)
    payment_items = []
    for record in payment_rows:
        serialized = _serialize_payment_record(record, users_lookup)
        haystack = " ".join(
            [
                str(serialized["id"]),
                serialized["username"],
                serialized["payment_method_label"],
                str(serialized.get("reference") or ""),
                str(serialized.get("note") or ""),
            ]
        ).lower()
        if needle not in haystack:
            continue
        payment_items.append(
            {
                "id": f"payment-{serialized['id']}",
                "title": f"Payment #{serialized['id']}",
                "subtitle": f"{serialized['username']} · {serialized['payment_method_label']} · {serialized['amount']} ₽",
                "href": f"/payments?record_id={serialized['id']}",
                "tag": serialized["payment_status_label"],
            }
        )
    payment_items = payment_items[:5]

    support_items = []
    for ticket in await get_support_tickets("all", query):
        ticket_user_id = int(ticket["user_id"])
        support_items.append(
            {
                "id": f"ticket-{ticket_user_id}",
                "title": str(ticket.get("username") or "Без username"),
                "subtitle": f"Ticket · {ticket.get('status')} · {ticket.get('last_user_message_preview') or '—'}",
                "href": f"/support?ticket_id={ticket_user_id}&q={query}",
                "tag": str(ticket.get("status") or "ticket"),
            }
        )
    support_items = support_items[:5]

    sections = []
    for key, label, items in [
        ("users", "Users", user_items),
        ("servers", "Servers", server_items),
        ("payments", "Payments", payment_items),
        ("support", "Support", support_items),
    ]:
        if items:
            sections.append({"key": key, "label": label, "items": items})
    return {"query": query, "sections": sections}


async def get_v2_audit_payload(limit: int = 150) -> dict:
    audits = await recent_audit_logs(limit)
    admins_lookup = await _get_admin_lookup()
    items = [_serialize_audit_log(item, admins_lookup) for item in audits]
    action_counts = Counter(item["action"] for item in items if item.get("action"))
    admin_counts = Counter(item["admin_name"] for item in items if item.get("admin_name"))
    target_counts = Counter(item["target_type"] for item in items if item.get("target_type"))
    return {
        "summary": {
            "total": len(items),
            "unique_actions": len(action_counts),
            "active_admins": len(admin_counts),
            "target_types": len(target_counts),
            "latest_event_at": items[0]["created_at"] if items else "—",
        },
        "items": items,
        "top_actions": [{"action": action, "count": count} for action, count in action_counts.most_common(6)],
        "top_admins": [{"name": name, "count": count} for name, count in admin_counts.most_common(6)],
        "top_targets": [{"target_type": target_type, "count": count} for target_type, count in target_counts.most_common(6)],
    }


async def get_v2_settings_payload(doc: str | None = None) -> dict:
    statuses = await get_service_statuses()
    logs = {
        name: await service_logs(service_name, 18)
        for name, service_name in {
            "main_bot": "amonora-bot.service",
            "support_bot": "amonora-support-bot.service",
            "dashboard": "amonora-dashboard.service",
        }.items()
    }
    docs = await get_documentation_page(doc)
    audits = await recent_audit_logs(20)
    admins_lookup = await _get_admin_lookup()
    active_admins = sorted(admins_lookup.values(), key=lambda item: (item.role, item.display_name, item.username))
    env_rows = read_masked_env()
    api_keys = [(key, value) for key, value in env_rows if any(hint in key.upper() for hint in ("TOKEN", "KEY", "SECRET"))]
    notification_profiles = await list_notification_preference_rows()
    permission_matrix = get_role_permission_matrix_snapshot()
    editable_roles = set(editable_permission_roles())
    role_matrix = [
        {
            "permission": permission,
            "label": PERMISSION_LABELS.get(permission, permission.replace("_", " ")),
            "owner": bool(permission_matrix.get("owner", {}).get(permission, True)),
            "owner_editable": False,
            "tech_admin": bool(permission_matrix.get("tech_admin", {}).get(permission, permission in ROLE_PERMISSIONS.get("tech_admin", set()))),
            "tech_admin_editable": "tech_admin" in editable_roles and permission in editable_permissions_for_role("tech_admin"),
            "manager": bool(permission_matrix.get("support_admin", {}).get(permission, permission in ROLE_PERMISSIONS.get("support_admin", set()))),
            "manager_editable": "support_admin" in editable_roles and permission in editable_permissions_for_role("support_admin"),
        }
        for permission in sorted(set().union(*ROLE_PERMISSIONS.values()))
    ]
    return {
        "service_statuses": statuses,
        "logs": logs,
        "env_rows": env_rows,
        "api_keys": api_keys,
        "audits": [_serialize_audit_log(item, admins_lookup) for item in audits],
        "tariffs": get_runtime_tariffs(),
        "tariff_options": get_runtime_tariffs_list(),
        "docs": docs,
        "docs_settings": documentation_settings(),
        "managed_servers": [
            {
                "id": row.id,
                "name": row.name,
                "country_name": row.country_name,
                "status": row.status,
                "provider": row.provider,
                "public_ip": row.public_ip,
            }
            for row in await get_managed_servers()
        ],
        "payment_methods": {
            "telegram_stars": True,
            "sbp_platega": bool(config.enable_platega_sbp_user_flow),
            "crypto_platega": bool(config.enable_platega_crypto_user_flow),
            "sbp_manual": bool(config.enable_manual_sbp_user_flow),
            "crypto_manual": bool(config.enable_manual_crypto_user_flow),
            "crypto_bot": False,
        },
        "available_roles": [
            {"value": "owner", "label": ROLE_NAMES["owner"]},
            {"value": "tech_admin", "label": ROLE_NAMES["tech_admin"]},
            {"value": "support_admin", "label": ROLE_NAMES["support_admin"]},
        ],
        "admins": [
            {
                "id": admin.id,
                "display_name": admin.display_name,
                "username": admin.username,
                "role": admin.role,
                "role_name": ROLE_NAMES.get(admin.role, admin.role),
                "telegram_id": admin.telegram_id,
                "is_active": admin.is_active,
            }
            for admin in active_admins
        ],
        "role_matrix": role_matrix,
        "notification_profiles": [
            {
                **profile,
                "categories": [
                    {
                        "key": category,
                        "label": CATEGORY_LABELS.get(category, category),
                        "enabled": bool(profile.get("preferences", {}).get(category, True)),
                        "mandatory": is_notification_category_mandatory(str(profile.get("role") or ""), category),
                    }
                    for category in NOTIFICATION_CATEGORIES
                ],
            }
            for profile in notification_profiles
        ],
        "integrations": [
            {
                "key": "dashboard_api",
                "label": "Dashboard API",
                "status": "active",
                "description": "FastAPI backend для панели и control-center actions.",
            },
            {
                "key": "amonora_bot",
                "label": "@amonora_bot",
                "status": "active",
                "description": "Основной Telegram-first продуктовый контур для абонентов.",
            },
            {
                "key": "amonora_support_bot",
                "label": "@amonora_support_bot",
                "status": "active",
                "description": "Контур тикетов, истории обращений и reply-flow.",
            },
            {
                "key": "amonora_control_bot",
                "label": "@amonora_control_bot",
                "status": "active",
                "description": "Внутренние алерты, review ручных оплат и коды входа.",
            },
            {
                "key": "docs_repo",
                "label": "Knowledge / GitHub",
                "status": "active",
                "description": f"{documentation_settings()['owner']}/{documentation_settings()['repo']} · branch {documentation_settings()['branch']}",
            },
        ],
    }


async def get_v2_knowledge_payload(doc: str | None = None) -> dict:
    return {
        "docs": await get_documentation_page(doc),
        "docs_settings": documentation_settings(),
    }
