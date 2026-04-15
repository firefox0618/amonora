import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.analytics import (
    EVENT_FIRST_CONNECTION_SUCCESS,
    EVENT_PAYMENT_FAILED,
    EVENT_PAYMENT_STARTED,
    EVENT_SUBSCRIPTION_PAYMENT_FAILED,
    EVENT_SUBSCRIPTION_PAYMENT_STARTED,
    EVENT_SUBSCRIPTION_ACTIVATED,
    EVENT_SUBSCRIPTION_RENEWED,
    EVENT_TRIAL_STARTED,
    EVENT_USER_FIRST_SEEN,
    PAYMENT_KIND_NEW,
    PAYMENT_KIND_RENEWAL,
    safe_emit_analytics_event,
    safe_upsert_user_attribution,
)
from backend.core.database import async_session
from backend.core.models import (
    ControlBroadcastDelivery,
    ControlTriggerDeliveryLog,
    DeviceSlotEntitlement,
    PublicSubscriptionLink,
    PublicSubscriptionRoute,
    Referral,
    ReferralReward,
    User,
    UserBalanceEvent,
    VpnClient,
    VpnClientActivation,
    VpnRepairEvent,
)
from backend.core.schema import ensure_schema
from backend.core.tracing import get_current_trace_id
from bot.config import config
from bot.utils.device_slots import clamp_device_slot_count, device_slot_max_extra_slots
from bot.utils.referrals import (
    ReferralDashboard,
    ReferralRewardOutcome,
    build_referral_link,
    calc_level,
    generate_ref_code,
    referral_bonus_for_tariff,
    render_progress_bar,
)
from bot.utils.modes import get_auto_mode, get_mode_protocol, normalize_mode
from bot.utils.tariffs import get_tariff
from control_bot.channel_content import mark_recent_channel_post_conversion
from control_bot.dispatcher import create_control_event
from control_bot.storage import mark_recent_campaign_conversion
from bot.utils.access import (
    can_activate_trial_from_user,
    get_access_expires_at_from_user,
    get_device_limit_for_user,
    has_active_access_from_user,
    has_active_subscription_from_user,
    has_active_trial_from_user,
    has_trial_window_from_user,
    TRIAL_ACTIVITY_LEVEL_ACTIVE,
    TRIAL_ACTIVITY_LEVEL_LOW,
    trial_is_paused_by_channel_from_user,
    utcnow,
)
from bot.utils.regions import normalize_country_code
from dashboard.models import PaymentRecord

ADMIN_COMPLIMENTARY_DAYS = 3650
MANUAL_PAYMENT_OPEN_STATUSES = {"awaiting_user_payment", "awaiting_admin_review"}
MANUAL_PAYMENT_REVIEWABLE_STATUSES = {"awaiting_admin_review"}
BALANCE_HOLD_PAYMENT_STATUSES = MANUAL_PAYMENT_OPEN_STATUSES | {"pending"}
REFERRAL_BONUS_RUB = 50
# Only invites created before the balance-rollout moment can be backfilled as legacy.
REFERRAL_BALANCE_LEGACY_CUTOFF = datetime(2026, 3, 21, 16, 11, 0)
REFERRAL_CREDIT_REASONS = {
    "referral_bonus",
    "referral_migration",
    "referral_backfill",
    "referral_reward_referrer",
    "referral_reward_invited",
}
LANDING_BRIDGE_USER_PREFIX = "bridge_"
LANDING_BRIDGE_SUBSCRIPTION_SOURCE = "landing_bridge"
LANDING_BRIDGE_TELEGRAM_ID_BASE = 9_000_000_000_000_000
_UNSET = object()
_PAYMENT_RECORD_FIELDS = set(PaymentRecord.__mapper__.attrs.keys())


def _payment_record_kwargs(**kwargs) -> dict:
    return {key: value for key, value in kwargs.items() if key in _PAYMENT_RECORD_FIELDS}


def _payment_product_type_from_record(record: PaymentRecord) -> str:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    product_type = str(metadata.get("product_type") or metadata.get("payload_type") or "").strip().lower()
    tariff_code = str(getattr(record, "tariff_code", "") or "").strip().lower()
    if product_type:
        return product_type
    if tariff_code == "balance_topup":
        return "balance_topup"
    return "subscription"


async def _emit_payment_started_analytics(record: PaymentRecord) -> None:
    if getattr(record, "user_id", None) is None:
        return
    product_type = _payment_product_type_from_record(record)
    await safe_emit_analytics_event(
        event_name=EVENT_PAYMENT_STARTED,
        occurred_at=getattr(record, "created_at", None) or utcnow(),
        user_id=int(record.user_id),
        dedupe_key=f"payment-started:{int(record.id)}",
        payment_record_id=int(record.id),
        tariff_code=getattr(record, "tariff_code", None),
        payment_method=getattr(record, "payment_method", None),
        payload={
            "amount_rub": int(getattr(record, "amount", 0) or 0),
            "list_price_amount": int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
            "product_type": product_type,
        },
    )
    if product_type == "subscription":
        await safe_emit_analytics_event(
            event_name=EVENT_SUBSCRIPTION_PAYMENT_STARTED,
            occurred_at=getattr(record, "created_at", None) or utcnow(),
            user_id=int(record.user_id),
            dedupe_key=f"subscription-payment-started:{int(record.id)}",
            payment_record_id=int(record.id),
            tariff_code=getattr(record, "tariff_code", None),
            payment_method=getattr(record, "payment_method", None),
            payload={
                "amount_rub": int(getattr(record, "amount", 0) or 0),
                "list_price_amount": int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
                "product_type": product_type,
            },
        )


async def _emit_payment_failed_analytics(record: PaymentRecord) -> None:
    if getattr(record, "user_id", None) is None:
        return
    product_type = _payment_product_type_from_record(record)
    await safe_emit_analytics_event(
        event_name=EVENT_PAYMENT_FAILED,
        occurred_at=getattr(record, "reviewed_at", None) or getattr(record, "expires_at", None) or utcnow(),
        user_id=int(record.user_id),
        dedupe_key=f"payment-failed:{int(record.id)}:{str(record.payment_status or '').strip().lower()}",
        payment_record_id=int(record.id),
        tariff_code=getattr(record, "tariff_code", None),
        payment_method=getattr(record, "payment_method", None),
        payload={
            "payment_status": str(getattr(record, "payment_status", "") or "").strip().lower(),
            "rejection_reason": str(getattr(record, "rejection_reason", "") or "").strip() or None,
            "product_type": product_type,
        },
    )
    if product_type == "subscription":
        await safe_emit_analytics_event(
            event_name=EVENT_SUBSCRIPTION_PAYMENT_FAILED,
            occurred_at=getattr(record, "reviewed_at", None) or getattr(record, "expires_at", None) or utcnow(),
            user_id=int(record.user_id),
            dedupe_key=f"subscription-payment-failed:{int(record.id)}:{str(record.payment_status or '').strip().lower()}",
            payment_record_id=int(record.id),
            tariff_code=getattr(record, "tariff_code", None),
            payment_method=getattr(record, "payment_method", None),
            payload={
                "payment_status": str(getattr(record, "payment_status", "") or "").strip().lower(),
                "rejection_reason": str(getattr(record, "rejection_reason", "") or "").strip() or None,
                "product_type": product_type,
            },
        )


def _new_user_control_event_message(telegram_id: int, username: str | None) -> str:
    username_label = f"@{username}" if username else "без username"
    return f"Telegram ID: <code>{telegram_id}</code> • Username: <b>{username_label}</b>"


def _trial_started_control_event_message(
    user_id: int,
    telegram_id: int | None,
    trial_expires_at: datetime | None,
) -> str:
    trial_expires_text = trial_expires_at.strftime("%Y-%m-%d %H:%M:%S") if trial_expires_at else "—"
    telegram_label = telegram_id if telegram_id is not None else "—"
    return (
        f"User: <code>{user_id}</code> • Tg ID: <code>{telegram_label}</code> • "
        f"Пробный доступ до: <b>{trial_expires_text}</b>"
    )


def _trial_channel_state_control_event_message(
    user_id: int,
    telegram_id: int | None,
    *,
    suspended_at: datetime | None,
    trial_expires_at: datetime | None,
) -> str:
    telegram_label = telegram_id if telegram_id is not None else "—"
    suspended_text = suspended_at.strftime("%Y-%m-%d %H:%M:%S") if suspended_at else "—"
    expires_text = trial_expires_at.strftime("%Y-%m-%d %H:%M:%S") if trial_expires_at else "—"
    return (
        f"User: <code>{user_id}</code> • Tg ID: <code>{telegram_label}</code> • "
        f"Пауза trial с: <b>{suspended_text}</b> • Trial до: <b>{expires_text}</b>"
    )


