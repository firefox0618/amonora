from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import desc, select

from backend.core.database import async_session
from backend.core.models import ControlNotificationEvent
from backend.core.tracing import get_current_trace_id, normalize_trace_id
from bot.config import config
from bot.utils.access import utcnow
from control_bot.access import control_allowed_telegram_ids, control_delivery_chat_ids
from control_bot.storage import get_notification_preferences


logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "payments": "Платежи",
    "nodes": "Ноды и инфраструктура",
    "users": "Пользователи",
    "new_users": "Новые пользователи",
    "trials": "Пробный период",
    "access_keys": "Ключи и конфиги",
    "access": "Доступы / ключи",
    "support": "Поддержка",
    "security": "Безопасность",
    "panel_auth": "Безопасность",
    "errors": "Системные ошибки",
    "system": "Системные события",
}
SEVERITY_ICONS = {
    "INFO": "♦️",
    "WARNING": "⚠️",
    "CRITICAL": "🚨",
}
SEVERITY_LABELS = {
    "INFO": "INFO",
    "WARNING": "WARNING",
    "CRITICAL": "CRITICAL",
}
INFRA_EVENT_TYPES = {"node_offline", "node_degraded", "node_overloaded"}


def preference_category(category: str, event_type: str | None = None) -> str:
    normalized_event_type = str(event_type or "").strip().lower()
    if normalized_event_type == "new_user":
        return "new_users"
    if normalized_event_type == "trial_started":
        return "trials"
    if normalized_event_type in {
        "access_key_issued",
        "access_key_reissued",
        "access_config_issued",
        "access_config_reissued",
    }:
        return "access_keys"
    mapping = {
        "payments": "payments",
        "users": "users",
        "access": "users",
        "support": "support",
        "nodes": "nodes",
        "panel_auth": "security",
        "errors": "system",
        "system": "system",
    }
    return mapping.get(category, "system")


def _bool_enabled(value: bool) -> bool:
    return bool(value)


def control_category_enabled(category: str) -> bool:
    mapping = {
        "payments": _bool_enabled(config.control_enable_payments),
        "nodes": _bool_enabled(config.control_enable_nodes),
        "users": _bool_enabled(config.control_enable_users),
        "access": _bool_enabled(config.control_enable_access),
        "panel_auth": _bool_enabled(config.control_enable_panel_auth),
        "errors": _bool_enabled(config.control_enable_errors),
        "system": _bool_enabled(config.control_enable_system),
    }
    return mapping.get(category, True)


def _now_local_hour() -> int:
    return datetime.now().hour


def _night_hours() -> tuple[int, int] | None:
    raw = (config.control_night_hours or "").strip()
    if not raw or "-" not in raw:
        return None
    left, right = raw.split("-", 1)
    try:
        start = max(min(int(left), 23), 0)
        end = max(min(int(right), 23), 0)
    except ValueError:
        return None
    return start, end


def _is_night_window() -> bool:
    window = _night_hours()
    if window is None:
        return False
    hour = _now_local_hour()
    start, end = window
    if start <= end:
        return start <= hour <= end
    return hour >= start or hour <= end


def _should_skip_send_for_night_mode(severity: str) -> bool:
    if not config.control_night_critical_only:
        return False
    if severity == "CRITICAL":
        return False
    return _is_night_window()


def mask_login_code(code: str) -> str:
    raw = (code or "").strip()
    if len(raw) <= 2:
        return "••"
    if len(raw) <= 4:
        return f"{raw[:1]}{'•' * (len(raw) - 2)}{raw[-1:]}"
    return f"{raw[:2]}{'•' * (len(raw) - 4)}{raw[-2:]}"


def _compact_message(message: str) -> str:
    parts = [line.strip() for line in (message or "").splitlines() if line.strip()]
    if not parts:
        return ""
    return " • ".join(parts[:3])


def format_event_text(title: str, message: str, *, severity: str, category: str) -> str:
    severity_icon = SEVERITY_ICONS.get(severity, "ℹ️")
    category_label = CATEGORY_LABELS.get(category, category)
    compact_title = title.strip()
    compact_message = _compact_message(message)
    if compact_message:
        return f"{severity_icon} <b>{compact_title}</b>\n{compact_message}"
    return f"{severity_icon} <b>{compact_title}</b>\n{category_label}"


