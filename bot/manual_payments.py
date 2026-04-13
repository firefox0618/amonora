import json
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import config
from bot.db import (
    get_payment_record_by_id,
    get_user_by_id,
    review_manual_payment_record,
)
from bot.payment_flow import finalize_payment_record_product, notify_referral_bonus
from bot.user_notifications import send_user_message, send_user_message_and_refresh_home
from bot.utils.tariffs import get_tariff
from bot.utils.texts import (
    PAYMENT_SYNC_WARNING_TEXT,
    device_slot_payment_success_text,
    manual_payment_method_label,
    manual_payment_rejected_text,
    payment_success_text,
)
from bot.utils.device_slots import DEVICE_SLOT_PRODUCT_TYPE, payment_product_type
from control_bot.access import CONTROL_ROLE_OPERATOR, control_admins, control_role_allows
from control_bot.dispatcher import create_control_event
from dashboard.finance import sync_income_entry_for_payment_record


logger = logging.getLogger(__name__)

PAYMENT_STATUS_LABELS = {
    "awaiting_user_payment": "🧾 Ожидает оплату",
    "awaiting_admin_review": "🕓 Ожидает проверку",
    "confirmed": "✅ Подтверждён",
    "rejected": "❌ Отклонён",
    "expired": "⌛ Истёк",
    "disputed": "⚠️ Спорный",
    "error": "🚨 Ошибка",
    "cancelled": "🚫 Отменён",
    "pending": "🕓 В обработке",
}


def _manual_payment_review_chat_ids() -> list[int]:
    review_chat_ids: list[int] = []
    for admin in control_admins():
        if control_role_allows(admin.role, CONTROL_ROLE_OPERATOR):
            review_chat_ids.append(int(admin.telegram_id))
    return review_chat_ids


def payment_metadata(record) -> dict:
    if not getattr(record, "metadata_json", None):
        return {}
    try:
        return json.loads(record.metadata_json)
    except json.JSONDecodeError:
        return {}


def payment_status_label(status: str) -> str:
    return PAYMENT_STATUS_LABELS.get(status, status)


def build_manual_payment_admin_text(record, user=None) -> str:
    metadata = payment_metadata(record)
    username = "—"
    telegram_id = "—"
    if user is not None:
        username = f"@{user.username}" if user.username else "без username"
        telegram_id = str(user.telegram_id)

    tariff = get_tariff(record.tariff_code or "")
    tariff_title = metadata.get("tariff_title") or (tariff.title if tariff else record.tariff_code or "Тариф")
    reference = record.reference or metadata.get("reference") or "—"
    note = record.note or metadata.get("user_comment") or "—"
    list_price_amount = int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0)
    balance_reserved_amount = int(getattr(record, "balance_reserved_amount", 0) or 0)
    balance_applied_amount = int(getattr(record, "balance_applied_amount", 0) or 0)
    paid_amount = int(getattr(record, "amount", 0) or 0)

    return (
        "💳 <b>Ручная заявка на оплату</b>\n\n"
        f"🆔 Заявка: <code>{record.id}</code>\n"
        f"👤 Пользователь: <code>{record.user_id or '—'}</code>\n"
        f"🔗 Telegram ID: <code>{telegram_id}</code>\n"
        f"👤 Username: {username}\n"
        f"📦 Тариф: <b>{tariff_title}</b>\n"
        f"💸 Метод: <b>{manual_payment_method_label(record.payment_method)}</b>\n"
        f"💰 Полная стоимость: <b>{list_price_amount} {record.currency}</b>\n"
        f"💳 К оплате деньгами: <b>{paid_amount} {record.currency}</b>\n"
        f"💰 Баланс: <b>{balance_reserved_amount or balance_applied_amount} {record.currency}</b>\n"
        f"⏳ Дней доступа: <b>{record.duration_days}</b>\n"
        f"📌 Статус: <b>{payment_status_label(record.payment_status)}</b>\n"
        f"🧾 Референс: <code>{reference}</code>\n"
        f"📝 Комментарий: <blockquote>{note}</blockquote>"
    )


