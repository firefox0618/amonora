from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from backend.core.database import async_session
from backend.core.models import (
    AnalyticsCohortRetention,
    AnalyticsDailyAttributionIntegrity,
    AnalyticsDailyConnection,
    AnalyticsDailyPaymentFailureReason,
    AnalyticsDailyRevenue,
    AnalyticsDailyRevenueSegment,
    AnalyticsDailyStageCount,
    AnalyticsDailyStageSegment,
    AnalyticsEvent,
    AnalyticsHourlyOpsIncident,
    AnalyticsHourlyOpsSnapshot,
    AnalyticsRefreshState,
    AnalyticsRuntimeStatus,
    AnalyticsUserAttribution,
    ChannelContentItem,
    ChannelPostTouch,
    ControlNotificationEvent,
    User,
    VpnClient,
    VpnClientActivation,
)
from backend.core.schema import ensure_schema
from backend.core.synthetic_users import is_synthetic_user
from bot.utils.access import has_active_access_from_user
from dashboard.models import FinanceEntry, PaymentRecord


logger = logging.getLogger(__name__)

SOURCE_MODE_FIRST = "first"
SOURCE_MODE_LAST = "last"
SOURCE_TYPE_ORGANIC = "organic_bot"
SOURCE_TYPE_CHANNEL_POST = "channel_post"
USER_SEGMENT_NEW = "new"
USER_SEGMENT_RETURNING = "returning"

EVENT_USER_FIRST_SEEN = "user_first_seen"
EVENT_LINK_TOUCHED = "link_touched"
EVENT_BOT_START = "bot_start"
EVENT_CHANNEL_MEMBERSHIP_CONFIRMED = "channel_membership_confirmed"
EVENT_TRIAL_STARTED = "trial_started"
EVENT_ONBOARDING_STARTED = "onboarding_started"
EVENT_ONBOARDING_COMPLETED = "onboarding_completed"
EVENT_CONNECTION_STARTED = "connection_started"
EVENT_CONNECTION_READY = "connection_ready"
EVENT_CONFIG_REQUESTED = "config_requested"
EVENT_CONFIG_ISSUED = "config_issued"
EVENT_CONFIG_ISSUE_FAILED = "config_issue_failed"
EVENT_PAYMENT_STARTED = "payment_started"
EVENT_SUBSCRIPTION_PAYMENT_STARTED = "subscription_payment_started"
EVENT_PAYMENT_SUCCESS = "payment_success"
EVENT_PAYMENT_FAILED = "payment_failed"
EVENT_SUBSCRIPTION_PAYMENT_FAILED = "subscription_payment_failed"
EVENT_FIRST_CONNECTION_SUCCESS = "first_connection_success"
EVENT_CONNECTION_FAILED = "connection_failed"
EVENT_SUBSCRIPTION_EXPIRED = "subscription_expired"
EVENT_SUBSCRIPTION_ACTIVATED = "subscription_activated"
EVENT_SUBSCRIPTION_RENEWED = "subscription_renewed"
PAYMENT_KIND_NEW = "new"
PAYMENT_KIND_RENEWAL = "renewal"
PAYMENT_KIND_OTHER = "other"
PAYMENT_KIND_UNKNOWN = "unknown"

CONNECTION_STARTED_EVENT_NAMES = (EVENT_ONBOARDING_STARTED, EVENT_CONNECTION_STARTED)
CONNECTION_READY_EVENT_NAMES = (EVENT_ONBOARDING_COMPLETED, EVENT_CONNECTION_READY)

ROLLUP_STAGE_EVENTS = {
    EVENT_LINK_TOUCHED,
    EVENT_BOT_START,
    EVENT_CHANNEL_MEMBERSHIP_CONFIRMED,
    EVENT_TRIAL_STARTED,
    EVENT_ONBOARDING_STARTED,
    EVENT_ONBOARDING_COMPLETED,
    EVENT_CONNECTION_STARTED,
    EVENT_CONNECTION_READY,
    EVENT_CONFIG_REQUESTED,
    EVENT_CONFIG_ISSUED,
    EVENT_CONFIG_ISSUE_FAILED,
    EVENT_PAYMENT_STARTED,
    EVENT_SUBSCRIPTION_PAYMENT_STARTED,
    EVENT_PAYMENT_SUCCESS,
    EVENT_PAYMENT_FAILED,
    EVENT_SUBSCRIPTION_PAYMENT_FAILED,
    EVENT_FIRST_CONNECTION_SUCCESS,
    EVENT_CONNECTION_FAILED,
    EVENT_SUBSCRIPTION_ACTIVATED,
    EVENT_SUBSCRIPTION_RENEWED,
    EVENT_SUBSCRIPTION_EXPIRED,
}
ROLLUP_REVENUE_EVENTS = {EVENT_PAYMENT_SUCCESS}
ROLLUP_CONNECTION_EVENTS = {
    EVENT_CONFIG_ISSUED,
    EVENT_CONFIG_ISSUE_FAILED,
    EVENT_FIRST_CONNECTION_SUCCESS,
    EVENT_CONNECTION_FAILED,
}
COHORT_TYPES = (EVENT_TRIAL_STARTED, EVENT_SUBSCRIPTION_ACTIVATED)
COHORT_PERIOD_DAYS = (0, 1, 3, 7, 14, 30, 60, 90)
ANALYTICS_RETENTION_DAYS = 180
REFRESH_STATE_LAST_EVENT_AT = "analytics:last_event_at"
REFRESH_STATE_LAST_OPS_EVENT_AT = "analytics:last_ops_event_at"
OPS_ROLLUP_MAX_LOOKBACK_DAYS = 30
OPS_ROLLUP_REWIND_HOURS = 2
RUNTIME_STATUS_ANALYTICS_REFRESH = "analytics_refresh"
RUNTIME_STATUS_RESTORE_PROOF = "restore_proof"
RUNTIME_STATUS_REPAIR_OPEN = "repair_open"
RUNTIME_STATUS_OPEN_INCIDENTS = "open_incidents"
RUNTIME_STATUS_SOURCE_KEY_INTEGRITY = "source_key_integrity"
RUNTIME_STATUS_GROWTH_ACTIVE_USERS = "growth_active_users"
RESTORE_PROOF_STATUS_PATH = Path("/opt/amonora_bot/backups/status/restore-proof.json")
RESTORE_PROOF_STALE_DAYS = 30
ANALYTICS_REALTIME_REFRESH_RUNNER = Path("/opt/amonora_bot/venv/bin/python")
ANALYTICS_REALTIME_REFRESH_TRIGGER_PATH = Path("/tmp/amonora-analytics-refresh-trigger.txt")
ANALYTICS_REALTIME_REFRESH_MIN_INTERVAL = timedelta(seconds=30)
PROVISIONING_FAILURE_EVENT_TYPES = {
    "access_provisioning_failed",
    "access_delivery_failed",
}
RECONCILE_FAILURE_EVENT_TYPES = {
    "user_access_repair_failed",
    "user_access_sync_failed",
    "payment_activation_issue",
    "server_region_migration_failed",
}
SERVICE_INCIDENT_EVENT_TYPES = {"service_health_issue"}
ATTRIBUTION_ISSUE_NULL_SOURCE_KEY = "null_source_key"
ATTRIBUTION_ISSUE_EMPTY_SOURCE_KEY = "empty_source_key"
ATTRIBUTION_ISSUE_ORGANIC_BOT = "organic_bot"
ATTRIBUTION_ISSUE_INVALID_START_PARAM = "invalid_start_param"
ATTRIBUTION_ISSUE_MISSING_SOURCE = "missing_source_attribution"
SAFE_ANALYTICS_CALL_TIMEOUT_SECONDS = float(os.getenv("AMONORA_SAFE_ANALYTICS_CALL_TIMEOUT_SECONDS", "2.0"))