def _load_payment_metadata(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


PAYMENT_EFFECT_APPLIED_AT_KEY = "effect_applied_at"
PAYMENT_EFFECT_KIND_KEY = "effect_kind"
PAYMENT_EFFECT_PROCESSING_AT_KEY = "effect_processing_at"
PAYMENT_EFFECT_PROCESSING_KIND_KEY = "effect_processing_kind"
PAYMENT_EFFECT_LAST_ERROR_KEY = "effect_last_error"
PAYMENT_FINANCE_SYNCED_AT_KEY = "finance_synced_at"
PAYMENT_ACCESS_SYNCED_AT_KEY = "access_synced_at"
PAYMENT_ACCESS_SYNC_STATE_KEY = "access_sync_state"
PAYMENT_RECONCILE_STATE_KEY = "reconcile_state"
PAYMENT_RECONCILED_AT_KEY = "reconciled_at"
PAYMENT_TRACE_ID_KEY = "trace_id"
PAYMENT_PROVIDER_CALLBACK_HASH_KEY = "provider_callback_hash"
PAYMENT_PROVIDER_CALLBACK_SEEN_AT_KEY = "provider_callback_seen_at"
PAYMENT_PROVIDER_CALLBACK_REPEAT_COUNT_KEY = "provider_callback_repeat_count"
PAYMENT_PROVIDER_CALLBACK_LAST_SIGNATURE_KEY = "provider_callback_last_signature"
PAYMENT_PROVIDER_CALLBACK_SIGNATURES_KEY = "provider_callback_signatures"
PAYMENT_PROVIDER_CALLBACK_LAST_EVENT_KEY = "provider_callback_last_event_key"
PAYMENT_PROVIDER_CALLBACK_EVENT_KEYS_KEY = "provider_callback_event_keys"
PAYMENT_EFFECT_PROCESSING_TIMEOUT_SECONDS = 300
DEVICE_SLOT_STATUS_ACTIVE = "active"
DEVICE_SLOT_STATUS_EXPIRED = "expired"
DEVICE_SLOT_STATUS_CANCELLED = "cancelled"


def payment_record_effect_applied(record) -> bool:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    return bool(metadata.get(PAYMENT_EFFECT_APPLIED_AT_KEY))


def payment_record_metadata_flag(record, key: str) -> bool:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    return bool(metadata.get(str(key or "").strip()))


def payment_record_effect_kind(record) -> str:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    return str(metadata.get(PAYMENT_EFFECT_KIND_KEY) or "").strip().lower()


def payment_record_access_sync_state(record) -> str:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    return str(metadata.get(PAYMENT_ACCESS_SYNC_STATE_KEY) or "").strip().lower()


def payment_record_finance_synced(record) -> bool:
    return payment_record_metadata_flag(record, PAYMENT_FINANCE_SYNCED_AT_KEY)


def payment_record_requires_access_sync(record) -> bool:
    if not payment_record_effect_applied(record):
        return False
    if payment_record_effect_kind(record) != "subscription_activation":
        return False
    return payment_record_access_sync_state(record) != "success"


def payment_record_requires_finance_sync(record) -> bool:
    from dashboard.finance import payment_method_counts_as_revenue

    if not payment_record_effect_applied(record):
        return False
    if int(getattr(record, "amount", 0) or 0) <= 0:
        return False
    if not payment_method_counts_as_revenue(getattr(record, "payment_method", None)):
        return False
    return not payment_record_finance_synced(record)


def payment_record_reconcile_state(record) -> str:
    status = str(getattr(record, "payment_status", "") or "").strip().lower()
    if status != "confirmed":
        return "not_confirmed"
    if not payment_record_effect_applied(record):
        return "missing_effect"
    if payment_record_requires_access_sync(record):
        return "access_pending"
    if payment_record_requires_finance_sync(record):
        return "finance_pending"
    return "converged"


def _apply_payment_reconcile_state(metadata: dict, record) -> None:
    record.metadata_json = json.dumps(metadata, ensure_ascii=False)
    state = payment_record_reconcile_state(record)
    if state == "not_confirmed":
        metadata.pop(PAYMENT_RECONCILE_STATE_KEY, None)
        metadata.pop(PAYMENT_RECONCILED_AT_KEY, None)
        return
    metadata[PAYMENT_RECONCILE_STATE_KEY] = state
    if state == "converged":
        metadata.setdefault(PAYMENT_RECONCILED_AT_KEY, utcnow().isoformat())
    else:
        metadata.pop(PAYMENT_RECONCILED_AT_KEY, None)


def payment_record_trace_id(record) -> str:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    existing = str(metadata.get(PAYMENT_TRACE_ID_KEY) or "").strip()
    if existing:
        return existing
    method = str(getattr(record, "payment_method", "") or "").strip().lower() or "payment"
    external_id = str(getattr(record, "external_payment_id", "") or getattr(record, "id", "") or "").strip() or "unknown"
    return f"{method}:{external_id}"


def _payment_trace_id_for_values(payment_method: str | None, external_payment_id: str | None) -> str:
    current_trace_id = get_current_trace_id()
    if current_trace_id:
        return current_trace_id
    method = str(payment_method or "").strip().lower() or "payment"
    external_id = str(external_payment_id or "").strip() or "unknown"
    return f"{method}:{external_id}"


def _with_payment_metadata_defaults(
    metadata: dict | None,
    *,
    payment_method: str | None,
    external_payment_id: str | None,
) -> dict:
    payload = dict(metadata or {})
    payload.setdefault(PAYMENT_TRACE_ID_KEY, _payment_trace_id_for_values(payment_method, external_payment_id))
    return payload


def _parse_effect_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def payment_record_effect_processing(
    record,
    *,
    effect_kind: str | None = None,
    now_utc: datetime | None = None,
    stale_after_seconds: int = PAYMENT_EFFECT_PROCESSING_TIMEOUT_SECONDS,
) -> bool:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    processing_at = _parse_effect_timestamp(metadata.get(PAYMENT_EFFECT_PROCESSING_AT_KEY))
    if processing_at is None:
        return False
    now_point = now_utc or utcnow()
    is_fresh = (now_point - processing_at).total_seconds() < max(int(stale_after_seconds), 1)
    if not is_fresh:
        return False
    processing_kind = str(metadata.get(PAYMENT_EFFECT_PROCESSING_KIND_KEY) or "").strip()
    if effect_kind and processing_kind and processing_kind != effect_kind:
        return True
    return True


async def claim_payment_record_effect(
    record_id: int,
    *,
    effect_kind: str,
    stale_after_seconds: int = PAYMENT_EFFECT_PROCESSING_TIMEOUT_SECONDS,
) -> tuple[PaymentRecord | None, str]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None, "missing"
        if str(record.payment_status or "").strip().lower() != "confirmed":
            return record, "invalid_status"

        metadata = _load_payment_metadata(record.metadata_json)
        if metadata.get(PAYMENT_EFFECT_APPLIED_AT_KEY):
            return record, "already_applied"

        processing_at = _parse_effect_timestamp(metadata.get(PAYMENT_EFFECT_PROCESSING_AT_KEY))
        processing_kind = str(metadata.get(PAYMENT_EFFECT_PROCESSING_KIND_KEY) or "").strip()
        now_point = utcnow()
        if (
            processing_at is not None
            and (now_point - processing_at).total_seconds() < max(int(stale_after_seconds), 1)
            and processing_kind
        ):
            return record, "in_progress"

        metadata[PAYMENT_EFFECT_PROCESSING_AT_KEY] = now_point.isoformat()
        metadata[PAYMENT_EFFECT_PROCESSING_KIND_KEY] = effect_kind
        metadata.pop(PAYMENT_EFFECT_LAST_ERROR_KEY, None)
        record.metadata_json = json.dumps(metadata, ensure_ascii=False)
        await session.commit()
        await session.refresh(record)
        return record, "claimed"


async def release_payment_record_effect_claim(
    record_id: int,
    *,
    effect_kind: str,
    error_text: str | None = None,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None

        metadata = _load_payment_metadata(record.metadata_json)
        processing_kind = str(metadata.get(PAYMENT_EFFECT_PROCESSING_KIND_KEY) or "").strip()
        if not processing_kind or processing_kind == effect_kind:
            metadata.pop(PAYMENT_EFFECT_PROCESSING_AT_KEY, None)
            metadata.pop(PAYMENT_EFFECT_PROCESSING_KIND_KEY, None)
            if error_text:
                metadata[PAYMENT_EFFECT_LAST_ERROR_KEY] = str(error_text)[:1000]
            record.metadata_json = json.dumps(metadata, ensure_ascii=False)
            await session.commit()
            await session.refresh(record)
        return record


async def mark_payment_record_effect_applied(record_id: int, *, effect_kind: str) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None

        metadata = _load_payment_metadata(record.metadata_json)
        metadata[PAYMENT_EFFECT_APPLIED_AT_KEY] = utcnow().isoformat()
        metadata[PAYMENT_EFFECT_KIND_KEY] = effect_kind
        metadata.pop(PAYMENT_EFFECT_PROCESSING_AT_KEY, None)
        metadata.pop(PAYMENT_EFFECT_PROCESSING_KIND_KEY, None)
        metadata.pop(PAYMENT_EFFECT_LAST_ERROR_KEY, None)
        _apply_payment_reconcile_state(metadata, record)
        record.metadata_json = json.dumps(metadata, ensure_ascii=False)
        await session.commit()
        await session.refresh(record)
        return record


async def update_payment_record_metadata(
    record_id: int,
    *,
    merge: dict[str, object] | None = None,
    remove_keys: set[str] | None = None,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None

        metadata = _load_payment_metadata(record.metadata_json)
        if merge:
            metadata.update({str(key): value for key, value in merge.items()})
        if remove_keys:
            for key in remove_keys:
                metadata.pop(str(key), None)
        record.metadata_json = json.dumps(metadata, ensure_ascii=False)
        await session.commit()
        await session.refresh(record)
        return record


async def refresh_payment_record_reconcile_state(record_id: int) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None

        metadata = _load_payment_metadata(record.metadata_json)
        _apply_payment_reconcile_state(metadata, record)
        record.metadata_json = json.dumps(metadata, ensure_ascii=False)
        await session.commit()
        await session.refresh(record)
        return record


async def mark_payment_record_finance_synced(
    record_id: int,
    *,
    finance_entry_id: int | None = None,
) -> PaymentRecord | None:
    merge = {
        PAYMENT_FINANCE_SYNCED_AT_KEY: utcnow().isoformat(),
    }
    if finance_entry_id is not None:
        merge["finance_entry_id"] = int(finance_entry_id)
    record = await update_payment_record_metadata(record_id, merge=merge)
    if record is None:
        return None
    return await refresh_payment_record_reconcile_state(record_id)


async def clear_payment_record_finance_synced(record_id: int) -> PaymentRecord | None:
    record = await update_payment_record_metadata(
        record_id,
        remove_keys={PAYMENT_FINANCE_SYNCED_AT_KEY, "finance_entry_id"},
    )
    if record is None:
        return None
    return await refresh_payment_record_reconcile_state(record_id)


async def create_device_slot_entitlement(
    *,
    user_id: int,
    payment_record_id: int,
    slots_count: int,
    unit_price_rub: int,
    total_amount_rub: int,
    starts_at: datetime,
    expires_at: datetime,
) -> DeviceSlotEntitlement | None:
    await ensure_schema()

    safe_slots = clamp_device_slot_count(slots_count)
    if safe_slots <= 0:
        return None

    async with async_session() as session:
        existing = (
            await session.execute(
                select(DeviceSlotEntitlement).where(DeviceSlotEntitlement.payment_record_id == payment_record_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        entitlement = DeviceSlotEntitlement(
            user_id=user_id,
            payment_record_id=payment_record_id,
            slots_count=safe_slots,
            unit_price_rub=max(int(unit_price_rub), 0),
            total_amount_rub=max(int(total_amount_rub), 0),
            starts_at=starts_at,
            expires_at=expires_at,
            status=DEVICE_SLOT_STATUS_ACTIVE,
        )
        session.add(entitlement)
        await session.commit()
        await session.refresh(entitlement)
        return entitlement


async def get_active_device_slot_counts_for_users(
    user_ids: list[int],
    *,
    now_utc: datetime | None = None,
) -> dict[int, int]:
    await ensure_schema()

    normalized_ids = sorted({int(user_id) for user_id in user_ids if int(user_id) > 0})
    if not normalized_ids:
        return {}

    current = now_utc or utcnow()
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(
                        DeviceSlotEntitlement.user_id,
                        func.coalesce(func.sum(DeviceSlotEntitlement.slots_count), 0),
                    )
                    .join(User, User.id == DeviceSlotEntitlement.user_id)
                    .where(
                        DeviceSlotEntitlement.user_id.in_(normalized_ids),
                        DeviceSlotEntitlement.status == DEVICE_SLOT_STATUS_ACTIVE,
                        DeviceSlotEntitlement.expires_at > current,
                        User.subscription_status == "active",
                        User.subscription_expires_at.is_not(None),
                        User.subscription_expires_at > current,
                    )
                    .group_by(DeviceSlotEntitlement.user_id)
                )
            ).all()
        )

    result: dict[int, int] = {}
    for user_id, slots_count in rows:
        result[int(user_id)] = clamp_device_slot_count(int(slots_count or 0))
    return result


async def get_active_device_slot_entitlements_for_user(
    user_id: int,
    *,
    now_utc: datetime | None = None,
) -> list[DeviceSlotEntitlement]:
    counts = await get_active_device_slot_counts_for_users([user_id], now_utc=now_utc)
    if counts.get(int(user_id), 0) <= 0:
        return []

    current = now_utc or utcnow()
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DeviceSlotEntitlement)
                    .join(User, User.id == DeviceSlotEntitlement.user_id)
                    .where(
                        DeviceSlotEntitlement.user_id == user_id,
                        DeviceSlotEntitlement.status == DEVICE_SLOT_STATUS_ACTIVE,
                        DeviceSlotEntitlement.expires_at > current,
                        User.subscription_status == "active",
                        User.subscription_expires_at.is_not(None),
                        User.subscription_expires_at > current,
                    )
                    .order_by(DeviceSlotEntitlement.expires_at.asc(), DeviceSlotEntitlement.id.asc())
                )
            ).scalars().all()
        )
    return rows


async def expire_device_slot_entitlements(*, now_utc: datetime | None = None) -> dict[str, int]:
    await ensure_schema()

    current = now_utc or utcnow()
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DeviceSlotEntitlement)
                    .join(User, User.id == DeviceSlotEntitlement.user_id)
                    .where(
                        DeviceSlotEntitlement.status == DEVICE_SLOT_STATUS_ACTIVE,
                        (
                            (DeviceSlotEntitlement.expires_at <= current)
                            | (User.subscription_expires_at.is_(None))
                            | (User.subscription_expires_at <= current)
                            | (User.subscription_status != "active")
                        ),
                    )
                )
            ).scalars().all()
        )
        if not rows:
            return {"expired": 0}

        for row in rows:
            row.status = DEVICE_SLOT_STATUS_EXPIRED
            row.updated_at = current
        await session.commit()
    return {"expired": len(rows)}


