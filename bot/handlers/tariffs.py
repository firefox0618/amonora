import json
import logging
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from bot.config import config
from bot.crypto_pay import CryptoPayClient, CryptoPayError
from bot.db import (
    _load_payment_metadata,
    build_balance_breakdown_for_price,
    cancel_manual_payment_record,
    confirm_external_payment_record,
    create_balance_aware_manual_payment_record,
    create_balance_only_custom_payment_record,
    create_balance_only_payment_record,
    create_external_payment_record,
    get_active_device_slot_counts_for_users,
    get_access_expires_at,
    get_open_payment_intent_for_user,
    get_payment_record_by_id,
    payment_record_effect_applied,
    get_user_balance_summary,
    get_payment_record_by_external_id,
    get_user_by_telegram_id,
    mark_manual_payment_record_submitted,
)
from bot.keyboards.main_menu import main_menu
from bot.keyboards.tariffs import (
    balance_external_payment_keyboard,
    balance_topup_amounts_keyboard,
    balance_topup_methods_keyboard,
    crypto_invoice_keyboard,
    device_slot_external_payment_keyboard,
    device_slot_manual_payment_keyboard,
    device_slot_methods_keyboard,
    external_payment_keyboard,
    manual_payment_keyboard,
    tariff_methods_keyboard,
    tariffs_keyboard,
)
from bot.manual_payments import notify_support_admins_about_manual_payment
from bot.payment_flow import finalize_payment_record_product, finalize_subscription_payment, notify_referral_bonus
from bot.platega import PlategaClient, PlategaError
from bot.platega_flow import (
    ensure_platega_balance_topup_record,
    ensure_platega_payment_record,
    platega_payment_method_for_choice,
    sync_platega_record_by_id,
)
from bot.utils.access import get_device_limit_for_user, has_active_subscription_from_user, utcnow
from bot.utils.device_slots import (
    DEFAULT_DEVICE_LIMIT,
    DEVICE_SLOT_PRODUCT_TYPE,
    DEVICE_SLOT_TARIFF_CODE,
    MAX_DEVICE_LIMIT,
    device_slot_display_title,
    device_slot_duration_days,
    device_slot_unit_price_rub,
    remaining_device_slot_capacity,
)
from bot.utils.payment_options import (
    sbp_balance_topup_uses_platega,
    sbp_manual_emergency_fallback_active,
    sbp_tariff_uses_manual,
    sbp_tariff_uses_platega,
)
from bot.utils.tariffs import get_tariff, marketing_tariff_title
from bot.utils.texts import (
    CRYPTO_PAYMENT_NOT_CONFIGURED_TEXT,
    PAYMENT_SYNC_WARNING_TEXT,
    PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
    SEP,
    blocked_user_action_text,
    balance_topup_methods_text,
    balance_topup_payment_text,
    balance_topup_success_text,
    crypto_invoice_text,
    device_slot_methods_text,
    device_slot_payment_success_text,
    manual_payment_details_text,
    manual_payment_inactive_text,
    manual_payment_rejected_text,
    manual_payment_waiting_review_text,
    platega_payment_text,
    payment_success_text,
    tariff_methods_text,
    tariffs_text,
)
from dashboard.finance import sync_income_entry_for_payment_record


logger = logging.getLogger(__name__)
router = Router()
MANUAL_PAYMENT_METHODS = {"sbp_manual", "crypto_manual"}


def _device_slot_title() -> str:
    return device_slot_display_title(1)


async def _safe_edit_callback_message(callback: CallbackQuery, text: str, *, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _annotate_user_device_slots(user) -> int:
    if user is None or getattr(user, "id", None) is None:
        return 0
    counts = await get_active_device_slot_counts_for_users([int(user.id)])
    active_slots = int(counts.get(int(user.id), 0))
    setattr(user, "active_device_slot_addons", active_slots)
    return active_slots


def _device_slot_allowed_for_user(user) -> bool:
    return (
        user is not None
        and not getattr(user, "is_blocked", False)
        and has_active_subscription_from_user(user)
        and get_device_limit_for_user(user) <= MAX_DEVICE_LIMIT
        and remaining_device_slot_capacity(user, base_limit=DEFAULT_DEVICE_LIMIT) > 0
    )


async def _device_slot_context_for_user(user) -> dict | None:
    if user is None:
        return None

    active_slots = await _annotate_user_device_slots(user)
    current_limit = DEFAULT_DEVICE_LIMIT + active_slots
    current_limit = min(current_limit, MAX_DEVICE_LIMIT)
    remaining_capacity = remaining_device_slot_capacity(user, base_limit=DEFAULT_DEVICE_LIMIT)
    expires_at = getattr(user, "subscription_expires_at", None)
    expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
    next_limit = min(current_limit + 1, MAX_DEVICE_LIMIT)
    return {
        "active_slots": active_slots,
        "current_limit": current_limit,
        "next_limit": next_limit,
        "remaining_capacity": remaining_capacity,
        "expires_at": expires_at,
        "expires_text": expires_text,
        "price_rub": device_slot_unit_price_rub(),
        "duration_days": device_slot_duration_days(expires_at),
        "eligible": _device_slot_allowed_for_user(user),
    }


def _device_slot_payment_metadata(*, user, context: dict, method: str | None = None) -> dict:
    metadata = {
        "product_type": DEVICE_SLOT_PRODUCT_TYPE,
        "product_title": _device_slot_title(),
        "tariff_title": _device_slot_title(),
        "slots_count": 1,
        "unit_price_rub": context["price_rub"],
        "total_amount_rub": context["price_rub"],
        "duration_days": context["duration_days"],
        "addon_expires_at": context["expires_at"].isoformat() if context.get("expires_at") is not None else None,
        "telegram_id": getattr(user, "telegram_id", None),
    }
    if method:
        metadata["method"] = method
    return metadata


def _device_slot_unavailable_text() -> str:
    return (
        "📱 <b>Дополнительные устройства доступны только при активной платной подписке</b>\n\n"
        "Trial и неактивные аккаунты не могут покупать доп. слоты."
    )


def _payment_result_text(payment_result: dict, *, fallback_title: str | None = None) -> str:
    if str(payment_result.get("product_type") or "").strip().lower() == DEVICE_SLOT_PRODUCT_TYPE:
        return device_slot_payment_success_text(
            title=str(payment_result.get("display_title") or fallback_title or _device_slot_title()),
            expires_at=str(payment_result.get("expires_text") or "—"),
            device_limit=int(payment_result.get("device_limit") or DEFAULT_DEVICE_LIMIT),
            slots_count=int(payment_result.get("slots_count") or 1),
            list_price_amount=payment_result.get("list_price_amount"),
            balance_applied_amount=int(payment_result.get("balance_applied_amount") or 0),
            paid_amount=payment_result.get("paid_amount"),
        )
    tariff = payment_result.get("tariff")
    title = fallback_title or (tariff.title if tariff is not None else "Тариф")
    return payment_success_text(
        title,
        payment_result["expires_text"],
        list_price_amount=payment_result["list_price_amount"],
        balance_applied_amount=payment_result["balance_applied_amount"],
        paid_amount=payment_result["paid_amount"],
    )


async def _device_slot_success_text_from_record(user, record) -> str:
    context = await _device_slot_context_for_user(user)
    metadata = _load_payment_metadata(getattr(record, "metadata_json", None))
    expires_at = getattr(user, "subscription_expires_at", None)
    expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
    return device_slot_payment_success_text(
        title=str(metadata.get("product_title") or metadata.get("tariff_title") or _device_slot_title()),
        expires_at=expires_text,
        device_limit=int(context["current_limit"] if context is not None else DEFAULT_DEVICE_LIMIT),
        slots_count=int(metadata.get("slots_count") or 1),
        list_price_amount=int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0),
        balance_applied_amount=int(getattr(record, "balance_applied_amount", 0) or 0),
        paid_amount=int(getattr(record, "amount", 0) or 0),
    )


