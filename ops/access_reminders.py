from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, or_, select

from backend.core.analytics import EVENT_SUBSCRIPTION_EXPIRED, safe_emit_analytics_event
from backend.core.database import async_session
from backend.core.models import ControlTriggerRule, User, VpnClient
from backend.core.schema import ensure_schema
from backend.core.synthetic_users import (
    is_synthetic_user as shared_is_synthetic_user,
    real_user_sql_clause as shared_real_user_sql_clause,
)
from bot.config import config
from bot.device_compensation import process_pending_device_compensation_jobs
from bot.db import (
    clear_vpn_repair_needed,
    delete_landing_bridge_user_if_unused,
    delete_vpn_client,
    expire_device_slot_entitlements,
    get_active_device_slot_counts_for_users,
    get_user_vpn_clients,
    pause_trial_for_channel_unsubscribe,
    resume_trial_after_channel_resubscribe,
)
from bot.payment_flow import reconcile_confirmed_payment_records, sync_user_vpn_access, sync_user_vpn_access_with_single_retry
from bot.keyboards.tariffs import tariffs_keyboard
from bot.utils.access import (
    VIP_SUBSCRIPTION_SOURCES,
    get_access_expires_at_from_user,
    get_device_limit_for_user,
    get_trial_activity_level_from_user,
    is_admin_telegram_id,
    utcnow,
)
from bot.utils.tariffs import PROMO_DATE_RANGE_LABEL, promo_active, promo_tariff_offer_block
from bot.utils.logging_setup import configure_logging
from bot.utils.subscription import is_user_subscribed
from bot.utils.texts import (
    no_access_reminder_text,
    CHANNEL_URL,
    trial_ends_today_reminder_text,
    trial_channel_pause_notice_text,
    trial_channel_resume_notice_text,
    trial_expired_reminder_text,
)
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import get_vless_provisioner
from control_bot.messaging import dispatch_campaign, process_pending_campaigns
from control_bot.storage import (
    CAMPAIGN_SCOPE_TRIGGER,
    create_broadcast_campaign,
    has_trigger_delivery,
    list_trigger_rules,
    register_trigger_delivery_log,
    serialize_template_buttons,
)
from ops.control_error_triggers import emit_control_error_triggers


logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent / "state" / "access_reminders_state.json"
UTC_ZONE = ZoneInfo("UTC")
REMINDER_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")
NO_ACCESS_COOLDOWN = timedelta(days=3)
TELEGRAM_DELIVERY_BACKOFF = timedelta(hours=24)
REPAIR_RECOVERY_COOLDOWN = timedelta(hours=1)
STATEFUL_STAGE_NAMES = frozenset(
    {
        "trial_channel",
        "revocations",
        "purges",
        "bridge_purges",
        "repair_recovery",
    }
)


def _trial_channel_notice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📡 Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="🤖 Открыть Amonora Bot", url="https://t.me/amonora_bot")],
        ]
    )


async def _send_notification_via_bot(
    bot: Bot,
    telegram_id: int,
    text: str,
    *,
    reply_markup=None,
) -> str:
    try:
        await bot.send_message(
            chat_id=int(telegram_id),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return "sent"
    except TelegramForbiddenError:
        logger.info("User notification suppressed: telegram_id=%s result=forbidden", telegram_id)
        return "forbidden"
    except TelegramBadRequest:
        logger.info("User notification suppressed: telegram_id=%s result=bad_request", telegram_id)
        return "bad_request"


async def _send_trial_channel_pause_notice(bot: Bot, user: User) -> str:
    telegram_id = getattr(user, "telegram_id", None)
    trial_expires_at = getattr(user, "trial_expires_at", None)
    if not telegram_id or trial_expires_at is None:
        return "skipped"
    return await _send_notification_via_bot(
        bot,
        int(telegram_id),
        trial_channel_pause_notice_text(trial_expires_at.strftime("%Y-%m-%d %H:%M:%S")),
        reply_markup=_trial_channel_notice_keyboard(),
    )


async def _send_trial_channel_resume_notice(bot: Bot, user: User) -> str:
    telegram_id = getattr(user, "telegram_id", None)
    trial_expires_at = getattr(user, "trial_expires_at", None)
    if not telegram_id or trial_expires_at is None:
        return "skipped"
    return await _send_notification_via_bot(
        bot,
        int(telegram_id),
        trial_channel_resume_notice_text(trial_expires_at.strftime("%Y-%m-%d %H:%M:%S")),
    )


def _empty_state() -> dict:
    return {"events": {}}


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return _empty_state()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_state()
    if not isinstance(payload, dict):
        return _empty_state()
    payload.setdefault("events", {})
    return payload


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_event_state(state: dict, telegram_id: int, event_key: str) -> dict:
    events = state.setdefault("events", {})
    user_events = events.setdefault(str(telegram_id), {})
    return user_events.setdefault(event_key, {})


def _get_event_state(state: dict, telegram_id: int, event_key: str) -> dict:
    events = state.get("events", {})
    user_events = events.get(str(telegram_id), {})
    current = user_events.get(event_key)
    return current if isinstance(current, dict) else {}


def _notification_backoff_active(event_state: dict, now_utc: datetime) -> bool:
    result = str(event_state.get("last_result") or "").strip().lower()
    if result not in {"forbidden", "bad_request"}:
        return False
    last_attempt = _parse_timestamp(event_state.get("last_attempt_at"))
    if last_attempt is None:
        return False
    return now_utc - last_attempt < TELEGRAM_DELIVERY_BACKOFF


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC_ZONE).replace(tzinfo=None)


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _normalize_utc_datetime(parsed)