async def _lock_user_row(session: AsyncSession, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    return result.scalar_one_or_none()


async def _lock_vpn_client_row(session: AsyncSession, vpn_client_id: int | None) -> VpnClient | None:
    if vpn_client_id is None:
        return None
    result = await session.execute(select(VpnClient).where(VpnClient.id == int(vpn_client_id)).with_for_update())
    return result.scalar_one_or_none()


async def _active_device_slot_count_for_user(session: AsyncSession, user_id: int, *, now_utc: datetime | None = None) -> int:
    current = now_utc or utcnow()
    value = (
        await session.execute(
            select(func.coalesce(func.sum(DeviceSlotEntitlement.slots_count), 0))
            .join(User, User.id == DeviceSlotEntitlement.user_id)
            .where(
                DeviceSlotEntitlement.user_id == int(user_id),
                DeviceSlotEntitlement.status == DEVICE_SLOT_STATUS_ACTIVE,
                DeviceSlotEntitlement.expires_at > current,
                User.subscription_status == "active",
                User.subscription_expires_at.is_not(None),
                User.subscription_expires_at > current,
            )
        )
    ).scalar_one()
    return clamp_device_slot_count(int(value or 0))


def _available_balance_from_user(user: User) -> int:
    return max(int(getattr(user, "balance_rub", 0)) - int(getattr(user, "balance_reserved_rub", 0)), 0)


async def _ensure_ref_code(session: AsyncSession, user: User) -> str:
    current = str(getattr(user, "ref_code", "") or "").strip().lower()
    if current:
        return current

    while True:
        candidate = generate_ref_code()
        existing = await session.execute(select(User.id).where(User.ref_code == candidate).limit(1))
        if existing.scalar_one_or_none() is None:
            user.ref_code = candidate
            return candidate


def _increment_referral_earned_total(user: User, amount: int) -> None:
    safe_amount = max(int(amount), 0)
    if safe_amount <= 0:
        return
    user.referral_earned_total_rub = int(getattr(user, "referral_earned_total_rub", 0) or 0) + safe_amount


def _decrement_referral_earned_total(user: User, amount: int) -> None:
    safe_amount = max(int(amount), 0)
    if safe_amount <= 0:
        return
    user.referral_earned_total_rub = max(int(getattr(user, "referral_earned_total_rub", 0) or 0) - safe_amount, 0)


async def _ensure_referral_row(session: AsyncSession, *, referrer_user_id: int, invited_user_id: int) -> Referral | None:
    existing = await session.execute(select(Referral).where(Referral.invited_user_id == invited_user_id))
    referral = existing.scalar_one_or_none()
    if referral is not None:
        return referral

    referral = Referral(
        referrer_user_id=referrer_user_id,
        invited_user_id=invited_user_id,
    )
    session.add(referral)
    return referral


def _append_balance_event(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    direction: str,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> None:
    session.add(
        UserBalanceEvent(
            user_id=user_id,
            amount=int(amount),
            direction=direction[:20],
            reason=reason[:100],
            reference_type=reference_type[:100] if reference_type else None,
            reference_id=reference_id[:255] if reference_id else None,
            note=note,
        )
    )


async def _credit_user_balance(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> int:
    credit_amount = max(int(amount), 0)
    if credit_amount <= 0:
        return 0
    user.balance_rub = int(getattr(user, "balance_rub", 0)) + credit_amount
    _append_balance_event(
        session,
        user_id=user.id,
        amount=credit_amount,
        direction="credit",
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    return credit_amount


async def _debit_user_balance(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> int:
    debit_amount = max(int(amount), 0)
    if debit_amount <= 0:
        return 0
    user.balance_rub = int(getattr(user, "balance_rub", 0)) - debit_amount
    _append_balance_event(
        session,
        user_id=user.id,
        amount=debit_amount,
        direction="debit",
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    return debit_amount


async def _reserve_user_balance(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> int:
    reserve_amount = min(max(int(amount), 0), _available_balance_from_user(user))
    if reserve_amount <= 0:
        return 0
    user.balance_reserved_rub = int(getattr(user, "balance_reserved_rub", 0)) + reserve_amount
    _append_balance_event(
        session,
        user_id=user.id,
        amount=reserve_amount,
        direction="reserve",
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    return reserve_amount


async def _release_user_balance_reserve(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> int:
    release_amount = min(max(int(amount), 0), int(getattr(user, "balance_reserved_rub", 0)))
    if release_amount <= 0:
        return 0
    user.balance_reserved_rub = int(getattr(user, "balance_reserved_rub", 0)) - release_amount
    _append_balance_event(
        session,
        user_id=user.id,
        amount=release_amount,
        direction="release",
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    return release_amount


async def _apply_reserved_balance_for_record(session: AsyncSession, record: PaymentRecord, *, reason: str) -> int:
    reserved_amount = int(getattr(record, "balance_reserved_amount", 0) or 0)
    if record.user_id is None or reserved_amount <= 0:
        record.balance_reserved_amount = 0
        return 0

    user = await _lock_user_row(session, record.user_id)
    if user is None:
        record.balance_reserved_amount = 0
        return 0

    applied_amount = min(
        reserved_amount,
        int(getattr(user, "balance_reserved_rub", 0)),
        int(getattr(user, "balance_rub", 0)),
    )
    if applied_amount <= 0:
        record.balance_reserved_amount = 0
        return 0

    user.balance_reserved_rub = int(getattr(user, "balance_reserved_rub", 0)) - applied_amount
    user.balance_rub = int(getattr(user, "balance_rub", 0)) - applied_amount
    record.balance_reserved_amount = reserved_amount - applied_amount
    record.balance_applied_amount = int(getattr(record, "balance_applied_amount", 0) or 0) + applied_amount
    _append_balance_event(
        session,
        user_id=user.id,
        amount=applied_amount,
        direction="debit",
        reason=reason,
        reference_type="payment_record",
        reference_id=str(record.id),
        note=f"Списано для платежа #{record.id}",
    )
    return applied_amount


async def _release_reserved_balance_for_record(session: AsyncSession, record: PaymentRecord, *, reason: str) -> int:
    reserved_amount = int(getattr(record, "balance_reserved_amount", 0) or 0)
    if record.user_id is None or reserved_amount <= 0:
        record.balance_reserved_amount = 0
        return 0

    user = await _lock_user_row(session, record.user_id)
    if user is None:
        record.balance_reserved_amount = 0
        return 0

    released = await _release_user_balance_reserve(
        session,
        user,
        amount=reserved_amount,
        reason=reason,
        reference_type="payment_record",
        reference_id=str(record.id),
        note=f"Резерв снят для платежа #{record.id}",
    )
    record.balance_reserved_amount = 0
    return released


async def _migrate_referral_balance_if_needed(session: AsyncSession, user: User) -> int:
    invited_result = await session.execute(select(User).where(User.referred_by_user_id == user.id))
    invited_users = list(invited_result.scalars().all())
    migration_cutoff = getattr(user, "referral_balance_migrated_at", None)

    if not invited_users:
        if migration_cutoff is None:
            user.referral_balance_migrated_at = utcnow()
        return 0

    legacy_cutoff = REFERRAL_BALANCE_LEGACY_CUTOFF
    qualified_referred_ids: set[int] = set()
    for referred_user in invited_users:
        # Legacy balance migration only applies to invites created before the
        # referral-reward rollout. Modern referrals are handled exclusively by
        # tariff-based ReferralReward rows.
        qualifies_by_legacy_migration = bool(referred_user.created_at and referred_user.created_at <= legacy_cutoff)
        if not qualifies_by_legacy_migration:
            continue
        qualified_referred_ids.add(referred_user.id)
        if not referred_user.referral_bonus_granted:
            referred_user.referral_bonus_granted = True

    credited_total_result = await session.execute(
        select(func.coalesce(func.sum(UserBalanceEvent.amount), 0)).where(
            UserBalanceEvent.user_id == user.id,
            UserBalanceEvent.direction == "credit",
            UserBalanceEvent.reason.in_(sorted(REFERRAL_CREDIT_REASONS)),
        )
    )
    credited_total = int(credited_total_result.scalar_one() or 0)
    expected_total = len(qualified_referred_ids) * REFERRAL_BONUS_RUB
    missing_amount = max(expected_total - credited_total, 0)

    if migration_cutoff is None:
        user.referral_balance_migrated_at = REFERRAL_BALANCE_LEGACY_CUTOFF

    if missing_amount <= 0:
        return 0

    reason = "referral_migration" if credited_total <= 0 else "referral_backfill"
    note_prefix = "Миграция старой реферальной системы" if reason == "referral_migration" else "Доначисление реферального баланса"
    credited = await _credit_user_balance(
        session,
        user,
        amount=missing_amount,
        reason=reason,
        reference_type="referral",
        reference_id=str(user.id),
        note=f"{note_prefix}: {len(qualified_referred_ids)} квалифицированных рефералов",
    )
    _increment_referral_earned_total(user, credited)
    return credited


async def reconcile_all_referral_balances() -> dict[str, int]:
    await ensure_schema()

    async with async_session() as session:
        users = list((await session.execute(select(User))).scalars().all())
        touched_users = 0
        credited_rub = 0

        for user in users:
            credited = await _migrate_referral_balance_if_needed(session, user)
            if credited > 0:
                touched_users += 1
                credited_rub += credited

        await session.commit()
        return {
            "users_scanned": len(users),
            "users_credited": touched_users,
            "credited_rub": credited_rub,
        }


async def _expire_open_manual_payment_records(session: AsyncSession) -> int:
    now = utcnow()
    result = await session.execute(
        select(PaymentRecord).where(
            PaymentRecord.payment_status.in_(sorted(BALANCE_HOLD_PAYMENT_STATUSES)),
            PaymentRecord.expires_at.is_not(None),
            PaymentRecord.expires_at < now,
        )
    )
    records = list(result.scalars().all())
    if not records:
        return 0

    for record in records:
        record.payment_status = "expired"
        record.rejection_reason = "Срок действия заявки истёк."
        await _release_reserved_balance_for_record(session, record, reason="payment_expired")

    await session.commit()
    return len(records)


def _is_admin_with_free_access(telegram_id: int) -> bool:
    return telegram_id in set(config.admin_ids) | set(config.support_admin_ids)


async def _sync_complimentary_admin_access(session: AsyncSession, user: User) -> User:
    if not _is_admin_with_free_access(user.telegram_id) or user.is_blocked:
        return user

    now = utcnow()
    desired_expires_at = now + timedelta(days=ADMIN_COMPLIMENTARY_DAYS)
    changed = False

    if user.subscription_started_at is None:
        user.subscription_started_at = now
        changed = True
    if user.subscription_status != "active":
        user.subscription_status = "active"
        changed = True
    if user.subscription_source != "vip_free":
        user.subscription_source = "vip_free"
        changed = True
    if user.subscription_expires_at is None or user.subscription_expires_at < desired_expires_at:
        user.subscription_expires_at = desired_expires_at
        changed = True

    if changed:
        await session.commit()
        await session.refresh(user)

    migration_was_missing = getattr(user, "referral_balance_migrated_at", None) is None
    migration_applied = await _migrate_referral_balance_if_needed(session, user)
    if migration_applied or migration_was_missing:
        await session.commit()
        await session.refresh(user)

    return user


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    referred_by_telegram_id: int | None = None,
    *,
    skip_initial_analytics_attribution: bool = False,
) -> tuple[User, bool]:
    await ensure_schema()

    async with async_session() as session:  # type: AsyncSession
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if user:
            changed = False
            if user.username != username and username is not None:
                user.username = username
                changed = True
            if not getattr(user, "ref_code", None):
                await _ensure_ref_code(session, user)
                changed = True
            if (
                user.referred_by_user_id is None
                and referred_by_telegram_id is not None
                and referred_by_telegram_id != telegram_id
            ):
                referrer_result = await session.execute(
                    select(User).where(User.telegram_id == referred_by_telegram_id)
                )
                referrer = referrer_result.scalar_one_or_none()
                if referrer is not None:
                    user.referred_by_user_id = referrer.id
                    await _ensure_referral_row(session, referrer_user_id=referrer.id, invited_user_id=user.id)
                    changed = True
            if changed:
                await session.commit()
                await session.refresh(user)
            user = await _sync_complimentary_admin_access(session, user)
            return user, False

        referrer_id = None
        if referred_by_telegram_id is not None and referred_by_telegram_id != telegram_id:
            referrer_result = await session.execute(
                select(User).where(User.telegram_id == referred_by_telegram_id)
            )
            referrer = referrer_result.scalar_one_or_none()
            if referrer is not None:
                referrer_id = referrer.id

        user = User(
            telegram_id=telegram_id,
            username=username,
            preferred_mode=normalize_mode(config.default_mode, default=get_auto_mode()),
            preferred_protocol=get_mode_protocol(normalize_mode(config.default_mode, default=get_auto_mode())),
            referred_by_user_id=referrer_id,
            last_activity_at=utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await _ensure_ref_code(session, user)
        if referrer_id is not None:
            await _ensure_referral_row(session, referrer_user_id=referrer_id, invited_user_id=user.id)
        await session.commit()
        await session.refresh(user)
        user = await _sync_complimentary_admin_access(session, user)
        await create_control_event(
            category="users",
            severity="INFO",
            event_type="new_user",
            title="Новый пользователь",
            message=_new_user_control_event_message(telegram_id, username),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": telegram_id,
                "username": username,
                "referred_by_telegram_id": referred_by_telegram_id,
            },
            dedupe_key=f"user-created:{user.id}",
            cooldown_seconds=0,
        )
        if not skip_initial_analytics_attribution:
            await safe_upsert_user_attribution(
                user_id=int(user.id),
                telegram_id=telegram_id,
                source_type="organic_bot",
                source_key="organic_bot",
                seen_at=getattr(user, "created_at", None) or utcnow(),
            )
        await safe_emit_analytics_event(
            event_name=EVENT_USER_FIRST_SEEN,
            occurred_at=getattr(user, "created_at", None) or utcnow(),
            user_id=int(user.id),
            telegram_id=telegram_id,
            dedupe_key=f"user-first-seen:{int(user.id)}",
            payload={"referred_by_telegram_id": referred_by_telegram_id},
        )
        return user, True


async def bind_referrer_by_token(user_id: int, referral_token: str | None) -> dict[str, int | str | bool | None]:
    await ensure_schema()

    normalized_token = str(referral_token or "").strip()
    if not normalized_token:
        return {"bound": False, "referrer_user_id": None, "referrer_telegram_id": None, "ref_code": None}

    async with async_session() as session:
        invited_user = await _lock_user_row(session, user_id)
        if invited_user is None:
            return {"bound": False, "referrer_user_id": None, "referrer_telegram_id": None, "ref_code": None}

        if invited_user.referred_by_user_id is not None:
            await _ensure_ref_code(session, invited_user)
            await _ensure_referral_row(
                session,
                referrer_user_id=invited_user.referred_by_user_id,
                invited_user_id=invited_user.id,
            )
            await session.commit()
            return {
                "bound": False,
                "referrer_user_id": invited_user.referred_by_user_id,
                "referrer_telegram_id": None,
                "ref_code": getattr(invited_user, "ref_code", None),
            }

        referrer = None
        if normalized_token.isdigit():
            referrer = (
                await session.execute(select(User).where(User.telegram_id == int(normalized_token)))
            ).scalar_one_or_none()
        else:
            referrer = (
                await session.execute(select(User).where(User.ref_code == normalized_token.lower()))
            ).scalar_one_or_none()

        if referrer is None or referrer.id == invited_user.id or referrer.telegram_id == invited_user.telegram_id:
            await _ensure_ref_code(session, invited_user)
            await session.commit()
            return {
                "bound": False,
                "referrer_user_id": None,
                "referrer_telegram_id": None,
                "ref_code": getattr(invited_user, "ref_code", None),
            }

        await _ensure_ref_code(session, invited_user)
        await _ensure_ref_code(session, referrer)
        invited_user.referred_by_user_id = referrer.id
        await _ensure_referral_row(
            session,
            referrer_user_id=referrer.id,
            invited_user_id=invited_user.id,
        )
        await session.commit()
        await session.refresh(invited_user)
        await session.refresh(referrer)
        return {
            "bound": True,
            "referrer_user_id": referrer.id,
            "referrer_telegram_id": referrer.telegram_id,
            "ref_code": getattr(invited_user, "ref_code", None),
        }


async def create_landing_bridge_user(duration_days: int = 1) -> User:
    await ensure_schema()

    normalized_mode = normalize_mode(config.default_mode, default=get_auto_mode())
    preferred_protocol = get_mode_protocol(normalized_mode)
    safe_duration_days = max(int(duration_days), 1)

    async with async_session() as session:  # type: AsyncSession
        now = utcnow()
        username = f"{LANDING_BRIDGE_USER_PREFIX}{uuid4().hex[:12]}"

        telegram_id = None
        for _ in range(6):
            candidate = LANDING_BRIDGE_TELEGRAM_ID_BASE + int(uuid4().int % 1_000_000_000_000_000)
            existing = await session.execute(select(User.id).where(User.telegram_id == candidate))
            if existing.scalar_one_or_none() is None:
                telegram_id = candidate
                break
        if telegram_id is None:
            raise ValueError("Failed to allocate synthetic landing bridge user")

        user = User(
            telegram_id=telegram_id,
            username=username,
            is_synthetic=True,
            preferred_mode=normalized_mode,
            preferred_protocol=preferred_protocol,
            subscription_started_at=now,
            subscription_expires_at=now + timedelta(days=safe_duration_days),
            subscription_status="active",
            subscription_source=LANDING_BRIDGE_SUBSCRIPTION_SOURCE,
            last_activity_at=now,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def delete_landing_bridge_user_if_unused(user_id: int) -> bool:
    await ensure_schema()

    async with async_session() as session:  # type: AsyncSession
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None or not (user.username or "").startswith(LANDING_BRIDGE_USER_PREFIX):
            return False

        has_devices = (
            await session.execute(select(VpnClient.id).where(VpnClient.user_id == user_id).limit(1))
        ).scalar_one_or_none() is not None
        if has_devices:
            return False

        await session.execute(
            update(ControlBroadcastDelivery)
            .where(ControlBroadcastDelivery.user_id == user_id)
            .values(user_id=None)
        )
        await session.execute(
            update(ControlTriggerDeliveryLog)
            .where(ControlTriggerDeliveryLog.user_id == user_id)
            .values(user_id=None)
        )
        await session.delete(user)
        await session.commit()
        return True


async def get_user_by_telegram_id(telegram_id: int) -> User | None:
    await ensure_schema()

    async with async_session() as session:  # type: AsyncSession
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not getattr(user, "ref_code", None):
            await _ensure_ref_code(session, user)
            await session.commit()
            await session.refresh(user)
        return await _sync_complimentary_admin_access(session, user)


async def get_user_by_id(user_id: int) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not getattr(user, "ref_code", None):
            await _ensure_ref_code(session, user)
            await session.commit()
            await session.refresh(user)
        user = await _sync_complimentary_admin_access(session, user)
        # Load active device slot add-ons so that public subscription surfaces
        # (client.amonoraconnect.com) report the correct device_limit.
        try:
            active_slots = await _active_device_slot_count_for_user(session, user_id)
            setattr(user, "active_device_slot_addons", active_slots)
        except Exception:
            # Non-critical: leave attribute unset; downstream code falls back to 0.
            pass
        return user


async def touch_user_activity(
    *,
    user_id: int | None = None,
    telegram_id: int | None = None,
) -> bool:
    if user_id is None and telegram_id is None:
        return False

    await ensure_schema()

    async with async_session() as session:
        query = select(User)
        if user_id is not None:
            query = query.where(User.id == int(user_id))
        else:
            query = query.where(User.telegram_id == int(telegram_id))
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.last_activity_at = utcnow()
        await session.commit()
        return True


async def get_active_public_subscription_link_for_user(user_id: int) -> PublicSubscriptionLink | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(PublicSubscriptionLink)
            .where(
                PublicSubscriptionLink.user_id == int(user_id),
                PublicSubscriptionLink.is_active.is_(True),
            )
            .order_by(PublicSubscriptionLink.id.desc())
        )
        return result.scalars().first()


async def get_public_subscription_link_by_token(
    token: str,
    *,
    active_only: bool = True,
) -> PublicSubscriptionLink | None:
    await ensure_schema()

    normalized_token = str(token or "").strip()
    if not normalized_token:
        return None

    async with async_session() as session:
        query = select(PublicSubscriptionLink).where(PublicSubscriptionLink.token == normalized_token)
        if active_only:
            query = query.where(PublicSubscriptionLink.is_active.is_(True))
        result = await session.execute(query.order_by(PublicSubscriptionLink.id.desc()))
        return result.scalars().first()


async def get_or_create_public_subscription_link(
    user_id: int,
    *,
    token: str,
) -> PublicSubscriptionLink:
    await ensure_schema()

    normalized_token = str(token or "").strip()
    if not normalized_token:
        raise ValueError("token is required")

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        if user is None:
            raise ValueError("User not found")

        result = await session.execute(
            select(PublicSubscriptionLink)
            .where(
                PublicSubscriptionLink.user_id == int(user_id),
                PublicSubscriptionLink.is_active.is_(True),
            )
            .order_by(PublicSubscriptionLink.id.desc())
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing

        link = PublicSubscriptionLink(
            user_id=int(user_id),
            token=normalized_token,
            is_active=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        return link


async def touch_public_subscription_link(
    link_id: int,
    *,
    viewed_at: datetime | None = None,
    feed_accessed_at: datetime | None = None,
) -> PublicSubscriptionLink | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PublicSubscriptionLink).where(PublicSubscriptionLink.id == int(link_id)))
        link = result.scalar_one_or_none()
        if link is None:
            return None

        current = utcnow()
        if viewed_at is not None:
            link.last_viewed_at = viewed_at
        if feed_accessed_at is not None:
            link.last_feed_accessed_at = feed_accessed_at
        link.updated_at = current
        await session.commit()
        await session.refresh(link)
        return link


async def get_public_subscription_routes_for_user(user_id: int) -> list[PublicSubscriptionRoute]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(PublicSubscriptionRoute)
            .where(PublicSubscriptionRoute.user_id == int(user_id))
            .order_by(PublicSubscriptionRoute.country_code.asc(), PublicSubscriptionRoute.slot_index.asc())
        )
        return list(result.scalars().all())


async def create_public_subscription_route(
    *,
    user_id: int,
    country_code: str,
    slot_index: int,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None = None,
    client_data: dict | None = None,
    status: str = "active",
) -> PublicSubscriptionRoute:
    await ensure_schema()

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        if user is None:
            raise ValueError("User not found")

        route = PublicSubscriptionRoute(
            user_id=int(user_id),
            country_code=str(country_code or "").strip().lower(),
            slot_index=max(int(slot_index or 1), 1),
            protocol=str(protocol or "vless").strip().lower() or "vless",
            client_uuid=str(client_uuid or "").strip(),
            email=str(email or "").strip(),
            xui_client_id=str(xui_client_id or "").strip() or None,
            client_data=json.dumps(client_data, ensure_ascii=False) if client_data else None,
            status=str(status or "active").strip().lower() or "active",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(route)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(
                select(PublicSubscriptionRoute).where(
                    PublicSubscriptionRoute.user_id == int(user_id),
                    PublicSubscriptionRoute.country_code == str(country_code or "").strip().lower(),
                    PublicSubscriptionRoute.slot_index == max(int(slot_index or 1), 1),
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return existing
        await session.refresh(route)
        return route


async def update_public_subscription_route(
    route_id: int,
    *,
    xui_client_id: str | None = None,
    client_data: dict | None = None,
    status: str | None = None,
    disabled_at: datetime | None | object = _UNSET,
) -> PublicSubscriptionRoute | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(PublicSubscriptionRoute).where(PublicSubscriptionRoute.id == int(route_id)))
        route = result.scalar_one_or_none()
        if route is None:
            return None

        if xui_client_id is not None:
            route.xui_client_id = str(xui_client_id).strip() or None
        if client_data is not None:
            route.client_data = json.dumps(client_data, ensure_ascii=False)
        if status is not None:
            route.status = str(status).strip().lower() or route.status
        if disabled_at is not _UNSET:
            route.disabled_at = disabled_at if isinstance(disabled_at, datetime) else None
        route.updated_at = utcnow()
        await session.commit()
        await session.refresh(route)
        return route


async def bind_public_subscription_device_slot(
    user_id: int,
    *,
    fingerprint_hash: str,
    device_payload: dict,
    max_slots: int,
) -> dict[str, int | str | bool]:
    await ensure_schema()

    safe_hash = str(fingerprint_hash or "").strip().lower()
    if not safe_hash:
        raise ValueError("fingerprint_hash is required")

    def _safe_route_metadata(route: PublicSubscriptionRoute) -> dict:
        raw_value = str(getattr(route, "client_data", "") or "").strip()
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async with async_session() as session:
        user = await _lock_user_row(session, int(user_id))
        if user is None:
            raise ValueError("User not found")

        routes = list(
            (
                await session.execute(
                    select(PublicSubscriptionRoute)
                    .where(PublicSubscriptionRoute.user_id == int(user_id))
                    .order_by(PublicSubscriptionRoute.slot_index.asc(), PublicSubscriptionRoute.country_code.asc())
                    .with_for_update()
                )
            ).scalars().all()
        )
        slot_rows: dict[int, list[PublicSubscriptionRoute]] = {}
        for route in routes:
            slot_rows.setdefault(int(route.slot_index or 1), []).append(route)

        selected_slot: int | None = None
        for slot_index, slot_routes in slot_rows.items():
            for route in slot_routes:
                metadata = _safe_route_metadata(route)
                if str(metadata.get("feed_device_fingerprint_hash") or "").strip().lower() == safe_hash:
                    selected_slot = int(slot_index)
                    break
            if selected_slot is not None:
                break

        created = False
        if selected_slot is None:
            occupied_slots: set[int] = set()
            for slot_index, slot_routes in slot_rows.items():
                for route in slot_routes:
                    metadata = _safe_route_metadata(route)
                    if str(metadata.get("feed_device_fingerprint_hash") or "").strip():
                        occupied_slots.add(int(slot_index))
                        break
            for candidate in range(1, max(int(max_slots or 1), 1) + 1):
                if candidate not in slot_rows:
                    continue
                if candidate in occupied_slots:
                    continue
                selected_slot = candidate
                created = True
                break

        if selected_slot is None:
            return {
                "status": "limit_reached",
                "created": False,
                "slot_index": 0,
                "active_devices": len(slot_rows),
            }

        current = utcnow()
        updated_count = 0
        for route in slot_rows.get(int(selected_slot), []):
            metadata = _safe_route_metadata(route)
            for key, value in device_payload.items():
                if key == "feed_device_bound_at" and str(metadata.get("feed_device_bound_at") or "").strip():
                    continue
                metadata[key] = value
            metadata["feed_device_fingerprint_hash"] = safe_hash
            metadata["feed_device_last_seen_at"] = current.isoformat()
            route.client_data = json.dumps(metadata, ensure_ascii=False)
            route.updated_at = current
            updated_count += 1

        await session.commit()
        return {
            "status": "ok",
            "created": created,
            "slot_index": int(selected_slot),
            "active_devices": len(
                [
                    slot_index
                    for slot_index, slot_routes in slot_rows.items()
                    if any(str(_safe_route_metadata(route).get("feed_device_fingerprint_hash") or "").strip() for route in slot_routes)
                ]
            )
            if routes
            else int(bool(updated_count)),
        }


async def clear_public_subscription_device_slot_binding(
    user_id: int,
    *,
    slot_index: int,
    binding_keys: set[str] | None = None,
) -> bool:
    await ensure_schema()

    safe_slot_index = max(int(slot_index or 0), 0)
    if safe_slot_index <= 0:
        return False

    keys_to_clear = {str(key).strip() for key in (binding_keys or set()) if str(key).strip()}

    def _safe_route_metadata(route: PublicSubscriptionRoute) -> dict:
        raw_value = str(getattr(route, "client_data", "") or "").strip()
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async with async_session() as session:
        user = await _lock_user_row(session, int(user_id))
        if user is None:
            return False

        routes = list(
            (
                await session.execute(
                    select(PublicSubscriptionRoute)
                    .where(
                        PublicSubscriptionRoute.user_id == int(user_id),
                        PublicSubscriptionRoute.slot_index == safe_slot_index,
                    )
                    .with_for_update()
                )
            ).scalars().all()
        )
        if not routes:
            return False

        current = utcnow()
        changed = False
        for route in routes:
            metadata = _safe_route_metadata(route)
            route_changed = False
            for key in keys_to_clear:
                if key in metadata:
                    metadata.pop(key, None)
                    route_changed = True
            if not route_changed:
                continue
            route.client_data = json.dumps(metadata, ensure_ascii=False) if metadata else None
            route.updated_at = current
            changed = True

        if not changed:
            return False
        await session.commit()
        return True


async def mark_trial_technical_engagement(
    user_id: int,
    *,
    engaged_at: datetime | None = None,
) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == int(user_id)).with_for_update())
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not has_active_trial_from_user(user):
            return user

        now = engaged_at or utcnow()
        changed = False
        if getattr(user, "trial_activity_level", TRIAL_ACTIVITY_LEVEL_LOW) != TRIAL_ACTIVITY_LEVEL_ACTIVE:
            user.trial_activity_level = TRIAL_ACTIVITY_LEVEL_ACTIVE
            changed = True
        if getattr(user, "trial_engaged_at", None) is None:
            user.trial_engaged_at = now
            changed = True
        if getattr(user, "last_activity_at", None) != now:
            changed = True
        user.last_activity_at = now
        if changed:
            await session.commit()
            await session.refresh(user)
        return user


async def create_vpn_client(
    user_id: int,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None = None,
    client_data: dict | None = None,
) -> VpnClient:
    await ensure_schema()

    async with async_session() as session:  # type: AsyncSession
        user = await _lock_user_row(session, user_id)
        if user is None:
            raise ValueError("User not found")
        active_slots = await _active_device_slot_count_for_user(session, user_id)
        setattr(user, "active_device_slot_addons", active_slots)
        active_clients = int(
            (
                await session.execute(
                    select(func.count()).select_from(VpnClient).where(VpnClient.user_id == int(user_id))
                )
            ).scalar_one()
        )
        if active_clients >= get_device_limit_for_user(user):
            raise ValueError("User has reached the current device limit")

        vpn_client = VpnClient(
            user_id=user_id,
            protocol=protocol,
            client_uuid=client_uuid,
            email=email,
            xui_client_id=xui_client_id,
            client_data=json.dumps(client_data, ensure_ascii=False) if client_data else None,
        )
        session.add(vpn_client)
        await session.commit()
        await session.refresh(vpn_client)
        return vpn_client


async def get_vpn_client_by_secret(client_secret: str) -> VpnClient | None:
    await ensure_schema()

    secret = str(client_secret or "").strip()
    if not secret:
        return None

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.client_uuid == secret))
        return result.scalar_one_or_none()


async def activate_vpn_client_device(
    *,
    vpn_client_id: int,
    user_id: int | None,
    country_code: str | None,
    fingerprint_hash: str,
    device_label: str | None,
    platform: str | None,
    app_version: str | None,
    source_ip: str | None,
    user_agent: str | None,
    max_devices: int,
) -> dict[str, int | str | bool]:
    await ensure_schema()

    safe_hash = str(fingerprint_hash or "").strip().lower()
    if not safe_hash:
        raise ValueError("fingerprint_hash is required")

    safe_country_code = normalize_country_code(country_code)
    safe_device_label = str(device_label or "").strip()[:255] or None
    safe_platform = str(platform or "").strip()[:50] or None
    safe_app_version = str(app_version or "").strip()[:50] or None
    safe_source_ip = str(source_ip or "").strip()[:64] or None
    safe_user_agent = str(user_agent or "").strip()[:500] or None
    max_allowed_devices = max(int(max_devices or 1), 1)
    now = utcnow()

    async with async_session() as session:
        vpn_client = await _lock_vpn_client_row(session, vpn_client_id)
        if vpn_client is None:
            raise ValueError("vpn_client not found")
        existing = (
            await session.execute(
                select(VpnClientActivation).where(
                    VpnClientActivation.vpn_client_id == int(vpn_client_id),
                    VpnClientActivation.fingerprint_hash == safe_hash,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.last_activated_at = now
            existing.activation_count = int(existing.activation_count or 0) + 1
            if safe_device_label:
                existing.device_label = safe_device_label
            if safe_platform:
                existing.platform = safe_platform
            if safe_app_version:
                existing.app_version = safe_app_version
            if safe_source_ip:
                existing.source_ip = safe_source_ip
            if safe_user_agent:
                existing.user_agent = safe_user_agent
            await session.commit()
            await session.refresh(existing)
            active_count = int(
                (
                    await session.execute(
                        select(func.count()).select_from(VpnClientActivation).where(
                            VpnClientActivation.vpn_client_id == int(vpn_client_id)
                        )
                    )
                ).scalar_one()
            )
            return {
                "status": "ok",
                "created": False,
                "activation_id": existing.id,
                "activation_count": int(existing.activation_count or 1),
                "active_devices": active_count,
            }

        active_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(VpnClientActivation).where(
                        VpnClientActivation.vpn_client_id == int(vpn_client_id)
                    )
                )
            ).scalar_one()
        )
        if active_count >= max_allowed_devices:
            return {
                "status": "limit_reached",
                "created": False,
                "activation_id": 0,
                "activation_count": 0,
                "active_devices": active_count,
            }

        row = VpnClientActivation(
            vpn_client_id=int(vpn_client_id),
            user_id=int(user_id) if user_id is not None else None,
            country_code=safe_country_code,
            fingerprint_hash=safe_hash,
            device_label=safe_device_label,
            platform=safe_platform,
            app_version=safe_app_version,
            source_ip=safe_source_ip,
            user_agent=safe_user_agent,
            activation_count=1,
            first_activated_at=now,
            last_activated_at=now,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

    if user_id is not None:
        await create_control_event(
            category="access",
            severity="INFO",
            event_type="vpn_key_activated",
            title="Новая активация ключа доступа",
            message=(
                f"Пользователь: <code>{user_id}</code>\n"
                f"Устройство: <b>{safe_device_label or safe_platform or 'unknown'}</b>\n"
                f"Страна: <b>{safe_country_code.upper()}</b>\n"
                f"IP: <code>{safe_source_ip or '—'}</code>"
            ),
            entity_type="user",
            entity_id=str(user_id),
            payload={
                "user_id": user_id,
                "vpn_client_id": vpn_client_id,
                "country_code": safe_country_code,
                "platform": safe_platform,
                "device_label": safe_device_label,
                "source_ip": safe_source_ip,
                "fingerprint_hash": safe_hash,
            },
            dedupe_key=f"vpn-activation:{vpn_client_id}:{safe_hash}",
            cooldown_seconds=0,
        )
        await safe_emit_analytics_event(
            event_name=EVENT_FIRST_CONNECTION_SUCCESS,
            occurred_at=now,
            user_id=int(user_id),
            dedupe_key=f"first-connection:{int(row.id)}",
            vpn_client_id=int(vpn_client_id),
            country_code=safe_country_code,
            payload={
                "device_label": safe_device_label,
                "platform": safe_platform,
                "source_ip": safe_source_ip,
                "fingerprint_hash": safe_hash,
                "activation_count": 1,
            },
        )

    return {
        "status": "ok",
        "created": True,
        "activation_id": row.id,
        "activation_count": 1,
        "active_devices": active_count + 1,
    }


async def create_external_payment_record(
    user_id: int | None,
    external_payment_id: str,
    tariff_code: str,
    payment_method: str,
    amount: int,
    currency: str,
    duration_days: int,
    note: str | None = None,
    *,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
    balance_applied_amount: int = 0,
    metadata: dict | None = None,
    expires_at=None,
) -> PaymentRecord:
    await ensure_schema()

    async with async_session() as session:
        await _lock_user_row(session, user_id)
        existing = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.external_payment_id == external_payment_id,
            )
        )
        record = existing.scalar_one_or_none()
        if record is not None:
            return record

        effective_metadata = _with_payment_metadata_defaults(
            metadata,
            payment_method=payment_method,
            external_payment_id=external_payment_id,
        )
        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=external_payment_id,
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_status="pending",
                amount=amount,
                list_price_amount=list_price_amount if list_price_amount is not None else amount,
                balance_reserved_amount=max(int(balance_reserved_amount), 0),
                balance_applied_amount=max(int(balance_applied_amount), 0),
                currency=currency,
                duration_days=duration_days,
                note=note,
                metadata_json=json.dumps(effective_metadata, ensure_ascii=False) if effective_metadata else None,
                expires_at=expires_at,
            )
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.execute(
                select(PaymentRecord).where(
                    PaymentRecord.payment_method == payment_method,
                    PaymentRecord.external_payment_id == external_payment_id,
                )
            )
            record = existing.scalar_one_or_none()
            if record is None:
                raise
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def get_payment_record_by_id(record_id: int) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id))
        return result.scalar_one_or_none()


async def list_payment_records(
    *,
    user_id: int | None = None,
    payment_method: str | None = None,
    statuses: set[str] | None = None,
) -> list[PaymentRecord]:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        query = select(PaymentRecord).order_by(PaymentRecord.created_at.desc())
        if user_id is not None:
            query = query.where(PaymentRecord.user_id == user_id)
        if payment_method is not None:
            query = query.where(PaymentRecord.payment_method == payment_method)
        if statuses:
            query = query.where(PaymentRecord.payment_status.in_(sorted(statuses)))
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_payment_records_by_ids(record_ids: list[int] | set[int] | tuple[int, ...]) -> list[PaymentRecord]:
    await ensure_schema()

    normalized_ids = sorted({int(item) for item in record_ids if item is not None})
    if not normalized_ids:
        return []

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        query = (
            select(PaymentRecord)
            .where(PaymentRecord.id.in_(normalized_ids))
            .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_confirmed_payment_records_missing_effect(*, limit: int = 50) -> list[PaymentRecord]:
    await ensure_schema()

    safe_limit = max(int(limit or 0), 1)
    fetch_limit = max(safe_limit * 5, safe_limit)
    async with async_session() as session:
        query = (
            select(PaymentRecord)
            .where(PaymentRecord.payment_status == "confirmed")
            .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
            .limit(fetch_limit)
        )
        result = await session.execute(query)
        rows = list(result.scalars().all())
    missing = [row for row in rows if not payment_record_effect_applied(row)]
    return missing[:safe_limit]


async def list_confirmed_payment_records_needing_full_reconcile(*, limit: int = 50) -> list[PaymentRecord]:
    await ensure_schema()

    safe_limit = max(int(limit or 0), 1)
    fetch_limit = max(safe_limit * 12, safe_limit)
    async with async_session() as session:
        query = (
            select(PaymentRecord)
            .where(PaymentRecord.payment_status == "confirmed")
            .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
            .limit(fetch_limit)
        )
        result = await session.execute(query)
        rows = list(result.scalars().all())
    return [row for row in rows if payment_record_reconcile_state(row) != "converged"][:safe_limit]


async def list_confirmed_applied_subscription_records_needing_access_sync(*, limit: int = 50) -> list[PaymentRecord]:
    await ensure_schema()

    safe_limit = max(int(limit or 0), 1)
    fetch_limit = max(safe_limit * 8, safe_limit)
    async with async_session() as session:
        query = (
            select(PaymentRecord)
            .where(PaymentRecord.payment_status == "confirmed")
            .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
            .limit(fetch_limit)
        )
        result = await session.execute(query)
        rows = list(result.scalars().all())
    return [
        row
        for row in rows
        if payment_record_effect_applied(row)
        and payment_record_effect_kind(row) == "subscription_activation"
        and payment_record_access_sync_state(row) != "success"
    ][:safe_limit]


async def list_confirmed_revenue_payment_records_missing_finance_marker(*, limit: int = 50) -> list[PaymentRecord]:
    await ensure_schema()

    from dashboard.finance import payment_method_counts_as_revenue

    safe_limit = max(int(limit or 0), 1)
    fetch_limit = max(safe_limit * 8, safe_limit)
    async with async_session() as session:
        query = (
            select(PaymentRecord)
            .where(
                PaymentRecord.payment_status == "confirmed",
                PaymentRecord.amount > 0,
            )
            .order_by(PaymentRecord.confirmed_at.asc().nullsfirst(), PaymentRecord.id.asc())
            .limit(fetch_limit)
        )
        result = await session.execute(query)
        rows = list(result.scalars().all())
    return [
        row
        for row in rows
        if payment_method_counts_as_revenue(getattr(row, "payment_method", None))
        and not payment_record_finance_synced(row)
    ][:safe_limit]


async def get_payment_record_by_external_id(
    payment_method: str,
    external_payment_id: str,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.external_payment_id == external_payment_id,
            )
        )
        return result.scalar_one_or_none()


async def create_manual_payment_record(
    user_id: int,
    tariff_code: str,
    payment_method: str,
    amount: int,
    currency: str,
    duration_days: int,
    note: str | None = None,
    metadata: dict | None = None,
    expires_at=None,
    *,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
    balance_applied_amount: int = 0,
) -> PaymentRecord:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        await _lock_user_row(session, user_id)
        existing_result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.user_id == user_id,
                PaymentRecord.tariff_code == tariff_code,
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.payment_status.in_(sorted(MANUAL_PAYMENT_OPEN_STATUSES)),
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        generated_external_payment_id = f"manual_{payment_method}_{uuid4().hex[:16]}"
        effective_metadata = _with_payment_metadata_defaults(
            metadata,
            payment_method=payment_method,
            external_payment_id=generated_external_payment_id,
        )
        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=generated_external_payment_id,
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_status="awaiting_user_payment",
                amount=amount,
                list_price_amount=list_price_amount if list_price_amount is not None else amount,
                balance_reserved_amount=max(int(balance_reserved_amount), 0),
                balance_applied_amount=max(int(balance_applied_amount), 0),
                currency=currency,
                duration_days=duration_days,
                note=note,
                metadata_json=json.dumps(effective_metadata, ensure_ascii=False) if effective_metadata else None,
                expires_at=expires_at,
            )
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def mark_manual_payment_record_submitted(
    record_id: int,
    *,
    reference: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id))
        record = result.scalar_one_or_none()
        if record is None:
            return None
        if record.payment_status not in MANUAL_PAYMENT_OPEN_STATUSES:
            return record

        record.payment_status = "awaiting_admin_review"
        if reference:
            record.reference = reference.strip()[:255]
        if note:
            record.note = note
        if metadata:
            merged_metadata = {
                **_load_payment_metadata(record.metadata_json),
                **metadata,
            }
            record.metadata_json = json.dumps(merged_metadata, ensure_ascii=False)
        await session.commit()
        await session.refresh(record)
        return record