def _external_payment_status_notice(payment_status: str, provider_status: str) -> str:
    normalized_payment_status = str(payment_status or "").strip().lower()
    normalized_provider_status = str(provider_status or "").strip().upper()
    if normalized_payment_status == "confirmed":
        return "Оплата успешно подтверждена"
    if normalized_payment_status in {"awaiting_user_payment", "pending"} or normalized_provider_status == "PENDING":
        return "Оплата в обработке"
    if normalized_payment_status in {"expired", "cancelled"}:
        return "Счёт больше не активен"
    if normalized_payment_status == "disputed":
        return "Платёж отмечен как спорный"
    if normalized_payment_status == "error":
        return "Платёж вернул ошибку"
    return f"Статус оплаты: {provider_status or payment_status or 'неизвестно'}"


async def _blocked_payment_guard(message_target: Message | None, telegram_id: int) -> object | None:
    user = await get_user_by_telegram_id(telegram_id)
    if user is not None and getattr(user, "is_blocked", False):
        if message_target is not None:
            await message_target.answer(blocked_user_action_text(), parse_mode="HTML")
        return user
    return None


def _manual_payment_settings(method: str) -> tuple[str, str]:
    if method == "sbp":
        return "sbp_manual", config.manual_sbp_details or "Реквизиты СБП временно не указаны. Напиши в поддержку."
    if method == "crypto":
        return "crypto_manual", config.manual_crypto_details or "Крипто-реквизиты временно не указаны. Напиши в поддержку."
    raise ValueError(f"Unsupported manual payment method: {method}")


def _payment_breakdown_from_record(record, fallback_price: int) -> dict[str, int]:
    list_price_amount = int(getattr(record, "list_price_amount", 0) or fallback_price)
    balance_amount = int(getattr(record, "balance_applied_amount", 0) or getattr(record, "balance_reserved_amount", 0) or 0)
    paid_amount = int(getattr(record, "amount", 0) or 0)
    return {
        "list_price_amount": list_price_amount,
        "balance_amount": balance_amount,
        "paid_amount": paid_amount,
    }


async def _load_user_and_breakdown(callback: CallbackQuery, tariff) -> tuple[object | None, dict[str, int] | None]:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return None, None
    breakdown = await build_balance_breakdown_for_price(user.id, tariff.rub_price)
    return user, breakdown


def _existing_open_payment_intro(record) -> str:
    payment_method = str(getattr(record, "payment_method", "") or "").strip().lower()
    if payment_method in MANUAL_PAYMENT_METHODS:
        return (
            "ℹ️ <b>У тебя уже есть активная заявка на эту покупку.</b>\n"
            "Открываю её снова, чтобы не создавать дубль."
        )
    return (
        "ℹ️ <b>У тебя уже есть активный счёт на эту покупку.</b>\n"
        "Открываю его снова, чтобы не создавать дубль."
    )


def _prefix_payment_text(text: str, intro_note: str | None) -> str:
    if not intro_note:
        return text
    return f"{intro_note}\n\n{SEP}\n\n{text}"


async def _finish_balance_only_payment(
    message_target: Message,
    *,
    user_id: int,
    tariff,
    bot: Bot | None = None,
) -> bool:
    record = await create_balance_only_payment_record(
        user_id=user_id,
        tariff_code=tariff.code,
        duration_days=tariff.duration_days,
    )
    if record is None:
        return False

    payment_result = await finalize_subscription_payment(
        user_id=user_id,
        tariff_code=tariff.code,
        payment_id=record.external_payment_id or f"balance_{record.id}",
        payment_source="balance_rub",
        payment_record_id=record.id,
    )
    if payment_result is None:
        return False

    await message_target.edit_text(
        payment_success_text(
            payment_result["tariff"].title,
            payment_result["expires_text"],
            list_price_amount=payment_result["list_price_amount"],
            balance_applied_amount=payment_result["balance_applied_amount"],
            paid_amount=payment_result["paid_amount"],
        ),
        parse_mode="HTML",
        reply_markup=tariff_methods_keyboard(tariff.code),
    )
    if payment_result["sync_failed"]:
        await message_target.answer(PAYMENT_SYNC_WARNING_TEXT)
    if bot is not None:
        await notify_referral_bonus(bot, payment_record_id=record.id)
    return True


async def _show_manual_payment(callback: CallbackQuery, *, method: str, tariff, user, intro_note: str | None = None) -> None:
    display_title = marketing_tariff_title(tariff.title, tariff.code)
    payment_method, details = _manual_payment_settings(method)
    record = await create_balance_aware_manual_payment_record(
        user_id=user.id,
        tariff_code=tariff.code,
        payment_method=payment_method,
        list_price_amount=tariff.rub_price,
        currency="RUB",
        duration_days=tariff.duration_days,
        metadata={
            "tariff_title": display_title,
            "telegram_id": user.telegram_id,
            "method": method,
        },
        expires_at=utcnow() + timedelta(hours=config.manual_payment_review_hours),
    )

    text = manual_payment_details_text(
        tariff_title=display_title,
        amount_rub=record.amount,
        list_price_amount=record.list_price_amount or tariff.rub_price,
        balance_reserved_amount=record.balance_reserved_amount or 0,
        method_label=payment_method,
        request_id=record.id,
        details=details,
        review_hours=config.manual_payment_review_hours,
    )
    await callback.message.edit_text(
        _prefix_payment_text(text, intro_note),
        parse_mode="HTML",
        reply_markup=manual_payment_keyboard(record.id, tariff.code),
    )
    await callback.answer()