def _to_local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC_ZONE).astimezone(REMINDER_TIMEZONE)
    return value.astimezone(REMINDER_TIMEZONE)


def _local_date(value: datetime) -> date:
    return _to_local_datetime(value).date()


def _is_synthetic_user(user: User) -> bool:
    return shared_is_synthetic_user(user)


def _has_active_trial(user: User, now_utc: datetime) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    trial_expires_at = getattr(user, "trial_expires_at", None)
    if not trial_expires_at or trial_expires_at <= now_utc:
        return False
    if getattr(user, "trial_channel_unsubscribed_at", None) is not None and not _has_active_subscription(user, now_utc):
        return False
    return True


def _has_active_subscription(user: User, now_utc: datetime) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    subscription_expires_at = getattr(user, "subscription_expires_at", None)
    return (
        getattr(user, "subscription_status", "inactive") == "active"
        and subscription_expires_at is not None
        and subscription_expires_at > now_utc
    )


def _has_vip_access(user: User, now_utc: datetime) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    telegram_id = getattr(user, "telegram_id", None)
    if is_admin_telegram_id(telegram_id):
        return True
    return _has_active_subscription(user, now_utc) and (getattr(user, "subscription_source", None) or "") in VIP_SUBSCRIPTION_SOURCES


def _trial_is_paused_by_channel(user: User, now_utc: datetime) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    trial_expires_at = getattr(user, "trial_expires_at", None)
    if trial_expires_at is None or trial_expires_at <= now_utc:
        return False
    if _has_active_subscription(user, now_utc):
        return False
    return getattr(user, "trial_channel_unsubscribed_at", None) is not None


def _access_status(user: User, now_utc: datetime) -> str:
    if getattr(user, "is_blocked", False):
        return "blocked"
    if _has_vip_access(user, now_utc):
        return "vip_active"
    if _has_active_subscription(user, now_utc):
        return "paid_active"
    if _has_active_trial(user, now_utc):
        return "trial_active"
    if getattr(user, "trial_used", False) or getattr(user, "subscription_expires_at", None) is not None:
        return "expired"
    return "inactive"


def _trigger_template_body(rule: ControlTriggerRule) -> str:
    if not promo_active():
        return rule.template_body
    if rule.key == "trial_ends_1d":
        return (
            "🎁 Пробный доступ заканчивается завтра.\n\n"
            f"Только {PROMO_DATE_RANGE_LABEL} можно подключить тариф с бонусными месяцами:\n"
            f"{promo_tariff_offer_block()}\n\n"
            "Откройте тарифы и зафиксируйте выгодные условия."
        )
    if rule.key == "trial_ends_today":
        return (
            "⏳ Пробный доступ заканчивается сегодня.\n\n"
            f"Только {PROMO_DATE_RANGE_LABEL} можно подключить тариф с подарочными месяцами:\n"
            f"{promo_tariff_offer_block(include_gift_wording=False)}\n\n"
            "Продлите доступ сейчас, чтобы не потерять подключение и забрать бонус."
        )
    if rule.key == "trial_expired_3d":
        return (
            "🔒 Пробный доступ уже завершился.\n\n"
            f"Акция с бонусными месяцами действует только {PROMO_DATE_RANGE_LABEL}:\n"
            f"{promo_tariff_offer_block()}\n\n"
            "Откройте тарифы, чтобы вернуть доступ сразу после оплаты."
        )
    return rule.template_body


def _revocation_marker_for_user(user: User, now_utc: datetime) -> str | None:
    if getattr(user, "is_blocked", False):
        return None

    status = _access_status(user, now_utc)
    if status != "expired":
        return None

    if getattr(user, "subscription_expires_at", None) is not None:
        return f"subscription:{user.subscription_expires_at.isoformat()}"
    if getattr(user, "trial_expires_at", None) is not None:
        return f"trial:{user.trial_expires_at.isoformat()}"
    return None


def _trial_device_purge_marker_for_user(user: User, now_utc: datetime) -> str | None:
    if getattr(user, "is_blocked", False):
        return None
    if not getattr(user, "trial_used", False):
        return None

    trial_expires_at = getattr(user, "trial_expires_at", None)
    if trial_expires_at is None or trial_expires_at > now_utc:
        return None

    if getattr(user, "subscription_status", "inactive") == "active":
        return None
    if getattr(user, "subscription_expires_at", None) is not None:
        return None

    return f"trial-only:{trial_expires_at.isoformat()}"


