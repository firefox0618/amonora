import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import httpx
from aiogram import Bot

from backend.core.analytics import (
    EVENT_PAYMENT_SUCCESS,
    PAYMENT_KIND_OTHER,
    PAYMENT_KIND_UNKNOWN,
    safe_emit_analytics_event,
)
from backend.core.promo_codes import (
    consume_discount_redemption_from_payment_record,
    create_gift_promo_code_for_payment,
)
from bot.config import config
from dashboard.security import utcnow
from bot.db import (
    activate_paid_subscription,
    clear_payment_record_finance_synced,
    claim_payment_record_effect,
    clear_vpn_repair_needed,
    credit_user_balance,
    create_device_slot_entitlement,
    create_vpn_repair_event,
    get_active_device_slot_counts_for_users,
    get_access_expires_at,
    get_payment_record_by_id,
    update_payment_record_metadata,
    get_user_by_id,
    get_user_vpn_clients,
    list_confirmed_payment_records_needing_full_reconcile,
    mark_payment_record_finance_synced,
    mark_payment_record_effect_applied,
    payment_record_reconcile_state,
    payment_record_requires_access_sync,
    payment_record_requires_finance_sync,
    payment_record_effect_applied,
    payment_record_effect_processing,
    payment_record_trace_id,
    mark_vpn_repair_needed,
    process_referral_reward_for_payment,
    release_payment_record_effect_claim,
    refresh_payment_record_reconcile_state,
    PAYMENT_ACCESS_SYNCED_AT_KEY,
    PAYMENT_ACCESS_SYNC_STATE_KEY,
    update_vpn_client_metadata,
)
from bot.user_notifications import send_user_message, send_user_message_and_refresh_home
from bot.utils.access import get_device_limit_for_user, has_active_subscription_from_user
from bot.utils.device_slots import (
    DEVICE_SLOT_PRODUCT_TYPE,
    clamp_device_slot_count,
    device_slot_display_title,
    device_slot_unit_price_rub,
    payment_product_type,
)
from bot.repair_reasons import (
    AUTO_REPAIR_FAILED,
    AUTO_REPAIR_SUCCESS,
    POST_PAYMENT_ACCESS_INCOMPLETE,
    POST_PAYMENT_SYNC_FAILED,
)
from bot.public_subscription import sync_public_subscription_access
from bot.utils.tariffs import get_tariff
from bot.utils.texts import (
    PAYMENT_SYNC_WARNING_TEXT,
    balance_topup_success_text,
    device_slot_payment_success_text,
    payment_success_text,
    referral_reward_invited_text,
    referral_reward_referrer_text,
)
from bot.vpn_provisioning import get_vless_provisioner
from bot.vpn_api import XUIClient
from control_bot.dispatcher import create_control_event


logger = logging.getLogger(__name__)
PAYMENT_EFFECT_WAIT_ATTEMPTS = 10
PAYMENT_EFFECT_WAIT_DELAY_SECONDS = 0.2
BALANCE_TOPUP_PRODUCT_TYPE = "balance_topup"
GIFT_SUBSCRIPTION_PRODUCT_TYPE = "gift_subscription"
ACCESS_SYNC_SUCCESS = "success"
ACCESS_SYNC_FAILED = "failed"
ACCESS_SYNC_INCOMPLETE = "incomplete"


def _record_metadata(record) -> dict:
    raw_value = getattr(record, "metadata_json", None)
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _mark_payment_finance_synced(record_id: int, *, finance_entry_id: int | None = None) -> None:
    await mark_payment_record_finance_synced(record_id, finance_entry_id=finance_entry_id)


async def _mark_payment_access_sync_state(
    payment_record_id: int,
    *,
    state: str,
    expires_at,
) -> None:
    await update_payment_record_metadata(
        payment_record_id,
        merge={
            PAYMENT_ACCESS_SYNCED_AT_KEY: utcnow().isoformat(),
            PAYMENT_ACCESS_SYNC_STATE_KEY: str(state or "").strip().lower(),
            "access_expires_at": expires_at.isoformat() if expires_at is not None else None,
        },
    )
    await refresh_payment_record_reconcile_state(payment_record_id)


async def _ensure_subscription_access_state(
    *,
    user_id: int,
    payment_record_id: int | None,
) -> dict[str, object]:
    expires_at = await get_access_expires_at(user_id)
    repair_reason: str | None = None
    sync_failed = False
    auto_retry_attempted = False
    auto_retry_succeeded = False
    access_state = ACCESS_SYNC_SUCCESS

    if expires_at is None:
        repair_reason = POST_PAYMENT_ACCESS_INCOMPLETE
        access_state = ACCESS_SYNC_INCOMPLETE
    else:
        sync_result = await sync_user_vpn_access_with_single_retry(user_id, expires_at)
        sync_failed = sync_result["sync_failed"]
        auto_retry_attempted = sync_result["auto_retry_attempted"]
        auto_retry_succeeded = sync_result["auto_retry_succeeded"]
        if sync_failed:
            repair_reason = POST_PAYMENT_SYNC_FAILED
            access_state = ACCESS_SYNC_FAILED

    if repair_reason is not None:
        await mark_vpn_repair_needed(user_id, repair_reason)
    else:
        await clear_vpn_repair_needed(user_id)

    if payment_record_id is not None:
        await _mark_payment_access_sync_state(
            payment_record_id,
            state=access_state,
            expires_at=expires_at,
        )

    return {
        "expires_at": expires_at,
        "sync_failed": sync_failed,
        "repair_reason": repair_reason,
        "auto_retry_attempted": auto_retry_attempted,
        "auto_retry_succeeded": auto_retry_succeeded,
        "access_state": access_state,
    }