async def cancel_manual_payment_record(record_id: int, *, reason: str | None = None) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id))
        record = result.scalar_one_or_none()
        if record is None:
            return None
        if record.payment_status not in MANUAL_PAYMENT_OPEN_STATUSES:
            return record

        record.payment_status = "cancelled"
        record.rejection_reason = (reason or "Заявка отменена пользователем.")[:1000]
        await _release_reserved_balance_for_record(session, record, reason="payment_cancelled")
        await session.commit()
        await session.refresh(record)
        await _emit_payment_failed_analytics(record)
        return record


async def review_manual_payment_record(
    record_id: int,
    *,
    reviewer_actor_id: str,
    reviewer_actor_name: str,
    action: str,
    reason: str | None = None,
) -> tuple[PaymentRecord | None, bool]:
    await ensure_schema()

    if action not in {"confirm", "reject"}:
        raise ValueError("Unsupported payment review action")

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None, False

        if record.payment_status == "confirmed" and action == "confirm":
            return record, False
        if record.payment_status == "rejected" and action == "reject":
            return record, False
        if record.payment_status not in MANUAL_PAYMENT_OPEN_STATUSES | {"pending"}:
            return record, False

        now = utcnow()
        record.reviewed_by_actor_id = reviewer_actor_id[:255]
        record.reviewed_by_actor_name = reviewer_actor_name[:255]
        record.reviewed_at = now

        if action == "confirm":
            record.payment_status = "confirmed"
            record.confirmed_at = now
            record.rejection_reason = None
            await _apply_reserved_balance_for_record(session, record, reason="payment_confirmed")
        else:
            record.payment_status = "rejected"
            record.rejection_reason = (reason or "Платёж отклонён администратором.")[:1000]
            await _release_reserved_balance_for_record(session, record, reason="payment_rejected")

        await session.commit()
        await session.refresh(record)
        if action == "reject":
            await _emit_payment_failed_analytics(record)
        return record, True