def manual_payment_admin_keyboard(record_id: int, allow_review: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if allow_review:
        rows.append(
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"payment:confirm:{record_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"payment:reject:{record_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"payment:open:{record_id}")])
    rows.append([InlineKeyboardButton(text="📂 Очередь оплат", callback_data="payment:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _manual_payment_event_message(record, user=None) -> str:
    username = f"@{user.username}" if user and getattr(user, "username", None) else f"TG {getattr(user, 'telegram_id', '—')}"
    paid_amount = int(getattr(record, "amount", 0) or 0)
    return (
        f"{username} — <b>{paid_amount} {record.currency}</b> "
        f"({manual_payment_method_label(record.payment_method)})\n"
        f"Заявка <code>#{record.id}</code> ожидает проверки"
    )


async def notify_support_admins_about_manual_payment(record_id: int) -> None:
    record = await get_payment_record_by_id(record_id)
    if record is None:
        return
    user = await get_user_by_id(record.user_id) if record.user_id is not None else None
    try:
        requester_label = (
            f"@{user.username}"
            if user and getattr(user, "username", None)
            else f"TG {getattr(user, 'telegram_id', '—')}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"control:payment:confirm:{record.id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"control:payment:reject:{record.id}"),
                ],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"control:payment:open:{record.id}")],
            ]
        )
        short_text = (
            f"💳 <b>Оплата</b>: {requester_label} "
            f"— <b>{int(getattr(record, 'amount', 0) or 0)} {record.currency}</b> "
            f"({manual_payment_method_label(record.payment_method)}) ожидает проверки"
        )
        await create_control_event(
            category="payments",
            severity="INFO",
            event_type="manual_payment_submitted",
            title="Новая заявка на оплату",
            message=_manual_payment_event_message(record, user),
            entity_type="payment_record",
            entity_id=str(record.id),
            payload={
                "record_id": record.id,
                "user_id": record.user_id,
                "telegram_id": getattr(user, "telegram_id", None),
                "payment_method": record.payment_method,
                "payment_status": record.payment_status,
            },
            dedupe_key=f"manual-payment:{record.id}:submitted",
            reply_markup=keyboard,
            delivery_text=short_text,
            chat_ids=_manual_payment_review_chat_ids(),
        )
    except Exception:
        logger.exception("Failed to notify control bot about manual payment %s", record_id)


async def _notify_user_payment_result(record, *, approved: bool, reason: str | None = None, payment_result: dict | None = None) -> None:
    if record.user_id is None:
        return
    user = await get_user_by_id(record.user_id)
    if user is None:
        return

    metadata = payment_metadata(record)
    tariff = get_tariff(record.tariff_code or "")
    tariff_title = metadata.get("tariff_title") or (tariff.title if tariff else (record.tariff_code or "Тариф"))
    product_type = payment_product_type(metadata, tariff_code=record.tariff_code)

    if approved:
        if payment_result is not None:
            if product_type == DEVICE_SLOT_PRODUCT_TYPE:
                await send_user_message_and_refresh_home(
                    user.telegram_id,
                    device_slot_payment_success_text(
                        title=str(payment_result.get("display_title") or tariff_title),
                        expires_at=str(payment_result.get("expires_text") or "—"),
                        device_limit=int(payment_result.get("device_limit") or 3),
                        slots_count=int(payment_result.get("slots_count") or 1),
                        list_price_amount=payment_result.get("list_price_amount"),
                        balance_applied_amount=int(payment_result.get("balance_applied_amount") or 0),
                        paid_amount=payment_result.get("paid_amount"),
                    ),
                )
            else:
                await send_user_message_and_refresh_home(
                    user.telegram_id,
                    payment_success_text(
                        tariff_title,
                        payment_result["expires_text"],
                        list_price_amount=payment_result["list_price_amount"],
                        balance_applied_amount=payment_result["balance_applied_amount"],
                        paid_amount=payment_result["paid_amount"],
                    ),
                )
            if payment_result.get("sync_failed"):
                await send_user_message(user.telegram_id, PAYMENT_SYNC_WARNING_TEXT)
            return

        await send_user_message_and_refresh_home(
            user.telegram_id,
            (
                f"✅ <b>{tariff_title}</b>\n\n"
                "Заявка подтверждена, но доступ ещё не активировался автоматически.\n"
                "Мы уже проверяем это со своей стороны."
            ),
        )
        return

    await send_user_message_and_refresh_home(
        user.telegram_id,
        manual_payment_rejected_text(
            tariff_title=tariff_title,
            request_id=record.id,
            reason=reason,
        ),
    )