async def _reconcile_applied_subscription_payment(
    *,
    user_id: int,
    tariff_code: str,
    payment_record_id: int,
) -> dict | None:
    tariff = get_tariff(tariff_code)
    if tariff is None:
        return None

    access_state = await _ensure_subscription_access_state(
        user_id=user_id,
        payment_record_id=payment_record_id,
    )
    payment_result = await _build_subscription_payment_result_snapshot(
        user_id=user_id,
        tariff_code=tariff.code,
        payment_record_id=payment_record_id,
        effect_applied_now=False,
    )
    if payment_result is None:
        return None
    payment_result.update(
        {
            "expires_at": access_state["expires_at"],
            "expires_text": access_state["expires_at"].strftime("%Y-%m-%d %H:%M:%S") if access_state["expires_at"] else "—",
            "sync_failed": access_state["sync_failed"],
            "repair_reason": access_state["repair_reason"],
            "auto_retry_attempted": access_state["auto_retry_attempted"],
            "auto_retry_succeeded": access_state["auto_retry_succeeded"],
        }
    )
    return payment_result


async def _wait_for_payment_effect(record_id: int, *, effect_kind: str) -> bool:
    for _ in range(PAYMENT_EFFECT_WAIT_ATTEMPTS):
        record = await get_payment_record_by_id(record_id)
        if record is None:
            return False
        if payment_record_effect_applied(record):
            return True
        if not payment_record_effect_processing(record, effect_kind=effect_kind):
            return False
        await asyncio.sleep(PAYMENT_EFFECT_WAIT_DELAY_SECONDS)
    return False


async def _resolve_existing_payment_effect(
    *,
    payment_record_id: int,
    effect_kind: str,
    claim_state: str,
    build_snapshot: Callable[[], Awaitable[dict | None]],
) -> dict | None:
    if claim_state == "already_applied":
        return await build_snapshot()
    if claim_state != "in_progress":
        return None
    effect_applied = await _wait_for_payment_effect(payment_record_id, effect_kind=effect_kind)
    if not effect_applied:
        logger.warning(
            "Payment effect wait finished without applied marker: payment_record_id=%s effect_kind=%s",
            payment_record_id,
            effect_kind,
        )
        return None
    return await build_snapshot()


async def _seal_performed_payment_effect_after_failure(
    *,
    payment_record_id: int,
    effect_kind: str,
) -> None:
    try:
        await mark_payment_record_effect_applied(payment_record_id, effect_kind=effect_kind)
        await refresh_payment_record_reconcile_state(payment_record_id)
    except Exception:
        logger.exception(
            "Failed to seal already-performed payment effect: payment_record_id=%s effect_kind=%s",
            payment_record_id,
            effect_kind,
        )


async def _build_subscription_payment_result_snapshot(
    *,
    user_id: int,
    tariff_code: str,
    payment_record_id: int | None = None,
    effect_applied_now: bool,
) -> dict | None:
    tariff = get_tariff(tariff_code)
    if tariff is None:
        return None

    updated_user = await get_user_by_id(user_id)
    if updated_user is None:
        return None

    expires_at = await get_access_expires_at(user_id)
    payment_record = await get_payment_record_by_id(payment_record_id) if payment_record_id is not None else None
    list_price_amount = (
        int(getattr(payment_record, "list_price_amount", 0))
        if payment_record is not None and getattr(payment_record, "list_price_amount", 0)
        else int(tariff.rub_price)
    )
    balance_applied_amount = int(getattr(payment_record, "balance_applied_amount", 0)) if payment_record is not None else 0
    paid_amount = int(getattr(payment_record, "amount", 0)) if payment_record is not None else int(tariff.rub_price)

    return {
        "product_type": "subscription",
        "user": updated_user,
        "tariff": tariff,
        "expires_at": expires_at,
        "expires_text": expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—",
        "sync_failed": False,
        "repair_reason": None,
        "auto_retry_attempted": False,
        "auto_retry_succeeded": False,
        "payment_record_id": payment_record_id,
        "list_price_amount": list_price_amount,
        "balance_applied_amount": balance_applied_amount,
        "paid_amount": paid_amount,
        "effect_applied_now": effect_applied_now,
    }


async def _build_device_slot_payment_result_snapshot(
    *,
    user_id: int,
    payment_record_id: int,
    effect_applied_now: bool,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    user = await get_user_by_id(user_id)
    if record is None or user is None:
        return None

    expires_at = getattr(user, "subscription_expires_at", None)
    if expires_at is None:
        return None

    metadata = _record_metadata(record)
    slots_count = clamp_device_slot_count(int(metadata.get("slots_count") or 1))
    extra_counts = await get_active_device_slot_counts_for_users([user.id])
    setattr(user, "active_device_slot_addons", int(extra_counts.get(user.id, 0)))
    device_limit = get_device_limit_for_user(user)
    list_price_amount = int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0)
    balance_applied_amount = int(getattr(record, "balance_applied_amount", 0) or 0)
    paid_amount = int(getattr(record, "amount", 0) or 0)

    return {
        "product_type": DEVICE_SLOT_PRODUCT_TYPE,
        "user": user,
        "slots_count": slots_count,
        "expires_at": expires_at,
        "expires_text": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "device_limit": device_limit,
        "base_limit": 3,
        "list_price_amount": list_price_amount,
        "balance_applied_amount": balance_applied_amount,
        "paid_amount": paid_amount,
        "display_title": device_slot_display_title(slots_count),
        "sync_failed": False,
        "effect_applied_now": effect_applied_now,
    }