async def confirm_external_payment_record(
    payment_method: str,
    external_payment_id: str,
    note: str | None = None,
) -> tuple[PaymentRecord | None, bool]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.external_payment_id == external_payment_id,
            ).with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None, False

        just_confirmed = False
        if record.payment_status != "confirmed":
            record.payment_status = "confirmed"
            record.confirmed_at = utcnow()
            await _apply_reserved_balance_for_record(session, record, reason="payment_confirmed")
            just_confirmed = True

        if note:
            record.note = note

        await session.commit()
        await session.refresh(record)
        return record, just_confirmed


async def get_open_payment_record_for_user(
    *,
    user_id: int,
    tariff_code: str,
    payment_method: str,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(
            select(PaymentRecord)
            .where(
                PaymentRecord.user_id == user_id,
                PaymentRecord.tariff_code == tariff_code,
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.payment_status.in_(sorted(BALANCE_HOLD_PAYMENT_STATUSES)),
            )
            .order_by(PaymentRecord.created_at.desc(), PaymentRecord.id.desc())
        )
        return result.scalar_one_or_none()


def _payment_record_matches_open_intent(
    record: PaymentRecord,
    *,
    list_price_amount: int | None = None,
    duration_days: int | None = None,
    product_type: str | None = None,
    payload_type: str | None = None,
    slots_count: int | None = None,
) -> bool:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))

    if list_price_amount is not None:
        record_price = int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0)
        if record_price != int(list_price_amount):
            return False
    if duration_days is not None and int(getattr(record, "duration_days", 0) or 0) != int(duration_days):
        return False
    if product_type is not None and str(metadata.get("product_type") or "").strip().lower() != str(product_type).strip().lower():
        return False
    if payload_type is not None and str(metadata.get("payload_type") or "").strip().lower() != str(payload_type).strip().lower():
        return False
    if slots_count is not None and int(metadata.get("slots_count") or 0) != int(slots_count):
        return False
    return True