async def _show_platega_payment(callback: CallbackQuery, *, method: str, tariff, user, breakdown: dict[str, int]) -> None:
    display_title = marketing_tariff_title(tariff.title, tariff.code)
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer()
        return

    client = PlategaClient()
    if not client.configured:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer()
        return

    try:
        record = await ensure_platega_payment_record(
            user_id=user.id,
            telegram_id=user.telegram_id,
            tariff_code=tariff.code,
            payment_method=payment_method,
            list_price_amount=tariff.rub_price,
            duration_days=tariff.duration_days,
            tariff_title=display_title,
            payable_amount=breakdown["payable_amount"],
        )
    except PlategaError as exc:
        logger.warning("Failed to create Platega payment: %s", exc)
        await callback.message.edit_text(
            "Не удалось создать оплату через провайдера. Попробуй ещё раз позже или выбери Telegram Stars.",
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer()
        return

    metadata = {}
    if record.metadata_json:
        try:
            metadata = json.loads(record.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        platega_payment_text(
            tariff_title=display_title,
            amount_rub=record.amount,
            method_label=payment_method,
            checkout_label="страница оплаты",
            list_price_amount=record.list_price_amount or tariff.rub_price,
            balance_reserved_amount=record.balance_reserved_amount or 0,
            extra_hint="После оплаты можно нажать «Проверить оплату», если подтверждение немного задержится.",
        ),
        parse_mode="HTML",
        reply_markup=external_payment_keyboard(checkout_url, tariff.code, record.id),
    )
    await callback.answer("Счёт создан")


async def _show_device_slot_methods(callback: CallbackQuery, *, user) -> None:
    context = await _device_slot_context_for_user(user)
    if context is None or not context["eligible"]:
        await callback.message.edit_text(
            _device_slot_unavailable_text(),
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Доп. устройства недоступны", show_alert=True)
        return
    if context["remaining_capacity"] <= 0:
        await callback.answer("Максимальный лимит устройств уже достигнут", show_alert=True)
        return

    breakdown = await build_balance_breakdown_for_price(user.id, context["price_rub"])
    await callback.message.edit_text(
        device_slot_methods_text(
            title=_device_slot_title(),
            amount_rub=context["price_rub"],
            expires_at=context["expires_text"],
            current_limit=context["current_limit"],
            next_limit=context["next_limit"],
            max_limit=MAX_DEVICE_LIMIT,
            list_price_amount=breakdown["list_price_amount"],
            balance_amount=breakdown["balance_amount"],
            payable_amount=breakdown["payable_amount"],
        ),
        parse_mode="HTML",
        reply_markup=device_slot_methods_keyboard(),
    )
    await callback.answer()


async def _finish_device_slot_balance_only_payment(message_target: Message, *, user, context: dict) -> bool:
    record = await create_balance_only_custom_payment_record(
        user_id=user.id,
        tariff_code=DEVICE_SLOT_TARIFF_CODE,
        list_price_amount=context["price_rub"],
        duration_days=context["duration_days"],
        payment_source="balance_rub",
        currency="RUB",
        note=_device_slot_title(),
        metadata=_device_slot_payment_metadata(user=user, context=context),
    )
    if record is None:
        return False

    payment_result = await finalize_payment_record_product(
        user_id=user.id,
        payment_source="balance_rub",
        payment_record_id=record.id,
        tariff_code=DEVICE_SLOT_TARIFF_CODE,
        payment_id=record.external_payment_id or f"balance_{record.id}",
    )
    if payment_result is None:
        return False

    await sync_income_entry_for_payment_record(record.id)
    await message_target.edit_text(
        _payment_result_text(payment_result, fallback_title=_device_slot_title()),
        parse_mode="HTML",
        reply_markup=device_slot_methods_keyboard(),
    )
    return True


async def _show_device_slot_manual_payment(callback: CallbackQuery, *, method: str, user, context: dict, intro_note: str | None = None) -> None:
    payment_method, details = _manual_payment_settings(method)
    record = await create_balance_aware_manual_payment_record(
        user_id=user.id,
        tariff_code=DEVICE_SLOT_TARIFF_CODE,
        payment_method=payment_method,
        list_price_amount=context["price_rub"],
        currency="RUB",
        duration_days=context["duration_days"],
        metadata=_device_slot_payment_metadata(user=user, context=context, method=method),
        expires_at=utcnow() + timedelta(hours=config.manual_payment_review_hours),
    )

    text = manual_payment_details_text(
        tariff_title=_device_slot_title(),
        amount_rub=record.amount,
        list_price_amount=record.list_price_amount or context["price_rub"],
        balance_reserved_amount=record.balance_reserved_amount or 0,
        method_label=payment_method,
        request_id=record.id,
        details=details,
        review_hours=config.manual_payment_review_hours,
    )
    await callback.message.edit_text(
        _prefix_payment_text(text, intro_note),
        parse_mode="HTML",
        reply_markup=device_slot_manual_payment_keyboard(record.id),
    )
    await callback.answer()


async def _show_device_slot_platega_payment(callback: CallbackQuery, *, method: str, user, context: dict, breakdown: dict[str, int]) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer()
        return

    client = PlategaClient()
    if not client.configured:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer()
        return

    try:
        record = await ensure_platega_payment_record(
            user_id=user.id,
            telegram_id=user.telegram_id,
            tariff_code=DEVICE_SLOT_TARIFF_CODE,
            payment_method=payment_method,
            list_price_amount=context["price_rub"],
            duration_days=context["duration_days"],
            tariff_title=_device_slot_title(),
            payable_amount=breakdown["payable_amount"],
            payload_type=DEVICE_SLOT_PRODUCT_TYPE,
            metadata_extra=_device_slot_payment_metadata(user=user, context=context, method=method),
            description=f"Amonora - {_device_slot_title()}",
        )
    except PlategaError as exc:
        logger.warning("Failed to create device-slot Platega payment: %s", exc)
        await callback.message.edit_text(
            "Не удалось создать оплату через провайдера. Попробуй ещё раз позже.",
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer()
        return

    metadata = _load_payment_metadata(record.metadata_json)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        platega_payment_text(
            tariff_title=_device_slot_title(),
            amount_rub=record.amount,
            method_label=record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=record.list_price_amount or context["price_rub"],
            balance_reserved_amount=record.balance_reserved_amount or 0,
        ),
        parse_mode="HTML",
        reply_markup=device_slot_external_payment_keyboard(checkout_url, record.id),
    )
    await callback.answer("Счёт создан")


async def _show_platega_balance_topup_payment(callback: CallbackQuery, *, method: str, amount_rub: int, user) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=balance_topup_methods_keyboard(amount_rub),
        )
        await callback.answer()
        return

    client = PlategaClient()
    if not client.configured:
        await callback.message.edit_text(
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            parse_mode="HTML",
            reply_markup=balance_topup_methods_keyboard(amount_rub),
        )
        await callback.answer()
        return

    try:
        record = await ensure_platega_balance_topup_record(
            user_id=user.id,
            telegram_id=user.telegram_id,
            payment_method=payment_method,
            amount_rub=amount_rub,
        )
    except PlategaError as exc:
        logger.warning("Failed to create Platega balance top-up payment: %s", exc)
        await callback.message.edit_text(
            "Не удалось создать счёт на пополнение баланса. Попробуй ещё раз позже.",
            parse_mode="HTML",
            reply_markup=balance_topup_methods_keyboard(amount_rub),
        )
        await callback.answer()
        return

    metadata = {}
    if record.metadata_json:
        try:
            metadata = json.loads(record.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            parse_mode="HTML",
            reply_markup=balance_topup_methods_keyboard(amount_rub),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        balance_topup_payment_text(
            amount_rub=amount_rub,
            method_label=payment_method,
            checkout_label="страницу оплаты",
        ),
        parse_mode="HTML",
        reply_markup=balance_external_payment_keyboard(checkout_url, amount_rub, record.id),
    )
    await callback.answer("Счёт на пополнение создан")


async def _show_existing_subscription_payment_intent(callback: CallbackQuery, *, record, tariff) -> None:
    intro_note = _existing_open_payment_intro(record)
    if str(getattr(record, "payment_method", "") or "").strip().lower() in MANUAL_PAYMENT_METHODS:
        if record.payment_status == "awaiting_admin_review":
            text = manual_payment_waiting_review_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or tariff.rub_price,
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            )
        else:
            payment_method, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or tariff.rub_price,
                balance_reserved_amount=record.balance_reserved_amount or 0,
                method_label=payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await callback.message.edit_text(
            _prefix_payment_text(text, intro_note),
            parse_mode="HTML",
            reply_markup=manual_payment_keyboard(record.id, tariff.code),
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    metadata = _load_payment_metadata(record.metadata_json)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            _prefix_payment_text(
                "Активный счёт уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже или выбери другой способ после завершения этого счёта.",
                intro_note,
            ),
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await callback.message.edit_text(
        _prefix_payment_text(
            platega_payment_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                amount_rub=record.amount,
                method_label=record.payment_method,
                checkout_label="страница оплаты",
                list_price_amount=record.list_price_amount or tariff.rub_price,
                balance_reserved_amount=record.balance_reserved_amount or 0,
                extra_hint="После оплаты можно нажать «Проверить оплату», если подтверждение немного задержится.",
            ),
            intro_note,
        ),
        parse_mode="HTML",
        reply_markup=external_payment_keyboard(checkout_url, tariff.code, record.id),
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


async def _show_existing_device_slot_payment_intent(callback: CallbackQuery, *, record, context: dict) -> None:
    intro_note = _existing_open_payment_intro(record)
    if str(getattr(record, "payment_method", "") or "").strip().lower() in MANUAL_PAYMENT_METHODS:
        if record.payment_status == "awaiting_admin_review":
            text = manual_payment_waiting_review_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or context["price_rub"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            )
        else:
            payment_method, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title=_device_slot_title(),
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or context["price_rub"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                method_label=payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await callback.message.edit_text(
            _prefix_payment_text(text, intro_note),
            parse_mode="HTML",
            reply_markup=device_slot_manual_payment_keyboard(record.id),
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    metadata = _load_payment_metadata(record.metadata_json)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            _prefix_payment_text(
                "Активный счёт уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await callback.message.edit_text(
        _prefix_payment_text(
            platega_payment_text(
                tariff_title=_device_slot_title(),
                amount_rub=record.amount,
                method_label=record.payment_method,
                checkout_label="страница оплаты",
                list_price_amount=record.list_price_amount or context["price_rub"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
            ),
            intro_note,
        ),
        parse_mode="HTML",
        reply_markup=device_slot_external_payment_keyboard(checkout_url, record.id),
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


async def _show_existing_balance_topup_payment_intent(callback: CallbackQuery, *, record, amount_rub: int) -> None:
    intro_note = _existing_open_payment_intro(record)
    metadata = _load_payment_metadata(record.metadata_json)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await callback.message.edit_text(
            _prefix_payment_text(
                "Активный счёт на пополнение уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            parse_mode="HTML",
            reply_markup=balance_topup_methods_keyboard(amount_rub),
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await callback.message.edit_text(
        _prefix_payment_text(
            balance_topup_payment_text(
                amount_rub=int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or amount_rub),
                method_label=record.payment_method,
                checkout_label="страницу оплаты",
            ),
            intro_note,
        ),
        parse_mode="HTML",
        reply_markup=balance_external_payment_keyboard(checkout_url, amount_rub, record.id),
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


@router.message(F.text == "💳 Купить")
@router.message(F.text == "💳 Продлить")
@router.message(F.text == "Тарифы")
async def tariffs_handler(message: Message) -> None:
    if await _blocked_payment_guard(message, message.from_user.id):
        return
    if message.text == "💳 Продлить":
        await message.answer(
            "Теперь кнопка называется <b>💳 Купить</b>.",
            parse_mode="HTML",
            reply_markup=main_menu,
        )
    await message.answer(
        tariffs_text(),
        parse_mode="HTML",
        reply_markup=tariffs_keyboard(),
    )


@router.callback_query(F.data.startswith("tariff:buy:"))
async def buy_tariff_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Оплата недоступна: доступ заблокирован.", show_alert=True)
        return
    tariff_code = callback.data.split(":")[2]
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.message.answer("Тариф не найден.")
        await callback.answer()
        return

    user, breakdown = await _load_user_and_breakdown(callback, tariff)
    if user is None or breakdown is None:
        return

    await callback.message.edit_text(
        tariff_methods_text(
            marketing_tariff_title(tariff.title, tariff.code),
            list_price_amount=tariff.rub_price,
            balance_amount=breakdown["balance_amount"],
            payable_amount=breakdown["payable_amount"],
        ),
        parse_mode="HTML",
        reply_markup=tariff_methods_keyboard(tariff.code),
    )
    await callback.answer()


@router.callback_query(F.data == "tariff:back")
async def tariff_back_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        tariffs_text(),
        parse_mode="HTML",
        reply_markup=tariffs_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "device-slot:buy")
async def device_slot_buy_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Покупка недоступна: доступ заблокирован.", show_alert=True)
        return
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return
    await _show_device_slot_methods(callback, user=user)


@router.callback_query(F.data.startswith("device-slot:method:"))
async def device_slot_method_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Покупка недоступна: доступ заблокирован.", show_alert=True)
        return
    method = callback.data.split(":")[2]
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    context = await _device_slot_context_for_user(user)
    if context is None or not context["eligible"]:
        await callback.message.edit_text(
            _device_slot_unavailable_text(),
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Доп. устройства недоступны", show_alert=True)
        return
    if context["remaining_capacity"] <= 0:
        await callback.answer("Максимальный лимит устройств уже достигнут", show_alert=True)
        return

    breakdown = await build_balance_breakdown_for_price(user.id, context["price_rub"])
    if breakdown["payable_amount"] <= 0:
        finished = await _finish_device_slot_balance_only_payment(callback.message, user=user, context=context)
        await callback.answer(
            "Доп. слот уже оплачен с Баланса" if finished else "Не удалось оформить покупку",
            show_alert=not finished,
        )
        return

    existing_record = await get_open_payment_intent_for_user(
        user_id=user.id,
        tariff_code=DEVICE_SLOT_TARIFF_CODE,
        list_price_amount=context["price_rub"],
        duration_days=context["duration_days"],
        product_type=DEVICE_SLOT_PRODUCT_TYPE,
        slots_count=1,
    )
    if existing_record is not None:
        await _show_existing_device_slot_payment_intent(callback, record=existing_record, context=context)
        return

    if method == "sbp":
        if sbp_tariff_uses_platega():
            await _show_device_slot_platega_payment(callback, method=method, user=user, context=context, breakdown=breakdown)
            return
        if sbp_tariff_uses_manual():
            intro_note = None
            if sbp_manual_emergency_fallback_active():
                intro_note = (
                    "⚠️ <b>Автоматический QR через СБП временно недоступен.</b>\n"
                    "Мы сразу переключили оплату на ручную заявку, чтобы слот всё равно можно было купить."
                )
            await _show_device_slot_manual_payment(callback, method=method, user=user, context=context, intro_note=intro_note)
            return
        await callback.answer("СБП сейчас недоступна", show_alert=True)
        return

    if method == "sbp_manual":
        if sbp_tariff_uses_manual():
            intro_note = None
            if sbp_manual_emergency_fallback_active():
                intro_note = (
                    "⚠️ <b>Если автоматический QR по СБП не сработал, используй эту ручную заявку.</b>\n"
                    "После перевода администратор подтвердит покупку слота вручную."
                )
            await _show_device_slot_manual_payment(callback, method="sbp", user=user, context=context, intro_note=intro_note)
            return
        await callback.answer("Ручная СБП сейчас недоступна", show_alert=True)
        return

    if config.enable_platega_crypto_user_flow:
        await _show_device_slot_platega_payment(callback, method=method, user=user, context=context, breakdown=breakdown)
        return
    if config.enable_manual_crypto_user_flow:
        await _show_device_slot_manual_payment(callback, method=method, user=user, context=context)
        return
    await callback.answer("Криптовалюта сейчас недоступна", show_alert=True)


@router.callback_query(F.data.startswith("tariff:method:"))
async def tariff_method_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Оплата недоступна: доступ заблокирован.", show_alert=True)
        return
    _, _, method, tariff_code = callback.data.split(":")
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.message.answer("Тариф не найден.")
        await callback.answer()
        return

    if method in {"sbp", "sbp_manual", "crypto"}:
        user, breakdown = await _load_user_and_breakdown(callback, tariff)
        if user is None or breakdown is None:
            return
        if breakdown["payable_amount"] <= 0:
            finished = await _finish_balance_only_payment(
                callback.message,
                user_id=user.id,
                tariff=tariff,
                bot=callback.bot,
            )
            await callback.answer(
                "Тариф уже оплачен с Баланса" if finished else "Не удалось оформить оплату",
                show_alert=not finished,
            )
            return

        existing_record = await get_open_payment_intent_for_user(
            user_id=user.id,
            tariff_code=tariff.code,
            list_price_amount=tariff.rub_price,
            duration_days=tariff.duration_days,
        )
        if existing_record is not None:
            await _show_existing_subscription_payment_intent(callback, record=existing_record, tariff=tariff)
            return

        if method == "sbp":
            if sbp_tariff_uses_platega():
                await _show_platega_payment(callback, method=method, tariff=tariff, user=user, breakdown=breakdown)
                return
            if sbp_tariff_uses_manual():
                intro_note = None
                if sbp_manual_emergency_fallback_active():
                    intro_note = (
                        "⚠️ <b>Автоматический QR через СБП временно недоступен.</b>\n"
                        "Мы сразу переключили оплату на ручную заявку, чтобы покупка всё равно прошла."
                    )
                await _show_manual_payment(callback, method=method, tariff=tariff, user=user, intro_note=intro_note)
                return
            await callback.answer("СБП сейчас недоступна", show_alert=True)
            return

        if method == "sbp_manual":
            if sbp_tariff_uses_manual():
                intro_note = None
                if sbp_manual_emergency_fallback_active():
                    intro_note = (
                        "⚠️ <b>Если автоматический QR по СБП не сработал, используй эту ручную заявку.</b>\n"
                        "После перевода администратор подтвердит оплату вручную."
                    )
                await _show_manual_payment(callback, method="sbp", tariff=tariff, user=user, intro_note=intro_note)
                return
            await callback.answer("Ручная СБП сейчас недоступна", show_alert=True)
            return

        if config.enable_platega_crypto_user_flow:
            await _show_platega_payment(callback, method=method, tariff=tariff, user=user, breakdown=breakdown)
            return
        if config.enable_manual_crypto_user_flow:
            await _show_manual_payment(callback, method=method, tariff=tariff, user=user)
            return
        await callback.answer("Криптовалюта сейчас недоступна", show_alert=True)
        return

    invoice_kwargs = {
        "title": f"Amonora - {marketing_tariff_title(tariff.title, tariff.code)}",
        "description": f"Покупка доступа к Amonora на {marketing_tariff_title(tariff.title.lower(), tariff.code)}",
        "payload": json.dumps({"type": "subscription", "tariff_code": tariff.code}),
        "currency": config.stars_currency,
        "prices": [LabeledPrice(label=marketing_tariff_title(tariff.title, tariff.code), amount=tariff.stars_price)],
        "start_parameter": f"amonora-{tariff.code}",
    }

    if config.stars_currency.upper() != "XTR" and config.stars_provider_token:
        invoice_kwargs["provider_token"] = config.stars_provider_token

    await callback.message.answer_invoice(**invoice_kwargs)
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.callback_query(F.data.startswith("tariff:manual:paid:"))
async def manual_payment_submitted_callback(callback: CallbackQuery) -> None:
    _, _, _, record_id_str, tariff_code = callback.data.split(":")
    record_id = int(record_id_str)
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    record_before = await get_payment_record_by_id(record_id)
    if record_before is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or record_before.user_id != user.id:
        await callback.answer("Эта заявка тебе не принадлежит", show_alert=True)
        return

    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)

    await _safe_edit_callback_message(
        callback,
        manual_payment_waiting_review_text(
            tariff_title=marketing_tariff_title(tariff.title, tariff.code),
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or tariff.rub_price,
            balance_reserved_amount=updated.balance_reserved_amount or 0,
            paid_amount=updated.amount,
        ),
        reply_markup=manual_payment_keyboard(updated.id, tariff.code),
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith("device-slot:manual:paid:"))
async def device_slot_manual_payment_submitted_callback(callback: CallbackQuery) -> None:
    record_id = int(callback.data.split(":")[3])
    record_before = await get_payment_record_by_id(record_id)
    if record_before is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or record_before.user_id != user.id:
        await callback.answer("Эта заявка тебе не принадлежит", show_alert=True)
        return

    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)

    await _safe_edit_callback_message(
        callback,
        manual_payment_waiting_review_text(
            tariff_title=_device_slot_title(),
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=updated.balance_reserved_amount or 0,
            paid_amount=updated.amount,
        ),
        reply_markup=device_slot_manual_payment_keyboard(updated.id),
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith("tariff:manual:status:"))
async def manual_payment_status_callback(callback: CallbackQuery) -> None:
    _, _, _, record_id_str, tariff_code = callback.data.split(":")
    record_id = int(record_id_str)
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    record = await get_payment_record_by_id(record_id)
    if record is None or user is None or record.user_id != user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if record.payment_status == "confirmed":
        expires_at = await get_access_expires_at(user.id)
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        breakdown = _payment_breakdown_from_record(record, tariff.rub_price)
        await _safe_edit_callback_message(
            callback,
            payment_success_text(
                marketing_tariff_title(tariff.title, tariff.code),
                expires_text,
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=record.balance_applied_amount or 0,
                paid_amount=breakdown["paid_amount"],
            ),
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer("Оплата уже подтверждена", show_alert=True)
        return

    if record.payment_status == "rejected":
        await _safe_edit_callback_message(
            callback,
            manual_payment_rejected_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            reply_markup=manual_payment_keyboard(record.id, tariff.code),
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return

    if record.payment_status in {"expired", "cancelled"}:
        await _safe_edit_callback_message(
            callback,
            manual_payment_inactive_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return

    if record.payment_status == "awaiting_admin_review":
        await _safe_edit_callback_message(
            callback,
            manual_payment_waiting_review_text(
                tariff_title=marketing_tariff_title(tariff.title, tariff.code),
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or tariff.rub_price,
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            ),
            reply_markup=manual_payment_keyboard(record.id, tariff.code),
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return

    payment_method, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _safe_edit_callback_message(
        callback,
        manual_payment_details_text(
            tariff_title=marketing_tariff_title(tariff.title, tariff.code),
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or tariff.rub_price,
            balance_reserved_amount=record.balance_reserved_amount or 0,
            method_label=payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        reply_markup=manual_payment_keyboard(record.id, tariff.code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device-slot:manual:status:"))
async def device_slot_manual_payment_status_callback(callback: CallbackQuery) -> None:
    record_id = int(callback.data.split(":")[3])

    user = await get_user_by_telegram_id(callback.from_user.id)
    record = await get_payment_record_by_id(record_id)
    if record is None or user is None or record.user_id != user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if record.payment_status == "confirmed":
        await _safe_edit_callback_message(
            callback,
            await _device_slot_success_text_from_record(user, record),
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Покупка уже подтверждена", show_alert=True)
        return

    if record.payment_status == "rejected":
        await _safe_edit_callback_message(
            callback,
            manual_payment_rejected_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            reply_markup=device_slot_manual_payment_keyboard(record.id),
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return

    if record.payment_status in {"expired", "cancelled"}:
        await _safe_edit_callback_message(
            callback,
            manual_payment_inactive_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return

    if record.payment_status == "awaiting_admin_review":
        await _safe_edit_callback_message(
            callback,
            manual_payment_waiting_review_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or device_slot_unit_price_rub(),
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            ),
            reply_markup=device_slot_manual_payment_keyboard(record.id),
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return

    payment_method, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _safe_edit_callback_message(
        callback,
        manual_payment_details_text(
            tariff_title=_device_slot_title(),
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=record.balance_reserved_amount or 0,
            method_label=payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        reply_markup=device_slot_manual_payment_keyboard(record.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff:manual:cancel:"))
async def manual_payment_cancel_callback(callback: CallbackQuery) -> None:
    _, _, _, record_id_str, tariff_code = callback.data.split(":")
    record_id = int(record_id_str)
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    record = await get_payment_record_by_id(record_id)
    if record is None or user is None or record.user_id != user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        manual_payment_inactive_text(
            tariff_title=marketing_tariff_title(tariff.title, tariff.code),
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        parse_mode="HTML",
        reply_markup=tariff_methods_keyboard(tariff.code),
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith("device-slot:manual:cancel:"))
async def device_slot_manual_payment_cancel_callback(callback: CallbackQuery) -> None:
    record_id = int(callback.data.split(":")[3])
    user = await get_user_by_telegram_id(callback.from_user.id)
    record = await get_payment_record_by_id(record_id)
    if record is None or user is None or record.user_id != user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        manual_payment_inactive_text(
            tariff_title=_device_slot_title(),
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        parse_mode="HTML",
        reply_markup=device_slot_methods_keyboard(),
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith("balance:amount:"))
async def balance_amount_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Пополнение недоступно: доступ заблокирован.", show_alert=True)
        return
    try:
        amount_rub = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Сумма не распознана", show_alert=True)
        return
    if amount_rub <= 0:
        await callback.answer("Сумма должна быть больше нуля", show_alert=True)
        return

    await callback.message.edit_text(
        balance_topup_methods_text(amount_rub),
        parse_mode="HTML",
        reply_markup=balance_topup_methods_keyboard(amount_rub),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("balance:method:"))
async def balance_method_callback(callback: CallbackQuery) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Пополнение недоступно: доступ заблокирован.", show_alert=True)
        return
    try:
        _, _, method, amount_raw = callback.data.split(":")
        amount_rub = int(amount_raw)
    except ValueError:
        await callback.answer("Сумма не распознана", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    existing_record = await get_open_payment_intent_for_user(
        user_id=user.id,
        tariff_code="balance_topup",
        list_price_amount=amount_rub,
        duration_days=0,
        payload_type="balance_topup",
    )
    if existing_record is not None:
        await _show_existing_balance_topup_payment_intent(callback, record=existing_record, amount_rub=amount_rub)
        return

    if method not in {"sbp", "crypto"}:
        await callback.answer("Способ оплаты не найден", show_alert=True)
        return
    if method == "sbp" and not sbp_balance_topup_uses_platega():
        await callback.answer("СБП для пополнения баланса временно недоступна", show_alert=True)
        return
    await _show_platega_balance_topup_payment(callback, method=method, amount_rub=amount_rub, user=user)


@router.callback_query(F.data.startswith("balance:external:check:"))
async def balance_external_payment_check_callback(callback: CallbackQuery, bot: Bot) -> None:
    if await _blocked_payment_guard(callback.message, callback.from_user.id):
        await callback.answer("Пополнение недоступно: доступ заблокирован.", show_alert=True)
        return
    try:
        _, _, _, record_id_str, amount_raw = callback.data.split(":")
        record_id = int(record_id_str)
        amount_rub = int(amount_raw)
    except ValueError:
        await callback.answer("Счёт не найден", show_alert=True)
        return

    record = await get_payment_record_by_id(record_id)
    if record is None:
        await callback.answer("Счёт не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or record.user_id != user.id:
        await callback.answer("Этот счёт тебе не принадлежит", show_alert=True)
        return

    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=bot)
    except PlategaError as exc:
        logger.warning("Failed to sync Platega balance top-up #%s: %s", record.id, exc)
        await callback.answer("Не удалось проверить оплату", show_alert=True)
        return

    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    if refreshed_record.payment_status == "confirmed":
        balance = await get_user_balance_summary(user.id)
        await callback.message.edit_text(
            balance_topup_success_text(
                amount_rub=int(getattr(refreshed_record, "amount", 0) or amount_rub),
                balance_rub=balance["balance_rub"],
            ),
            parse_mode="HTML",
            reply_markup=balance_topup_amounts_keyboard(),
        )
        await callback.answer("Баланс пополнен", show_alert=True)
        return

    metadata = {}
    if refreshed_record.metadata_json:
        try:
            metadata = json.loads(refreshed_record.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    checkout_url = str(metadata.get("checkout_url") or "").strip()

    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await callback.message.edit_text(
            (
                "⌛ <b>Счёт на пополнение больше не активен</b>\n\n"
                f"Статус провайдера: <b>{provider_status or refreshed_record.payment_status}</b>\n\n"
                "Создай новый счёт на нужную сумму."
            ),
            parse_mode="HTML",
            reply_markup=balance_topup_amounts_keyboard(),
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return

    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напиши в поддержку.", show_alert=True)
        return

    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуй позже.", show_alert=True)
        return

    reply_markup = (
        balance_external_payment_keyboard(checkout_url, amount_rub, refreshed_record.id)
        if checkout_url
        else balance_topup_methods_keyboard(amount_rub)
    )
    await callback.message.edit_text(
        balance_topup_payment_text(
            amount_rub=amount_rub,
            method_label=refreshed_record.payment_method,
            checkout_label="страницу оплаты",
        ),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    await callback.answer(
        _external_payment_status_notice(refreshed_record.payment_status, provider_status),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("tariff:external:check:"))
async def external_payment_check_callback(callback: CallbackQuery, bot: Bot) -> None:
    _, _, _, record_id_str, tariff_code = callback.data.split(":")
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    try:
        record_id = int(record_id_str)
    except ValueError:
        await callback.answer("Счёт не найден", show_alert=True)
        return
    record = await get_payment_record_by_id(record_id)
    if record is None:
        await callback.answer("Счёт не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or record.user_id != user.id:
        await callback.answer("Этот счёт тебе не принадлежит", show_alert=True)
        return

    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=bot)
    except PlategaError as exc:
        logger.warning("Failed to sync Platega payment #%s: %s", record.id, exc)
        await callback.answer("Не удалось проверить оплату", show_alert=True)
        return

    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    if refreshed_record.payment_status == "confirmed":
        expires_at = await get_access_expires_at(user.id)
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        breakdown = _payment_breakdown_from_record(refreshed_record, tariff.rub_price)
        await callback.message.edit_text(
            payment_success_text(
                tariff.title,
                expires_text,
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=refreshed_record.balance_applied_amount or 0,
                paid_amount=breakdown["paid_amount"],
            ),
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer("Оплата подтверждена", show_alert=True)
        return

    metadata = {}
    if refreshed_record.metadata_json:
        try:
            metadata = json.loads(refreshed_record.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await callback.message.edit_text(
            manual_payment_inactive_text(
                tariff_title=tariff.title,
                request_id=refreshed_record.id,
                status=refreshed_record.payment_status,
                reason=f"Статус провайдера: {provider_status}",
            ),
            parse_mode="HTML",
            reply_markup=tariff_methods_keyboard(tariff.code),
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return

    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напиши в поддержку.", show_alert=True)
        return

    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуй позже.", show_alert=True)
        return

    reply_markup = (
        external_payment_keyboard(checkout_url, tariff.code, refreshed_record.id)
        if checkout_url
        else tariff_methods_keyboard(tariff.code)
    )
    await callback.message.edit_text(
        platega_payment_text(
            tariff_title=tariff.title,
            amount_rub=refreshed_record.amount,
            method_label=refreshed_record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=refreshed_record.list_price_amount or tariff.rub_price,
            balance_reserved_amount=refreshed_record.balance_reserved_amount or 0,
        ),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    await callback.answer(
        _external_payment_status_notice(refreshed_record.payment_status, provider_status),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("device-slot:external:check:"))
async def device_slot_external_payment_check_callback(callback: CallbackQuery, bot: Bot) -> None:
    record_id = int(callback.data.split(":")[3])
    record = await get_payment_record_by_id(record_id)
    if record is None:
        await callback.answer("Счёт не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None or record.user_id != user.id:
        await callback.answer("Этот счёт тебе не принадлежит", show_alert=True)
        return

    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=bot)
    except PlategaError as exc:
        logger.warning("Failed to sync device-slot payment #%s: %s", record.id, exc)
        await callback.answer("Не удалось проверить оплату", show_alert=True)
        return

    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    payment_result = sync_result.get("payment_result")
    if refreshed_record.payment_status == "confirmed":
        text = (
            _payment_result_text(payment_result, fallback_title=_device_slot_title())
            if payment_result is not None
            else await _device_slot_success_text_from_record(user, refreshed_record)
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Оплата подтверждена", show_alert=True)
        return

    metadata = _load_payment_metadata(refreshed_record.metadata_json)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await callback.message.edit_text(
            manual_payment_inactive_text(
                tariff_title=_device_slot_title(),
                request_id=refreshed_record.id,
                status=refreshed_record.payment_status,
                reason=f"Статус провайдера: {provider_status}",
            ),
            parse_mode="HTML",
            reply_markup=device_slot_methods_keyboard(),
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return

    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напиши в поддержку.", show_alert=True)
        return

    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуй позже.", show_alert=True)
        return

    reply_markup = (
        device_slot_external_payment_keyboard(checkout_url, refreshed_record.id)
        if checkout_url
        else device_slot_methods_keyboard()
    )
    await callback.message.edit_text(
        platega_payment_text(
            tariff_title=_device_slot_title(),
            amount_rub=refreshed_record.amount,
            method_label=refreshed_record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=refreshed_record.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=refreshed_record.balance_reserved_amount or 0,
        ),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    await callback.answer(
        _external_payment_status_notice(refreshed_record.payment_status, provider_status),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("tariff:crypto:check:"))
async def crypto_check_callback(callback: CallbackQuery, bot: Bot) -> None:
    _, _, _, tariff_code, invoice_id = callback.data.split(":")
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    crypto_pay = CryptoPayClient()
    if not crypto_pay.configured:
        await callback.answer("Crypto Bot пока не настроен", show_alert=True)
        return

    record = await get_payment_record_by_external_id("crypto_bot", invoice_id)
    if record is not None and record.payment_status == "confirmed":
        expires_at = await get_access_expires_at(record.user_id) if record.user_id is not None else None
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        breakdown = _payment_breakdown_from_record(record, tariff.rub_price)
        await callback.message.answer(
            payment_success_text(
                tariff.title,
                expires_text,
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=record.balance_applied_amount or 0,
                paid_amount=breakdown["paid_amount"],
            ),
            parse_mode="HTML",
        )
        await callback.answer("Оплата уже подтверждена и обработана", show_alert=True)
        return

    try:
        invoice = await crypto_pay.get_invoice(invoice_id)
    except CryptoPayError as exc:
        logger.warning("Failed to fetch Crypto Pay invoice status: %s", exc)
        await callback.answer("Не удалось проверить статус оплаты", show_alert=True)
        return

    if invoice is None:
        await callback.answer("Счёт не найден", show_alert=True)
        return

    if invoice.get("status") != "paid":
        await callback.answer("Оплата ещё не подтверждена", show_alert=True)
        return

    payload = CryptoPayClient.parse_invoice_payload(invoice.get("payload"))
    if record is None:
        record = await create_external_payment_record(
            user_id=payload.get("user_id"),
            external_payment_id=str(invoice.get("invoice_id")),
            tariff_code=payload.get("tariff_code", tariff.code),
            payment_method="crypto_bot",
            amount=tariff.rub_price,
            list_price_amount=tariff.rub_price,
            balance_reserved_amount=0,
            balance_applied_amount=0,
            currency=invoice.get("fiat", "RUB"),
            duration_days=tariff.duration_days,
            note=json.dumps(invoice, ensure_ascii=False),
        )

    record, just_confirmed = await confirm_external_payment_record(
        payment_method="crypto_bot",
        external_payment_id=str(invoice.get("invoice_id")),
        note=json.dumps(invoice, ensure_ascii=False),
    )
    if record is None:
        await callback.answer("Не удалось записать оплату", show_alert=True)
        return
    if not just_confirmed and payment_record_effect_applied(record):
        await callback.answer("Оплата уже обработана", show_alert=True)
        return

    await sync_income_entry_for_payment_record(record.id)

    payment_result = await finalize_subscription_payment(
        user_id=record.user_id,
        tariff_code=record.tariff_code or tariff.code,
        payment_id=record.external_payment_id or invoice_id,
        payment_source="crypto_bot",
        payment_record_id=record.id,
    )
    if payment_result is None:
        await callback.answer("Оплата прошла, но подписку не удалось активировать", show_alert=True)
        return

    await callback.message.answer(
        payment_success_text(
            payment_result["tariff"].title,
            payment_result["expires_text"],
            list_price_amount=payment_result["list_price_amount"],
            balance_applied_amount=payment_result["balance_applied_amount"],
            paid_amount=payment_result["paid_amount"],
        ),
        parse_mode="HTML",
    )
    if payment_result["sync_failed"]:
        await callback.message.answer(PAYMENT_SYNC_WARNING_TEXT)
    await notify_referral_bonus(bot, payment_record_id=record.id)
    await callback.answer("Оплата подтверждена", show_alert=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, bot: Bot) -> None:
    successful_payment = message.successful_payment
    if successful_payment is None:
        return

    user = await get_user_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("Пользователь не найден. Нажми /start")
        return

    try:
        payload = json.loads(successful_payment.invoice_payload)
    except json.JSONDecodeError:
        logger.exception("Failed to decode invoice payload for telegram_id=%s", message.from_user.id)
        await message.answer("Платёж подтверждён, но данные тарифа повреждены. Напиши в поддержку.")
        return

    tariff = get_tariff(payload.get("tariff_code", ""))
    if tariff is None:
        await message.answer("Не удалось определить тариф по платёжным данным.")
        return

    charge_id = successful_payment.telegram_payment_charge_id
    record = await create_external_payment_record(
        user_id=user.id,
        external_payment_id=charge_id,
        tariff_code=tariff.code,
        payment_method="telegram_stars",
        amount=tariff.rub_price,
        list_price_amount=tariff.rub_price,
        balance_reserved_amount=0,
        balance_applied_amount=0,
        currency="RUB",
        duration_days=tariff.duration_days,
        note=json.dumps(
            {
                "currency": successful_payment.currency,
                "total_amount": successful_payment.total_amount,
                "invoice_payload": successful_payment.invoice_payload,
            },
            ensure_ascii=False,
        ),
    )
    record, just_confirmed = await confirm_external_payment_record(
        payment_method="telegram_stars",
        external_payment_id=charge_id,
        note=json.dumps(
            {
                "currency": successful_payment.currency,
                "total_amount": successful_payment.total_amount,
                "telegram_payment_charge_id": charge_id,
                "invoice_payload": successful_payment.invoice_payload,
            },
            ensure_ascii=False,
        ),
    )
    if record is not None and just_confirmed:
        await sync_income_entry_for_payment_record(record.id)

    if not just_confirmed and record is not None and payment_record_effect_applied(record):
        expires_at = await get_access_expires_at(user.id)
        if expires_at is None:
            await message.answer("Платёж уже подтверждён. Если доступ не появился, напиши в поддержку.")
            return

        breakdown = _payment_breakdown_from_record(record, tariff.rub_price) if record is not None else {
            "list_price_amount": tariff.rub_price,
            "balance_amount": 0,
            "paid_amount": tariff.rub_price,
        }
        await message.answer(
            payment_success_text(
                tariff.title,
                expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=breakdown["balance_amount"],
                paid_amount=breakdown["paid_amount"],
            ),
            parse_mode="HTML",
        )
        return

    if record is not None and not just_confirmed:
        await sync_income_entry_for_payment_record(record.id)

    payment_result = await finalize_subscription_payment(
        user_id=user.id,
        tariff_code=tariff.code,
        payment_id=charge_id,
        payment_source="telegram_stars",
        payment_record_id=record.id if record is not None else None,
    )
    if payment_result is None:
        await message.answer("Не удалось активировать подписку. Напиши в поддержку.")
        return

    await message.answer(
        payment_success_text(
            payment_result["tariff"].title,
            payment_result["expires_text"],
            list_price_amount=payment_result["list_price_amount"],
            balance_applied_amount=payment_result["balance_applied_amount"],
            paid_amount=payment_result["paid_amount"],
        ),
        parse_mode="HTML",
    )

    bonus_applied = await notify_referral_bonus(bot, payment_record_id=record.id if record is not None else None)
    if bonus_applied:
        await message.answer("🎁 Бонус пригласившему пользователю уже начислен автоматически.", parse_mode="HTML")

    if payment_result["sync_failed"]:
        await message.answer(PAYMENT_SYNC_WARNING_TEXT)
