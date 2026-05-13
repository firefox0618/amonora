import hashlib
import json
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.analytics import EVENT_PAYMENT_FAILED, safe_emit_analytics_event
from backend.core.database import async_session
from bot.config import config
from bot.db import (
    _load_payment_metadata,
    _release_reserved_balance_for_record,
    confirm_external_payment_record,
    create_balance_aware_external_payment_record,
    create_external_payment_record,
    get_payment_record_by_external_id,
    get_payment_record_by_id,
    get_open_payment_intent_for_user,
    get_open_payment_record_for_user,
    payment_record_effect_applied,
    payment_record_trace_id,
    update_payment_record_metadata,
    PAYMENT_PROVIDER_CALLBACK_HASH_KEY,
    PAYMENT_PROVIDER_CALLBACK_EVENT_KEYS_KEY,
    PAYMENT_PROVIDER_CALLBACK_LAST_EVENT_KEY,
    PAYMENT_PROVIDER_CALLBACK_LAST_SIGNATURE_KEY,
    PAYMENT_PROVIDER_CALLBACK_REPEAT_COUNT_KEY,
    PAYMENT_PROVIDER_CALLBACK_SEEN_AT_KEY,
    PAYMENT_PROVIDER_CALLBACK_SIGNATURES_KEY,
)
from bot.payment_flow import apply_referral_bonus, finalize_payment_record_product, notify_payment_result
from bot.platega import PlategaClient, PlategaError
from bot.utils.access import utcnow
from bot.utils.device_slots import DEVICE_SLOT_PRODUCT_TYPE, device_slot_duration_days, is_device_slot_product
from bot.utils.tariffs import get_tariff, marketing_tariff_title
from control_bot.dispatcher import create_control_event
from dashboard.finance import sync_income_entry_for_payment_record
from dashboard.models import PaymentRecord


PLATEGA_PAYMENT_METHODS = {"sbp_platega", "crypto_platega"}
PLATEGA_METHOD_IDS = {
    "sbp_platega": PlategaClient.METHOD_SBP_QR,
    "crypto_platega": PlategaClient.METHOD_CRYPTO,
}
PLATEGA_PAYMENT_SOURCES = {
    "sbp_platega": "platega_sbp",
    "crypto_platega": "platega_crypto",
}
PLATEGA_PROVIDER_NAMES = {
    "sbp_platega": "Platega SBP",
    "crypto_platega": "Platega Crypto",
}
BALANCE_TOPUP_TARIFF_CODE = "balance_topup"
BALANCE_TOPUP_PAYLOAD_TYPE = "balance_topup"
PLATEGA_CALLBACK_SIGNATURE_HISTORY_LIMIT = 12
PLATEGA_CALLBACK_EVENT_HISTORY_LIMIT = 12


def is_platega_payment_method(method: str | None) -> bool:
    return str(method or "").strip().lower() in PLATEGA_PAYMENT_METHODS


def platega_payment_enabled_for_choice(choice: str) -> bool:
    if choice == "sbp":
        return bool(config.enable_platega_sbp_user_flow)
    if choice == "crypto":
        return bool(config.enable_platega_crypto_user_flow)
    return False


def platega_payment_method_for_choice(choice: str) -> str | None:
    mapping = {
        "sbp": "sbp_platega" if config.enable_platega_sbp_user_flow else None,
        "crypto": "crypto_platega" if config.enable_platega_crypto_user_flow else None,
    }
    return mapping.get(choice)


def platega_payload(
    *,
    user_id: int,
    telegram_id: int | None,
    tariff_code: str,
    payment_method: str,
    payload_type: str = "subscription",
) -> dict[str, Any]:
    return {
        "type": payload_type,
        "user_id": user_id,
        "telegram_id": telegram_id,
        "tariff_code": tariff_code,
        "payment_method": payment_method,
    }


def _return_to_bot_url() -> str:
    return "https://t.me/amonora_bot"