def _serialize_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _deliver_message(
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    chat_ids: list[int] | None = None,
    category: str | None = None,
    event_type: str | None = None,
) -> bool:
    token = config.control_bot_token
    if not token:
        logger.warning("Amonora Control delivery skipped: AMONORA_CONTROL_BOT_TOKEN is not configured")
        return False

    target_ids = control_allowed_telegram_ids()
    if category:
        preference_bucket = preference_category(category, event_type)
        filtered_ids: list[int] = []
        for telegram_id in target_ids:
            preferences = await get_notification_preferences(telegram_id)
            if preferences.get(preference_bucket, True):
                filtered_ids.append(telegram_id)
        target_ids = filtered_ids
    extra_chat_ids = control_delivery_chat_ids()
    if chat_ids:
        extra_chat_ids.extend(chat_ids)
    ordered_targets: list[int] = []
    seen: set[int] = set()
    for item in [*target_ids, *extra_chat_ids]:
        if item in seen:
            continue
        seen.add(item)
        ordered_targets.append(item)

    if not ordered_targets:
        return False

    bot = Bot(token=token)
    delivered = False
    try:
        for chat_id in ordered_targets:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )
                delivered = True
            except (TelegramForbiddenError, TelegramBadRequest):
                logger.warning("Failed to deliver control event to chat_id=%s", chat_id)
    finally:
        await bot.session.close()
    return delivered