def _bridge_access_purge_marker_for_user(user: User, now_utc: datetime) -> str | None:
    if getattr(user, "is_blocked", False):
        return None
    username = (getattr(user, "username", None) or "").strip().lower()
    if not username.startswith("bridge_"):
        return None

    expires_at = getattr(user, "subscription_expires_at", None)
    if expires_at is None or expires_at > now_utc:
        return None

    return f"bridge-expired:{expires_at.isoformat()}"


def _trial_channel_enforcement_marker(user: User, *, subscribed: bool, now_utc: datetime) -> str | None:
    if getattr(user, "is_blocked", False):
        return None
    if _has_active_subscription(user, now_utc):
        return None

    trial_expires_at = getattr(user, "trial_expires_at", None)
    if trial_expires_at is None or trial_expires_at <= now_utc:
        return None
    if subscribed:
        return f"active:{trial_expires_at.isoformat()}"
    unsubscribed_at = getattr(user, "trial_channel_unsubscribed_at", None)
    marker = unsubscribed_at.isoformat() if unsubscribed_at else "pending"
    return f"paused:{marker}:{trial_expires_at.isoformat()}"


def _event_was_sent_today(state: dict, telegram_id: int, event_key: str, current_local_date: date) -> bool:
    event_state = _get_event_state(state, telegram_id, event_key)
    return event_state.get("last_sent_local_date") == current_local_date.isoformat()


def _event_was_sent_before(state: dict, telegram_id: int, event_key: str) -> bool:
    event_state = _get_event_state(state, telegram_id, event_key)
    return bool(event_state.get("last_sent_at"))


def _latest_event_attempt_at(state: dict, telegram_id: int, event_keys: tuple[str, ...]) -> datetime | None:
    timestamps = []
    for event_key in event_keys:
        event_state = _get_event_state(state, telegram_id, event_key)
        parsed = _parse_timestamp(event_state.get("last_sent_at"))
        if parsed is not None:
            timestamps.append(parsed)
    if not timestamps:
        return None
    return max(timestamps)


def _no_access_due(state: dict, telegram_id: int, now_utc: datetime) -> bool:
    last_sent_at = _latest_event_attempt_at(state, telegram_id, ("trial_expired", "no_access"))
    if last_sent_at is None:
        return True
    return now_utc - last_sent_at >= NO_ACCESS_COOLDOWN


def classify_access_reminder(user: User, state: dict, now_utc: datetime | None = None) -> str | None:
    now_utc = _normalize_utc_datetime(now_utc or utcnow())
    telegram_id = getattr(user, "telegram_id", None)
    if telegram_id is None or _is_synthetic_user(user):
        return None

    status = _access_status(user, now_utc)
    if status in {"blocked", "vip_active", "paid_active"}:
        return None

    current_local_date = _local_date(now_utc)
    if (
        _has_active_trial(user, now_utc)
        and not _has_active_subscription(user, now_utc)
        and getattr(user, "trial_expires_at", None) is not None
        and _local_date(user.trial_expires_at) == current_local_date
    ):
        if _event_was_sent_today(state, telegram_id, "trial_ends_today", current_local_date):
            return None
        return "trial_ends_today"

    if (
        getattr(user, "trial_used", False)
        and not _has_active_trial(user, now_utc)
        and not _has_active_subscription(user, now_utc)
        and not _event_was_sent_before(state, telegram_id, "trial_expired")
    ):
        return "trial_expired"

    if status in {"inactive", "expired"} and _no_access_due(state, telegram_id, now_utc):
        return "no_access"

    return None


def reminder_text_for_event(event_key: str) -> str:
    if event_key == "trial_ends_today":
        return trial_ends_today_reminder_text()
    if event_key == "trial_expired":
        return trial_expired_reminder_text()
    if event_key == "no_access":
        return no_access_reminder_text()
    raise ValueError(f"Unsupported reminder event: {event_key}")


def record_delivery_result(
    state: dict,
    telegram_id: int,
    event_key: str,
    *,
    result: str,
    now_utc: datetime | None = None,
) -> None:
    now_utc = _normalize_utc_datetime(now_utc or utcnow())
    event_state = _ensure_event_state(state, telegram_id, event_key)
    event_state["last_sent_at"] = now_utc.isoformat()
    event_state["last_sent_local_date"] = _local_date(now_utc).isoformat()
    event_state["last_result"] = result


async def _deliver_reminder(bot: Bot, telegram_id: int, event_key: str) -> str:
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=reminder_text_for_event(event_key),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=tariffs_keyboard(),
        )
        return "sent"
    except TelegramForbiddenError:
        logger.info("Reminder delivery suppressed: telegram_id=%s event=%s result=forbidden", telegram_id, event_key)
        return "forbidden"
    except TelegramBadRequest:
        logger.info("Reminder delivery suppressed: telegram_id=%s event=%s result=bad_request", telegram_id, event_key)
        return "bad_request"