def _metadata_for_payment(
    *,
    payment_method: str,
    tariff_title: str,
    telegram_id: int | None,
    provider_status: str,
    checkout_url: str | None = None,
    payload_type: str = "subscription",
    provider_payload: dict[str, Any] | None = None,
    provider_sync_problem: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider": "platega",
        "provider_name": PLATEGA_PROVIDER_NAMES.get(payment_method, "Platega"),
        "provider_status": provider_status,
        "payload_type": payload_type,
        "telegram_id": telegram_id,
        "tariff_title": tariff_title,
        "last_synced_at": PlategaClient.now_sync_stamp(),
    }
    if checkout_url:
        metadata["checkout_url"] = checkout_url
    if provider_payload is not None:
        metadata["provider_payload"] = provider_payload
    if provider_sync_problem:
        metadata["provider_sync_problem"] = provider_sync_problem
    return metadata


def _platega_intent_conflict_message(record: PaymentRecord) -> str:
    method = str(getattr(record, "payment_method", "") or "").strip()
    if method in {"manual_sbp", "manual_sbp_qr"}:
        return "У пользователя уже есть открытая ручная заявка на этот платёж. Сначала закрой или отмени её."
    return "У пользователя уже есть открытый счёт на этот продукт. Используй существующий платёж вместо создания дубля."


def _platega_callback_signature(payload: dict[str, Any]) -> str:
    payload_hash = str(payload.get("_callback_hash") or "").strip()
    status = str(payload.get("status") or "").strip().upper()
    if not payload_hash or not status:
        return ""
    return f"{payload_hash}:{status}"