async def create_control_event(
    *,
    category: str,
    severity: str,
    event_type: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    cooldown_seconds: int | None = None,
    resolve_dedupe_key: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    delivery_text: str | None = None,
    chat_ids: list[int] | None = None,
    request_id: str | None = None,
) -> ControlNotificationEvent | None:
    if not control_category_enabled(category):
        return None

    now = utcnow()
    normalized_severity = (severity or "INFO").upper()
    effective_payload = dict(payload or {})
    normalized_request_id = (
        normalize_trace_id(request_id)
        or normalize_trace_id(effective_payload.get("trace_id"))
        or normalize_trace_id(effective_payload.get("request_id"))
        or get_current_trace_id()
    )
    if normalized_request_id and "request_id" not in effective_payload:
        effective_payload["request_id"] = normalized_request_id
    effective_cooldown = cooldown_seconds
    if effective_cooldown is None:
        effective_cooldown = (
            config.control_infra_cooldown_seconds
            if event_type in INFRA_EVENT_TYPES or category == "nodes"
            else config.control_default_cooldown_seconds
        )

    async with async_session() as session:
        if resolve_dedupe_key:
            rows = list(
                (
                    await session.execute(
                        select(ControlNotificationEvent).where(
                            ControlNotificationEvent.dedupe_key == resolve_dedupe_key,
                            ControlNotificationEvent.resolved_at.is_(None),
                        )
                    )
                ).scalars().all()
            )
            for row in rows:
                row.resolved_at = now

        existing = None
        if dedupe_key:
            existing = (
                await session.execute(
                    select(ControlNotificationEvent)
                    .where(
                        ControlNotificationEvent.category == category,
                        ControlNotificationEvent.event_type == event_type,
                        ControlNotificationEvent.dedupe_key == dedupe_key,
                        ControlNotificationEvent.resolved_at.is_(None),
                    )
                    .order_by(desc(ControlNotificationEvent.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()

        if existing is None:
            event = ControlNotificationEvent(
                category=category[:50],
                severity=normalized_severity[:20],
                event_type=event_type[:100],
                title=title[:255],
                message=message,
                entity_type=entity_type[:100] if entity_type else None,
                entity_id=entity_id[:255] if entity_id else None,
                payload_json=_serialize_payload(effective_payload),
                request_id=normalized_request_id,
                dedupe_key=dedupe_key[:255] if dedupe_key else None,
                repeat_count=0,
            )
            session.add(event)
            await session.flush()
        else:
            event = existing
            event.severity = normalized_severity[:20]
            event.title = title[:255]
            event.message = message
            event.entity_type = entity_type[:100] if entity_type else event.entity_type
            event.entity_id = entity_id[:255] if entity_id else event.entity_id
            event.payload_json = _serialize_payload(effective_payload) or event.payload_json
            event.request_id = normalized_request_id or event.request_id
            event.repeat_count = int(event.repeat_count or 0) + 1

        should_send = not _should_skip_send_for_night_mode(normalized_severity)
        if existing is not None and existing.last_sent_at is not None and effective_cooldown > 0:
            seconds_since_last = (now - existing.last_sent_at).total_seconds()
            if seconds_since_last < effective_cooldown:
                should_send = False

        if should_send:
            delivered = await _deliver_message(
                text=delivery_text or format_event_text(title, message, severity=normalized_severity, category=category),
                reply_markup=reply_markup,
                chat_ids=chat_ids,
                category=category,
                event_type=event_type,
            )
            if delivered:
                event.last_sent_at = now

        await session.commit()
        await session.refresh(event)
        return event


async def send_panel_auth_code(
    *,
    admin_username: str,
    telegram_id: int,
    code: str,
    ttl_minutes: int = 5,
) -> tuple[int | None, str]:
    token = config.control_bot_token
    if not token:
        raise RuntimeError("AMONORA_CONTROL_BOT_TOKEN is not configured")

    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    delivery_text = (
        f"♦️Код: <tg-spoiler>{code}</tg-spoiler>"
    )
    bot = Bot(token)
    try:
        message = await bot.send_message(
            chat_id=telegram_id,
            text=delivery_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    finally:
        await bot.session.close()

    await create_control_event(
        category="panel_auth",
        severity="INFO",
        event_type="login_code_requested",
        title="Код входа в панель",
        message=f"{admin_username} → <code>{mask_login_code(code)}</code> ({ttl_minutes} мин)\nПанель управления · {sent_at}",
        entity_type="dashboard_admin",
        entity_id=str(telegram_id),
        payload={
            "admin_username": admin_username,
            "telegram_id": telegram_id,
            "masked_code": mask_login_code(code),
            "ttl_minutes": ttl_minutes,
            "sent_at": sent_at,
        },
        dedupe_key=f"login-code:{telegram_id}",
        cooldown_seconds=0,
        delivery_text=None,
    )
    return message.message_id, "control"


async def delete_control_message(telegram_id: int | None, message_id: int | None) -> None:
    if not telegram_id or not message_id or not config.control_bot_token:
        return
    bot = Bot(config.control_bot_token)
    try:
        await bot.delete_message(telegram_id, message_id)
    except Exception:
        logger.debug("Failed to delete control bot message telegram_id=%s message_id=%s", telegram_id, message_id)
    finally:
        await bot.session.close()


async def list_control_events(
    *,
    category: str | None = None,
    severities: set[str] | None = None,
    limit: int = 20,
    unresolved_only: bool = False,
    event_type: str | None = None,
) -> list[ControlNotificationEvent]:
    async with async_session() as session:
        query = select(ControlNotificationEvent).order_by(
            ControlNotificationEvent.created_at.desc(),
            ControlNotificationEvent.id.desc(),
        )
        if category is not None:
            query = query.where(ControlNotificationEvent.category == category)
        if severities:
            query = query.where(ControlNotificationEvent.severity.in_(sorted(severities)))
        if unresolved_only:
            query = query.where(ControlNotificationEvent.resolved_at.is_(None))
        if event_type is not None:
            query = query.where(ControlNotificationEvent.event_type == event_type)
        query = query.limit(limit)
        return list((await session.execute(query)).scalars().all())


async def get_unresolved_event_count(*, severities: set[str] | None = None) -> int:
    rows = await list_control_events(severities=severities, limit=200, unresolved_only=True)
    return len(rows)


def event_payload(event: ControlNotificationEvent) -> dict[str, Any]:
    payload = _deserialize_payload(event.payload_json)
    request_id = str(getattr(event, "request_id", "") or "").strip()
    if request_id and "request_id" not in payload:
        payload["request_id"] = request_id
    return payload