async def confirm_manual_payment(record_id: int, reviewer_actor_id: str, reviewer_actor_name: str) -> dict | None:
    record, changed = await review_manual_payment_record(
        record_id,
        reviewer_actor_id=reviewer_actor_id,
        reviewer_actor_name=reviewer_actor_name,
        action="confirm",
    )
    if record is None:
        return None

    payment_result = None
    if changed and record.user_id is not None and record.tariff_code:
        payment_result = await finalize_payment_record_product(
            user_id=record.user_id,
            payment_source=record.payment_method,
            payment_record_id=record.id,
            tariff_code=record.tariff_code,
            payment_id=record.external_payment_id or f"manual_{record.id}",
        )
        if payment_result is not None and payment_result.get("product_type") != DEVICE_SLOT_PRODUCT_TYPE:
            bot = Bot(config.bot_token)
            try:
                await notify_referral_bonus(bot, payment_record_id=record.id)
            finally:
                await bot.session.close()

    if changed:
        await sync_income_entry_for_payment_record(record.id)
        await _notify_user_payment_result(record, approved=True, payment_result=payment_result)
        user = await get_user_by_id(record.user_id) if record.user_id is not None else None
        await create_control_event(
            category="payments",
            severity="INFO",
            event_type="manual_payment_confirmed",
            title="Ручной платёж подтверждён",
            message=(
                f"{_manual_payment_event_message(record, user)}\n"
                f"Проверил: <b>{reviewer_actor_name}</b>"
            ),
            entity_type="payment_record",
            entity_id=str(record.id),
            payload={
                "record_id": record.id,
                "user_id": record.user_id,
                "reviewer_actor_id": reviewer_actor_id,
                "reviewer_actor_name": reviewer_actor_name,
            },
            dedupe_key=f"manual-payment:{record.id}:confirmed",
        )
    return {
        "record": record,
        "changed": changed,
        "payment_result": payment_result,
    }


async def reject_manual_payment(
    record_id: int,
    reviewer_actor_id: str,
    reviewer_actor_name: str,
    reason: str | None = None,
) -> dict | None:
    record, changed = await review_manual_payment_record(
        record_id,
        reviewer_actor_id=reviewer_actor_id,
        reviewer_actor_name=reviewer_actor_name,
        action="reject",
        reason=reason,
    )
    if record is None:
        return None
    if changed:
        await _notify_user_payment_result(record, approved=False, reason=record.rejection_reason)
        user = await get_user_by_id(record.user_id) if record.user_id is not None else None
        await create_control_event(
            category="payments",
            severity="WARNING",
            event_type="manual_payment_rejected",
            title="Ручной платёж отклонён",
            message=(
                f"{_manual_payment_event_message(record, user)}\n"
                f"Проверил: <b>{reviewer_actor_name}</b>\n"
                f"Причина: <b>{record.rejection_reason or 'Отклонено администратором'}</b>"
            ),
            entity_type="payment_record",
            entity_id=str(record.id),
            payload={
                "record_id": record.id,
                "user_id": record.user_id,
                "reviewer_actor_id": reviewer_actor_id,
                "reviewer_actor_name": reviewer_actor_name,
                "reason": record.rejection_reason or "",
            },
            dedupe_key=f"manual-payment:{record.id}:rejected",
        )
    return {
        "record": record,
        "changed": changed,
    }