@dataclass(frozen=True)
class AttributionSnapshot:
    source_type: str
    source_key: str
    channel_item_id: int | None
    content_type: str | None
    seen_at: datetime | None = None


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_json_dumps(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=_json_default)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _safe_json_loads(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _payment_product_type(record: PaymentRecord) -> str:
    metadata = _safe_json_loads(getattr(record, "metadata_json", None))
    product_type = str(metadata.get("product_type") or metadata.get("payload_type") or "").strip().lower()
    tariff_code = str(getattr(record, "tariff_code", "") or "").strip().lower()
    if product_type:
        return product_type
    if tariff_code == "balance_topup":
        return "balance_topup"
    return "subscription"


def _normalize_payment_kind(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL, PAYMENT_KIND_OTHER}:
        return normalized
    return PAYMENT_KIND_UNKNOWN


def _payment_kind_from_payload(*, payload: dict | None, product_type: str | None) -> str:
    normalized = _normalize_payment_kind((payload or {}).get("payment_kind"))
    if normalized != PAYMENT_KIND_UNKNOWN:
        return normalized
    if str(product_type or "").strip().lower() != "subscription":
        return PAYMENT_KIND_OTHER
    return PAYMENT_KIND_UNKNOWN


def _payment_sort_key(record: PaymentRecord) -> tuple[datetime, datetime, int]:
    confirmed_at = getattr(record, "confirmed_at", None) or datetime.min
    created_at = getattr(record, "created_at", None) or confirmed_at
    return (confirmed_at, created_at, int(getattr(record, "id", 0) or 0))


def _classify_subscription_payment_kinds(payments: list[PaymentRecord]) -> dict[int, str]:
    by_user: dict[int, list[PaymentRecord]] = defaultdict(list)
    for payment in payments:
        if getattr(payment, "user_id", None) is None:
            continue
        if str(getattr(payment, "payment_status", "") or "").strip().lower() != "confirmed":
            continue
        if _payment_product_type(payment) != "subscription":
            continue
        by_user[int(payment.user_id)].append(payment)

    payment_kind_by_id: dict[int, str] = {}
    for user_id in sorted(by_user):
        rows = sorted(by_user[user_id], key=_payment_sort_key)
        for index, payment in enumerate(rows):
            payment_kind_by_id[int(payment.id)] = PAYMENT_KIND_NEW if index == 0 else PAYMENT_KIND_RENEWAL
    return payment_kind_by_id


def _payment_failed_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in {"rejected", "expired", "disputed", "error", "cancelled"}


def _normalize_payment_failure_reason(*, payment_status: str | None, payload: dict | None) -> str:
    safe_payload = dict(payload or {})
    raw_reason = str(
        safe_payload.get("reason")
        or safe_payload.get("rejection_reason")
        or safe_payload.get("provider_status")
        or ""
    ).strip().lower()
    normalized_status = str(payment_status or safe_payload.get("payment_status") or "").strip().lower()
    provider = str(safe_payload.get("provider") or "").strip().lower()
    review_source = str(safe_payload.get("review_source") or "").strip().lower()

    if normalized_status == "expired":
        return "expired"
    if provider or normalized_status in {"error"} or "provider" in raw_reason:
        return "provider_error"
    if review_source == "dashboard" and normalized_status == "rejected":
        return "manual_rejected"
    if normalized_status in {"rejected", "cancelled", "disputed"}:
        return "rejected"
    return "unknown"


def _classify_attribution_issue(payload: dict | None) -> str | None:
    safe_payload = dict(payload or {})
    has_source_fields = "source_key" in safe_payload or "source_type" in safe_payload
    if not has_source_fields:
        return ATTRIBUTION_ISSUE_MISSING_SOURCE

    raw_source_key = safe_payload.get("source_key")
    if raw_source_key is None:
        return ATTRIBUTION_ISSUE_NULL_SOURCE_KEY

    source_key = str(raw_source_key).strip().lower()
    source_type = str(safe_payload.get("source_type") or "").strip().lower()

    if not source_key:
        return ATTRIBUTION_ISSUE_EMPTY_SOURCE_KEY
    if source_type == SOURCE_TYPE_ORGANIC or source_key == SOURCE_TYPE_ORGANIC:
        return ATTRIBUTION_ISSUE_ORGANIC_BOT
    if source_type != SOURCE_TYPE_CHANNEL_POST:
        return ATTRIBUTION_ISSUE_INVALID_START_PARAM
    return None


async def _load_real_user(session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    user = (
        await session.execute(
            select(User).where(User.id == int(user_id))
        )
    ).scalar_one_or_none()
    if is_synthetic_user(user):
        return None
    return user


async def upsert_user_attribution(
    *,
    user_id: int,
    telegram_id: int | None,
    source_type: str,
    source_key: str,
    channel_item_id: int | None = None,
    seen_at: datetime | None = None,
    override_first: bool = False,
) -> AnalyticsUserAttribution | None:
    await ensure_schema()

    normalized_source_type = str(source_type or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC
    normalized_source_key = str(source_key or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC
    marker = seen_at or _utcnow()

    async with async_session() as session:
        user = await _load_real_user(session, user_id)
        if user is None:
            return None

        row = (
            await session.execute(
                select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id == int(user_id))
            )
        ).scalar_one_or_none()

        if row is None:
            row = AnalyticsUserAttribution(
                user_id=int(user_id),
                telegram_id=int(telegram_id) if telegram_id is not None else getattr(user, "telegram_id", None),
                first_source_type=normalized_source_type,
                first_source_key=normalized_source_key,
                first_channel_item_id=int(channel_item_id) if channel_item_id is not None else None,
                first_seen_at=marker,
                last_source_type=normalized_source_type,
                last_source_key=normalized_source_key,
                last_channel_item_id=int(channel_item_id) if channel_item_id is not None else None,
                last_seen_at=marker,
                created_at=marker,
                updated_at=marker,
            )
            session.add(row)
        else:
            if override_first or row.first_seen_at is None:
                row.first_source_type = normalized_source_type
                row.first_source_key = normalized_source_key
                row.first_channel_item_id = int(channel_item_id) if channel_item_id is not None else None
                row.first_seen_at = marker
            row.telegram_id = int(telegram_id) if telegram_id is not None else row.telegram_id
            row.last_source_type = normalized_source_type
            row.last_source_key = normalized_source_key
            row.last_channel_item_id = int(channel_item_id) if channel_item_id is not None else None
            row.last_seen_at = marker
            row.updated_at = marker
        await session.commit()
        await session.refresh(row)
        return row


async def safe_upsert_user_attribution(**kwargs) -> AnalyticsUserAttribution | None:
    try:
        return await upsert_user_attribution(**kwargs)
    except Exception:
        logger.exception("Analytics attribution upsert failed for payload=%s", kwargs)
        return None


async def emit_analytics_event(
    *,
    event_name: str,
    occurred_at: datetime | None = None,
    user_id: int | None = None,
    telegram_id: int | None = None,
    dedupe_key: str | None = None,
    payment_record_id: int | None = None,
    vpn_client_id: int | None = None,
    channel_item_id: int | None = None,
    tariff_code: str | None = None,
    payment_method: str | None = None,
    country_code: str | None = None,
    payload: dict | None = None,
) -> AnalyticsEvent | None:
    await ensure_schema()

    stamp = occurred_at or _utcnow()
    safe_payload = dict(payload or {})
    async with async_session() as session:
        if user_id is not None:
            user = await _load_real_user(session, user_id)
            if user is None:
                return None
            if telegram_id is None:
                telegram_id = getattr(user, "telegram_id", None)
        safe_payload = await _augment_payload_with_current_attribution(
            session,
            user_id=int(user_id) if user_id is not None else None,
            payload=safe_payload,
        )

        row = AnalyticsEvent(
            occurred_at=stamp,
            user_id=int(user_id) if user_id is not None else None,
            telegram_id=int(telegram_id) if telegram_id is not None else None,
            event_name=str(event_name or "").strip().lower(),
            dedupe_key=(str(dedupe_key).strip()[:255] if dedupe_key else None),
            payment_record_id=int(payment_record_id) if payment_record_id is not None else None,
            vpn_client_id=int(vpn_client_id) if vpn_client_id is not None else None,
            channel_item_id=int(channel_item_id) if channel_item_id is not None else None,
            tariff_code=(str(tariff_code).strip()[:50] if tariff_code else None),
            payment_method=(str(payment_method).strip()[:50] if payment_method else None),
            country_code=(str(country_code).strip().lower()[:10] if country_code else None),
            payload_json=_safe_json_dumps(safe_payload) if safe_payload else None,
            created_at=_utcnow(),
        )
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if row.dedupe_key:
                existing = (
                    await session.execute(
                        select(AnalyticsEvent).where(AnalyticsEvent.dedupe_key == row.dedupe_key)
                    )
                ).scalar_one_or_none()
                return existing
            raise
        await session.refresh(row)
    _request_near_realtime_refresh_for_event(row.event_name)
    return row


async def safe_emit_analytics_event(**kwargs) -> AnalyticsEvent | None:
    try:
        return await asyncio.wait_for(
            emit_analytics_event(**kwargs),
            timeout=SAFE_ANALYTICS_CALL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.exception(
            "Analytics event emit timed out for event_name=%s dedupe_key=%s",
            kwargs.get("event_name"),
            kwargs.get("dedupe_key"),
        )
        return None
    except Exception:
        logger.exception(
            "Analytics event emit failed for event_name=%s dedupe_key=%s",
            kwargs.get("event_name"),
            kwargs.get("dedupe_key"),
        )
        return None


async def emit_bot_start_event(
    *,
    user_id: int,
    telegram_id: int | None,
    source_type: str,
    source_key: str,
    channel_item_id: int | None = None,
) -> None:
    dedupe_key = f"bot-start:{user_id}:{str(source_type or SOURCE_TYPE_ORGANIC).strip().lower()}:{str(source_key or SOURCE_TYPE_ORGANIC).strip().lower()}"
    await safe_emit_analytics_event(
        event_name=EVENT_BOT_START,
        user_id=user_id,
        telegram_id=telegram_id,
        dedupe_key=dedupe_key,
        channel_item_id=channel_item_id,
        payload={
            "source_type": source_type,
            "source_key": source_key,
            "channel_item_id": channel_item_id,
        },
    )


async def emit_link_touched_event(
    *,
    user_id: int,
    telegram_id: int | None,
    source_type: str,
    source_key: str,
    channel_item_id: int | None = None,
) -> None:
    dedupe_key = (
        f"link-touched:{user_id}:"
        f"{str(source_type or SOURCE_TYPE_ORGANIC).strip().lower()}:"
        f"{str(source_key or SOURCE_TYPE_ORGANIC).strip().lower()}"
    )
    await safe_emit_analytics_event(
        event_name=EVENT_LINK_TOUCHED,
        user_id=user_id,
        telegram_id=telegram_id,
        dedupe_key=dedupe_key,
        channel_item_id=channel_item_id,
        payload={
            "source_type": source_type,
            "source_key": source_key,
            "channel_item_id": channel_item_id,
        },
    )


async def _load_attribution_snapshot_map(user_ids: set[int]) -> dict[int, dict[str, AttributionSnapshot]]:
    if not user_ids:
        return {}
    async with async_session() as session:
        attr_rows = list(
            (
                await session.execute(
                    select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id.in_(sorted(user_ids)))
                )
            ).scalars().all()
        )
        channel_ids = sorted(
            {
                int(channel_id)
                for row in attr_rows
                for channel_id in (row.first_channel_item_id, row.last_channel_item_id)
                if channel_id is not None
            }
        )
        content_type_by_id: dict[int, str | None] = {}
        if channel_ids:
            items = list(
                (
                    await session.execute(
                        select(ChannelContentItem).where(ChannelContentItem.id.in_(channel_ids))
                    )
                ).scalars().all()
            )
            content_type_by_id = {int(item.id): item.content_type for item in items}

    result: dict[int, dict[str, AttributionSnapshot]] = {}
    for row in attr_rows:
        first_channel_item_id = int(row.first_channel_item_id) if row.first_channel_item_id is not None else None
        last_channel_item_id = int(row.last_channel_item_id) if row.last_channel_item_id is not None else None
        result[int(row.user_id)] = {
            SOURCE_MODE_FIRST: AttributionSnapshot(
                source_type=str(row.first_source_type or SOURCE_TYPE_ORGANIC),
                source_key=str(row.first_source_key or SOURCE_TYPE_ORGANIC),
                channel_item_id=first_channel_item_id,
                content_type=content_type_by_id.get(first_channel_item_id) if first_channel_item_id is not None else None,
                seen_at=getattr(row, "first_seen_at", None),
            ),
            SOURCE_MODE_LAST: AttributionSnapshot(
                source_type=str(row.last_source_type or row.first_source_type or SOURCE_TYPE_ORGANIC),
                source_key=str(row.last_source_key or row.first_source_key or SOURCE_TYPE_ORGANIC),
                channel_item_id=last_channel_item_id,
                content_type=content_type_by_id.get(last_channel_item_id) if last_channel_item_id is not None else None,
                seen_at=getattr(row, "last_seen_at", None),
            ),
        }
    return result


def _fallback_attribution_from_event(event: AnalyticsEvent) -> dict[str, AttributionSnapshot]:
    payload = _safe_json_loads(getattr(event, "payload_json", None))
    source_type = str(payload.get("source_type") or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC
    source_key = str(payload.get("source_key") or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC
    channel_item_id = int(event.channel_item_id) if getattr(event, "channel_item_id", None) is not None else None
    snapshot = AttributionSnapshot(
        source_type=source_type,
        source_key=source_key,
        channel_item_id=channel_item_id,
        content_type=str(payload.get("content_type") or "").strip().lower() or None,
        seen_at=getattr(event, "occurred_at", None),
    )
    return {
        SOURCE_MODE_FIRST: snapshot,
        SOURCE_MODE_LAST: snapshot,
    }


def _snapshot_to_payload(snapshot: AttributionSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "source_type": snapshot.source_type,
        "source_key": snapshot.source_key,
        "channel_item_id": snapshot.channel_item_id,
        "content_type": snapshot.content_type,
        "seen_at": snapshot.seen_at.isoformat() if snapshot.seen_at is not None else None,
    }


def _snapshot_from_payload(raw_value) -> AttributionSnapshot | None:
    if not isinstance(raw_value, dict):
        return None
    source_type = str(raw_value.get("source_type") or "").strip().lower()
    source_key = str(raw_value.get("source_key") or "").strip().lower()
    if not source_type or not source_key:
        return None
    channel_item_id = raw_value.get("channel_item_id")
    try:
        normalized_channel_item_id = int(channel_item_id) if channel_item_id is not None else None
    except (TypeError, ValueError):
        normalized_channel_item_id = None
    return AttributionSnapshot(
        source_type=source_type,
        source_key=source_key,
        channel_item_id=normalized_channel_item_id,
        content_type=str(raw_value.get("content_type") or "").strip().lower() or None,
        seen_at=_parse_datetime_like(raw_value.get("seen_at")),
    )


def _snapshot_applies_to_event(snapshot: AttributionSnapshot | None, occurred_at: datetime | None) -> bool:
    if snapshot is None:
        return False
    if snapshot.seen_at is None or occurred_at is None:
        return True
    return occurred_at >= snapshot.seen_at


async def _augment_payload_with_current_attribution(
    session,
    *,
    user_id: int | None,
    payload: dict | None,
) -> dict:
    safe_payload = dict(payload or {})
    if user_id is None:
        return safe_payload
    if safe_payload.get("attribution_first") and safe_payload.get("attribution_last"):
        return safe_payload

    attr_row = (
        await session.execute(
            select(AnalyticsUserAttribution).where(AnalyticsUserAttribution.user_id == int(user_id))
        )
    ).scalar_one_or_none()
    if attr_row is None:
        return safe_payload

    channel_ids = sorted(
        {
            int(channel_id)
            for channel_id in (attr_row.first_channel_item_id, attr_row.last_channel_item_id)
            if channel_id is not None
        }
    )
    content_type_by_id: dict[int, str | None] = {}
    if channel_ids:
        items = list(
            (
                await session.execute(
                    select(ChannelContentItem).where(ChannelContentItem.id.in_(channel_ids))
                )
            ).scalars().all()
        )
        content_type_by_id = {int(item.id): item.content_type for item in items}

    first_channel_item_id = int(attr_row.first_channel_item_id) if attr_row.first_channel_item_id is not None else None
    last_channel_item_id = int(attr_row.last_channel_item_id) if attr_row.last_channel_item_id is not None else None
    first_snapshot = AttributionSnapshot(
        source_type=str(attr_row.first_source_type or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC,
        source_key=str(attr_row.first_source_key or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC,
        channel_item_id=first_channel_item_id,
        content_type=content_type_by_id.get(first_channel_item_id) if first_channel_item_id is not None else None,
        seen_at=getattr(attr_row, "first_seen_at", None),
    )
    last_snapshot = AttributionSnapshot(
        source_type=str(attr_row.last_source_type or attr_row.first_source_type or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC,
        source_key=str(attr_row.last_source_key or attr_row.first_source_key or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC,
        channel_item_id=last_channel_item_id,
        content_type=content_type_by_id.get(last_channel_item_id) if last_channel_item_id is not None else None,
        seen_at=getattr(attr_row, "last_seen_at", None),
    )
    safe_payload.setdefault("attribution_first", _snapshot_to_payload(first_snapshot))
    safe_payload.setdefault("attribution_last", _snapshot_to_payload(last_snapshot))
    return safe_payload


def _event_snapshots_for_rollup(
    event: AnalyticsEvent,
    attribution_map: dict[int, dict[str, AttributionSnapshot]],
) -> dict[str, AttributionSnapshot]:
    payload = _safe_json_loads(getattr(event, "payload_json", None))
    occurred_at = getattr(event, "occurred_at", None)
    if event.event_name == EVENT_LINK_TOUCHED:
        source_type = str(payload.get("source_type") or SOURCE_TYPE_CHANNEL_POST).strip().lower() or SOURCE_TYPE_CHANNEL_POST
        source_key = str(payload.get("source_key") or SOURCE_TYPE_ORGANIC).strip().lower() or SOURCE_TYPE_ORGANIC
        channel_item_id = int(event.channel_item_id) if getattr(event, "channel_item_id", None) is not None else None
        snapshot = AttributionSnapshot(
            source_type=source_type,
            source_key=source_key,
            channel_item_id=channel_item_id,
            content_type=str(payload.get("content_type") or "").strip().lower() or None,
            seen_at=occurred_at,
        )
        return {
            SOURCE_MODE_FIRST: snapshot,
            SOURCE_MODE_LAST: snapshot,
        }
    payload_first_snapshot = _snapshot_from_payload(payload.get("attribution_first"))
    payload_last_snapshot = _snapshot_from_payload(payload.get("attribution_last"))
    if payload_first_snapshot is not None or payload_last_snapshot is not None:
        snapshots: dict[str, AttributionSnapshot] = {}
        if payload_first_snapshot is not None:
            snapshots[SOURCE_MODE_FIRST] = payload_first_snapshot
        if payload_last_snapshot is not None:
            snapshots[SOURCE_MODE_LAST] = payload_last_snapshot
        return snapshots
    attr_modes = attribution_map.get(int(event.user_id)) if event.user_id is not None else None
    if attr_modes:
        snapshots: dict[str, AttributionSnapshot] = {}
        first_snapshot = attr_modes.get(SOURCE_MODE_FIRST)
        last_snapshot = attr_modes.get(SOURCE_MODE_LAST)
        if _snapshot_applies_to_event(first_snapshot, occurred_at):
            snapshots[SOURCE_MODE_FIRST] = first_snapshot
        if _snapshot_applies_to_event(last_snapshot, occurred_at):
            snapshots[SOURCE_MODE_LAST] = last_snapshot
        if snapshots:
            return snapshots
    return _fallback_attribution_from_event(event)


def _event_user_segment(*, user_id: int | None, bucket: date, first_bot_start_by_user: dict[int, date]) -> str:
    if user_id is None:
        return USER_SEGMENT_RETURNING
    first_bot_start_date = first_bot_start_by_user.get(int(user_id))
    if first_bot_start_date == bucket:
        return USER_SEGMENT_NEW
    return USER_SEGMENT_RETURNING


def _bot_start_integrity_payload(events: list[AnalyticsEvent]) -> tuple[str, dict]:
    totals = {
        "total_bot_start": 0,
        "tracked_source_key": 0,
        "organic_fallback": 0,
        "blank_or_invalid_source_key": 0,
    }
    for event in events:
        if event.event_name != EVENT_BOT_START:
            continue
        totals["total_bot_start"] += 1
        payload = _safe_json_loads(getattr(event, "payload_json", None))
        issue_type = _classify_attribution_issue(payload)
        source_type = str(payload.get("source_type") or "").strip().lower()
        source_key = str(payload.get("source_key") or "").strip().lower()
        if issue_type is None and source_type == SOURCE_TYPE_CHANNEL_POST and source_key and source_key != SOURCE_TYPE_ORGANIC:
            totals["tracked_source_key"] += 1
        elif issue_type == ATTRIBUTION_ISSUE_ORGANIC_BOT:
            totals["organic_fallback"] += 1
        else:
            totals["blank_or_invalid_source_key"] += 1

    total = totals["total_bot_start"]
    integrity_ratio = round(
        ((totals["tracked_source_key"] + totals["organic_fallback"]) / total) if total else 1.0,
        4,
    )
    totals["integrity_ratio"] = integrity_ratio
    if total == 0 or integrity_ratio >= 0.995 and totals["blank_or_invalid_source_key"] == 0:
        status_value = "healthy"
    elif integrity_ratio < 0.95:
        status_value = "critical"
    else:
        status_value = "warning"
    return status_value, totals


def _day_bounds(bucket: date) -> tuple[datetime, datetime]:
    start = datetime.combine(bucket, time.min)
    end = start + timedelta(days=1)
    return start, end


def _hour_floor(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _normalize_trace_value(raw_value) -> str | None:
    value = str(raw_value or "").strip()
    return value[:64] or None


def _parse_datetime_like(raw_value) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _request_near_realtime_refresh_for_event(event_name: str | None) -> None:
    normalized_event = str(event_name or "").strip().lower()
    if normalized_event not in ROLLUP_STAGE_EVENTS:
        return
    if not ANALYTICS_REALTIME_REFRESH_RUNNER.exists():
        return
    try:
        import fcntl
    except ImportError:
        return

    now = _utcnow()
    should_trigger = False
    try:
        ANALYTICS_REALTIME_REFRESH_TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_REALTIME_REFRESH_TRIGGER_PATH.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            last_requested_at = _parse_datetime_like(handle.read().strip())
            if last_requested_at is None or now - last_requested_at >= ANALYTICS_REALTIME_REFRESH_MIN_INTERVAL:
                handle.seek(0)
                handle.truncate()
                handle.write(now.isoformat())
                handle.flush()
                os.fsync(handle.fileno())
                should_trigger = True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        logger.exception("Failed to update analytics realtime refresh debounce marker")
        return

    if not should_trigger:
        return

    env = dict(os.environ)
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = f"/opt/amonora_bot:{existing_pythonpath}" if existing_pythonpath else "/opt/amonora_bot"
    try:
        subprocess.Popen(
            [str(ANALYTICS_REALTIME_REFRESH_RUNNER), "-m", "ops.analytics_refresh"],
            cwd="/opt/amonora_bot",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except Exception:
        logger.exception("Failed to spawn near-realtime analytics refresh for event=%s", normalized_event)


def _control_event_incident_class(event: ControlNotificationEvent) -> str:
    payload = _safe_json_loads(getattr(event, "payload_json", None))
    label = str(payload.get("alert_class") or "").strip().lower()
    if label in {"growth", "revenue", "ops"}:
        return label
    if str(getattr(event, "category", "") or "").strip().lower() == "payments":
        return "revenue"
    return "ops"


def _control_event_entity_key(event: ControlNotificationEvent) -> str:
    entity_type = str(getattr(event, "entity_type", "") or "").strip().lower() or "none"
    entity_id = str(getattr(event, "entity_id", "") or "").strip().lower() or "none"
    return f"{entity_type}:{entity_id}"


def _restore_proof_runtime_payload(*, now: datetime | None = None) -> tuple[str, datetime | None, dict]:
    stamp = now or _utcnow()
    if not RESTORE_PROOF_STATUS_PATH.exists():
        return (
            "missing",
            None,
            {
                "path": str(RESTORE_PROOF_STATUS_PATH),
                "reason": "missing",
            },
        )
    try:
        payload = json.loads(RESTORE_PROOF_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (
            "invalid",
            None,
            {
                "path": str(RESTORE_PROOF_STATUS_PATH),
                "reason": "invalid_json",
            },
        )
    if not isinstance(payload, dict):
        return (
            "invalid",
            None,
            {
                "path": str(RESTORE_PROOF_STATUS_PATH),
                "reason": "invalid_payload",
            },
        )
    observed_at = (
        _parse_datetime_like(payload.get("verified_at"))
        or _parse_datetime_like(payload.get("last_restore_validation_at"))
        or _parse_datetime_like(payload.get("updated_at"))
    )
    proof_kind = str(payload.get("proof_kind") or "").strip().lower()
    proof_status = str(payload.get("proof_status") or "").strip().lower()
    proof_scope = payload.get("proof_scope")
    if isinstance(proof_scope, (list, tuple, set)):
        normalized_scope = [str(item).strip().lower() for item in proof_scope if str(item).strip()]
    else:
        normalized_scope = [str(proof_scope).strip().lower()] if str(proof_scope or "").strip() else []
    stale = False
    if observed_at is not None:
        stale = (stamp - observed_at) > timedelta(days=RESTORE_PROOF_STALE_DAYS)
    is_verified = (
        proof_kind == "temporary_database_restore"
        and proof_status == "verified"
        and "core_pg" in normalized_scope
    )
    if is_verified and not stale:
        status_value = "healthy"
    elif is_verified and stale:
        status_value = "stale"
    else:
        status_value = "degraded"
    return (
        status_value,
        observed_at,
        {
            "path": str(RESTORE_PROOF_STATUS_PATH),
            "proof_kind": proof_kind or None,
            "proof_status": proof_status or None,
            "proof_scope": normalized_scope,
            "stale": stale,
            "stale_definition_days": RESTORE_PROOF_STALE_DAYS,
        },
    )


async def _replace_daily_stage_rows(bucket: date, rows: list[AnalyticsDailyStageCount]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyStageCount).where(AnalyticsDailyStageCount.bucket_date == bucket)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_stage_segment_rows(bucket: date, rows: list[AnalyticsDailyStageSegment]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyStageSegment).where(AnalyticsDailyStageSegment.bucket_date == bucket)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_revenue_rows(bucket: date, rows: list[AnalyticsDailyRevenue]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyRevenue).where(AnalyticsDailyRevenue.bucket_date == bucket)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_revenue_segment_rows(bucket: date, rows: list[AnalyticsDailyRevenueSegment]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyRevenueSegment).where(AnalyticsDailyRevenueSegment.bucket_date == bucket)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_connection_rows(bucket: date, rows: list[AnalyticsDailyConnection]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyConnection).where(AnalyticsDailyConnection.bucket_date == bucket)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_payment_failure_reason_rows(
    bucket: date,
    rows: list[AnalyticsDailyPaymentFailureReason],
) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyPaymentFailureReason).where(
                AnalyticsDailyPaymentFailureReason.bucket_date == bucket
            )
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_daily_attribution_integrity_rows(
    bucket: date,
    rows: list[AnalyticsDailyAttributionIntegrity],
) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsDailyAttributionIntegrity).where(
                AnalyticsDailyAttributionIntegrity.bucket_date == bucket
            )
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _replace_hourly_ops_incident_rows(bucket_hour: datetime, rows: list[AnalyticsHourlyOpsIncident]) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsHourlyOpsIncident).where(AnalyticsHourlyOpsIncident.bucket_hour == bucket_hour)
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _upsert_hourly_ops_snapshot(row: AnalyticsHourlyOpsSnapshot) -> None:
    async with async_session() as session:
        existing = (
            await session.execute(
                select(AnalyticsHourlyOpsSnapshot).where(
                    AnalyticsHourlyOpsSnapshot.bucket_hour == row.bucket_hour
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(row)
        else:
            existing.repair_needed_open_count = row.repair_needed_open_count
            existing.unresolved_incident_count = row.unresolved_incident_count
            existing.unresolved_warning_count = row.unresolved_warning_count
            existing.unresolved_critical_count = row.unresolved_critical_count
            existing.unresolved_access_count = row.unresolved_access_count
            existing.unresolved_node_count = row.unresolved_node_count
            existing.unresolved_service_count = row.unresolved_service_count
            existing.provisioning_failure_events_24h = row.provisioning_failure_events_24h
            existing.reconcile_failure_events_24h = row.reconcile_failure_events_24h
            existing.updated_at = row.updated_at
        await session.commit()


async def _set_runtime_status(
    *,
    status_key: str,
    status_group: str,
    status_value: str,
    observed_at: datetime | None,
    detail: dict | None = None,
) -> None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(AnalyticsRuntimeStatus).where(AnalyticsRuntimeStatus.status_key == status_key)
            )
        ).scalar_one_or_none()
        payload = _safe_json_dumps(detail) if detail else None
        if row is None:
            row = AnalyticsRuntimeStatus(
                status_key=status_key,
                status_group=status_group,
                status_value=status_value,
                observed_at=observed_at,
                detail_json=payload,
                updated_at=_utcnow(),
            )
            session.add(row)
        else:
            row.status_group = status_group
            row.status_value = status_value
            row.observed_at = observed_at
            row.detail_json = payload
            row.updated_at = _utcnow()
        await session.commit()


async def _replace_cohort_rows(
    *,
    cohort_type: str,
    cohort_date_value: date,
    rows: list[AnalyticsCohortRetention],
) -> None:
    async with async_session() as session:
        await session.execute(
            delete(AnalyticsCohortRetention).where(
                AnalyticsCohortRetention.cohort_type == cohort_type,
                AnalyticsCohortRetention.cohort_date == cohort_date_value,
            )
        )
        if rows:
            session.add_all(rows)
        await session.commit()


async def _get_refresh_cursor(state_key: str) -> datetime | None:
    async with async_session() as session:
        row = (
            await session.execute(select(AnalyticsRefreshState).where(AnalyticsRefreshState.state_key == state_key))
        ).scalar_one_or_none()
        return row.cursor_at if row is not None else None


async def _set_refresh_cursor(state_key: str, cursor_at: datetime | None, *, metadata: dict | None = None) -> None:
    async with async_session() as session:
        row = (
            await session.execute(select(AnalyticsRefreshState).where(AnalyticsRefreshState.state_key == state_key))
        ).scalar_one_or_none()
        payload = _safe_json_dumps(metadata) if metadata else None
        if row is None:
            row = AnalyticsRefreshState(
                state_key=state_key,
                cursor_at=cursor_at,
                metadata_json=payload,
                updated_at=_utcnow(),
            )
            session.add(row)
        else:
            row.cursor_at = cursor_at
            row.metadata_json = payload
            row.updated_at = _utcnow()
        await session.commit()


async def prune_analytics_events(*, retention_days: int = ANALYTICS_RETENTION_DAYS) -> int:
    await ensure_schema()

    cutoff = _utcnow() - timedelta(days=max(int(retention_days), 1))
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(AnalyticsEvent).where(AnalyticsEvent.occurred_at < cutoff)
                )
            ).scalars().all()
        )
        deleted = len(rows)
        if deleted:
            for row in rows:
                await session.delete(row)
            await session.commit()
        return deleted


async def refresh_analytics_rollups(*, force_full: bool = False) -> dict[str, int | str]:
    await ensure_schema()

    now = _utcnow()
    previous_cursor = None if force_full else await _get_refresh_cursor(REFRESH_STATE_LAST_EVENT_AT)
    query_start = previous_cursor - timedelta(days=1) if previous_cursor is not None else None

    async with async_session() as session:
        query = select(AnalyticsEvent)
        if query_start is not None:
            query = query.where(AnalyticsEvent.occurred_at >= query_start)
        events = list((await session.execute(query.order_by(AnalyticsEvent.occurred_at.asc(), AnalyticsEvent.id.asc()))).scalars().all())
        touch_query = select(ChannelPostTouch)
        if query_start is not None:
            touch_query = touch_query.where(ChannelPostTouch.first_seen_at >= query_start)
        touch_rows = list(
            (
                await session.execute(
                    touch_query.order_by(ChannelPostTouch.first_seen_at.asc(), ChannelPostTouch.id.asc())
                )
            ).scalars().all()
        )
        touch_item_ids = sorted(
            {
                int(row.item_id)
                for row in touch_rows
                if getattr(row, "item_id", None) is not None
            }
        )
        touch_items = []
        if touch_item_ids:
            touch_items = list(
                (
                    await session.execute(
                        select(ChannelContentItem).where(ChannelContentItem.id.in_(touch_item_ids))
                    )
                ).scalars().all()
            )
        cohort_start_rows = list(
            (
                await session.execute(
                    select(AnalyticsEvent).where(AnalyticsEvent.event_name.in_(COHORT_TYPES))
                )
            ).scalars().all()
        )
        recent_bot_start_events = list(
            (
                await session.execute(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.event_name == EVENT_BOT_START,
                        AnalyticsEvent.occurred_at >= now - timedelta(days=30),
                    )
                    .order_by(AnalyticsEvent.occurred_at.asc(), AnalyticsEvent.id.asc())
                )
            ).scalars().all()
        )
        real_users = list(
            (
                await session.execute(
                    select(User).where(User.is_synthetic.is_(False))
                )
            ).scalars().all()
        )

    all_event_dates = sorted(
        {
            event.occurred_at.date()
            for event in events
            if getattr(event, "occurred_at", None) is not None
        }
        | {
            touch.first_seen_at.date()
            for touch in touch_rows
            if getattr(touch, "first_seen_at", None) is not None
        }
    )
    user_ids = {int(event.user_id) for event in events if event.user_id is not None} | {
        int(touch.user_id)
        for touch in touch_rows
        if getattr(touch, "user_id", None) is not None
    }
    attribution_map = await _load_attribution_snapshot_map(user_ids)
    touch_item_map = {int(item.id): item for item in touch_items}
    first_bot_start_by_user: dict[int, date] = {}
    if user_ids:
        async with async_session() as session:
            first_bot_start_rows = (
                await session.execute(
                    select(
                        AnalyticsEvent.user_id,
                        func.min(AnalyticsEvent.occurred_at),
                    )
                    .where(
                        AnalyticsEvent.user_id.in_(sorted(user_ids)),
                        AnalyticsEvent.event_name == EVENT_BOT_START,
                    )
                    .group_by(AnalyticsEvent.user_id)
                )
            ).all()
        first_bot_start_by_user = {
            int(user_id): occurred_at.date()
            for user_id, occurred_at in first_bot_start_rows
            if user_id is not None and occurred_at is not None
        }
    if not events and not touch_rows and previous_cursor is not None and not force_full:
        source_integrity_status, source_integrity_detail = _bot_start_integrity_payload(recent_bot_start_events)
        await _set_runtime_status(
            status_key=RUNTIME_STATUS_SOURCE_KEY_INTEGRITY,
            status_group="growth",
            status_value=source_integrity_status,
            observed_at=now,
            detail=source_integrity_detail,
        )
        active_access_count = sum(1 for user in real_users if has_active_access_from_user(user))
        await _set_runtime_status(
            status_key=RUNTIME_STATUS_GROWTH_ACTIVE_USERS,
            status_group="growth",
            status_value="healthy",
            observed_at=now,
            detail={
                "active_users": active_access_count,
                "real_users": len(real_users),
            },
        )
        return {"dates_refreshed": 0, "cohorts_refreshed": 0, "events_scanned": 0, "deleted_old_events": 0}

    for bucket in all_event_dates:
        bucket_events = [event for event in events if event.occurred_at.date() == bucket]
        bucket_touches = [touch for touch in touch_rows if touch.first_seen_at.date() == bucket]
        stage_counts: dict[tuple, dict[str, object]] = {}
        stage_segments: dict[tuple, dict[str, object]] = {}
        revenue_counts: dict[tuple, dict[str, object]] = {}
        revenue_segments: dict[tuple, dict[str, object]] = {}
        connection_counts: dict[tuple, dict[str, object]] = {}
        payment_failure_counts: dict[tuple, dict[str, object]] = {}
        attribution_issue_counts: dict[str, dict[str, object]] = {}
        config_issued_events = [
            event for event in bucket_events
            if event.event_name == EVENT_CONFIG_ISSUED and event.user_id is not None
        ]
        total_bot_start_count = 0

        for touch in bucket_touches:
            if getattr(touch, "user_id", None) is None:
                continue
            item_id = int(touch.item_id) if getattr(touch, "item_id", None) is not None else None
            item = touch_item_map.get(item_id) if item_id is not None else None
            source_key = (
                str(getattr(item, "deep_link_token", "") or "").strip().lower()
                if item is not None
                else ""
            ) or (f"channel-item-{item_id}" if item_id is not None else SOURCE_TYPE_ORGANIC)
            content_type = getattr(item, "content_type", None) if item is not None else None
            user_segment = _event_user_segment(
                user_id=int(touch.user_id),
                bucket=bucket,
                first_bot_start_by_user=first_bot_start_by_user,
            )
            for source_mode in (SOURCE_MODE_FIRST, SOURCE_MODE_LAST):
                stage_key = (
                    bucket,
                    EVENT_LINK_TOUCHED,
                    source_mode,
                    SOURCE_TYPE_CHANNEL_POST,
                    source_key,
                    item_id,
                )
                stage_bucket = stage_counts.setdefault(
                    stage_key,
                    {
                        "events_count": 0,
                        "user_ids": set(),
                        "content_type": content_type,
                    },
                )
                stage_bucket["events_count"] += 1
                stage_bucket["user_ids"].add(int(touch.user_id))
                stage_segment_key = (
                    bucket,
                    EVENT_LINK_TOUCHED,
                    source_mode,
                    SOURCE_TYPE_CHANNEL_POST,
                    source_key,
                    item_id,
                    user_segment,
                )
                stage_segment_bucket = stage_segments.setdefault(
                    stage_segment_key,
                    {
                        "events_count": 0,
                        "user_ids": set(),
                        "content_type": content_type,
                    },
                )
                stage_segment_bucket["events_count"] += 1
                stage_segment_bucket["user_ids"].add(int(touch.user_id))

        for event in bucket_events:
            payload = _safe_json_loads(event.payload_json)
            if event.event_name == EVENT_BOT_START:
                total_bot_start_count += 1
                issue_type = _classify_attribution_issue(payload)
                if issue_type is not None:
                    issue_bucket = attribution_issue_counts.setdefault(
                        issue_type,
                        {
                            "issue_count": 0,
                            "user_ids": set(),
                        },
                    )
                    issue_bucket["issue_count"] += 1
                    if event.user_id is not None:
                        issue_bucket["user_ids"].add(int(event.user_id))

            if event.event_name not in ROLLUP_STAGE_EVENTS:
                continue
            snapshots = _event_snapshots_for_rollup(event, attribution_map)
            user_segment = _event_user_segment(
                user_id=int(event.user_id) if event.user_id is not None else None,
                bucket=bucket,
                first_bot_start_by_user=first_bot_start_by_user,
            )

            for source_mode, snapshot in snapshots.items():
                stage_key = (
                    bucket,
                    event.event_name,
                    source_mode,
                    snapshot.source_type,
                    snapshot.source_key,
                    snapshot.channel_item_id,
                )
                stage_bucket = stage_counts.setdefault(
                    stage_key,
                    {
                        "events_count": 0,
                        "user_ids": set(),
                        "content_type": snapshot.content_type,
                    },
                )
                stage_bucket["events_count"] += 1
                if event.user_id is not None:
                    stage_bucket["user_ids"].add(int(event.user_id))
                    stage_segment_key = (
                        bucket,
                        event.event_name,
                        source_mode,
                        snapshot.source_type,
                        snapshot.source_key,
                        snapshot.channel_item_id,
                        user_segment,
                    )
                    stage_segment_bucket = stage_segments.setdefault(
                        stage_segment_key,
                        {
                            "events_count": 0,
                            "user_ids": set(),
                            "content_type": snapshot.content_type,
                        },
                    )
                    stage_segment_bucket["events_count"] += 1
                    stage_segment_bucket["user_ids"].add(int(event.user_id))

                if event.event_name in ROLLUP_REVENUE_EVENTS:
                    amount_rub = int(payload.get("amount_rub") or 0)
                    payment_kind = _payment_kind_from_payload(
                        payload=payload,
                        product_type=payload.get("product_type"),
                    )
                    revenue_key = (
                        bucket,
                        source_mode,
                        snapshot.source_type,
                        snapshot.source_key,
                        snapshot.channel_item_id,
                        str(event.tariff_code or payload.get("tariff_code") or "").strip().lower() or None,
                        str(event.payment_method or payload.get("payment_method") or "").strip().lower() or None,
                        payment_kind,
                    )
                    revenue_bucket = revenue_counts.setdefault(
                        revenue_key,
                        {"payments_count": 0, "revenue_amount_rub": 0, "content_type": snapshot.content_type},
                    )
                    revenue_bucket["payments_count"] += 1
                    revenue_bucket["revenue_amount_rub"] += amount_rub
                    if event.user_id is not None:
                        revenue_segment_key = (
                            bucket,
                            source_mode,
                            snapshot.source_type,
                            snapshot.source_key,
                            snapshot.channel_item_id,
                            str(event.tariff_code or payload.get("tariff_code") or "").strip().lower() or None,
                            str(event.payment_method or payload.get("payment_method") or "").strip().lower() or None,
                            payment_kind,
                            user_segment,
                        )
                        revenue_segment_bucket = revenue_segments.setdefault(
                            revenue_segment_key,
                            {
                                "payments_count": 0,
                                "revenue_amount_rub": 0,
                                "content_type": snapshot.content_type,
                            },
                        )
                        revenue_segment_bucket["payments_count"] += 1
                        revenue_segment_bucket["revenue_amount_rub"] += amount_rub

                if event.event_name == EVENT_SUBSCRIPTION_PAYMENT_FAILED or (
                    event.event_name == EVENT_PAYMENT_FAILED
                    and str(payload.get("product_type") or "").strip().lower() == "subscription"
                ):
                    failure_key = (
                        bucket,
                        source_mode,
                        snapshot.source_type,
                        snapshot.source_key,
                        snapshot.channel_item_id,
                        str(event.payment_method or payload.get("payment_method") or "").strip().lower() or None,
                        _normalize_payment_failure_reason(
                            payment_status=payload.get("payment_status"),
                            payload=payload,
                        ),
                    )
                    failure_bucket = payment_failure_counts.setdefault(
                        failure_key,
                        {
                            "failures_count": 0,
                            "content_type": snapshot.content_type,
                        },
                    )
                    failure_bucket["failures_count"] += 1

                if event.event_name in ROLLUP_CONNECTION_EVENTS:
                    connection_key = (
                        bucket,
                        source_mode,
                        snapshot.source_type,
                        snapshot.source_key,
                        snapshot.channel_item_id,
                        str(event.country_code or payload.get("country_code") or "").strip().lower() or None,
                    )
                    connection_bucket = connection_counts.setdefault(
                        connection_key,
                        {
                            "config_issued_count": 0,
                            "config_issue_failed_count": 0,
                            "first_connection_success_count": 0,
                            "connection_failed_count": 0,
                            "lag_values": [],
                            "content_type": snapshot.content_type,
                        },
                    )
                    if event.event_name == EVENT_CONFIG_ISSUED:
                        connection_bucket["config_issued_count"] += 1
                    elif event.event_name == EVENT_CONFIG_ISSUE_FAILED:
                        connection_bucket["config_issue_failed_count"] += 1
                    elif event.event_name == EVENT_CONNECTION_FAILED:
                        connection_bucket["connection_failed_count"] += 1
                    elif event.event_name == EVENT_FIRST_CONNECTION_SUCCESS:
                        connection_bucket["first_connection_success_count"] += 1
                        config_event = next(
                            (
                                candidate
                                for candidate in reversed(config_issued_events)
                                if candidate.user_id == event.user_id
                                and (candidate.vpn_client_id == event.vpn_client_id or candidate.vpn_client_id is None or event.vpn_client_id is None)
                                and candidate.occurred_at <= event.occurred_at
                            ),
                            None,
                        )
                        if config_event is not None:
                            lag_minutes = int(max((event.occurred_at - config_event.occurred_at).total_seconds(), 0) // 60)
                            connection_bucket["lag_values"].append(lag_minutes)

        stage_rows = [
            AnalyticsDailyStageCount(
                bucket_date=bucket,
                event_name=event_name,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                events_count=int(data["events_count"]),
                users_count=len(data["user_ids"]),
                updated_at=_utcnow(),
            )
            for (bucket_date, event_name, source_mode, source_type, source_key, channel_item_id), data in stage_counts.items()
            if bucket_date == bucket
        ]
        await _replace_daily_stage_rows(bucket, stage_rows)
        stage_segment_rows = [
            AnalyticsDailyStageSegment(
                bucket_date=bucket,
                event_name=event_name,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                user_segment=user_segment,
                events_count=int(data["events_count"]),
                users_count=len(data["user_ids"]),
                updated_at=now,
            )
            for (bucket_date, event_name, source_mode, source_type, source_key, channel_item_id, user_segment), data in stage_segments.items()
            if bucket_date == bucket
        ]
        await _replace_daily_stage_segment_rows(bucket, stage_segment_rows)

        revenue_rows = [
            AnalyticsDailyRevenue(
                bucket_date=bucket,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_kind=payment_kind,
                payments_count=int(data["payments_count"]),
                revenue_amount_rub=int(data["revenue_amount_rub"]),
                updated_at=_utcnow(),
            )
            for (
                bucket_date,
                source_mode,
                source_type,
                source_key,
                channel_item_id,
                tariff_code,
                payment_method,
                payment_kind,
            ), data in revenue_counts.items()
            if bucket_date == bucket
        ]
        await _replace_daily_revenue_rows(bucket, revenue_rows)
        revenue_segment_rows = [
            AnalyticsDailyRevenueSegment(
                bucket_date=bucket,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                tariff_code=tariff_code,
                payment_method=payment_method,
                payment_kind=payment_kind,
                user_segment=user_segment,
                payments_count=int(data["payments_count"]),
                revenue_amount_rub=int(data["revenue_amount_rub"]),
                updated_at=now,
            )
            for (
                bucket_date,
                source_mode,
                source_type,
                source_key,
                channel_item_id,
                tariff_code,
                payment_method,
                payment_kind,
                user_segment,
            ), data in revenue_segments.items()
            if bucket_date == bucket
        ]
        await _replace_daily_revenue_segment_rows(bucket, revenue_segment_rows)

        connection_rows = [
            AnalyticsDailyConnection(
                bucket_date=bucket,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                country_code=country_code,
                config_issued_count=int(data["config_issued_count"]),
                config_issue_failed_count=int(data["config_issue_failed_count"]),
                first_connection_success_count=int(data["first_connection_success_count"]),
                connection_failed_count=int(data["connection_failed_count"]),
                avg_first_connection_lag_minutes=int(sum(data["lag_values"]) / len(data["lag_values"])) if data["lag_values"] else 0,
                updated_at=_utcnow(),
            )
            for (bucket_date, source_mode, source_type, source_key, channel_item_id, country_code), data in connection_counts.items()
            if bucket_date == bucket
        ]
        await _replace_daily_connection_rows(bucket, connection_rows)
        payment_failure_rows = [
            AnalyticsDailyPaymentFailureReason(
                bucket_date=bucket,
                source_mode=source_mode,
                source_type=source_type,
                source_key=source_key,
                channel_item_id=channel_item_id,
                content_type=data.get("content_type"),
                payment_method=payment_method,
                reason_key=reason_key,
                failures_count=int(data["failures_count"]),
                updated_at=_utcnow(),
            )
            for (
                bucket_date,
                source_mode,
                source_type,
                source_key,
                channel_item_id,
                payment_method,
                reason_key,
            ), data in payment_failure_counts.items()
            if bucket_date == bucket
        ]
        await _replace_daily_payment_failure_reason_rows(bucket, payment_failure_rows)
        integrity_rows = [
            AnalyticsDailyAttributionIntegrity(
                bucket_date=bucket,
                issue_type=issue_type,
                issue_count=int(data["issue_count"]),
                affected_users_count=len(data["user_ids"]),
                total_bot_start_count=total_bot_start_count,
                updated_at=_utcnow(),
            )
            for issue_type, data in attribution_issue_counts.items()
        ]
        await _replace_daily_attribution_integrity_rows(bucket, integrity_rows)

    cohorts_by_type_date: dict[tuple[str, date], set[int]] = defaultdict(set)
    for row in cohort_start_rows:
        if row.user_id is None:
            continue
        cohorts_by_type_date[(row.event_name, row.occurred_at.date())].add(int(row.user_id))

    cohort_refresh_count = 0
    for (cohort_type, cohort_date_value), cohort_user_ids in sorted(cohorts_by_type_date.items(), key=lambda item: (item[0][0], item[0][1])):
        rows: list[AnalyticsCohortRetention] = []
        cohort_size = len(cohort_user_ids)
        for period_days in COHORT_PERIOD_DAYS:
            deadline = datetime.combine(cohort_date_value, time.min) + timedelta(days=period_days + 1)
            if force_full:
                relevant = [
                    event
                    for event in events if event.user_id is not None and int(event.user_id) in cohort_user_ids and event.occurred_at < deadline
                ]
            else:
                async with async_session() as session:
                    relevant = list(
                        (
                            await session.execute(
                                select(AnalyticsEvent).where(
                                    AnalyticsEvent.user_id.in_(sorted(cohort_user_ids)),
                                    AnalyticsEvent.occurred_at < deadline,
                                )
                            )
                        ).scalars().all()
                    )
            connected_users = {int(event.user_id) for event in relevant if event.user_id is not None and event.event_name == EVENT_FIRST_CONNECTION_SUCCESS}
            converted_users = {
                int(event.user_id)
                for event in relevant
                if event.user_id is not None and event.event_name == EVENT_SUBSCRIPTION_ACTIVATED
            }
            renewed_users = {int(event.user_id) for event in relevant if event.user_id is not None and event.event_name == EVENT_SUBSCRIPTION_RENEWED}
            expired_users = {int(event.user_id) for event in relevant if event.user_id is not None and event.event_name == EVENT_SUBSCRIPTION_EXPIRED}
            latest_active_markers: dict[int, datetime] = {}
            latest_expired_markers: dict[int, datetime] = {}
            for event in relevant:
                if event.user_id is None:
                    continue
                user_id = int(event.user_id)
                if event.event_name in {EVENT_TRIAL_STARTED, EVENT_SUBSCRIPTION_ACTIVATED, EVENT_SUBSCRIPTION_RENEWED}:
                    latest_active_markers[user_id] = max(
                        latest_active_markers.get(user_id, datetime.min),
                        event.occurred_at,
                    )
                elif event.event_name == EVENT_SUBSCRIPTION_EXPIRED:
                    latest_expired_markers[user_id] = max(
                        latest_expired_markers.get(user_id, datetime.min),
                        event.occurred_at,
                    )
            active_users = {
                user_id
                for user_id, marker in latest_active_markers.items()
                if marker > latest_expired_markers.get(user_id, datetime.min)
            }
            rows.append(
                AnalyticsCohortRetention(
                    cohort_type=cohort_type,
                    cohort_date=cohort_date_value,
                    period_days=period_days,
                    cohort_size=cohort_size,
                    connected_users=len(connected_users),
                    converted_users=len(converted_users),
                    renewed_users=len(renewed_users),
                    expired_users=len(expired_users),
                    active_users=len(active_users),
                    updated_at=now,
                )
            )
        await _replace_cohort_rows(cohort_type=cohort_type, cohort_date_value=cohort_date_value, rows=rows)
        cohort_refresh_count += 1

    last_event_at = max(
        [event.occurred_at for event in events if getattr(event, "occurred_at", None) is not None]
        + [touch.first_seen_at for touch in touch_rows if getattr(touch, "first_seen_at", None) is not None],
        default=previous_cursor,
    )
    await _set_refresh_cursor(
        REFRESH_STATE_LAST_EVENT_AT,
        last_event_at,
        metadata={
            "dates_refreshed": len(all_event_dates),
            "cohorts_refreshed": cohort_refresh_count,
        },
    )
    source_integrity_status, source_integrity_detail = _bot_start_integrity_payload(recent_bot_start_events)
    await _set_runtime_status(
        status_key=RUNTIME_STATUS_SOURCE_KEY_INTEGRITY,
        status_group="growth",
        status_value=source_integrity_status,
        observed_at=now,
        detail=source_integrity_detail,
    )
    active_access_count = sum(1 for user in real_users if has_active_access_from_user(user))
    await _set_runtime_status(
        status_key=RUNTIME_STATUS_GROWTH_ACTIVE_USERS,
        status_group="growth",
        status_value="healthy",
        observed_at=now,
        detail={
            "active_users": active_access_count,
            "real_users": len(real_users),
        },
    )
    deleted_old_events = await prune_analytics_events()
    return {
        "dates_refreshed": len(all_event_dates),
        "cohorts_refreshed": cohort_refresh_count,
        "events_scanned": len(events),
        "touches_scanned": len(touch_rows),
        "deleted_old_events": deleted_old_events,
    }


async def refresh_ops_analytics_rollups(*, force_full: bool = False) -> dict[str, int | str]:
    await ensure_schema()

    now = _utcnow()
    current_hour = _hour_floor(now)
    previous_cursor = None if force_full else await _get_refresh_cursor(REFRESH_STATE_LAST_OPS_EVENT_AT)
    minimum_start = now - timedelta(days=OPS_ROLLUP_MAX_LOOKBACK_DAYS)
    if previous_cursor is None:
        query_start = minimum_start
    else:
        query_start = max(previous_cursor - timedelta(hours=OPS_ROLLUP_REWIND_HOURS), minimum_start)

    async with async_session() as session:
        events = list(
            (
                await session.execute(
                    select(ControlNotificationEvent)
                    .where(
                        or_(
                            ControlNotificationEvent.created_at >= query_start,
                            ControlNotificationEvent.resolved_at >= query_start,
                        )
                    )
                    .order_by(ControlNotificationEvent.created_at.asc(), ControlNotificationEvent.id.asc())
                )
            ).scalars().all()
        )
        all_unresolved_events = list(
            (
                await session.execute(
                    select(ControlNotificationEvent).where(ControlNotificationEvent.resolved_at.is_(None))
                )
            ).scalars().all()
        )
        repair_users = list(
            (
                await session.execute(
                    select(User).where(
                        User.vpn_repair_needed.is_(True),
                    )
                )
            ).scalars().all()
        )
    repair_users = [user for user in repair_users if not is_synthetic_user(user)]

    bucket_hours = {current_hour}
    for event in events:
        if getattr(event, "created_at", None) is not None and event.created_at >= query_start:
            bucket_hours.add(_hour_floor(event.created_at))
        if getattr(event, "resolved_at", None) is not None and event.resolved_at >= query_start:
            bucket_hours.add(_hour_floor(event.resolved_at))

    refreshed_hours = 0
    for bucket_hour in sorted(bucket_hours):
        bucket_end = bucket_hour + timedelta(hours=1)
        created_rows = [
            row
            for row in events
            if getattr(row, "created_at", None) is not None and bucket_hour <= row.created_at < bucket_end
        ]
        resolved_rows = [
            row
            for row in events
            if getattr(row, "resolved_at", None) is not None and bucket_hour <= row.resolved_at < bucket_end
        ]
        grouped: dict[tuple, dict[str, object]] = {}
        for row in created_rows:
            incident_class = _control_event_incident_class(row)
            key = (
                incident_class,
                str(getattr(row, "category", "") or "").strip().lower() or "system",
                str(getattr(row, "severity", "") or "").strip().upper() or "INFO",
                str(getattr(row, "event_type", "") or "").strip().lower() or "unknown",
            )
            bucket = grouped.setdefault(
                key,
                {
                    "created_count": 0,
                    "resolved_count": 0,
                    "repeated_count": 0,
                    "entity_keys": set(),
                },
            )
            bucket["created_count"] += 1
            bucket["repeated_count"] += int(getattr(row, "repeat_count", 0) or 0)
            bucket["entity_keys"].add(_control_event_entity_key(row))
        for row in resolved_rows:
            incident_class = _control_event_incident_class(row)
            key = (
                incident_class,
                str(getattr(row, "category", "") or "").strip().lower() or "system",
                str(getattr(row, "severity", "") or "").strip().upper() or "INFO",
                str(getattr(row, "event_type", "") or "").strip().lower() or "unknown",
            )
            bucket = grouped.setdefault(
                key,
                {
                    "created_count": 0,
                    "resolved_count": 0,
                    "repeated_count": 0,
                    "entity_keys": set(),
                },
            )
            bucket["resolved_count"] += 1
        rows = [
            AnalyticsHourlyOpsIncident(
                bucket_hour=bucket_hour,
                incident_class=incident_class,
                category=category,
                severity=severity,
                event_type=event_type,
                created_count=int(data["created_count"]),
                resolved_count=int(data["resolved_count"]),
                repeated_count=int(data["repeated_count"]),
                unique_entities_count=len(data["entity_keys"]),
                updated_at=now,
            )
            for (incident_class, category, severity, event_type), data in grouped.items()
        ]
        await _replace_hourly_ops_incident_rows(bucket_hour, rows)
        refreshed_hours += 1

    unresolved_events = [
        row
        for row in all_unresolved_events
        if str(getattr(row, "severity", "") or "").strip().upper() in {"WARNING", "CRITICAL"}
    ]
    unresolved_warning_count = sum(
        1 for row in unresolved_events if str(getattr(row, "severity", "") or "").strip().upper() == "WARNING"
    )
    unresolved_critical_count = sum(
        1 for row in unresolved_events if str(getattr(row, "severity", "") or "").strip().upper() == "CRITICAL"
    )
    unresolved_access_count = sum(
        1 for row in unresolved_events if str(getattr(row, "category", "") or "").strip().lower() == "access"
    )
    unresolved_node_count = sum(
        1 for row in unresolved_events if str(getattr(row, "category", "") or "").strip().lower() == "nodes"
    )
    unresolved_service_count = sum(
        1 for row in unresolved_events if str(getattr(row, "event_type", "") or "").strip().lower() in SERVICE_INCIDENT_EVENT_TYPES
    )
    lookback_24h = now - timedelta(hours=24)
    provisioning_failure_events_24h = sum(
        1
        for row in events
        if getattr(row, "created_at", None) is not None
        and row.created_at >= lookback_24h
        and str(getattr(row, "event_type", "") or "").strip().lower() in PROVISIONING_FAILURE_EVENT_TYPES
    )
    reconcile_failure_events_24h = sum(
        1
        for row in events
        if getattr(row, "created_at", None) is not None
        and row.created_at >= lookback_24h
        and str(getattr(row, "event_type", "") or "").strip().lower() in RECONCILE_FAILURE_EVENT_TYPES
    )
    await _upsert_hourly_ops_snapshot(
        AnalyticsHourlyOpsSnapshot(
            bucket_hour=current_hour,
            repair_needed_open_count=len(repair_users),
            unresolved_incident_count=len(unresolved_events),
            unresolved_warning_count=unresolved_warning_count,
            unresolved_critical_count=unresolved_critical_count,
            unresolved_access_count=unresolved_access_count,
            unresolved_node_count=unresolved_node_count,
            unresolved_service_count=unresolved_service_count,
            provisioning_failure_events_24h=provisioning_failure_events_24h,
            reconcile_failure_events_24h=reconcile_failure_events_24h,
            updated_at=now,
        )
    )

    payment_related_repairs = 0
    for user in repair_users:
        reason = str(getattr(user, "vpn_repair_reason", "") or "").strip().lower()
        if "payment" in reason:
            payment_related_repairs += 1

    await _set_runtime_status(
        status_key=RUNTIME_STATUS_ANALYTICS_REFRESH,
        status_group="analytics",
        status_value="healthy",
        observed_at=now,
        detail={
            "query_start": query_start.isoformat(),
            "previous_cursor": previous_cursor.isoformat() if previous_cursor is not None else None,
            "hours_refreshed": refreshed_hours,
            "events_scanned": len(events),
        },
    )
    restore_status_value, restore_observed_at, restore_detail = _restore_proof_runtime_payload(now=now)
    await _set_runtime_status(
        status_key=RUNTIME_STATUS_RESTORE_PROOF,
        status_group="backup",
        status_value=restore_status_value,
        observed_at=restore_observed_at,
        detail=restore_detail,
    )
    await _set_runtime_status(
        status_key=RUNTIME_STATUS_REPAIR_OPEN,
        status_group="ops",
        status_value="warning" if repair_users else "healthy",
        observed_at=now,
        detail={
            "repair_needed_open_count": len(repair_users),
            "payment_related_repairs": payment_related_repairs,
        },
    )
    open_incident_status = "critical" if unresolved_critical_count > 0 else "warning" if unresolved_events else "healthy"
    await _set_runtime_status(
        status_key=RUNTIME_STATUS_OPEN_INCIDENTS,
        status_group="ops",
        status_value=open_incident_status,
        observed_at=now,
        detail={
            "unresolved_incident_count": len(unresolved_events),
            "warning_count": unresolved_warning_count,
            "critical_count": unresolved_critical_count,
            "access_count": unresolved_access_count,
            "node_count": unresolved_node_count,
            "service_count": unresolved_service_count,
        },
    )
    await _set_refresh_cursor(
        REFRESH_STATE_LAST_OPS_EVENT_AT,
        now,
        metadata={
            "hours_refreshed": refreshed_hours,
            "events_scanned": len(events),
        },
    )
    return {
        "hours_refreshed": refreshed_hours,
        "events_scanned": len(events),
        "repair_open_count": len(repair_users),
        "unresolved_incidents": len(unresolved_events),
    }


async def backfill_analytics_user_attribution(*, limit: int | None = None) -> dict[str, int]:
    await ensure_schema()

    async with async_session() as session:
        users = list((await session.execute(select(User).order_by(User.id.asc()))).scalars().all())
        touches = list(
            (
                await session.execute(
                    select(ChannelPostTouch).order_by(ChannelPostTouch.user_id.asc(), ChannelPostTouch.first_seen_at.asc(), ChannelPostTouch.id.asc())
                )
            ).scalars().all()
        )
        items = list((await session.execute(select(ChannelContentItem))).scalars().all())
        attribution_rows = list(
            (
                await session.execute(
                    select(AnalyticsUserAttribution).order_by(AnalyticsUserAttribution.user_id.asc())
                )
            ).scalars().all()
        )
        fallback_events = list(
            (
                await session.execute(
                    select(AnalyticsEvent)
                    .where(AnalyticsEvent.event_name.in_((EVENT_LINK_TOUCHED, EVENT_BOT_START)))
                    .order_by(
                        AnalyticsEvent.user_id.asc(),
                        AnalyticsEvent.occurred_at.asc(),
                        AnalyticsEvent.id.asc(),
                    )
                )
            ).scalars().all()
        )

    item_tokens = {int(item.id): str(item.deep_link_token or "").strip().lower() for item in items}
    touches_by_user: dict[int, list[ChannelPostTouch]] = defaultdict(list)
    for touch in touches:
        touches_by_user[int(touch.user_id)].append(touch)
    current_attr_by_user = {int(row.user_id): row for row in attribution_rows if getattr(row, "user_id", None) is not None}
    fallback_candidates_by_user: dict[int, list[tuple[datetime, str, str, int | None]]] = defaultdict(list)
    for event in fallback_events:
        if getattr(event, "user_id", None) is None:
            continue
        payload = _safe_json_loads(getattr(event, "payload_json", None))
        source_type = str(payload.get("source_type") or "").strip().lower()
        source_key = str(payload.get("source_key") or "").strip().lower()
        if source_type != SOURCE_TYPE_CHANNEL_POST or not source_key or source_key == SOURCE_TYPE_ORGANIC:
            continue
        occurred_at = getattr(event, "occurred_at", None)
        if occurred_at is None:
            continue
        fallback_candidates_by_user[int(event.user_id)].append(
            (
                occurred_at,
                SOURCE_TYPE_CHANNEL_POST,
                source_key,
                int(event.channel_item_id) if getattr(event, "channel_item_id", None) is not None else None,
            )
        )

    processed = 0
    attributed = 0
    for user in users:
        if is_synthetic_user(user):
            continue
        processed += 1
        user_touches = touches_by_user.get(int(user.id), [])
        fallback_candidates = fallback_candidates_by_user.get(int(user.id), [])
        source_candidates: list[tuple[datetime, str, str, int | None]] = []
        for touch in user_touches:
            item_id = int(touch.item_id)
            source_candidates.append(
                (
                    touch.first_seen_at,
                    SOURCE_TYPE_CHANNEL_POST,
                    item_tokens.get(item_id) or f"channel-item-{item_id}",
                    item_id,
                )
            )
            if touch.last_seen_at and touch.last_seen_at != touch.first_seen_at:
                source_candidates.append(
                    (
                        touch.last_seen_at,
                        SOURCE_TYPE_CHANNEL_POST,
                        item_tokens.get(item_id) or f"channel-item-{item_id}",
                        item_id,
                    )
                )
        source_candidates.extend(fallback_candidates)
        source_candidates.sort(key=lambda value: (value[0], value[3] or 0, value[2]))
        current_row = current_attr_by_user.get(int(user.id))

        if source_candidates:
            first_seen_at, first_source_type, first_source_key, first_channel_item_id = source_candidates[0]
            last_seen_at, last_source_type, last_source_key, last_channel_item_id = source_candidates[-1]
            created_at = getattr(user, "created_at", None)
            delta_seconds: float | None = None
            if created_at is not None:
                delta_seconds = (first_seen_at - created_at).total_seconds()

            should_preserve_organic_first = (
                current_row is not None
                and str(getattr(current_row, "first_source_key", "") or "").strip().lower() == SOURCE_TYPE_ORGANIC
            )
            if should_preserve_organic_first and delta_seconds is not None and delta_seconds <= 300:
                should_preserve_organic_first = False
            if current_row is None and delta_seconds is not None:
                should_preserve_organic_first = delta_seconds > 300

            if should_preserve_organic_first:
                row = await upsert_user_attribution(
                    user_id=int(user.id),
                    telegram_id=getattr(user, "telegram_id", None),
                    source_type=SOURCE_TYPE_ORGANIC,
                    source_key=SOURCE_TYPE_ORGANIC,
                    channel_item_id=None,
                    seen_at=created_at or _utcnow(),
                )
            else:
                row = await upsert_user_attribution(
                    user_id=int(user.id),
                    telegram_id=getattr(user, "telegram_id", None),
                    source_type=first_source_type,
                    source_key=first_source_key,
                    channel_item_id=first_channel_item_id,
                    seen_at=first_seen_at,
                    override_first=(
                        current_row is not None
                        and str(getattr(current_row, "first_source_key", "") or "").strip().lower() == SOURCE_TYPE_ORGANIC
                    ),
                )
            should_update_last = (
                row is not None
                and (
                    current_row is None
                    or getattr(current_row, "last_seen_at", None) is None
                    or last_seen_at >= current_row.last_seen_at
                    or str(getattr(current_row, "last_source_key", "") or "").strip().lower() == SOURCE_TYPE_ORGANIC
                )
            )
            if should_update_last:
                await upsert_user_attribution(
                    user_id=int(user.id),
                    telegram_id=getattr(user, "telegram_id", None),
                    source_type=last_source_type,
                    source_key=last_source_key,
                    channel_item_id=last_channel_item_id,
                    seen_at=last_seen_at,
                )
            if row is not None:
                attributed += 1
        else:
            row = await upsert_user_attribution(
                user_id=int(user.id),
                telegram_id=getattr(user, "telegram_id", None),
                source_type=SOURCE_TYPE_ORGANIC,
                source_key=SOURCE_TYPE_ORGANIC,
                channel_item_id=None,
                seen_at=getattr(user, "created_at", None) or _utcnow(),
            )
            if row is not None:
                attributed += 1
        if limit is not None and attributed >= max(int(limit), 0):
            break
    return {"processed": processed, "attributed": attributed}


async def backfill_analytics_events(*, limit: int | None = None) -> dict[str, int]:
    await ensure_schema()

    counters = defaultdict(int)
    max_items = None if limit is None else max(int(limit), 0)

    async with async_session() as session:
        users = list((await session.execute(select(User).order_by(User.id.asc()))).scalars().all())
        touches = list((await session.execute(select(ChannelPostTouch).order_by(ChannelPostTouch.id.asc()))).scalars().all())
        items = list((await session.execute(select(ChannelContentItem))).scalars().all())
        payments = list((await session.execute(select(PaymentRecord).order_by(PaymentRecord.id.asc()))).scalars().all())
        vpn_clients = list((await session.execute(select(VpnClient).order_by(VpnClient.created_at.asc(), VpnClient.id.asc()))).scalars().all())
        activations = list((await session.execute(select(VpnClientActivation).order_by(VpnClientActivation.id.asc()))).scalars().all())
        finance_entries = list(
            (
                await session.execute(
                    select(FinanceEntry).where(FinanceEntry.source_type == "payment_record")
                )
            ).scalars().all()
        )

    finance_by_payment = {str(entry.source_id): entry for entry in finance_entries if entry.source_id}
    item_tokens = {int(item.id): str(item.deep_link_token or "").strip().lower() for item in items}
    subscription_payment_kind_by_id = _classify_subscription_payment_kinds(payments)

    for user in users:
        if is_synthetic_user(user):
            continue
        if getattr(user, "created_at", None) is None:
            continue
        created = await emit_analytics_event(
            event_name=EVENT_USER_FIRST_SEEN,
            occurred_at=user.created_at,
            user_id=int(user.id),
            telegram_id=getattr(user, "telegram_id", None),
            dedupe_key=f"user-first-seen:{int(user.id)}",
            payload={"source": "backfill"},
        )
        if created is not None:
            counters[EVENT_USER_FIRST_SEEN] += 1
        if getattr(user, "trial_started_at", None) is not None:
            created = await emit_analytics_event(
                event_name=EVENT_CHANNEL_MEMBERSHIP_CONFIRMED,
                occurred_at=user.trial_started_at,
                user_id=int(user.id),
                telegram_id=getattr(user, "telegram_id", None),
                dedupe_key=f"channel-membership-confirmed:{int(user.id)}",
                payload={"source": "backfill"},
            )
            if created is not None:
                counters[EVENT_CHANNEL_MEMBERSHIP_CONFIRMED] += 1
            created = await emit_analytics_event(
                event_name=EVENT_TRIAL_STARTED,
                occurred_at=user.trial_started_at,
                user_id=int(user.id),
                telegram_id=getattr(user, "telegram_id", None),
                dedupe_key=f"trial-started:{int(user.id)}",
                payload={"source": "backfill"},
            )
            if created is not None:
                counters[EVENT_TRIAL_STARTED] += 1
        if max_items is not None and sum(counters.values()) >= max_items:
            return dict(counters)

    earliest_vpn_client_by_user: dict[int, VpnClient] = {}
    for vpn_client in vpn_clients:
        if getattr(vpn_client, "user_id", None) is None or getattr(vpn_client, "created_at", None) is None:
            continue
        user_id = int(vpn_client.user_id)
        earliest_vpn_client_by_user.setdefault(user_id, vpn_client)
    for user_id, vpn_client in earliest_vpn_client_by_user.items():
        created = await emit_analytics_event(
            event_name=EVENT_CONNECTION_READY,
            occurred_at=vpn_client.created_at,
            user_id=user_id,
            dedupe_key=f"connection-ready:{user_id}",
            vpn_client_id=int(vpn_client.id),
            payload={"source": "backfill"},
        )
        if created is not None:
            counters[EVENT_CONNECTION_READY] += 1
        if max_items is not None and sum(counters.values()) >= max_items:
            return dict(counters)

    for touch in touches:
        source_key = item_tokens.get(int(touch.item_id)) or f"channel-item-{int(touch.item_id)}"
        created = await emit_analytics_event(
            event_name=EVENT_BOT_START,
            occurred_at=touch.first_seen_at,
            user_id=int(touch.user_id),
            telegram_id=int(touch.telegram_id),
            dedupe_key=f"bot-start:{int(touch.user_id)}:{SOURCE_TYPE_CHANNEL_POST}:{source_key}",
            channel_item_id=int(touch.item_id),
            payload={
                "source": "backfill",
                "source_type": SOURCE_TYPE_CHANNEL_POST,
                "source_key": source_key,
                "channel_item_id": int(touch.item_id),
            },
        )
        if created is not None:
            counters[EVENT_BOT_START] += 1
        if max_items is not None and sum(counters.values()) >= max_items:
            return dict(counters)

    for payment in payments:
        user_id = getattr(payment, "user_id", None)
        if user_id is None:
            continue
        product_type = _payment_product_type(payment)
        created = await emit_analytics_event(
            event_name=EVENT_PAYMENT_STARTED,
            occurred_at=getattr(payment, "created_at", None) or _utcnow(),
            user_id=int(user_id),
            dedupe_key=f"payment-started:{int(payment.id)}",
            payment_record_id=int(payment.id),
            tariff_code=getattr(payment, "tariff_code", None),
            payment_method=getattr(payment, "payment_method", None),
            payload={
                "amount_rub": int(getattr(payment, "amount", 0) or 0),
                "list_price_amount": int(getattr(payment, "list_price_amount", 0) or getattr(payment, "amount", 0) or 0),
                "product_type": product_type,
                "source": "backfill",
            },
        )
        if created is not None:
            counters[EVENT_PAYMENT_STARTED] += 1
        if product_type == "subscription":
            created = await emit_analytics_event(
                event_name=EVENT_SUBSCRIPTION_PAYMENT_STARTED,
                occurred_at=getattr(payment, "created_at", None) or _utcnow(),
                user_id=int(user_id),
                dedupe_key=f"subscription-payment-started:{int(payment.id)}",
                payment_record_id=int(payment.id),
                tariff_code=getattr(payment, "tariff_code", None),
                payment_method=getattr(payment, "payment_method", None),
                payload={
                    "amount_rub": int(getattr(payment, "amount", 0) or 0),
                    "list_price_amount": int(getattr(payment, "list_price_amount", 0) or getattr(payment, "amount", 0) or 0),
                    "product_type": product_type,
                    "source": "backfill",
                },
            )
            if created is not None:
                counters[EVENT_SUBSCRIPTION_PAYMENT_STARTED] += 1

        if getattr(payment, "payment_status", None) == "confirmed":
            confirmed_at = getattr(payment, "confirmed_at", None) or getattr(payment, "created_at", None) or _utcnow()
            entry = finance_by_payment.get(str(payment.id))
            payment_kind = subscription_payment_kind_by_id.get(int(payment.id), PAYMENT_KIND_OTHER if product_type != "subscription" else PAYMENT_KIND_UNKNOWN)
            created = await emit_analytics_event(
                event_name=EVENT_PAYMENT_SUCCESS,
                occurred_at=confirmed_at,
                user_id=int(user_id),
                dedupe_key=f"payment-success:{int(payment.id)}",
                payment_record_id=int(payment.id),
                tariff_code=getattr(payment, "tariff_code", None),
                payment_method=getattr(payment, "payment_method", None),
                payload={
                    "amount_rub": int(getattr(payment, "amount", 0) or 0),
                    "product_type": product_type,
                    "payment_kind": payment_kind,
                    "finance_entry_id": int(entry.id) if entry is not None else None,
                    "source": "backfill",
                },
            )
            if created is not None:
                counters[EVENT_PAYMENT_SUCCESS] += 1

            if product_type == "subscription" and payment_kind in {PAYMENT_KIND_NEW, PAYMENT_KIND_RENEWAL}:
                subscription_event_name = EVENT_SUBSCRIPTION_ACTIVATED if payment_kind == PAYMENT_KIND_NEW else EVENT_SUBSCRIPTION_RENEWED
                subscription_dedupe_prefix = "subscription-activated" if payment_kind == PAYMENT_KIND_NEW else "subscription-renewed"
                created = await emit_analytics_event(
                    event_name=subscription_event_name,
                    occurred_at=confirmed_at,
                    user_id=int(user_id),
                    dedupe_key=f"{subscription_dedupe_prefix}:payment:{int(payment.id)}",
                    payment_record_id=int(payment.id),
                    tariff_code=getattr(payment, "tariff_code", None),
                    payment_method=getattr(payment, "payment_method", None),
                    payload={
                        "amount_rub": int(getattr(payment, "amount", 0) or 0),
                        "payment_kind": payment_kind,
                        "source": "backfill",
                    },
                )
                if created is not None:
                    counters[subscription_event_name] += 1
        elif _payment_failed_status(getattr(payment, "payment_status", None)):
            failure_at = getattr(payment, "reviewed_at", None) or getattr(payment, "expires_at", None) or getattr(payment, "created_at", None) or _utcnow()
            created = await emit_analytics_event(
                event_name=EVENT_PAYMENT_FAILED,
                occurred_at=failure_at,
                user_id=int(user_id),
                dedupe_key=f"payment-failed:{int(payment.id)}:{str(payment.payment_status).strip().lower()}",
                payment_record_id=int(payment.id),
                tariff_code=getattr(payment, "tariff_code", None),
                payment_method=getattr(payment, "payment_method", None),
                payload={
                    "payment_status": getattr(payment, "payment_status", None),
                    "rejection_reason": getattr(payment, "rejection_reason", None),
                    "product_type": _payment_product_type(payment),
                    "source": "backfill",
                },
            )
            if created is not None:
                counters[EVENT_PAYMENT_FAILED] += 1
            if product_type == "subscription":
                created = await emit_analytics_event(
                    event_name=EVENT_SUBSCRIPTION_PAYMENT_FAILED,
                    occurred_at=failure_at,
                    user_id=int(user_id),
                    dedupe_key=f"subscription-payment-failed:{int(payment.id)}:{str(payment.payment_status).strip().lower()}",
                    payment_record_id=int(payment.id),
                    tariff_code=getattr(payment, "tariff_code", None),
                    payment_method=getattr(payment, "payment_method", None),
                    payload={
                        "payment_status": getattr(payment, "payment_status", None),
                        "rejection_reason": getattr(payment, "rejection_reason", None),
                        "product_type": product_type,
                        "source": "backfill",
                    },
                )
                if created is not None:
                    counters[EVENT_SUBSCRIPTION_PAYMENT_FAILED] += 1

        if max_items is not None and sum(counters.values()) >= max_items:
            return dict(counters)

    for activation in activations:
        if getattr(activation, "user_id", None) is None:
            continue
        created = await emit_analytics_event(
            event_name=EVENT_FIRST_CONNECTION_SUCCESS,
            occurred_at=getattr(activation, "first_activated_at", None) or _utcnow(),
            user_id=int(activation.user_id),
            telegram_id=None,
            dedupe_key=f"first-connection:{int(activation.id)}",
            vpn_client_id=int(activation.vpn_client_id),
            country_code=getattr(activation, "country_code", None),
            payload={
                "activation_count": int(getattr(activation, "activation_count", 0) or 0),
                "source": "backfill",
            },
        )
        if created is not None:
            counters[EVENT_FIRST_CONNECTION_SUCCESS] += 1
        if max_items is not None and sum(counters.values()) >= max_items:
            return dict(counters)

    return dict(counters)


async def run_analytics_maintenance(*, backfill: bool = False, full_refresh: bool = False) -> dict[str, object]:
    attribution_result = {"processed": 0, "attributed": 0}
    backfill_result: dict[str, int] | None = None
    if backfill:
        attribution_result = await backfill_analytics_user_attribution()
        backfill_result = await backfill_analytics_events()
    refresh_result = await refresh_analytics_rollups(force_full=full_refresh)
    ops_refresh_result = await refresh_ops_analytics_rollups(force_full=full_refresh)
    return {
        "attribution": attribution_result,
        "backfill": backfill_result,
        "refresh": refresh_result,
        "ops_refresh": ops_refresh_result,
    }