def _build_users_query(
    *,
    include_synthetic: bool = False,
    require_telegram: bool = False,
    only_trial_users: bool = False,
    only_access_candidates: bool = False,
    only_repair_needed: bool = False,
):
    query = select(User)
    if not include_synthetic:
        query = query.where(shared_real_user_sql_clause(User))
    if require_telegram:
        query = query.where(User.telegram_id.is_not(None))
    if only_trial_users:
        query = query.where(User.trial_expires_at.is_not(None))
    if only_access_candidates:
        query = query.where(
            or_(
                User.trial_expires_at.is_not(None),
                User.subscription_expires_at.is_not(None),
            )
        )
    if only_repair_needed:
        query = query.where(User.vpn_repair_needed.is_(True))
    return query


def _build_expired_bridge_users_query():
    return select(User).where(
        func.lower(func.coalesce(User.username, "")).like("bridge_%"),
        User.subscription_expires_at.is_not(None),
    )


async def _load_users(
    *,
    include_synthetic: bool = False,
    require_telegram: bool = False,
    only_trial_users: bool = False,
    only_access_candidates: bool = False,
    only_repair_needed: bool = False,
) -> list[User]:
    async with async_session() as session:
        query = _build_users_query(
            include_synthetic=include_synthetic,
            require_telegram=require_telegram,
            only_trial_users=only_trial_users,
            only_access_candidates=only_access_candidates,
            only_repair_needed=only_repair_needed,
        )
        return list((await session.execute(query)).scalars().all())


async def _load_expired_bridge_users() -> list[User]:
    async with async_session() as session:
        return list((await session.execute(_build_expired_bridge_users_query())).scalars().all())


async def _load_device_counts(user_ids: list[int] | None = None) -> dict[int, int]:
    async with async_session() as session:
        query = select(VpnClient.user_id)
        normalized_user_ids = sorted({int(user_id) for user_id in user_ids or [] if user_id is not None})
        if normalized_user_ids:
            query = query.where(VpnClient.user_id.in_(normalized_user_ids))
        rows = list((await session.execute(query)).scalars().all())
    counts: dict[int, int] = {}
    for user_id in rows:
        if user_id is None:
            continue
        counts[int(user_id)] = counts.get(int(user_id), 0) + 1
    return counts