async def get_open_payment_intent_for_user(
    *,
    user_id: int,
    tariff_code: str,
    list_price_amount: int | None = None,
    duration_days: int | None = None,
    product_type: str | None = None,
    payload_type: str | None = None,
    slots_count: int | None = None,
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        result = await session.execute(
            select(PaymentRecord)
            .where(
                PaymentRecord.user_id == user_id,
                PaymentRecord.tariff_code == tariff_code,
                PaymentRecord.payment_status.in_(sorted(BALANCE_HOLD_PAYMENT_STATUSES)),
            )
            .order_by(PaymentRecord.created_at.desc(), PaymentRecord.id.desc())
        )
        rows = list(result.scalars().all())

    for record in rows:
        if _payment_record_matches_open_intent(
            record,
            list_price_amount=list_price_amount,
            duration_days=duration_days,
            product_type=product_type,
            payload_type=payload_type,
            slots_count=slots_count,
        ):
            return record
    return None


async def get_user_balance_summary(user_id: int) -> dict[str, int]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return {"balance_rub": 0, "balance_reserved_rub": 0, "balance_available_rub": 0}
        return {
            "balance_rub": int(getattr(user, "balance_rub", 0)),
            "balance_reserved_rub": int(getattr(user, "balance_reserved_rub", 0)),
            "balance_available_rub": _available_balance_from_user(user),
        }


async def credit_user_balance(
    user_id: int,
    *,
    amount: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        if user is None:
            return None
        credited_amount = await _credit_user_balance(
            session,
            user,
            amount=amount,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
        )
        if credited_amount <= 0:
            return None
        await session.commit()
        await session.refresh(user)
        return user


async def build_balance_breakdown_for_price(user_id: int, list_price_amount: int) -> dict[str, int]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        available_balance = _available_balance_from_user(user) if user is not None else 0
        applied_balance = min(max(int(list_price_amount), 0), available_balance)
        return {
            "list_price_amount": int(list_price_amount),
            "balance_available_rub": available_balance,
            "balance_amount": applied_balance,
            "payable_amount": max(int(list_price_amount) - applied_balance, 0),
        }


async def create_balance_aware_manual_payment_record(
    *,
    user_id: int,
    tariff_code: str,
    payment_method: str,
    list_price_amount: int,
    currency: str,
    duration_days: int,
    note: str | None = None,
    metadata: dict | None = None,
    expires_at=None,
) -> PaymentRecord:
    await ensure_schema()

    async with async_session() as session:
        await _expire_open_manual_payment_records(session)
        user = await _lock_user_row(session, user_id)
        existing_result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.user_id == user_id,
                PaymentRecord.tariff_code == tariff_code,
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.payment_status.in_(sorted(MANUAL_PAYMENT_OPEN_STATUSES)),
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        available_balance = _available_balance_from_user(user) if user is not None else 0
        reserved_amount = min(max(int(list_price_amount), 0), available_balance)

        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=f"manual_{payment_method}_{uuid4().hex[:16]}",
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_status="awaiting_user_payment",
                amount=max(int(list_price_amount) - reserved_amount, 0),
                list_price_amount=int(list_price_amount),
                balance_reserved_amount=reserved_amount,
                balance_applied_amount=0,
                currency=currency,
                duration_days=duration_days,
                note=note,
                metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                expires_at=expires_at,
            )
        )
        session.add(record)
        await session.flush()

        if user is not None and reserved_amount > 0:
            await _reserve_user_balance(
                session,
                user,
                amount=reserved_amount,
                reason="payment_reserved",
                reference_type="payment_record",
                reference_id=str(record.id),
                note=f"Резерв под платёж #{record.id}",
            )

        await session.commit()
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def create_balance_aware_external_payment_record(
    *,
    user_id: int,
    tariff_code: str,
    payment_method: str,
    external_payment_id: str,
    list_price_amount: int,
    currency: str,
    duration_days: int,
    note: str | None = None,
    metadata: dict | None = None,
    expires_at=None,
) -> PaymentRecord:
    await ensure_schema()

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        result = await session.execute(
            select(PaymentRecord).where(
                PaymentRecord.payment_method == payment_method,
                PaymentRecord.external_payment_id == external_payment_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        available_balance = _available_balance_from_user(user) if user is not None else 0
        reserved_amount = min(max(int(list_price_amount), 0), available_balance)

        effective_metadata = _with_payment_metadata_defaults(
            metadata,
            payment_method=payment_method,
            external_payment_id=external_payment_id,
        )
        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=external_payment_id,
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_status="pending",
                amount=max(int(list_price_amount) - reserved_amount, 0),
                list_price_amount=int(list_price_amount),
                balance_reserved_amount=reserved_amount,
                balance_applied_amount=0,
                currency=currency,
                duration_days=duration_days,
                note=note,
                metadata_json=json.dumps(effective_metadata, ensure_ascii=False) if effective_metadata else None,
                expires_at=expires_at,
            )
        )
        session.add(record)
        await session.flush()

        if user is not None and reserved_amount > 0:
            await _reserve_user_balance(
                session,
                user,
                amount=reserved_amount,
                reason="payment_reserved",
                reference_type="payment_record",
                reference_id=str(record.id),
                note=f"Резерв под внешний платёж #{record.id}",
            )

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.execute(
                select(PaymentRecord).where(
                    PaymentRecord.payment_method == payment_method,
                    PaymentRecord.external_payment_id == external_payment_id,
                )
            )
            record = existing.scalar_one_or_none()
            if record is None:
                raise
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def create_balance_only_payment_record(
    *,
    user_id: int,
    tariff_code: str,
    duration_days: int,
    payment_source: str = "balance_rub",
) -> PaymentRecord | None:
    await ensure_schema()

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        if user is None:
            return None

        from bot.utils.tariffs import get_tariff

        tariff = get_tariff(tariff_code)
        if tariff is None:
            return None

        if _available_balance_from_user(user) < int(tariff.rub_price):
            return None

        external_payment_id = f"{payment_source}_{uuid4().hex[:16]}"
        metadata = _with_payment_metadata_defaults(
            None,
            payment_method=payment_source,
            external_payment_id=external_payment_id,
        )
        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=external_payment_id,
                tariff_code=tariff.code,
                payment_method=payment_source,
                payment_status="confirmed",
                amount=0,
                list_price_amount=int(tariff.rub_price),
                balance_reserved_amount=0,
                balance_applied_amount=int(tariff.rub_price),
                currency="RUB",
                duration_days=duration_days,
                metadata_json=json.dumps(metadata, ensure_ascii=False),
                confirmed_at=utcnow(),
            )
        )
        session.add(record)
        await session.flush()
        user.balance_rub = int(getattr(user, "balance_rub", 0)) - int(tariff.rub_price)
        _append_balance_event(
            session,
            user_id=user.id,
            amount=int(tariff.rub_price),
            direction="debit",
            reason="balance_payment",
            reference_type="payment_record",
            reference_id=str(record.id),
            note=f"Полная оплата тарифа {tariff.code} балансом",
        )

        await session.commit()
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def create_balance_only_custom_payment_record(
    *,
    user_id: int,
    tariff_code: str,
    list_price_amount: int,
    duration_days: int,
    payment_source: str = "balance_rub",
    currency: str = "RUB",
    note: str | None = None,
    metadata: dict | None = None,
) -> PaymentRecord | None:
    await ensure_schema()

    safe_amount = max(int(list_price_amount), 0)
    if safe_amount <= 0:
        return None

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)
        if user is None:
            return None
        if _available_balance_from_user(user) < safe_amount:
            return None

        external_payment_id = f"{payment_source}_{uuid4().hex[:16]}"
        effective_metadata = _with_payment_metadata_defaults(
            metadata,
            payment_method=payment_source,
            external_payment_id=external_payment_id,
        )
        record = PaymentRecord(
            **_payment_record_kwargs(
                user_id=user_id,
                external_payment_id=external_payment_id,
                tariff_code=tariff_code,
                payment_method=payment_source,
                payment_status="confirmed",
                amount=0,
                list_price_amount=safe_amount,
                balance_reserved_amount=0,
                balance_applied_amount=safe_amount,
                currency=currency,
                duration_days=duration_days,
                note=note,
                metadata_json=json.dumps(effective_metadata, ensure_ascii=False) if effective_metadata else None,
                confirmed_at=utcnow(),
            )
        )
        session.add(record)
        await session.flush()
        user.balance_rub = int(getattr(user, "balance_rub", 0)) - safe_amount
        _append_balance_event(
            session,
            user_id=user.id,
            amount=safe_amount,
            direction="debit",
            reason="balance_payment",
            reference_type="payment_record",
            reference_id=str(record.id),
            note=note or f"Полная оплата {tariff_code} балансом",
        )

        await session.commit()
        await session.refresh(record)
        await _emit_payment_started_analytics(record)
        return record