def _platega_callback_signatures(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get(PAYMENT_PROVIDER_CALLBACK_SIGNATURES_KEY)
    if not isinstance(raw, list):
        legacy_signature = str(metadata.get(PAYMENT_PROVIDER_CALLBACK_LAST_SIGNATURE_KEY) or "").strip()
        if legacy_signature:
            return [legacy_signature]
        legacy_hash = str(metadata.get(PAYMENT_PROVIDER_CALLBACK_HASH_KEY) or "").strip()
        legacy_status = str(metadata.get("provider_last_callback_status") or "").strip().upper()
        if legacy_hash and legacy_status:
            return [f"{legacy_hash}:{legacy_status}"]
        return []
    normalized: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            normalized.append(value)
    if len(normalized) > PLATEGA_CALLBACK_SIGNATURE_HISTORY_LIMIT:
        normalized = normalized[-PLATEGA_CALLBACK_SIGNATURE_HISTORY_LIMIT:]
    return normalized


def _platega_callback_event_key(payload: dict[str, Any], parsed_payload: dict[str, Any]) -> str:
    identity = {
        "transaction_id": str(payload.get("id") or "").strip(),
        "status": str(payload.get("status") or "").strip().upper(),
        "payment_method": str(payload.get("paymentMethod") or "").strip(),
        "amount": str(payload.get("amount") or "").strip(),
        "currency": str(payload.get("currency") or "RUB").strip().upper(),
        "payload": parsed_payload,
    }
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _platega_callback_event_keys(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get(PAYMENT_PROVIDER_CALLBACK_EVENT_KEYS_KEY)
    if not isinstance(raw, list):
        legacy_value = str(metadata.get(PAYMENT_PROVIDER_CALLBACK_LAST_EVENT_KEY) or "").strip()
        return [legacy_value] if legacy_value else []
    normalized: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            normalized.append(value)
    if len(normalized) > PLATEGA_CALLBACK_EVENT_HISTORY_LIMIT:
        normalized = normalized[-PLATEGA_CALLBACK_EVENT_HISTORY_LIMIT:]
    return normalized


def _platega_callback_signature_seen(record: PaymentRecord, payload: dict[str, Any]) -> bool:
    signature = _platega_callback_signature(payload)
    if not signature:
        return False
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    return signature in _platega_callback_signatures(metadata)


def _platega_callback_event_seen(record: PaymentRecord, payload: dict[str, Any], parsed_payload: dict[str, Any]) -> bool:
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    event_key = _platega_callback_event_key(payload, parsed_payload)
    return bool(event_key) and event_key in _platega_callback_event_keys(metadata)


def _platega_callback_is_duplicate_noop(record: PaymentRecord, payload: dict[str, Any], parsed_payload: dict[str, Any]) -> bool:
    current_status = str(payload.get("status") or "").strip().upper()
    if not (_platega_callback_signature_seen(record, payload) or _platega_callback_event_seen(record, payload, parsed_payload)):
        return False
    if current_status != PlategaClient.STATUS_CONFIRMED:
        return True
    return payment_record_effect_applied(record)


async def _mark_platega_callback_seen(record: PaymentRecord, *, payload: dict[str, Any], parsed_payload: dict[str, Any]) -> None:
    payload_hash = str(payload.get("_callback_hash") or "").strip()
    signature = _platega_callback_signature(payload)
    event_key = _platega_callback_event_key(payload, parsed_payload)
    if not payload_hash or not signature or not event_key:
        return
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    previous_hash = str(metadata.get(PAYMENT_PROVIDER_CALLBACK_HASH_KEY) or "").strip()
    repeat_count = int(metadata.get(PAYMENT_PROVIDER_CALLBACK_REPEAT_COUNT_KEY) or 0)
    if previous_hash == payload_hash:
        repeat_count += 1
    else:
        repeat_count = 1
    signatures = _platega_callback_signatures(metadata)
    if signature in signatures:
        signatures = [item for item in signatures if item != signature]
    signatures.append(signature)
    signatures = signatures[-PLATEGA_CALLBACK_SIGNATURE_HISTORY_LIMIT:]
    event_keys = _platega_callback_event_keys(metadata)
    if event_key in event_keys:
        event_keys = [item for item in event_keys if item != event_key]
    event_keys.append(event_key)
    event_keys = event_keys[-PLATEGA_CALLBACK_EVENT_HISTORY_LIMIT:]
    await update_payment_record_metadata(
        int(record.id),
        merge={
            PAYMENT_PROVIDER_CALLBACK_HASH_KEY: payload_hash,
            PAYMENT_PROVIDER_CALLBACK_REPEAT_COUNT_KEY: repeat_count,
            PAYMENT_PROVIDER_CALLBACK_SEEN_AT_KEY: utcnow().isoformat(),
            PAYMENT_PROVIDER_CALLBACK_LAST_SIGNATURE_KEY: signature,
            PAYMENT_PROVIDER_CALLBACK_SIGNATURES_KEY: signatures,
            PAYMENT_PROVIDER_CALLBACK_LAST_EVENT_KEY: event_key,
            PAYMENT_PROVIDER_CALLBACK_EVENT_KEYS_KEY: event_keys,
            "provider_last_callback_status": str(payload.get("status") or "").strip().upper(),
        },
    )


async def _emit_platega_callback_mismatch_event(
    record: PaymentRecord,
    *,
    mismatch: str,
    expected: Any,
    received: Any,
    payload: dict[str, Any],
    parsed_payload: dict[str, Any],
) -> None:
    await create_control_event(
        category="payments",
        severity="WARNING",
        event_type="platega_callback_mismatch",
        title="Platega callback не совпал с локальной записью платежа",
        message=(
            f"Платёж <code>#{record.id}</code> получил callback с конфликтующими данными.\n"
            f"Поле: <b>{mismatch}</b>\n"
            f"Expected: <code>{expected}</code>\n"
            f"Received: <code>{received}</code>"
        ),
        entity_type="payment_record",
        entity_id=str(record.id),
        payload={
            "record_id": int(record.id),
            "mismatch": mismatch,
            "expected": expected,
            "received": received,
            "provider_status": str(payload.get("status") or "").strip().upper(),
            "transaction_id": str(payload.get("id") or "").strip(),
            "parsed_payload": parsed_payload,
        },
        dedupe_key=f"platega-callback-mismatch:{int(record.id)}:{mismatch}:{received}",
    )


async def _validate_platega_callback_matches_record(
    record: PaymentRecord,
    *,
    payload: dict[str, Any],
    parsed_payload: dict[str, Any],
    payment_method: str,
    payload_type: str,
    tariff_code: str,
) -> None:
    checks: list[tuple[str, Any, Any]] = []
    if str(getattr(record, "payment_method", "") or "").strip().lower() != str(payment_method or "").strip().lower():
        checks.append(("payment_method", getattr(record, "payment_method", None), payment_method))
    callback_user_id = parsed_payload.get("user_id")
    if callback_user_id is not None and getattr(record, "user_id", None) is not None:
        if int(callback_user_id) != int(record.user_id):
            checks.append(("user_id", int(record.user_id), int(callback_user_id)))
    expected_tariff_code = BALANCE_TOPUP_TARIFF_CODE if payload_type == BALANCE_TOPUP_PAYLOAD_TYPE else tariff_code
    if expected_tariff_code and str(getattr(record, "tariff_code", "") or "").strip() != expected_tariff_code:
        checks.append(("tariff_code", getattr(record, "tariff_code", None), expected_tariff_code))
    callback_amount_raw = payload.get("amount")
    if callback_amount_raw not in (None, ""):
        try:
            callback_amount = int(float(callback_amount_raw))
        except (TypeError, ValueError):
            callback_amount = None
        if callback_amount is not None and int(getattr(record, "amount", 0) or 0) != callback_amount:
            checks.append(("amount", int(getattr(record, "amount", 0) or 0), callback_amount))
    callback_currency = str(payload.get("currency") or "").strip().upper()
    if callback_currency and str(getattr(record, "currency", "") or "").strip().upper() != callback_currency:
        checks.append(("currency", getattr(record, "currency", None), callback_currency))
    if not checks:
        return
    mismatch, expected, received = checks[0]
    await _emit_platega_callback_mismatch_event(
        record,
        mismatch=mismatch,
        expected=expected,
        received=received,
        payload=payload,
        parsed_payload=parsed_payload,
    )
    raise PlategaError(f"Callback payload mismatch for existing payment record: {mismatch}")


async def ensure_platega_payment_record(
    *,
    user_id: int,
    telegram_id: int | None,
    tariff_code: str,
    payment_method: str,
    list_price_amount: int,
    payable_amount: int,
    duration_days: int,
    tariff_title: str,
    payload_type: str = "subscription",
    metadata_extra: dict[str, Any] | None = None,
    description: str | None = None,
) -> PaymentRecord:
    existing_intent = await get_open_payment_intent_for_user(
        user_id=user_id,
        tariff_code=tariff_code,
        list_price_amount=list_price_amount,
        duration_days=duration_days,
        product_type=metadata_extra.get("product_type") if metadata_extra else (payload_type if payload_type != "subscription" else None),
        payload_type=payload_type,
        slots_count=int(metadata_extra.get("slots_count") or 0) if metadata_extra else None,
    )
    if existing_intent is not None and str(existing_intent.payment_method or "").strip().lower() != payment_method:
        raise PlategaError(_platega_intent_conflict_message(existing_intent))
    existing_record = await get_open_payment_record_for_user(
        user_id=user_id,
        tariff_code=tariff_code,
        payment_method=payment_method,
    )
    if existing_record is not None:
        metadata = _load_payment_metadata(existing_record.metadata_json)
        if metadata.get("checkout_url"):
            return existing_record

    client = PlategaClient()
    if not client.configured:
        raise PlategaError("Platega is not configured")

    payload = platega_payload(
        user_id=user_id,
        telegram_id=telegram_id,
        tariff_code=tariff_code,
        payment_method=payment_method,
        payload_type=payload_type,
    )
    payload["list_price_amount"] = int(list_price_amount)
    payload["payable_amount"] = max(int(payable_amount), 0)
    payload["balance_amount"] = max(int(list_price_amount) - max(int(payable_amount), 0), 0)
    if metadata_extra:
        for key in ("product_type", "slots_count", "addon_expires_at", "unit_price_rub", "total_amount_rub", "duration_days", "tariff_title", "product_title"):
            value = metadata_extra.get(key)
            if value is not None:
                payload[key] = value
    created = await client.create_payment(
        amount_rub=max(int(payable_amount), 0),
        payment_method_id=PLATEGA_METHOD_IDS[payment_method],
        description=description or f"Amonora - {tariff_title}",
        payload=payload,
        return_url=_return_to_bot_url(),
        failed_url=_return_to_bot_url(),
    )

    metadata = _metadata_for_payment(
        payment_method=payment_method,
        tariff_title=tariff_title,
        telegram_id=telegram_id,
        provider_status=created.status,
        checkout_url=created.checkout_url,
        payload_type=payload_type,
        provider_payload=created.raw,
    )
    if metadata_extra:
        metadata.update(metadata_extra)
    record = await create_balance_aware_external_payment_record(
        user_id=user_id,
        external_payment_id=created.transaction_id,
        tariff_code=tariff_code,
        payment_method=payment_method,
        list_price_amount=list_price_amount,
        currency="RUB",
        duration_days=duration_days,
        note=json.dumps(created.raw, ensure_ascii=False),
        metadata=metadata,
        expires_at=None,
    )
    return record


async def ensure_platega_balance_topup_record(
    *,
    user_id: int,
    telegram_id: int | None,
    payment_method: str,
    amount_rub: int,
) -> PaymentRecord:
    existing_intent = await get_open_payment_intent_for_user(
        user_id=user_id,
        tariff_code=BALANCE_TOPUP_TARIFF_CODE,
        list_price_amount=amount_rub,
        duration_days=0,
        product_type=BALANCE_TOPUP_PAYLOAD_TYPE,
        payload_type=BALANCE_TOPUP_PAYLOAD_TYPE,
    )
    if existing_intent is not None and str(existing_intent.payment_method or "").strip().lower() != payment_method:
        raise PlategaError(_platega_intent_conflict_message(existing_intent))
    client = PlategaClient()
    if not client.configured:
        raise PlategaError("Platega is not configured")

    amount_rub = max(int(amount_rub), 0)
    if amount_rub <= 0:
        raise PlategaError("Top-up amount must be positive")

    payload = platega_payload(
        user_id=user_id,
        telegram_id=telegram_id,
        tariff_code=BALANCE_TOPUP_TARIFF_CODE,
        payment_method=payment_method,
        payload_type=BALANCE_TOPUP_PAYLOAD_TYPE,
    )
    payload["topup_amount"] = amount_rub
    created = await client.create_payment(
        amount_rub=amount_rub,
        payment_method_id=PLATEGA_METHOD_IDS[payment_method],
        description="Amonora - Пополнение баланса",
        payload=payload,
        return_url=_return_to_bot_url(),
        failed_url=_return_to_bot_url(),
    )

    metadata = _metadata_for_payment(
        payment_method=payment_method,
        tariff_title="Пополнение баланса",
        telegram_id=telegram_id,
        provider_status=created.status,
        checkout_url=created.checkout_url,
        payload_type=BALANCE_TOPUP_PAYLOAD_TYPE,
        provider_payload=created.raw,
    )
    return await create_external_payment_record(
        user_id=user_id,
        external_payment_id=created.transaction_id,
        tariff_code=BALANCE_TOPUP_TARIFF_CODE,
        payment_method=payment_method,
        amount=amount_rub,
        list_price_amount=amount_rub,
        balance_reserved_amount=0,
        balance_applied_amount=0,
        currency="RUB",
        duration_days=0,
        note=json.dumps(created.raw, ensure_ascii=False),
        metadata=metadata,
    )


async def _update_record_metadata(
    session: AsyncSession,
    record: PaymentRecord,
    *,
    provider_status: str,
    provider_payload: dict[str, Any],
    provider_sync_problem: str | None = None,
) -> None:
    previous_metadata = _load_payment_metadata(record.metadata_json)
    merged = {
        **previous_metadata,
        "provider": "platega",
        "provider_name": PLATEGA_PROVIDER_NAMES.get(record.payment_method, "Platega"),
        "provider_status": provider_status,
        "provider_payload": provider_payload,
        "last_synced_at": PlategaClient.now_sync_stamp(),
        "provider_sync_problem": provider_sync_problem,
    }
    if previous_metadata.get("checkout_url"):
        merged["checkout_url"] = previous_metadata["checkout_url"]
    record.metadata_json = json.dumps(merged, ensure_ascii=False)
    record.note = json.dumps(provider_payload, ensure_ascii=False)


async def _set_non_confirmed_status(
    session: AsyncSession,
    record: PaymentRecord,
    *,
    normalized_status: str,
    provider_payload: dict[str, Any],
    provider_sync_problem: str | None = None,
) -> PaymentRecord:
    if record.payment_status == "confirmed":
        await _update_record_metadata(
            session,
            record,
            provider_status=str(provider_payload.get("status") or ""),
            provider_payload=provider_payload,
            provider_sync_problem=provider_sync_problem,
        )
        await session.commit()
        await session.refresh(record)
        return record

    record.payment_status = normalized_status
    if normalized_status == "expired":
        record.expires_at = record.expires_at or utcnow()
    if normalized_status in {"expired", "cancelled", "rejected", "disputed"}:
        await _release_reserved_balance_for_record(
            session,
            record,
            reason=f"payment_{normalized_status}",
        )
    await _update_record_metadata(
        session,
        record,
        provider_status=str(provider_payload.get("status") or ""),
        provider_payload=provider_payload,
        provider_sync_problem=provider_sync_problem,
    )
    await session.commit()
    await session.refresh(record)
    if record.user_id is not None:
        await safe_emit_analytics_event(
            event_name=EVENT_PAYMENT_FAILED,
            occurred_at=getattr(record, "expires_at", None) or utcnow(),
            user_id=int(record.user_id),
            dedupe_key=f"payment-failed:{int(record.id)}:{normalized_status}",
            payment_record_id=int(record.id),
            tariff_code=getattr(record, "tariff_code", None),
            payment_method=getattr(record, "payment_method", None),
            payload={
                "payment_status": normalized_status,
                "provider_status": str(provider_payload.get("status") or "").strip().upper(),
                "provider": "platega",
            },
        )
    return record


def _provider_problem_text(*, record: PaymentRecord, provider_status: str) -> str | None:
    if record.payment_status != "confirmed":
        return None
    if provider_status not in {PlategaClient.STATUS_CANCELED, PlategaClient.STATUS_CHARGEBACKED}:
        return None
    return (
        "Provider returned terminal status after local confirmation. "
        f"Local status stays confirmed until manual compensation flow: {provider_status}."
    )


async def _emit_provider_mismatch_event(record: PaymentRecord, provider_status: str, provider_payload: dict[str, Any]) -> None:
    await create_control_event(
        category="payments",
        severity="WARNING",
        event_type="payment_provider_mismatch",
        title="Провайдер вернул спорный статус после локального подтверждения",
        message=(
            f"Платёж <code>#{record.id}</code> уже подтверждён локально.\n"
            f"Провайдер: <b>Platega</b>\n"
            f"Метод: <b>{record.payment_method}</b>\n"
            f"Provider status: <b>{provider_status}</b>\n"
            f"Transaction ID: <code>{record.external_payment_id or '—'}</code>"
        ),
        entity_type="payment_record",
        entity_id=str(record.id),
        payload={
            "record_id": record.id,
            "payment_method": record.payment_method,
            "provider_status": provider_status,
            "provider_payload": provider_payload,
        },
        dedupe_key=f"platega-mismatch:{record.id}:{provider_status}",
    )


async def sync_platega_record_by_id(
    record_id: int,
    *,
    notify_user: bool = False,
    bot: Bot | None = None,
) -> dict[str, Any]:
    record = await get_payment_record_by_id(record_id)
    if record is None:
        raise PlategaError("Payment record not found")
    if not is_platega_payment_method(record.payment_method):
        raise PlategaError("Payment record is not managed by Platega")
    return await sync_platega_record(record, notify_user=notify_user, bot=bot)


async def sync_platega_record(record: PaymentRecord, *, notify_user: bool = False, bot: Bot | None = None) -> dict[str, Any]:
    if not is_platega_payment_method(record.payment_method):
        raise PlategaError("Payment record is not managed by Platega")
    if not record.external_payment_id:
        raise PlategaError("Provider transaction ID is missing")

    metadata = _load_payment_metadata(record.metadata_json)
    payload_type = str(metadata.get("payload_type") or "subscription").strip().lower()
    client = PlategaClient()
    payload = await client.get_payment_status(record.external_payment_id)
    provider_status = str(payload.get("status") or "").upper()
    just_confirmed = False
    payment_result = None
    provider_sync_problem = _provider_problem_text(record=record, provider_status=provider_status)

    if provider_status == PlategaClient.STATUS_CONFIRMED:
        updated_record, just_confirmed = await confirm_external_payment_record(
            payment_method=record.payment_method,
            external_payment_id=record.external_payment_id,
            note=json.dumps(payload, ensure_ascii=False),
        )
        if updated_record is None:
            raise PlategaError("Unable to confirm payment record")
        async with async_session() as session:
            locked = (
                await session.execute(select(PaymentRecord).where(PaymentRecord.id == updated_record.id).with_for_update())
            ).scalar_one_or_none()
            if locked is not None:
                await _update_record_metadata(
                    session,
                    locked,
                    provider_status=provider_status,
                    provider_payload=payload,
                    provider_sync_problem=provider_sync_problem,
                )
                await session.commit()
                await session.refresh(locked)
                updated_record = locked
        record = updated_record
        effect_applied = payment_record_effect_applied(record)
        if just_confirmed or not effect_applied:
            if record.user_id is None:
                raise PlategaError("Confirmed payment is not linked to a user")
            await sync_income_entry_for_payment_record(record.id)
            payment_result = await finalize_payment_record_product(
                user_id=record.user_id,
                payment_source=PLATEGA_PAYMENT_SOURCES[record.payment_method],
                payment_record_id=record.id,
                tariff_code=record.tariff_code or "",
                payment_id=record.external_payment_id,
            )
            if payment_result is None:
                raise PlategaError("Payment confirmed, but access activation failed")
            if (
                payment_result.get("effect_applied_now", True)
                and payment_result.get("product_type") == "subscription"
            ):
                await apply_referral_bonus(
                    bot if notify_user else None,
                    payment_record_id=record.id,
                )
            if (
                notify_user
                and payment_result.get("effect_applied_now", True)
                and bot is not None
                and payment_result["user"].telegram_id
            ):
                await notify_payment_result(
                    bot=bot,
                    telegram_id=payment_result["user"].telegram_id,
                    payment_result=payment_result,
                )
    else:
        mapped_status = {
            PlategaClient.STATUS_PENDING: "pending",
            PlategaClient.STATUS_CANCELED: "expired",
            PlategaClient.STATUS_CHARGEBACKED: "disputed",
        }.get(provider_status, "error")
        async with async_session() as session:
            locked = (
                await session.execute(select(PaymentRecord).where(PaymentRecord.id == record.id).with_for_update())
            ).scalar_one_or_none()
            if locked is None:
                raise PlategaError("Payment record disappeared during sync")
            record = await _set_non_confirmed_status(
                session,
                locked,
                normalized_status=mapped_status,
                provider_payload=payload,
                provider_sync_problem=provider_sync_problem,
            )

    if provider_sync_problem:
        await _emit_provider_mismatch_event(record, provider_status, payload)

    return {
        "record": record,
        "provider_status": provider_status,
        "just_confirmed": just_confirmed,
        "payment_result": payment_result,
        "provider_sync_problem": provider_sync_problem,
    }


async def handle_platega_callback_payload(payload: dict[str, Any], *, notify_user: bool = False, bot: Bot | None = None) -> dict[str, Any]:
    raw_payment_method = str(payload.get("paymentMethod") or "").strip()
    raw_payload = payload.get("payload")
    parsed_payload = PlategaClient.parse_payload(raw_payload)
    payload_type = str(parsed_payload.get("type") or "subscription").strip().lower()
    payment_method = str(parsed_payload.get("payment_method") or "").strip()
    transaction_id = str(payload.get("id") or "").strip()
    tariff_code = str(parsed_payload.get("tariff_code") or "").strip()
    device_slot_product = is_device_slot_product(
        product_type=str(parsed_payload.get("product_type") or payload_type),
        tariff_code=tariff_code,
    )
    tariff = get_tariff(tariff_code) if payload_type != BALANCE_TOPUP_PAYLOAD_TYPE and not device_slot_product else None
    if payload_type != BALANCE_TOPUP_PAYLOAD_TYPE and not device_slot_product and tariff is None:
        raise PlategaError("Tariff not found for callback payload")
    if not is_platega_payment_method(payment_method):
        if raw_payment_method == str(PlategaClient.METHOD_SBP_QR):
            payment_method = "sbp_platega"
        elif raw_payment_method == str(PlategaClient.METHOD_CRYPTO):
            payment_method = "crypto_platega"
    if not is_platega_payment_method(payment_method):
        raise PlategaError("Unsupported payment method in callback payload")

    record = await get_payment_record_by_external_id(payment_method, transaction_id)
    if record is None:
        if payload_type == BALANCE_TOPUP_PAYLOAD_TYPE:
            topup_amount = max(int(float(parsed_payload.get("topup_amount") or payload.get("amount") or 0)), 0)
            if topup_amount <= 0:
                raise PlategaError("Balance top-up amount is missing in callback payload")
            record = await create_external_payment_record(
                user_id=parsed_payload.get("user_id"),
                external_payment_id=transaction_id,
                tariff_code=BALANCE_TOPUP_TARIFF_CODE,
                payment_method=payment_method,
                amount=topup_amount,
                list_price_amount=topup_amount,
                balance_reserved_amount=0,
                balance_applied_amount=0,
                currency="RUB",
                duration_days=0,
                note=json.dumps(payload, ensure_ascii=False),
                metadata=_metadata_for_payment(
                    payment_method=payment_method,
                    tariff_title="Пополнение баланса",
                    telegram_id=parsed_payload.get("telegram_id"),
                    provider_status=str(payload.get("status") or ""),
                    payload_type=payload_type,
                    provider_payload=payload,
                ),
            )
        else:
            list_price_amount = max(
                int(parsed_payload.get("list_price_amount") or (tariff.rub_price if tariff is not None else 0)),
                0,
            )
            balance_amount = max(int(parsed_payload.get("balance_amount") or 0), 0)
            payable_amount = max(int(parsed_payload.get("payable_amount") or payload.get("amount") or list_price_amount - balance_amount), 0)
            tariff_title = (
                str(parsed_payload.get("tariff_title") or parsed_payload.get("product_title") or "").strip()
                or (
                    marketing_tariff_title(tariff.title, tariff.code)
                    if tariff is not None
                    else "Дополнительное устройство"
                )
            )
            record = await create_external_payment_record(
                user_id=parsed_payload.get("user_id"),
                external_payment_id=transaction_id,
                tariff_code=tariff.code if tariff is not None else tariff_code,
                payment_method=payment_method,
                amount=payable_amount,
                list_price_amount=list_price_amount,
                balance_reserved_amount=balance_amount,
                balance_applied_amount=0,
                currency="RUB",
                duration_days=(
                    int(parsed_payload.get("duration_days") or 0)
                    if device_slot_product
                    else tariff.duration_days
                ),
                note=json.dumps(payload, ensure_ascii=False),
                metadata={
                    **_metadata_for_payment(
                        payment_method=payment_method,
                        tariff_title=tariff_title,
                        telegram_id=parsed_payload.get("telegram_id"),
                        provider_status=str(payload.get("status") or ""),
                        payload_type=payload_type,
                        provider_payload=payload,
                    ),
                    **(
                        {
                            "product_type": DEVICE_SLOT_PRODUCT_TYPE,
                            "slots_count": int(parsed_payload.get("slots_count") or 1),
                            "unit_price_rub": int(parsed_payload.get("unit_price_rub") or list_price_amount),
                            "total_amount_rub": int(parsed_payload.get("total_amount_rub") or list_price_amount),
                            "addon_expires_at": parsed_payload.get("addon_expires_at"),
                            "product_title": tariff_title,
                            "tariff_title": tariff_title,
                        }
                        if device_slot_product
                        else {}
                    ),
                },
            )
    else:
        await _validate_platega_callback_matches_record(
            record,
            payload=payload,
            parsed_payload=parsed_payload,
            payment_method=payment_method,
            payload_type=payload_type,
            tariff_code=tariff.code if tariff is not None else tariff_code,
        )
    await _mark_platega_callback_seen(record, payload=payload, parsed_payload=parsed_payload)
    if _platega_callback_is_duplicate_noop(record, payload, parsed_payload):
        return {
            "record": record,
            "provider_status": str(payload.get("status") or "").strip().upper(),
            "duplicate": True,
        }
    return await sync_platega_record(record, notify_user=notify_user, bot=bot)


async def ensure_user_for_platega_record(record_id: int) -> tuple[int, int | None]:
    record = await get_payment_record_by_id(record_id)
    if record is None or record.user_id is None:
        raise PlategaError("Payment record is not linked to a user")
    user = await get_user_by_id(record.user_id)
    return record.user_id, user.telegram_id if user is not None else None