def _trigger_config(rule: ControlTriggerRule) -> dict:
    try:
        value = json.loads(rule.config_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _send_hour_matches(config_payload: dict, now_utc: datetime) -> bool:
    send_hour = config_payload.get("send_hour")
    if send_hour is None:
        return True
    try:
        expected_hour = int(send_hour)
    except (TypeError, ValueError):
        return True
    return _to_local_datetime(now_utc).hour == expected_hour


def _local_days_until(target: datetime, now_utc: datetime) -> int:
    return (_local_date(target) - _local_date(now_utc)).days


def _hours_since(moment: datetime, now_utc: datetime) -> float:
    return max(0.0, (now_utc - moment).total_seconds() / 3600)


def _hours_until(moment: datetime, now_utc: datetime) -> float:
    return (moment - now_utc).total_seconds() / 3600


def _trigger_match_for_user(
    rule: ControlTriggerRule,
    user: User,
    *,
    device_count: int,
    now_utc: datetime,
) -> tuple[bool, str | None]:
    if getattr(user, "telegram_id", None) is None or _is_synthetic_user(user):
        return False, None

    config_payload = _trigger_config(rule)
    if not _send_hour_matches(config_payload, now_utc):
        return False, None

    status = _access_status(user, now_utc)
    last_activity = getattr(user, "last_activity_at", None) or user.created_at
    kind = (config_payload.get("kind") or "").strip()

    if kind == "days_before":
        trial_expires_at = getattr(user, "trial_expires_at", None)
        if status != "trial_active" or trial_expires_at is None:
            return False, None
        days = int(config_payload.get("days", 0))
        if _local_days_until(trial_expires_at, now_utc) != days:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{_local_date(trial_expires_at).isoformat()}"

    if kind == "trial_hours_since_start":
        trial_started_at = getattr(user, "trial_started_at", None)
        if status != "trial_active" or trial_started_at is None:
            return False, None
        segment = str(config_payload.get("segment", "") or "").strip().lower()
        if segment and get_trial_activity_level_from_user(user) != segment:
            return False, None
        hours = int(config_payload.get("hours", 0))
        if _hours_since(trial_started_at, now_utc) < hours:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{trial_started_at.isoformat()}"

    if kind == "trial_hours_before_expiry":
        trial_expires_at = getattr(user, "trial_expires_at", None)
        if status != "trial_active" or trial_expires_at is None:
            return False, None
        segment = str(config_payload.get("segment", "") or "").strip().lower()
        if segment and get_trial_activity_level_from_user(user) != segment:
            return False, None
        hours = int(config_payload.get("hours", 0))
        hours_until = _hours_until(trial_expires_at, now_utc)
        if hours_until < 0 or hours_until > hours:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{trial_expires_at.isoformat()}"

    if kind == "days_after_trial_expiry":
        trial_expires_at = getattr(user, "trial_expires_at", None)
        if trial_expires_at is None or status not in {"expired", "inactive"}:
            return False, None
        days = int(config_payload.get("days", 0))
        if (_local_date(now_utc) - _local_date(trial_expires_at)).days != days:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{_local_date(trial_expires_at).isoformat()}"

    if kind == "inactive_days":
        days = int(config_payload.get("days", 0))
        if last_activity > now_utc - timedelta(days=days):
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{last_activity.date().isoformat()}"

    if kind == "start_no_action_hours":
        hours = int(config_payload.get("hours", 0))
        if status != "inactive":
            return False, None
        if getattr(user, "trial_used", False) or getattr(user, "subscription_expires_at", None) is not None:
            return False, None
        if device_count > 0:
            return False, None
        if now_utc < user.created_at + timedelta(hours=hours):
            return False, None
        if last_activity > user.created_at + timedelta(minutes=5):
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{user.created_at.isoformat()}"

    if kind == "days_before_access_expiry":
        subscription_expires_at = getattr(user, "subscription_expires_at", None)
        if status not in {"paid_active", "vip_active"} or subscription_expires_at is None:
            return False, None
        days = int(config_payload.get("days", 0))
        if _local_days_until(subscription_expires_at, now_utc) != days:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{_local_date(subscription_expires_at).isoformat()}"

    if kind == "device_limit":
        limit = get_device_limit_for_user(user)
        if device_count < limit:
            return False, None
        return True, f"trigger:{rule.key}:{user.id}:{device_count}:{_local_date(now_utc).isoformat()}"

    if kind == "access_issue":
        if not bool(getattr(user, "vpn_repair_needed", False)):
            return False, None
        marker = getattr(user, "vpn_repair_marked_at", None) or _local_date(now_utc)
        marker_value = marker.isoformat() if hasattr(marker, "isoformat") else str(marker)
        return True, f"trigger:{rule.key}:{user.id}:{marker_value}"

    return False, None


async def _dispatch_trigger_campaign(
    rule: ControlTriggerRule,
    user: User,
    *,
    dedupe_key: str,
) -> str:
    campaign = await create_broadcast_campaign(
        scope=CAMPAIGN_SCOPE_TRIGGER,
        name=rule.title,
        audience_key=rule.key,
        message_body=_trigger_template_body(rule),
        buttons=serialize_template_buttons(rule),
        metadata={
            "source": "amonora_access_reminders",
            "trigger_rule_id": rule.id,
            "trigger_key": rule.key,
            "recipients": [{"user_id": user.id, "telegram_id": int(user.telegram_id)}],
        },
        created_by_telegram_id=None,
        priority_label="medium",
        trigger_rule_id=rule.id,
        status="queued",
    )
    result = await dispatch_campaign(campaign.id)
    delivery_result = "sent" if result["sent"] > 0 else ("failed" if result["failed"] > 0 else "skipped")
    await register_trigger_delivery_log(
        trigger_rule_id=rule.id,
        campaign_id=campaign.id,
        user_id=user.id,
        telegram_id=int(user.telegram_id),
        event_key=rule.key,
        dedupe_key=dedupe_key,
        result=delivery_result,
    )
    if delivery_result != "sent":
        logger.info(
            "Trigger delivery issue suppressed from control notifications: rule_id=%s rule_key=%s user_id=%s telegram_id=%s result=%s",
            rule.id,
            rule.key,
            user.id,
            user.telegram_id,
            delivery_result,
        )
    return delivery_result


async def _process_trigger_rules(now_utc: datetime) -> dict[str, int]:
    users = await _load_users(require_telegram=True)
    device_counts = await _load_device_counts([int(getattr(user, "id", 0) or 0) for user in users])
    extra_slot_counts = await get_active_device_slot_counts_for_users([int(getattr(user, "id", 0) or 0) for user in users])
    for user in users:
        setattr(user, "active_device_slot_addons", int(extra_slot_counts.get(int(getattr(user, "id", 0) or 0), 0)))
    rules = [row for row in await list_trigger_rules() if row.enabled]
    processed = 0
    sent = 0
    failed = 0

    for rule in rules:
        for user in users:
            matches, dedupe_key = _trigger_match_for_user(
                rule,
                user,
                device_count=device_counts.get(int(getattr(user, "id", 0) or 0), 0),
                now_utc=now_utc,
            )
            if not matches or not dedupe_key:
                continue
            if await has_trigger_delivery(dedupe_key):
                continue
            processed += 1
            result = await _dispatch_trigger_campaign(rule, user, dedupe_key=dedupe_key)
            if result == "sent":
                sent += 1
            elif result == "failed":
                failed += 1
    return {"processed": processed, "sent": sent, "failed": failed}


async def _revoke_expired_vpn_access(state: dict, now_utc: datetime) -> dict[str, int]:
    users = await _load_users(only_access_candidates=True)
    processed = 0
    revoked = 0
    failed = 0

    for user in users:
        marker = _revocation_marker_for_user(user, now_utc)
        if marker is None:
            continue

        event_state = _get_event_state(state, int(user.id), "vpn_access_revoked")
        if event_state.get("marker") == marker and event_state.get("last_result") == "success":
            continue

        processed += 1
        sync_failed = await sync_user_vpn_access(int(user.id), None)

        current_state = _ensure_event_state(state, int(user.id), "vpn_access_revoked")
        current_state["marker"] = marker
        current_state["last_attempt_at"] = now_utc.isoformat()
        current_state["last_result"] = "failed" if sync_failed else "success"

        if sync_failed:
            failed += 1
        else:
            revoked += 1
            if marker.startswith("subscription:"):
                await safe_emit_analytics_event(
                    event_name=EVENT_SUBSCRIPTION_EXPIRED,
                    occurred_at=now_utc,
                    user_id=int(user.id),
                    telegram_id=getattr(user, "telegram_id", None),
                    dedupe_key=f"subscription-expired:{int(user.id)}:{marker}",
                    payload={
                        "subscription_expires_at": getattr(user, "subscription_expires_at", None).isoformat()
                        if getattr(user, "subscription_expires_at", None) is not None
                        else None,
                    },
                )

    return {"processed": processed, "revoked": revoked, "failed": failed}


async def _recover_vpn_repair_needed_users(state: dict, now_utc: datetime, *, limit: int = 10) -> dict[str, int]:
    users = await _load_users(only_repair_needed=True)
    checked = 0
    recovered = 0
    failed = 0
    skipped = 0
    safe_limit = max(int(limit or 0), 1)

    for user in users:
        if checked >= safe_limit:
            break
        if _is_synthetic_user(user) or not bool(getattr(user, "vpn_repair_needed", False)):
            continue
        access_expires_at = get_access_expires_at_from_user(user)
        if access_expires_at is None:
            skipped += 1
            continue
        devices = await get_user_vpn_clients(int(user.id))
        if not devices:
            skipped += 1
            continue

        marker = getattr(user, "vpn_repair_marked_at", None) or access_expires_at
        marker_value = marker.isoformat() if hasattr(marker, "isoformat") else str(marker)
        event_state = _get_event_state(state, int(user.id), "vpn_repair_recovery")
        last_attempt_at = _parse_timestamp(event_state.get("last_attempt_at"))
        if (
            event_state.get("marker") == marker_value
            and last_attempt_at is not None
            and now_utc - last_attempt_at < REPAIR_RECOVERY_COOLDOWN
        ):
            continue

        checked += 1
        sync_result = await sync_user_vpn_access_with_single_retry(int(user.id), access_expires_at)
        current_state = _ensure_event_state(state, int(user.id), "vpn_repair_recovery")
        current_state["marker"] = marker_value
        current_state["last_attempt_at"] = now_utc.isoformat()
        current_state["last_result"] = "failed" if sync_result["sync_failed"] else "success"

        if sync_result["sync_failed"]:
            failed += 1
            continue

        await clear_vpn_repair_needed(int(user.id))
        recovered += 1

    return {
        "checked": checked,
        "recovered": recovered,
        "failed": failed,
        "skipped": skipped,
    }


async def _purge_expired_trial_device(device: VpnClient) -> bool:
    try:
        metadata = json.loads(device.client_data or "{}") if device.client_data else {}
    except json.JSONDecodeError:
        metadata = {}

    country_code = metadata.get("country_code") or "de"
    client_uuid = device.xui_client_id or device.client_uuid

    try:
        if device.protocol == "vless":
            provisioner = get_vless_provisioner(country_code, metadata.get("provider_type"))
            try:
                await provisioner.delete_vless_client(
                    client_uuid=client_uuid,
                    email=device.email,
                    metadata=metadata,
                )
            finally:
                await provisioner.close()
        elif device.protocol == "trojan":
            xui_client = XUIClient(country_code=country_code)
            try:
                success = await xui_client.login()
                if not success:
                    return False
                await xui_client.delete_trojan_client(
                    inbound_id=int(metadata.get("inbound_id") or 0),
                    client_uuid=client_uuid,
                    email=device.email,
                )
            finally:
                await xui_client.close()
        else:
            logger.warning("Unsupported protocol during expired trial purge device_id=%s protocol=%s", device.id, device.protocol)
            return False
    except Exception:
        logger.exception("Failed to purge expired trial remote device state device_id=%s user_id=%s", device.id, device.user_id)
        return False

    deleted = await delete_vpn_client(int(device.id))
    if not deleted:
        logger.warning("Expired trial device disappeared before DB purge device_id=%s user_id=%s", device.id, device.user_id)
    return deleted


async def _purge_expired_trial_vpn_access(state: dict, now_utc: datetime) -> dict[str, int]:
    users = await _load_users(only_trial_users=True)
    processed = 0
    purged = 0
    failed = 0

    for user in users:
        marker = _trial_device_purge_marker_for_user(user, now_utc)
        if marker is None:
            continue

        devices = await get_user_vpn_clients(int(user.id))
        event_state = _get_event_state(state, int(user.id), "trial_devices_purged")
        if not devices:
            if event_state.get("marker") != marker or event_state.get("last_result") != "success":
                current_state = _ensure_event_state(state, int(user.id), "trial_devices_purged")
                current_state["marker"] = marker
                current_state["last_attempt_at"] = now_utc.isoformat()
                current_state["last_result"] = "success"
                current_state["last_purged_count"] = 0
            continue

        processed += len(devices)
        current_state = _ensure_event_state(state, int(user.id), "trial_devices_purged")
        current_state["marker"] = marker
        current_state["last_attempt_at"] = now_utc.isoformat()

        user_failures = 0
        user_purged = 0
        for device in devices:
            deleted = await _purge_expired_trial_device(device)
            if deleted:
                purged += 1
                user_purged += 1
            else:
                failed += 1
                user_failures += 1

        current_state["last_purged_count"] = user_purged
        current_state["last_result"] = "failed" if user_failures else "success"

    return {"processed": processed, "purged": purged, "failed": failed}


async def _purge_expired_bridge_access(state: dict, now_utc: datetime) -> dict[str, int]:
    users = await _load_expired_bridge_users()
    processed = 0
    purged = 0
    deleted_users = 0
    failed = 0

    for user in users:
        marker = _bridge_access_purge_marker_for_user(user, now_utc)
        if marker is None:
            continue

        current_state = _ensure_event_state(state, int(user.id), "bridge_access_purged")
        if current_state.get("marker") == marker and current_state.get("last_result") == "success":
            continue

        devices = await get_user_vpn_clients(int(user.id))
        processed += len(devices)
        current_state["marker"] = marker
        current_state["last_attempt_at"] = now_utc.isoformat()

        user_failures = 0
        user_purged = 0
        for device in devices:
            deleted = await _purge_expired_trial_device(device)
            if deleted:
                purged += 1
                user_purged += 1
            else:
                failed += 1
                user_failures += 1

        current_state["last_purged_count"] = user_purged
        if user_failures:
            current_state["last_result"] = "failed"
            continue

        deleted_user = await delete_landing_bridge_user_if_unused(int(user.id))
        if deleted_user:
            deleted_users += 1
        else:
            remaining_devices = await get_user_vpn_clients(int(user.id))
            if remaining_devices:
                failed += 1
                current_state["last_result"] = "failed"
                continue
        current_state["last_result"] = "success"

    return {
        "processed": processed,
        "purged": purged,
        "deleted_users": deleted_users,
        "failed": failed,
    }


async def _enforce_trial_channel_membership(state: dict, now_utc: datetime) -> dict[str, int]:
    channel_id = str(getattr(config, "channel_id", "") or "").strip()
    token = str(getattr(config, "bot_token", "") or "").strip()
    if not channel_id or not token:
        return {"checked": 0, "paused": 0, "resumed": 0, "notified": 0, "suppressed": 0, "failed": 0}
    users = await _load_users(require_telegram=True, only_trial_users=True)
    candidates = [
        user
        for user in users
        if getattr(user, "telegram_id", None) is not None
        and not _is_synthetic_user(user)
        and getattr(user, "trial_expires_at", None) is not None
        and getattr(user, "trial_expires_at") > now_utc
        and not _has_active_subscription(user, now_utc)
    ]
    if not candidates:
        return {"checked": 0, "paused": 0, "resumed": 0, "notified": 0, "suppressed": 0, "failed": 0}

    checked = 0
    paused = 0
    resumed = 0
    notified = 0
    suppressed = 0
    failed = 0
    bot = Bot(token=token)
    try:
        for user in candidates:
            checked += 1
            try:
                subscribed = await is_user_subscribed(bot, channel_id, int(user.telegram_id))
            except Exception:
                logger.exception("Failed to resolve trial channel membership for user_id=%s telegram_id=%s", user.id, user.telegram_id)
                failed += 1
                continue

            event_state = _get_event_state(state, int(user.id), "trial_channel_membership")
            marker = _trial_channel_enforcement_marker(user, subscribed=subscribed, now_utc=now_utc)

            current_state = _ensure_event_state(state, int(user.id), "trial_channel_membership")
            current_state["last_checked_at"] = now_utc.isoformat()
            notice_state = _ensure_event_state(state, int(user.id), "trial_channel_membership_notice")

            if subscribed:
                if _trial_is_paused_by_channel(user, now_utc):
                    resumed_user = await resume_trial_after_channel_resubscribe(int(user.id))
                    access_expires_at = getattr(resumed_user, "trial_expires_at", None) if resumed_user is not None else None
                    sync_result = await sync_user_vpn_access_with_single_retry(int(user.id), access_expires_at)
                    current_state["marker"] = _trial_channel_enforcement_marker(
                        resumed_user or user,
                        subscribed=True,
                        now_utc=now_utc,
                    )
                    current_state["last_result"] = "failed" if sync_result["sync_failed"] else "success"
                    if sync_result["sync_failed"]:
                        failed += 1
                    else:
                        resumed += 1
                        resume_marker = current_state.get("marker")
                        should_send_notice = notice_state.get("marker") != resume_marker or notice_state.get("last_result") != "sent"
                        if should_send_notice and _notification_backoff_active(notice_state, now_utc):
                            suppressed += 1
                            should_send_notice = False
                        if should_send_notice:
                            delivery_result = await _send_trial_channel_resume_notice(bot, resumed_user or user)
                            notice_state["marker"] = resume_marker
                            notice_state["last_attempt_at"] = now_utc.isoformat()
                            notice_state["last_result"] = delivery_result
                            if delivery_result == "sent":
                                notified += 1
                            elif delivery_result not in {"skipped"}:
                                failed += 1
                    continue

                if marker and event_state.get("marker") == marker and event_state.get("last_result") == "success":
                    continue
                current_state["marker"] = marker
                current_state["last_result"] = "success"
                continue

            paused_user = user
            membership_already_paused = marker and event_state.get("marker") == marker and event_state.get("last_result") == "success"
            if not _trial_is_paused_by_channel(user, now_utc):
                maybe_paused_user = await pause_trial_for_channel_unsubscribe(int(user.id), paused_at=now_utc)
                if maybe_paused_user is not None:
                    paused_user = maybe_paused_user

            pause_marker = _trial_channel_enforcement_marker(
                paused_user,
                subscribed=False,
                now_utc=now_utc,
            )
            if not membership_already_paused:
                sync_failed = await sync_user_vpn_access(int(user.id), None)
                current_state["marker"] = pause_marker
                current_state["last_result"] = "failed" if sync_failed else "success"
                if sync_failed:
                    failed += 1
                else:
                    paused += 1
            else:
                current_state["marker"] = pause_marker
                current_state["last_result"] = "success"

            should_send_notice = notice_state.get("marker") != pause_marker or notice_state.get("last_result") != "sent"
            if should_send_notice and _notification_backoff_active(notice_state, now_utc):
                suppressed += 1
                should_send_notice = False
            if should_send_notice:
                delivery_result = await _send_trial_channel_pause_notice(bot, paused_user)
                notice_state["marker"] = pause_marker
                notice_state["last_attempt_at"] = now_utc.isoformat()
                notice_state["last_result"] = delivery_result
                if delivery_result == "sent":
                    notified += 1
                elif delivery_result not in {"skipped"}:
                    failed += 1
    finally:
        await bot.session.close()

    return {"checked": checked, "paused": paused, "resumed": resumed, "notified": notified, "suppressed": suppressed, "failed": failed}


def _normalize_stage_payload(result: object, *, ok: bool) -> dict[str, object]:
    payload: dict[str, object] = {"status": "ok" if ok else "failed"}
    if isinstance(result, dict):
        payload.update(result)
    elif result is not None:
        payload["result"] = result
    return payload


def _compact_stage_payload(payload: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {}
    status = str(payload.get("status") or "ok")
    if status != "ok":
        compact["status"] = status
    for key, value in payload.items():
        if key == "status":
            continue
        if isinstance(value, bool):
            if value:
                compact[key] = value
            continue
        if isinstance(value, (int, float)):
            if value:
                compact[key] = value
            continue
        if value not in (None, "", [], {}):
            compact[key] = value
    return compact or {"status": status}


async def _run_worker_stage(
    stage_name: str,
    runner,
    *,
    state: dict | None = None,
) -> dict[str, object]:
    ok = True
    result: object = None
    try:
        result = await runner()
    except Exception:
        ok = False
        logger.exception("Access reminders stage failed: stage=%s", stage_name)
    if state is not None and stage_name in STATEFUL_STAGE_NAMES:
        try:
            _save_state(state)
        except Exception:
            ok = False
            logger.exception("Access reminders stage state persistence failed: stage=%s", stage_name)
    return _normalize_stage_payload(result, ok=ok)


async def _run_worker_pipeline(state: dict, now_utc: datetime) -> dict[str, dict[str, object]]:
    stage_results: dict[str, dict[str, object]] = {}
    stage_definitions = [
        ("trial_channel", lambda: _enforce_trial_channel_membership(state, now_utc)),
        ("revocations", lambda: _revoke_expired_vpn_access(state, now_utc)),
        ("purges", lambda: _purge_expired_trial_vpn_access(state, now_utc)),
        ("bridge_purges", lambda: _purge_expired_bridge_access(state, now_utc)),
        ("device_slots", lambda: expire_device_slot_entitlements(now_utc=now_utc)),
        ("repair_recovery", lambda: _recover_vpn_repair_needed_users(state, now_utc, limit=10)),
        ("scheduled", process_pending_campaigns),
        ("trigger", lambda: _process_trigger_rules(now_utc)),
        ("incidents", lambda: emit_control_error_triggers(now_utc=now_utc)),
        ("payment_reconcile", lambda: reconcile_confirmed_payment_records(limit=25)),
        ("device_compensation", lambda: process_pending_device_compensation_jobs(limit=10)),
    ]
    for stage_name, runner in stage_definitions:
        stage_results[stage_name] = await _run_worker_stage(
            stage_name,
            runner,
            state=state,
        )
    return stage_results


async def main() -> None:
    configure_logging()
    await ensure_schema()

    token = config.bot_token
    if not token:
        raise RuntimeError("Bot token is not configured")

    now_utc = _normalize_utc_datetime(utcnow())
    state = _load_state()
    stage_results = await _run_worker_pipeline(state, now_utc)
    logger.info(
        "Amonora access reminders worker completed: %s",
        {name: _compact_stage_payload(payload) for name, payload in stage_results.items()},
    )


if __name__ == "__main__":
    asyncio.run(main())