async def get_user_vpn_client(user_id: int):
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.user_id == user_id))
        return result.scalar_one_or_none()


async def has_active_trial(user_id: int) -> bool:
    user = await get_user_by_id(user_id)
    return bool(user and has_active_trial_from_user(user))


async def has_active_subscription(user_id: int) -> bool:
    user = await get_user_by_id(user_id)
    return bool(user and has_active_subscription_from_user(user))


async def has_active_access(user_id: int) -> bool:
    user = await get_user_by_id(user_id)
    return bool(user and has_active_access_from_user(user))


async def get_access_expires_at(user_id: int):
    user = await get_user_by_id(user_id)
    if user is None:
        return None
    return get_access_expires_at_from_user(user)


async def mark_vpn_repair_needed(user_id: int, reason: str) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        user.vpn_repair_needed = True
        user.vpn_repair_reason = reason[:1000]
        user.vpn_repair_marked_at = utcnow()

        await session.commit()
        await session.refresh(user)
        await create_control_event(
            category="access",
            severity="WARNING",
            event_type="access_issue_marked",
            title="Проблема с доступом",
            message=(
                f"Пользователь: <code>{user.id}</code>\n"
                f"Telegram ID: <code>{user.telegram_id}</code>\n"
                f"Причина: <b>{user.vpn_repair_reason or 'unknown'}</b>"
            ),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "reason": user.vpn_repair_reason,
            },
            dedupe_key=f"vpn-repair:{user.id}",
        )
        return user


async def clear_vpn_repair_needed(user_id: int, *, emit_control_event: bool = True) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        user.vpn_repair_needed = False
        user.vpn_repair_reason = None
        user.vpn_repair_marked_at = None

        await session.commit()
        await session.refresh(user)
        if emit_control_event:
            await create_control_event(
                category="access",
                severity="INFO",
                event_type="access_issue_cleared",
                title="Проблема с доступом устранена",
                message=(
                    f"Пользователь: <code>{user.id}</code>\n"
                    f"Telegram ID: <code>{user.telegram_id}</code>\n"
                    "Маркер repair-needed снят."
                ),
                entity_type="user",
                entity_id=str(user.id),
                payload={
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                },
                dedupe_key=f"vpn-repair-cleared:{user.id}",
                resolve_dedupe_key=f"vpn-repair:{user.id}",
                cooldown_seconds=0,
            )
        return user


async def get_vpn_repair_needed(user_id: int) -> dict | None:
    user = await get_user_by_id(user_id)
    if user is None:
        return None
    return {
        "repair_needed": bool(getattr(user, "vpn_repair_needed", False)),
        "reason": getattr(user, "vpn_repair_reason", None),
        "marked_at": getattr(user, "vpn_repair_marked_at", None),
    }