async def _build_balance_topup_payment_result_snapshot(
    *,
    user_id: int,
    payment_record_id: int,
    effect_applied_now: bool,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    user = await get_user_by_id(user_id)
    if record is None or user is None:
        return None

    return {
        "product_type": BALANCE_TOPUP_PRODUCT_TYPE,
        "user": user,
        "amount_rub": int(getattr(record, "amount", 0) or 0),
        "balance_rub": int(getattr(user, "balance_rub", 0) or 0),
        "effect_applied_now": effect_applied_now,
    }


def _is_balance_topup_record(record, metadata: dict | None = None) -> bool:
    payload = metadata if isinstance(metadata, dict) else _record_metadata(record)
    product_type = str(payload.get("product_type") or payload.get("payload_type") or "").strip().lower()
    tariff_code = str(getattr(record, "tariff_code", "") or "").strip().lower()
    return product_type == BALANCE_TOPUP_PRODUCT_TYPE or tariff_code == BALANCE_TOPUP_PRODUCT_TYPE


async def _send_referral_push_notification(
    *,
    user_id: int | None,
    telegram_id: int | None,
    payment_record_id: int,
    recipient_role: str,
    text: str,
    bonus_rub: int,
) -> bool:
    webhook_url = str(getattr(config, "referral_push_webhook_url", "") or "").strip()
    if not webhook_url:
        return False

    headers = {"Content-Type": "application/json"}
    token = str(getattr(config, "referral_push_webhook_token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    timeout = max(float(getattr(config, "referral_push_timeout_seconds", 5) or 5), 1.0)
    payload = {
        "event": "referral_reward_notification",
        "payment_record_id": payment_record_id,
        "recipient_role": recipient_role,
        "user_id": user_id,
        "telegram_id": telegram_id,
        "bonus_rub": int(bonus_rub),
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception(
            "Referral push delivery failed for payment_record_id=%s recipient_role=%s",
            payment_record_id,
            recipient_role,
        )
        return False


async def _log_referral_notification_delivery(
    *,
    payment_record_id: int,
    outcome,
    deliveries: dict[str, dict[str, bool | int | None]],
) -> None:
    delivered = any(bool(item.get("telegram_bot")) or bool(item.get("push")) for item in deliveries.values())
    await create_control_event(
        category="payments",
        severity="INFO" if delivered else "WARNING",
        event_type="referral_reward_notifications_sent" if delivered else "referral_reward_notifications_skipped",
        title="Реферальные уведомления обработаны" if delivered else "Реферальные уведомления не доставлены",
        message=(
            f"Платёж: <code>{payment_record_id}</code>\n"
            f"Реферер: <b>{'telegram' if deliveries['referrer'].get('telegram_bot') else '—'}</b> • "
            f"push: <b>{'yes' if deliveries['referrer'].get('push') else 'no'}</b>\n"
            f"Реферал: <b>{'telegram' if deliveries['invited'].get('telegram_bot') else '—'}</b> • "
            f"push: <b>{'yes' if deliveries['invited'].get('push') else 'no'}</b>"
        ),
        entity_type="payment_record",
        entity_id=str(payment_record_id),
        payload={
            "payment_record_id": payment_record_id,
            "referrer_user_id": outcome.referrer_user_id,
            "invited_user_id": outcome.invited_user_id,
            "deliveries": deliveries,
        },
        dedupe_key=f"referral-reward-notify:{payment_record_id}",
        cooldown_seconds=0,
    )


async def sync_user_vpn_access(user_id: int, access_expires_at) -> bool:
    clients = await get_user_vpn_clients(user_id)

    sync_failed = False
    for client in clients:
        client_data = json.loads(client.client_data) if client.client_data else {}
        original_client_data = dict(client_data)
        try:
            if client.protocol == "vless":
                provisioner = get_vless_provisioner(client_data.get("country_code"), client_data.get("provider_type"))
                try:
                    success = await provisioner.health_check()
                    if not success:
                        sync_failed = True
                        continue
                    await provisioner.sync_vless_client(
                        client_uuid=client.xui_client_id or client.client_uuid,
                        email=client.email,
                        metadata=client_data,
                        access_expires_at=access_expires_at,
                    )
                finally:
                    await provisioner.close()
                if client_data != original_client_data:
                    await update_vpn_client_metadata(int(client.id), client_data)
            elif client.protocol == "trojan":
                xui_client = XUIClient(country_code=client_data.get("country_code"))
                try:
                    success = await xui_client.login()
                    if not success:
                        sync_failed = True
                        continue
                    result = await xui_client.sync_trojan_client_expiry(
                        inbound_id=int(client_data.get("inbound_id") or 0),
                        client_uuid=client.xui_client_id or client.client_uuid,
                        email=client.email,
                        access_expires_at=access_expires_at,
                    )
                    resolved_inbound_id = result.get("inbound_id")
                    if resolved_inbound_id:
                        client_data["inbound_id"] = int(resolved_inbound_id)
                finally:
                    await xui_client.close()
                if client_data != original_client_data:
                    await update_vpn_client_metadata(int(client.id), client_data)
        except Exception:
            logger.exception(
                "Failed to sync VPN access state for user_id=%s access_expires_at=%s",
                user_id,
                access_expires_at,
            )
            sync_failed = True

    try:
        public_sync_failed = await sync_public_subscription_access(int(user_id), create_missing=False)
    except Exception:
        logger.exception(
            "Failed to sync public subscription access state for user_id=%s access_expires_at=%s",
            user_id,
            access_expires_at,
        )
        public_sync_failed = True
    sync_failed = sync_failed or public_sync_failed

    return sync_failed


async def sync_user_vpn_access_with_single_retry(user_id: int, access_expires_at) -> dict:
    sync_failed = await sync_user_vpn_access(user_id, access_expires_at)
    if not sync_failed:
        return {
            "sync_failed": False,
            "auto_retry_attempted": False,
            "auto_retry_succeeded": False,
        }

    retry_failed = await sync_user_vpn_access(user_id, access_expires_at)
    if retry_failed:
        await create_vpn_repair_event(user_id, "failed", AUTO_REPAIR_FAILED)
        return {
            "sync_failed": True,
            "auto_retry_attempted": True,
            "auto_retry_succeeded": False,
        }

    await create_vpn_repair_event(user_id, "success", AUTO_REPAIR_SUCCESS)
    return {
        "sync_failed": False,
        "auto_retry_attempted": True,
        "auto_retry_succeeded": True,
    }


async def finalize_subscription_payment(
    user_id: int,
    tariff_code: str,
    payment_id: str,
    payment_source: str,
    payment_record_id: int | None = None,
) -> dict | None:
    tariff = get_tariff(tariff_code)
    if tariff is None:
        return None
    effect_claimed = False
    effect_performed = False
    effect_marked = False
    payment_record = None
    if payment_record_id is not None:
        _, claim_state = await claim_payment_record_effect(payment_record_id, effect_kind="subscription_activation")
        if claim_state == "invalid_status":
            return None
        if claim_state in {"already_applied", "in_progress"}:
            return await _resolve_existing_payment_effect(
                payment_record_id=payment_record_id,
                effect_kind="subscription_activation",
                claim_state=claim_state,
                build_snapshot=lambda: _build_subscription_payment_result_snapshot(
                    user_id=user_id,
                    tariff_code=tariff.code,
                    payment_record_id=payment_record_id,
                    effect_applied_now=False,
                ),
            )
        if claim_state != "claimed":
            return None
        effect_claimed = True

    try:
        updated_user = await activate_paid_subscription(
            user_id=user_id,
            tariff_code=tariff.code,
            payment_id=payment_id,
            duration_days=tariff.duration_days,
            payment_source=payment_source,
        )
        if updated_user is None:
            if payment_record_id is not None and effect_claimed:
                await release_payment_record_effect_claim(
                    payment_record_id,
                    effect_kind="subscription_activation",
                    error_text="activate_paid_subscription_failed",
                )
            return None

        effect_performed = True

        if payment_record_id is not None:
            payment_record = await mark_payment_record_effect_applied(payment_record_id, effect_kind="subscription_activation")
            effect_marked = True

        access_state = await _ensure_subscription_access_state(
            user_id=user_id,
            payment_record_id=payment_record_id,
        )
        expires_at = access_state["expires_at"]
        sync_failed = bool(access_state["sync_failed"])
        post_payment_repair_reason = access_state["repair_reason"]
        auto_retry_attempted = bool(access_state["auto_retry_attempted"])
        auto_retry_succeeded = bool(access_state["auto_retry_succeeded"])

        if payment_record_id is not None and payment_record is None:
            payment_record = await get_payment_record_by_id(payment_record_id)
        if payment_record is not None:
            await consume_discount_redemption_from_payment_record(payment_record)

        list_price_amount = (
            int(getattr(payment_record, "list_price_amount", 0))
            if payment_record is not None and getattr(payment_record, "list_price_amount", 0)
            else int(tariff.rub_price)
        )
        balance_applied_amount = int(getattr(payment_record, "balance_applied_amount", 0)) if payment_record is not None else 0
        paid_amount = int(getattr(payment_record, "amount", 0)) if payment_record is not None else int(tariff.rub_price)
        payment_kind = str(getattr(updated_user, "_subscription_payment_kind", PAYMENT_KIND_UNKNOWN) or PAYMENT_KIND_UNKNOWN).strip().lower()

        if payment_record_id is not None:
            await safe_emit_analytics_event(
                event_name=EVENT_PAYMENT_SUCCESS,
                occurred_at=payment_record.confirmed_at if payment_record is not None else utcnow(),
                user_id=int(user_id),
                telegram_id=getattr(updated_user, "telegram_id", None),
                dedupe_key=f"payment-success:{int(payment_record_id)}",
                payment_record_id=int(payment_record_id),
                tariff_code=tariff.code,
                payment_method=getattr(payment_record, "payment_method", None) if payment_record is not None else payment_source,
                payload={
                    "amount_rub": paid_amount,
                    "list_price_amount": list_price_amount,
                    "balance_applied_amount": balance_applied_amount,
                    "product_type": "subscription",
                    "payment_kind": payment_kind,
                    "payment_source": payment_source,
                    "access_sync_state": access_state["access_state"],
                },
            )

        await create_control_event(
            category="payments",
            severity="WARNING" if sync_failed or post_payment_repair_reason else "INFO",
            event_type="payment_activation_issue" if sync_failed or post_payment_repair_reason else "payment_activated",
            title="Оплата активировала доступ с предупреждением" if sync_failed or post_payment_repair_reason else "Оплата успешно активировала доступ",
            message=(
                f"Пользователь: <code>{user_id}</code>\n"
                f"Тариф: <b>{tariff.title}</b>\n"
                f"Источник: <b>{payment_source}</b>\n"
                f"Полная стоимость: <b>{list_price_amount} RUB</b>\n"
                f"Баланс: <b>{balance_applied_amount} RUB</b>\n"
                f"Оплачено деньгами: <b>{paid_amount} RUB</b>\n"
                f"Доступ до: <b>{expires_at.strftime('%Y-%m-%d %H:%M:%S') if expires_at else '—'}</b>\n"
                f"Repair reason: <b>{post_payment_repair_reason or 'none'}</b>"
            ),
            entity_type="payment_record" if payment_record_id is not None else "user",
            entity_id=str(payment_record_id or user_id),
            payload={
                "user_id": user_id,
                "payment_record_id": payment_record_id,
                "payment_source": payment_source,
                "sync_failed": sync_failed,
                "repair_reason": post_payment_repair_reason,
                "tariff_code": tariff.code,
                "trace_id": payment_record_trace_id(payment_record) if payment_record is not None else f"{payment_source}:{payment_id}",
            },
            dedupe_key=f"payment-finalized:{payment_record_id or payment_id}",
            cooldown_seconds=0,
        )

        return {
            "product_type": "subscription",
            "user": updated_user,
            "tariff": tariff,
            "expires_at": expires_at,
            "expires_text": expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—",
            "sync_failed": sync_failed,
            "repair_reason": post_payment_repair_reason,
            "auto_retry_attempted": auto_retry_attempted,
            "auto_retry_succeeded": auto_retry_succeeded,
            "payment_record_id": payment_record_id,
            "list_price_amount": list_price_amount,
            "balance_applied_amount": balance_applied_amount,
            "paid_amount": paid_amount,
            "effect_applied_now": effect_claimed or payment_record_id is None,
        }
    except Exception as exc:
        if payment_record_id is not None and effect_claimed:
            if effect_performed:
                if not effect_marked:
                    await _seal_performed_payment_effect_after_failure(
                        payment_record_id=payment_record_id,
                        effect_kind="subscription_activation",
                    )
            else:
                await release_payment_record_effect_claim(
                    payment_record_id,
                    effect_kind="subscription_activation",
                    error_text=str(exc),
                )
        raise


async def finalize_device_slot_payment(
    *,
    user_id: int,
    payment_source: str,
    payment_record_id: int,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    if record is None or record.user_id != user_id:
        return None

    user = await get_user_by_id(user_id)
    if user is None or not has_active_subscription_from_user(user):
        return None

    expires_at = getattr(user, "subscription_expires_at", None)
    if expires_at is None:
        return None

    metadata = _record_metadata(record)
    slots_count = clamp_device_slot_count(int(metadata.get("slots_count") or 1))
    if slots_count <= 0:
        return None

    claimed_record, claim_state = await claim_payment_record_effect(payment_record_id, effect_kind="device_slot_activation")
    if claim_state == "invalid_status":
        return None
    if claim_state in {"already_applied", "in_progress"}:
        return await _resolve_existing_payment_effect(
            payment_record_id=payment_record_id,
            effect_kind="device_slot_activation",
            claim_state=claim_state,
            build_snapshot=lambda: _build_device_slot_payment_result_snapshot(
                user_id=user_id,
                payment_record_id=payment_record_id,
                effect_applied_now=False,
            ),
        )
    if claim_state != "claimed":
        return None
    record = claimed_record or record

    starts_at = user.subscription_started_at or record.confirmed_at or record.created_at
    effect_performed = False
    effect_marked = False
    try:
        entitlement = await create_device_slot_entitlement(
            user_id=user_id,
            payment_record_id=record.id,
            slots_count=slots_count,
            unit_price_rub=int(metadata.get("unit_price_rub") or device_slot_unit_price_rub()),
            total_amount_rub=int(metadata.get("total_amount_rub") or getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
            starts_at=starts_at,
            expires_at=expires_at,
        )
        if entitlement is None:
            await release_payment_record_effect_claim(
                payment_record_id,
                effect_kind="device_slot_activation",
                error_text="device_slot_entitlement_failed",
            )
            return None

        effect_performed = True
        await mark_payment_record_effect_applied(payment_record_id, effect_kind="device_slot_activation")
        effect_marked = True
    except Exception as exc:
        if effect_performed:
            if not effect_marked:
                await _seal_performed_payment_effect_after_failure(
                    payment_record_id=payment_record_id,
                    effect_kind="device_slot_activation",
                )
        else:
            await release_payment_record_effect_claim(
                payment_record_id,
                effect_kind="device_slot_activation",
                error_text=str(exc),
            )
        raise

    extra_counts = await get_active_device_slot_counts_for_users([user.id])
    setattr(user, "active_device_slot_addons", int(extra_counts.get(user.id, 0)))
    device_limit = get_device_limit_for_user(user)

    await create_control_event(
        category="payments",
        severity="INFO",
        event_type="device_slot_addon_activated",
        title="Дополнительное устройство активировано",
        message=(
            f"Пользователь: <code>{user_id}</code>\n"
            f"Источник: <b>{payment_source}</b>\n"
            f"Слотов: <b>{slots_count}</b>\n"
            f"Лимит устройств: <b>{device_limit}</b>\n"
            f"Действует до: <b>{expires_at.strftime('%Y-%m-%d %H:%M:%S')}</b>"
        ),
        entity_type="payment_record",
        entity_id=str(payment_record_id),
        payload={
            "user_id": user_id,
            "payment_record_id": payment_record_id,
            "slots_count": slots_count,
            "device_limit": device_limit,
            "payment_source": payment_source,
            "product_type": DEVICE_SLOT_PRODUCT_TYPE,
            "trace_id": payment_record_trace_id(record),
        },
        dedupe_key=f"device-slot-finalized:{payment_record_id}",
        cooldown_seconds=0,
    )
    await safe_emit_analytics_event(
        event_name=EVENT_PAYMENT_SUCCESS,
        occurred_at=getattr(record, "confirmed_at", None) or utcnow(),
        user_id=int(user_id),
        telegram_id=getattr(user, "telegram_id", None),
        dedupe_key=f"payment-success:{int(payment_record_id)}",
        payment_record_id=int(payment_record_id),
        tariff_code=getattr(record, "tariff_code", None),
        payment_method=getattr(record, "payment_method", None),
        payload={
            "amount_rub": int(getattr(record, "amount", 0) or 0),
            "list_price_amount": int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
            "balance_applied_amount": int(getattr(record, "balance_applied_amount", 0) or 0),
            "product_type": DEVICE_SLOT_PRODUCT_TYPE,
            "payment_kind": PAYMENT_KIND_OTHER,
            "slots_count": slots_count,
            "device_limit": device_limit,
        },
    )

    list_price_amount = int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0)
    balance_applied_amount = int(getattr(record, "balance_applied_amount", 0) or 0)
    paid_amount = int(getattr(record, "amount", 0) or 0)

    return {
        "product_type": DEVICE_SLOT_PRODUCT_TYPE,
        "user": user,
        "slots_count": slots_count,
        "expires_at": expires_at,
        "expires_text": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "device_limit": device_limit,
        "base_limit": 3,
        "list_price_amount": list_price_amount,
        "balance_applied_amount": balance_applied_amount,
        "paid_amount": paid_amount,
        "display_title": device_slot_display_title(slots_count),
        "sync_failed": False,
        "effect_applied_now": True,
    }


async def finalize_balance_topup_payment(
    *,
    user_id: int,
    payment_record_id: int,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    if record is None or record.user_id != user_id:
        return None
    if not _is_balance_topup_record(record):
        return None

    _, claim_state = await claim_payment_record_effect(payment_record_id, effect_kind="balance_topup")
    if claim_state == "invalid_status":
        return None
    if claim_state in {"already_applied", "in_progress"}:
        return await _resolve_existing_payment_effect(
            payment_record_id=payment_record_id,
            effect_kind="balance_topup",
            claim_state=claim_state,
            build_snapshot=lambda: _build_balance_topup_payment_result_snapshot(
                user_id=user_id,
                payment_record_id=payment_record_id,
                effect_applied_now=False,
            ),
        )
    if claim_state != "claimed":
        return None

    effect_performed = False
    effect_marked = False
    try:
        topped_up_user = await credit_user_balance(
            user_id,
            amount=int(getattr(record, "amount", 0) or 0),
            reason="balance_topup",
            reference_type="payment_record",
            reference_id=str(record.id),
            note=f"Пополнение через Platega #{record.id}",
        )
        if topped_up_user is None:
            await release_payment_record_effect_claim(
                payment_record_id,
                effect_kind="balance_topup",
                error_text="balance_topup_credit_failed",
            )
            return None
        effect_performed = True
        await mark_payment_record_effect_applied(payment_record_id, effect_kind="balance_topup")
        effect_marked = True
        await safe_emit_analytics_event(
            event_name=EVENT_PAYMENT_SUCCESS,
            occurred_at=getattr(record, "confirmed_at", None) or utcnow(),
            user_id=int(user_id),
            telegram_id=getattr(topped_up_user, "telegram_id", None),
            dedupe_key=f"payment-success:{int(payment_record_id)}",
            payment_record_id=int(payment_record_id),
            tariff_code=getattr(record, "tariff_code", None),
            payment_method=getattr(record, "payment_method", None),
            payload={
                "amount_rub": int(getattr(record, "amount", 0) or 0),
                "product_type": BALANCE_TOPUP_PRODUCT_TYPE,
                "payment_kind": PAYMENT_KIND_OTHER,
                "balance_rub": int(getattr(topped_up_user, "balance_rub", 0) or 0),
            },
        )
        return await _build_balance_topup_payment_result_snapshot(
            user_id=user_id,
            payment_record_id=payment_record_id,
            effect_applied_now=True,
        )
    except Exception as exc:
        if effect_performed:
            if not effect_marked:
                await _seal_performed_payment_effect_after_failure(
                    payment_record_id=payment_record_id,
                    effect_kind="balance_topup",
                )
        else:
            await release_payment_record_effect_claim(
                payment_record_id,
                effect_kind="balance_topup",
                error_text=str(exc),
            )
        raise


async def finalize_gift_subscription_payment(
    *,
    user_id: int,
    payment_source: str,
    payment_record_id: int,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    if record is None or record.user_id != user_id:
        return None

    metadata = _record_metadata(record)
    grant_days = max(int(metadata.get("gift_days") or getattr(record, "duration_days", 0) or 0), 0)
    if grant_days <= 0:
        return None

    _, claim_state = await claim_payment_record_effect(payment_record_id, effect_kind="gift_code_created")
    if claim_state == "invalid_status":
        return None
    if claim_state in {"already_applied", "in_progress"}:
        promo = await create_gift_promo_code_for_payment(
            buyer_user_id=int(user_id),
            payment_record_id=int(payment_record_id),
            grant_days=grant_days,
            tariff_code=getattr(record, "tariff_code", None),
            title=str(metadata.get("gift_title") or metadata.get("tariff_title") or "Подарочная подписка"),
        )
        return {
            "product_type": GIFT_SUBSCRIPTION_PRODUCT_TYPE,
            "user": await get_user_by_id(int(user_id)),
            "gift_code": promo.code,
            "gift_days": grant_days,
            "gift_title": str(metadata.get("gift_title") or metadata.get("tariff_title") or "Подарочная подписка"),
            "list_price_amount": int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
            "balance_applied_amount": int(getattr(record, "balance_applied_amount", 0) or 0),
            "paid_amount": int(getattr(record, "amount", 0) or 0),
            "effect_applied_now": False,
        }
    if claim_state != "claimed":
        return None

    try:
        promo = await create_gift_promo_code_for_payment(
            buyer_user_id=int(user_id),
            payment_record_id=int(payment_record_id),
            grant_days=grant_days,
            tariff_code=getattr(record, "tariff_code", None),
            title=str(metadata.get("gift_title") or metadata.get("tariff_title") or "Подарочная подписка"),
        )
        await mark_payment_record_effect_applied(payment_record_id, effect_kind="gift_code_created")
        await create_control_event(
            category="payments",
            severity="INFO",
            event_type="gift_code_created",
            title="Создан подарочный промокод",
            message=(
                f"Пользователь: <code>{user_id}</code>\n"
                f"Источник: <b>{payment_source}</b>\n"
                f"Код: <code>{promo.code}</code>\n"
                f"Срок подарка: <b>{grant_days} дней</b>"
            ),
            entity_type="payment_record",
            entity_id=str(payment_record_id),
            payload={
                "user_id": int(user_id),
                "payment_record_id": int(payment_record_id),
                "promo_code_id": int(promo.id),
                "promo_code": promo.code,
                "grant_days": grant_days,
            },
            dedupe_key=f"gift-code-created:{payment_record_id}",
            cooldown_seconds=0,
        )
        return {
            "product_type": GIFT_SUBSCRIPTION_PRODUCT_TYPE,
            "user": await get_user_by_id(int(user_id)),
            "gift_code": promo.code,
            "gift_days": grant_days,
            "gift_title": str(metadata.get("gift_title") or metadata.get("tariff_title") or "Подарочная подписка"),
            "list_price_amount": int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
            "balance_applied_amount": int(getattr(record, "balance_applied_amount", 0) or 0),
            "paid_amount": int(getattr(record, "amount", 0) or 0),
            "effect_applied_now": True,
        }
    except Exception as exc:
        await release_payment_record_effect_claim(
            payment_record_id,
            effect_kind="gift_code_created",
            error_text=str(exc),
        )
        raise


async def finalize_payment_record_product(
    *,
    user_id: int,
    payment_source: str,
    payment_record_id: int,
    tariff_code: str | None = None,
    payment_id: str | None = None,
) -> dict | None:
    record = await get_payment_record_by_id(payment_record_id)
    if record is None:
        return None

    metadata = _record_metadata(record)
    if _is_balance_topup_record(record, metadata):
        return await finalize_balance_topup_payment(
            user_id=user_id,
            payment_record_id=payment_record_id,
        )
    product_type = payment_product_type(metadata, tariff_code=tariff_code or getattr(record, "tariff_code", None))
    if product_type == GIFT_SUBSCRIPTION_PRODUCT_TYPE:
        return await finalize_gift_subscription_payment(
            user_id=user_id,
            payment_source=payment_source,
            payment_record_id=payment_record_id,
        )
    if product_type == DEVICE_SLOT_PRODUCT_TYPE:
        return await finalize_device_slot_payment(
            user_id=user_id,
            payment_source=payment_source,
            payment_record_id=payment_record_id,
        )

    return await finalize_subscription_payment(
        user_id=user_id,
        tariff_code=tariff_code or record.tariff_code or "",
        payment_id=payment_id or str(record.external_payment_id or record.id),
        payment_source=payment_source,
        payment_record_id=payment_record_id,
    )


async def reconcile_confirmed_payment_records(*, limit: int = 25) -> dict[str, int]:
    from dashboard.finance import sync_income_entry_for_payment_record

    rows = await list_confirmed_payment_records_needing_full_reconcile(limit=limit)
    result = {
        "checked": len(rows),
        "reconciled": 0,
        "failed": 0,
        "skipped": 0,
        "finance_synced": 0,
        "finance_only": 0,
    }
    for record in rows:
        if record.user_id is None:
            result["skipped"] += 1
            continue
        try:
            record = await refresh_payment_record_reconcile_state(record.id) or record
            payment_result = None
            initial_state = payment_record_reconcile_state(record)
            if initial_state == "missing_effect":
                payment_result = await finalize_payment_record_product(
                    user_id=int(record.user_id),
                    payment_source=f"reconcile_{record.payment_method}",
                    payment_record_id=record.id,
                    tariff_code=record.tariff_code,
                    payment_id=str(record.reference or record.external_payment_id or record.id),
                )
                if payment_result is None:
                    result["failed"] += 1
                    logger.warning("Confirmed payment reconcile failed: record_id=%s user_id=%s", record.id, record.user_id)
                    continue
                record = await refresh_payment_record_reconcile_state(record.id) or await get_payment_record_by_id(record.id) or record

            if payment_record_requires_access_sync(record):
                payment_result = await _reconcile_applied_subscription_payment(
                    user_id=int(record.user_id),
                    tariff_code=record.tariff_code or "",
                    payment_record_id=record.id,
                )
                if payment_result is None:
                    result["failed"] += 1
                    logger.warning(
                        "Confirmed payment reconcile failed to sync access: record_id=%s user_id=%s",
                        record.id,
                        record.user_id,
                    )
                    continue
                record = await refresh_payment_record_reconcile_state(record.id) or await get_payment_record_by_id(record.id) or record

            finance_pending_before = payment_record_requires_finance_sync(record)
            if finance_pending_before:
                finance_entry = await sync_income_entry_for_payment_record(record.id)
                if finance_entry is not None:
                    result["finance_synced"] += 1
                else:
                    await clear_payment_record_finance_synced(record.id)
                record = await refresh_payment_record_reconcile_state(record.id) or await get_payment_record_by_id(record.id) or record

            final_state = payment_record_reconcile_state(record)
            if final_state != "converged":
                result["failed"] += 1
                logger.warning(
                    "Confirmed payment reconcile left record unconverged: record_id=%s user_id=%s state=%s",
                    record.id,
                    record.user_id,
                    final_state,
                )
                continue
            if finance_pending_before and payment_result is None:
                result["finance_only"] += 1
            result["reconciled"] += 1
        except Exception:
            result["failed"] += 1
            logger.exception("Confirmed payment reconcile crashed: record_id=%s user_id=%s", record.id, record.user_id)
    return result


async def notify_payment_success(
    bot: Bot,
    telegram_id: int,
    tariff_title: str,
    expires_text: str,
    sync_failed: bool = False,
    *,
    list_price_amount: int | None = None,
    balance_applied_amount: int = 0,
    paid_amount: int | None = None,
) -> None:
    del bot
    await send_user_message_and_refresh_home(
        telegram_id,
        payment_success_text(
            tariff_title,
            expires_text,
            list_price_amount=list_price_amount,
            balance_applied_amount=balance_applied_amount,
            paid_amount=paid_amount,
        ),
    )
    if sync_failed:
        await send_user_message(telegram_id, PAYMENT_SYNC_WARNING_TEXT)


async def notify_payment_result(bot: Bot, telegram_id: int, payment_result: dict) -> None:
    product_type = str(payment_result.get("product_type") or "subscription").strip().lower()
    if product_type == BALANCE_TOPUP_PRODUCT_TYPE:
        del bot
        await send_user_message_and_refresh_home(
            telegram_id,
            balance_topup_success_text(
                amount_rub=int(payment_result.get("amount_rub") or 0),
                balance_rub=int(payment_result.get("balance_rub") or 0),
            ),
        )
        return
    if product_type == DEVICE_SLOT_PRODUCT_TYPE:
        del bot
        await send_user_message_and_refresh_home(
            telegram_id,
            device_slot_payment_success_text(
                title=str(payment_result.get("display_title") or "Дополнительное устройство"),
                expires_at=str(payment_result.get("expires_text") or "—"),
                device_limit=int(payment_result.get("device_limit") or 3),
                slots_count=int(payment_result.get("slots_count") or 1),
                list_price_amount=payment_result.get("list_price_amount"),
                balance_applied_amount=int(payment_result.get("balance_applied_amount") or 0),
                paid_amount=payment_result.get("paid_amount"),
            ),
        )
        return
    if product_type == GIFT_SUBSCRIPTION_PRODUCT_TYPE:
        del bot
        await send_user_message_and_refresh_home(
            telegram_id,
            (
                "🎁 <b>Подарочный код готов</b>\n\n"
                f"Срок подарка: <b>{int(payment_result.get('gift_days') or 0)} дн.</b>\n"
                "Передайте этот код другу:\n\n"
                f"<code>{str(payment_result.get('gift_code') or '—')}</code>\n\n"
                "Друг сможет ввести его в разделе «Бонусная система» → «Ввести промокод»."
            ),
        )
        return

    await notify_payment_success(
        bot=bot,
        telegram_id=telegram_id,
        tariff_title=payment_result["tariff"].title,
        expires_text=payment_result["expires_text"],
        sync_failed=payment_result["sync_failed"],
        list_price_amount=payment_result["list_price_amount"],
        balance_applied_amount=payment_result["balance_applied_amount"],
        paid_amount=payment_result["paid_amount"],
    )


async def _deliver_referral_reward_notifications(bot: Bot | None, payment_record_id: int) -> bool:
    del bot
    outcome = await process_referral_reward_for_payment(payment_record_id)
    if not outcome.applied:
        return False

    referrer_text = referral_reward_referrer_text(
        bonus_rub=outcome.bonus_referrer_rub,
        balance_rub=outcome.referrer_balance_rub,
        tariff_title=outcome.tariff_title,
    )
    invited_text = referral_reward_invited_text(
        bonus_rub=outcome.bonus_invited_rub,
        balance_rub=outcome.invited_balance_rub,
        tariff_title=outcome.tariff_title,
    )
    deliveries: dict[str, dict[str, bool | int | None]] = {
        "referrer": {
            "user_id": outcome.referrer_user_id,
            "telegram_id": outcome.referrer_telegram_id,
            "bonus_rub": outcome.bonus_referrer_rub,
            "telegram_bot": False,
            "in_app": False,
            "push": False,
        },
        "invited": {
            "user_id": outcome.invited_user_id,
            "telegram_id": outcome.invited_telegram_id,
            "bonus_rub": outcome.bonus_invited_rub,
            "telegram_bot": False,
            "in_app": False,
            "push": False,
        },
    }

    if outcome.referrer_telegram_id:
        delivered = await send_user_message_and_refresh_home(outcome.referrer_telegram_id, referrer_text)
        deliveries["referrer"]["telegram_bot"] = delivered
        deliveries["referrer"]["in_app"] = delivered
        deliveries["referrer"]["push"] = await _send_referral_push_notification(
            user_id=outcome.referrer_user_id,
            telegram_id=outcome.referrer_telegram_id,
            payment_record_id=payment_record_id,
            recipient_role="referrer",
            text=referrer_text,
            bonus_rub=outcome.bonus_referrer_rub,
        )

    if outcome.invited_telegram_id:
        delivered = await send_user_message_and_refresh_home(outcome.invited_telegram_id, invited_text)
        deliveries["invited"]["telegram_bot"] = delivered
        deliveries["invited"]["in_app"] = delivered
        deliveries["invited"]["push"] = await _send_referral_push_notification(
            user_id=outcome.invited_user_id,
            telegram_id=outcome.invited_telegram_id,
            payment_record_id=payment_record_id,
            recipient_role="invited",
            text=invited_text,
            bonus_rub=outcome.bonus_invited_rub,
        )

    await _log_referral_notification_delivery(
        payment_record_id=payment_record_id,
        outcome=outcome,
        deliveries=deliveries,
    )

    return True


async def notify_referral_bonus(bot: Bot, user_id: int | None = None, *, payment_record_id: int | None = None) -> bool:
    del user_id
    if payment_record_id is None:
        return False
    return await _deliver_referral_reward_notifications(bot, payment_record_id)


async def apply_referral_bonus(
    bot: Bot | None,
    user_id: int | None = None,
    *,
    payment_record_id: int | None = None,
) -> bool:
    del user_id
    if payment_record_id is None:
        return False
    return await _deliver_referral_reward_notifications(bot, payment_record_id)


async def get_user_telegram_id(user_id: int) -> int | None:
    user = await get_user_by_id(user_id)
    if user is None:
        return None
    return user.telegram_id