async def create_vpn_repair_event(
    user_id: int,
    result: str,
    reason: str | None = None,
) -> VpnRepairEvent:
    await ensure_schema()

    async with async_session() as session:
        event = VpnRepairEvent(
            user_id=user_id,
            result=result[:32],
            reason=reason[:255] if reason else None,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def list_vpn_repair_events(user_id: int, limit: int = 5) -> list[VpnRepairEvent]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(VpnRepairEvent)
            .where(VpnRepairEvent.user_id == user_id)
            .order_by(VpnRepairEvent.created_at.desc(), VpnRepairEvent.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def activate_trial(user_id: int) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()

        if user is None:
            return None
        if not can_activate_trial_from_user(user):
            raise ValueError("Пробный доступ уже недоступен для этого пользователя")

        now = utcnow()
        user.trial_used = True
        user.trial_started_at = now
        user.trial_expires_at = now + timedelta(days=config.trial_days)
        user.trial_channel_unsubscribed_at = None
        user.trial_activity_level = TRIAL_ACTIVITY_LEVEL_LOW
        user.trial_engaged_at = None
        user.last_activity_at = now

        await session.commit()
        await session.refresh(user)
        await mark_recent_campaign_conversion(user.id, reason="trial_started")
        await mark_recent_channel_post_conversion(user.id, reason="trial_started")
        await create_control_event(
            category="users",
            severity="INFO",
            event_type="trial_started",
            title="Старт пробного периода",
            message=_trial_started_control_event_message(user.id, user.telegram_id, user.trial_expires_at),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "trial_expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
            },
            dedupe_key=f"trial-started:{user.id}:{user.trial_expires_at.isoformat() if user.trial_expires_at else 'none'}",
            cooldown_seconds=0,
        )
        await safe_emit_analytics_event(
            event_name=EVENT_TRIAL_STARTED,
            occurred_at=now,
            user_id=int(user.id),
            telegram_id=getattr(user, "telegram_id", None),
            dedupe_key=f"trial-started:{int(user.id)}",
            payload={
                "trial_expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
            },
        )
        return user


async def pause_trial_for_channel_unsubscribe(user_id: int, *, paused_at: datetime | None = None) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not has_trial_window_from_user(user):
            return user
        if has_active_subscription_from_user(user):
            return user
        if trial_is_paused_by_channel_from_user(user):
            return user

        marker = paused_at or utcnow()
        user.trial_channel_unsubscribed_at = marker
        await session.commit()
        await session.refresh(user)

    await create_control_event(
        category="users",
        severity="WARNING",
        event_type="trial_channel_unsubscribed",
        title="Пробный доступ приостановлен из-за отписки от канала",
        message=_trial_channel_state_control_event_message(
            user.id,
            user.telegram_id,
            suspended_at=user.trial_channel_unsubscribed_at,
            trial_expires_at=user.trial_expires_at,
        ),
        entity_type="user",
        entity_id=str(user.id),
        payload={
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "trial_channel_unsubscribed_at": user.trial_channel_unsubscribed_at.isoformat() if user.trial_channel_unsubscribed_at else None,
            "trial_expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
        },
        dedupe_key=f"trial-channel-paused:{user.id}:{user.trial_channel_unsubscribed_at.isoformat() if user.trial_channel_unsubscribed_at else 'none'}",
        cooldown_seconds=0,
    )
    return user


async def resume_trial_after_channel_resubscribe(user_id: int) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not has_trial_window_from_user(user):
            return user
        if has_active_subscription_from_user(user):
            return user
        if not trial_is_paused_by_channel_from_user(user):
            return user

        user.trial_channel_unsubscribed_at = None
        user.last_activity_at = utcnow()
        await session.commit()
        await session.refresh(user)

    await create_control_event(
        category="users",
        severity="INFO",
        event_type="trial_channel_resubscribed",
        title="Пробный доступ возобновлён после возвращения в канал",
        message=(
            f"User: <code>{user.id}</code> • Tg ID: <code>{user.telegram_id if user.telegram_id is not None else '—'}</code> • "
            f"Trial до: <b>{user.trial_expires_at.strftime('%Y-%m-%d %H:%M:%S') if user.trial_expires_at else '—'}</b>"
        ),
        entity_type="user",
        entity_id=str(user.id),
        payload={
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "trial_expires_at": user.trial_expires_at.isoformat() if user.trial_expires_at else None,
        },
        dedupe_key=f"trial-channel-resumed:{user.id}:{user.trial_expires_at.isoformat() if user.trial_expires_at else 'none'}",
        cooldown_seconds=0,
    )
    return user


async def activate_paid_subscription(
    user_id: int,
    tariff_code: str,
    payment_id: str,
    duration_days: int,
    payment_source: str = "telegram_stars",
) -> User | None:
    del payment_id
    await ensure_schema()

    async with async_session() as session:
        user = await _lock_user_row(session, user_id)

        if user is None:
            return None

        now = utcnow()
        was_active = has_active_subscription_from_user(user)
        base = user.subscription_expires_at if was_active else now

        user.subscription_started_at = user.subscription_started_at or now
        user.subscription_expires_at = base + timedelta(days=duration_days)
        user.subscription_status = "active"
        user.subscription_source = payment_source
        user.last_activity_at = now

        await session.commit()
        await session.refresh(user)
        await mark_recent_campaign_conversion(user.id, reason="subscription_activated")
        await mark_recent_channel_post_conversion(user.id, reason="subscription_activated")
        event_type = "subscription_extended" if was_active else "subscription_activated"
        title = "Подписка продлена" if was_active else "Платный доступ активирован"
        payment_kind = PAYMENT_KIND_RENEWAL if was_active else PAYMENT_KIND_NEW
        analytics_event_name = EVENT_SUBSCRIPTION_RENEWED if was_active else EVENT_SUBSCRIPTION_ACTIVATED
        await create_control_event(
            category="users",
            severity="INFO",
            event_type=event_type,
            title=title,
            message=(
                f"Пользователь: <code>{user.id}</code>\n"
                f"Telegram ID: <code>{user.telegram_id}</code>\n"
                f"Источник: <b>{payment_source}</b>\n"
                f"Доступ до: <b>{user.subscription_expires_at.strftime('%Y-%m-%d %H:%M:%S')}</b>"
            ),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "payment_source": payment_source,
                "duration_days": duration_days,
                "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            },
            dedupe_key=f"{event_type}:{user.id}:{user.subscription_expires_at.isoformat() if user.subscription_expires_at else 'none'}",
            cooldown_seconds=0,
        )
        await safe_emit_analytics_event(
            event_name=analytics_event_name,
            occurred_at=now,
            user_id=int(user.id),
            telegram_id=getattr(user, "telegram_id", None),
            dedupe_key=f"{'subscription-renewed' if was_active else 'subscription-activated'}:{int(user.id)}:{user.subscription_expires_at.isoformat() if user.subscription_expires_at else 'none'}",
            tariff_code=str(tariff_code or "").strip() or None,
            payment_method=str(payment_source or "").strip() or None,
            payload={
                "payment_source": payment_source,
                "duration_days": duration_days,
                "payment_kind": payment_kind,
                "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            },
        )
        setattr(user, "_subscription_payment_kind", payment_kind)
        setattr(user, "_subscription_analytics_event_name", analytics_event_name)
        return user


def _qualifying_referral_payment_query(*, user_id: int):
    return (
        select(PaymentRecord)
        .where(
            PaymentRecord.user_id == user_id,
            PaymentRecord.payment_status == "confirmed",
            PaymentRecord.duration_days > 0,
            PaymentRecord.tariff_code.in_(sorted({"1m", "3m", "6m", "12m"})),
        )
        .order_by(PaymentRecord.confirmed_at.asc(), PaymentRecord.created_at.asc(), PaymentRecord.id.asc())
    )


async def process_referral_reward_for_payment(payment_record_id: int) -> ReferralRewardOutcome:
    await ensure_schema()

    async with async_session() as session:
        payment = (
            await session.execute(
                select(PaymentRecord).where(PaymentRecord.id == payment_record_id).with_for_update()
            )
        ).scalar_one_or_none()
        if (
            payment is None
            or payment.user_id is None
            or payment.payment_status != "confirmed"
            or int(getattr(payment, "duration_days", 0) or 0) <= 0
        ):
            return ReferralRewardOutcome(False, None, None, None, None, 0, 0, 0, 0, None, None)

        bonus_amount = referral_bonus_for_tariff(payment.tariff_code)
        tariff = get_tariff(payment.tariff_code or "")
        if bonus_amount <= 0:
            return ReferralRewardOutcome(False, None, None, None, None, 0, 0, 0, 0, payment.tariff_code, tariff.title if tariff else None)

        existing_reward = (
            await session.execute(select(ReferralReward).where(ReferralReward.payment_record_id == payment.id))
        ).scalar_one_or_none()
        if existing_reward is not None:
            referrer = await _lock_user_row(session, existing_reward.referrer_user_id)
            invited_user = await _lock_user_row(session, existing_reward.invited_user_id)
            return ReferralRewardOutcome(
                False,
                existing_reward.referrer_user_id,
                existing_reward.invited_user_id,
                getattr(referrer, "telegram_id", None),
                getattr(invited_user, "telegram_id", None),
                int(getattr(existing_reward, "bonus_referrer_rub", 0) or 0),
                int(getattr(existing_reward, "bonus_invited_rub", 0) or 0),
                int(getattr(referrer, "balance_rub", 0) or 0),
                int(getattr(invited_user, "balance_rub", 0) or 0),
                payment.tariff_code,
                tariff.title if tariff else None,
            )

        invited_user = await _lock_user_row(session, payment.user_id)
        if invited_user is None or invited_user.referred_by_user_id is None:
            return ReferralRewardOutcome(False, None, None, None, None, 0, 0, 0, 0, payment.tariff_code, tariff.title if tariff else None)

        prior_reward = (
            await session.execute(select(ReferralReward).where(ReferralReward.invited_user_id == invited_user.id))
        ).scalar_one_or_none()
        if prior_reward is not None:
            referrer = await _lock_user_row(session, prior_reward.referrer_user_id)
            return ReferralRewardOutcome(
                False,
                prior_reward.referrer_user_id,
                invited_user.id,
                getattr(referrer, "telegram_id", None),
                getattr(invited_user, "telegram_id", None),
                int(getattr(prior_reward, "bonus_referrer_rub", 0) or 0),
                int(getattr(prior_reward, "bonus_invited_rub", 0) or 0),
                int(getattr(referrer, "balance_rub", 0) or 0),
                int(getattr(invited_user, "balance_rub", 0) or 0),
                payment.tariff_code,
                tariff.title if tariff else None,
            )

        first_payment = (await session.execute(_qualifying_referral_payment_query(user_id=invited_user.id))).scalars().first()
        if first_payment is None or first_payment.id != payment.id:
            return ReferralRewardOutcome(False, None, invited_user.id, None, getattr(invited_user, "telegram_id", None), 0, 0, 0, int(getattr(invited_user, "balance_rub", 0) or 0), payment.tariff_code, tariff.title if tariff else None)

        referrer = await _lock_user_row(session, invited_user.referred_by_user_id)
        if referrer is None or referrer.id == invited_user.id:
            return ReferralRewardOutcome(False, None, invited_user.id, None, getattr(invited_user, "telegram_id", None), 0, 0, 0, int(getattr(invited_user, "balance_rub", 0) or 0), payment.tariff_code, tariff.title if tariff else None)

        await _ensure_ref_code(session, referrer)
        await _ensure_ref_code(session, invited_user)
        await _ensure_referral_row(session, referrer_user_id=referrer.id, invited_user_id=invited_user.id)
        await _migrate_referral_balance_if_needed(session, referrer)

        session.add(
            ReferralReward(
                referrer_user_id=referrer.id,
                invited_user_id=invited_user.id,
                payment_record_id=payment.id,
                tariff_code=payment.tariff_code,
                bonus_referrer_rub=bonus_amount,
                bonus_invited_rub=bonus_amount,
                status="applied",
            )
        )
        await _credit_user_balance(
            session,
            referrer,
            amount=bonus_amount,
            reason="referral_reward_referrer",
            reference_type="payment_record",
            reference_id=str(payment.id),
            note=f"Реферальный бонус за первую оплату user_id={invited_user.id}",
        )
        await _credit_user_balance(
            session,
            invited_user,
            amount=bonus_amount,
            reason="referral_reward_invited",
            reference_type="payment_record",
            reference_id=str(payment.id),
            note=f"Бонус приглашенному за первый тариф {payment.tariff_code or '—'}",
        )
        _increment_referral_earned_total(referrer, bonus_amount)
        _increment_referral_earned_total(invited_user, bonus_amount)
        invited_user.referral_bonus_granted = True

        await session.commit()
        await session.refresh(referrer)
        await session.refresh(invited_user)
        await create_control_event(
            category="payments",
            severity="INFO",
            event_type="referral_reward_applied",
            title="Реферальный бонус начислен",
            message=(
                f"Платёж: <code>{payment.id}</code>\n"
                f"Реферер: <code>{referrer.id}</code> • Tg ID: <code>{referrer.telegram_id}</code>\n"
                f"Реферал: <code>{invited_user.id}</code> • Tg ID: <code>{invited_user.telegram_id}</code>\n"
                f"Тариф: <b>{tariff.title if tariff else payment.tariff_code or '—'}</b>\n"
                f"Начислено: <b>{bonus_amount} RUB</b> каждой стороне"
            ),
            entity_type="payment_record",
            entity_id=str(payment.id),
            payload={
                "payment_record_id": payment.id,
                "referrer_user_id": referrer.id,
                "invited_user_id": invited_user.id,
                "bonus_rub": bonus_amount,
                "tariff_code": payment.tariff_code,
            },
            dedupe_key=f"referral-reward-applied:{payment.id}",
            cooldown_seconds=0,
        )
        return ReferralRewardOutcome(
            True,
            referrer.id,
            invited_user.id,
            referrer.telegram_id,
            invited_user.telegram_id,
            bonus_amount,
            bonus_amount,
            int(getattr(referrer, "balance_rub", 0) or 0),
            int(getattr(invited_user, "balance_rub", 0) or 0),
            payment.tariff_code,
            tariff.title if tariff else None,
        )


async def reverse_referral_reward_by_payment(payment_record_id: int) -> bool:
    await ensure_schema()

    async with async_session() as session:
        reward = (
            await session.execute(
                select(ReferralReward).where(ReferralReward.payment_record_id == payment_record_id).with_for_update()
            )
        ).scalar_one_or_none()
        if reward is None or reward.status == "reversed":
            return False

        referrer = await _lock_user_row(session, reward.referrer_user_id)
        invited_user = await _lock_user_row(session, reward.invited_user_id)
        if referrer is None or invited_user is None:
            return False

        await _debit_user_balance(
            session,
            referrer,
            amount=reward.bonus_referrer_rub,
            reason="referral_reward_reversal",
            reference_type="payment_record",
            reference_id=str(payment_record_id),
            note=f"Откат реферального бонуса за платеж #{payment_record_id}",
        )
        await _debit_user_balance(
            session,
            invited_user,
            amount=reward.bonus_invited_rub,
            reason="referral_reward_reversal",
            reference_type="payment_record",
            reference_id=str(payment_record_id),
            note=f"Откат бонуса приглашенному за платеж #{payment_record_id}",
        )
        _decrement_referral_earned_total(referrer, reward.bonus_referrer_rub)
        _decrement_referral_earned_total(invited_user, reward.bonus_invited_rub)
        reward.status = "reversed"
        reward.reversed_at = utcnow()
        await session.commit()
        return True


async def grant_referral_bonus_if_needed(referred_user_id: int) -> tuple[bool, User | None]:
    await ensure_schema()

    async with async_session() as session:
        first_payment = (await session.execute(_qualifying_referral_payment_query(user_id=referred_user_id))).scalars().first()
        if first_payment is None:
            return False, None

    outcome = await process_referral_reward_for_payment(first_payment.id)
    if not outcome.referrer_user_id:
        return outcome.applied, None
    referrer = await get_user_by_id(outcome.referrer_user_id)
    return outcome.applied, referrer


async def get_referral_dashboard(user_id: int) -> ReferralDashboard | None:
    await ensure_schema()

    async with async_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            return None

        await _ensure_ref_code(session, user)
        await _migrate_referral_balance_if_needed(session, user)
        await session.commit()
        await session.refresh(user)

        invited_users = list((await session.execute(select(User).where(User.referred_by_user_id == user_id))).scalars().all())
        paid_count = sum(1 for invited_user in invited_users if bool(getattr(invited_user, "referral_bonus_granted", False)))
        earned_total_result = await session.execute(
            select(func.coalesce(func.sum(UserBalanceEvent.amount), 0)).where(
                UserBalanceEvent.user_id == user.id,
                UserBalanceEvent.direction == "credit",
                UserBalanceEvent.reason.in_(sorted(REFERRAL_CREDIT_REASONS)),
            )
        )
        earned_total_rub = int(earned_total_result.scalar_one() or 0)
        current_level, next_level, left_to_next_level, progress_percent = calc_level(paid_count)
        return ReferralDashboard(
            ref_link=build_referral_link(str(user.ref_code)),
            balance_rub=int(getattr(user, "balance_rub", 0) or 0),
            earned_total_rub=earned_total_rub,
            invited_count=len(invited_users),
            paid_count=paid_count,
            current_level_name=current_level,
            next_level_name=next_level,
            left_to_next_level=left_to_next_level,
            progress_percent=progress_percent,
            progress_bar=render_progress_bar(progress_percent),
        )


async def get_user_referral_stats(user_id: int) -> dict:
    dashboard = await get_referral_dashboard(user_id)
    if dashboard is None:
        return {
            "invited_count": 0,
            "transitions_count": 0,
            "paid_count": 0,
            "credited_count": 0,
            "bonus_rub": 0,
            "total_earned_rub": 0,
            "balance_rub": 0,
            "balance_reserved_rub": 0,
            "balance_available_rub": 0,
            "ref_link": "",
            "current_level_name": "Без уровня",
            "next_level_name": "Новичок",
            "left_to_next_level": 1,
            "progress_percent": 0,
            "progress_bar": render_progress_bar(0),
        }

    user = await get_user_by_id(user_id)
    return {
        "invited_count": dashboard.invited_count,
        "transitions_count": dashboard.invited_count,
        "paid_count": dashboard.paid_count,
        "credited_count": dashboard.paid_count,
        "bonus_rub": dashboard.earned_total_rub,
        "total_earned_rub": dashboard.earned_total_rub,
        "balance_rub": dashboard.balance_rub,
        "balance_reserved_rub": int(getattr(user, "balance_reserved_rub", 0) or 0) if user is not None else 0,
        "balance_available_rub": _available_balance_from_user(user) if user is not None else 0,
        "ref_link": dashboard.ref_link,
        "current_level_name": dashboard.current_level_name,
        "next_level_name": dashboard.next_level_name,
        "left_to_next_level": dashboard.left_to_next_level,
        "progress_percent": dashboard.progress_percent,
        "progress_bar": dashboard.progress_bar,
    }


async def update_vpn_client_metadata(client_id: int, client_data: dict) -> VpnClient | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == client_id))
        vpn_client = result.scalar_one_or_none()
        if vpn_client is None:
            return None

        vpn_client.client_data = json.dumps(client_data, ensure_ascii=False)
        await session.commit()
        await session.refresh(vpn_client)
        return vpn_client


async def count_user_vpn_clients(user_id: int) -> int:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(VpnClient).where(VpnClient.user_id == user_id)
        )
        return int(result.scalar_one())


async def count_region_vpn_clients(country_code: str, *, active_only: bool = False) -> int:
    await ensure_schema()

    normalized_code = normalize_country_code(country_code)
    async with async_session() as session:
        users = {item.id: item for item in (await session.execute(select(User))).scalars().all()}
        clients = list((await session.execute(select(VpnClient))).scalars().all())

    count = 0
    for client in clients:
        try:
            metadata = json.loads(client.client_data or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if normalize_country_code(metadata.get("country_code")) != normalized_code:
            continue
        if active_only:
            user = users.get(client.user_id)
            if user is None or user.is_blocked or not has_active_access_from_user(user):
                continue
        count += 1
    return count


async def set_user_preferred_protocol(user_id: int, protocol: str) -> User | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            return None

        user.preferred_protocol = protocol
        await session.commit()
        await session.refresh(user)
        return user


async def set_user_preferred_mode(user_id: int, mode: str) -> User | None:
    await ensure_schema()

    normalized_mode = normalize_mode(mode)
    resolved_protocol = get_mode_protocol(normalized_mode)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            return None

        user.preferred_mode = normalized_mode
        user.preferred_protocol = resolved_protocol
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_preferred_mode(user_id: int) -> str | None:
    user = await get_user_by_id(user_id)
    if user is None:
        return None

    preferred_mode = getattr(user, "preferred_mode", None)
    if preferred_mode:
        return normalize_mode(preferred_mode)
    return normalize_mode(None, default="reserve" if user.preferred_protocol == "trojan" else "stable")


async def get_user_preferred_protocol(user_id: int) -> str | None:
    user = await get_user_by_id(user_id)
    if user is None:
        return None
    return user.preferred_protocol


async def get_user_vpn_clients(user_id: int) -> list[VpnClient]:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.user_id == user_id))
        return list(result.scalars().all())


async def get_vpn_client_by_id(client_id: int) -> VpnClient | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == client_id))
        return result.scalar_one_or_none()


async def delete_vpn_client(client_id: int) -> bool:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == client_id))
        vpn_client = result.scalar_one_or_none()
        if vpn_client is None:
            return False

        await session.delete(vpn_client)
        await session.commit()
        return True


async def delete_vpn_client_and_return(client_id: int) -> VpnClient | None:
    await ensure_schema()

    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == client_id))
        vpn_client = result.scalar_one_or_none()
        if vpn_client is None:
            return None

        await session.delete(vpn_client)
        await session.commit()
        return vpn_client
