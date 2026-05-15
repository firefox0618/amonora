from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    CopyTextButton,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.analytics import emit_bot_start_event, safe_upsert_user_attribution
from backend.core.promo_codes import (
    GIFT_SUBSCRIPTION_PRODUCT_TYPE,
    PROMO_KIND_DISCOUNT_PERCENT,
    apply_discount_percent,
    create_gift_promo_code_for_payment,
    get_promo_code_by_payment_record_id,
    get_user_pending_discount,
    redeem_promo_code_for_user,
)
from bot.config import config
from bot.db import (
    activate_trial,
    bind_referrer_by_token,
    build_balance_breakdown_for_price,
    cancel_manual_payment_record,
    clear_public_subscription_device_slot_binding,
    create_balance_aware_manual_payment_record,
    create_balance_only_custom_payment_record,
    create_balance_only_payment_record,
    get_active_device_slot_counts_for_users,
    get_open_payment_intent_for_user,
    get_payment_record_by_id,
    get_user_balance_summary,
    get_user_referral_stats,
    get_or_create_user,
    get_user_by_telegram_id,
    get_user_vpn_clients,
    delete_vpn_client_and_return,
    get_vpn_client_by_id,
    mark_manual_payment_record_submitted,
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
from bot.ui.screens.user import _bonus_stats_text, _bonus_text
from bot.public_subscription import (
    _normalize_device_type,
    _normalize_public_os_version,
    build_public_subscription_feed_url,
    build_public_subscription_happ_wrapper_url,
    build_public_subscription_page_url,
    extract_public_subscription_token_from_url,
    get_or_create_public_subscription_page_url_for_user,
    get_public_subscription_bound_devices_for_user,
)
from bot.keyboards.referrals import referral_share_url
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_access_status_from_user,
    get_device_limit_for_user,
    has_active_access_from_user,
    has_active_subscription_from_user,
    utcnow,
)
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
from bot.utils.qr import generate_qr_image
from bot.utils.subscription_accounting import (
    ADMIN_ACCESS_SOURCES,
    MANUAL_ACCESS_SOURCES,
    MANUAL_EXTENSION_SOURCES,
    humanize_extension_duration,
    load_subscription_payment_snapshot,
    manual_extension_days,
)
from bot.utils.subscription import is_user_subscribed
from bot.utils.texts import (
    CHANNEL_URL,
    PAYMENT_SYNC_WARNING_TEXT,
    PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
    PRIVACY_URL,
    REFUNDS_URL,
    SUPPORT_URL,
    TERMS_URL,
    OS_LABELS,
    PANEL_CONNECTION_ERROR_TEXT,
    PANEL_OPERATION_ERROR_TEXT,
    USER_NOT_FOUND_TEXT,
    balance_topup_payment_text,
    balance_topup_success_text,
    delete_device_not_found_text,
    device_slot_payment_success_text,
    manual_payment_details_text,
    manual_payment_inactive_text,
    manual_payment_rejected_text,
    manual_payment_waiting_review_text,
    payment_success_text,
    platega_payment_text,
    referral_registered_text,
)
from bot.utils.tariffs import get_tariff
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import get_vless_provisioner
from bot.user_notifications import send_user_message
from control_bot.channel_content import parse_channel_post_start_token, register_channel_post_touch
from dashboard.finance import sync_income_entry_for_payment_record
from dashboard.models import PaymentRecord
from test_bot.access import is_test_bot_allowed
from test_bot.device_binding import TEST_SWITCH_DEVICE_CHOICES, activate_test_profile_device, get_test_profile_runtime
from test_bot.profiles import get_test_profiles


router = Router()
logger = logging.getLogger(__name__)
PROMO_INPUT_WAITERS: set[int] = set()


class AwaitingPromoInputFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return int(message.from_user.id) in PROMO_INPUT_WAITERS

DENIED_TEXT = "Доступ ограничен. Этот экран доступен только админам для legacy тестовых конфигов."

V2_SHOW_AGREEMENT_CALLBACK = "testv2:terms:show"
V2_ACCEPT_TERMS_CALLBACK = "testv2:terms:accept"
V2_CHECK_SUBSCRIPTION_CALLBACK = "testv2:trial:check"
V2_TRIAL_READY_CALLBACK = "testv2:trial:ready"
V2_GUIDES_CALLBACK = "testv2:guides"
V2_INFO_GUIDES_CALLBACK = "testv2:info:guides"
V2_MENU_CALLBACK = "testv2:menu"
V2_MY_SUBSCRIPTION_CALLBACK = "testv2:subscription"
V2_RENEW_CALLBACK = "testv2:renew"
V2_SUPPORT_CALLBACK = "testv2:support"
V2_BONUS_CALLBACK = "testv2:bonus"
V2_BONUS_STATS_CALLBACK = "testv2:bonus:stats"
V2_BONUS_PROMO_CALLBACK = "testv2:bonus:promo"
V2_BONUS_GIFT_CALLBACK = "testv2:bonus:gift"
V2_BONUS_GIFT_TARIFFS_CALLBACK = "testv2:bonus:gift:tariffs"
V2_BONUS_GIFT_TARIFF_PREFIX = "testv2:bonus:gift:tariff:"
V2_BONUS_GIFT_PAY_PREFIX = "testv2:bonus:gift:pay:"
V2_BONUS_GIFT_METHOD_PREFIX = "testv2:bonus:gift:method:"
V2_BONUS_GIFT_MANUAL_PAID_PREFIX = "testv2:bonus:gift:manual:paid:"
V2_BONUS_GIFT_MANUAL_STATUS_PREFIX = "testv2:bonus:gift:manual:status:"
V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX = "testv2:bonus:gift:manual:cancel:"
V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX = "testv2:bonus:gift:external:check:"
V2_INFO_CALLBACK = "testv2:info"
V2_INFO_DOCS_CALLBACK = "testv2:info:docs"
V2_MY_DEVICES_CALLBACK = "testv2:mydevices"
V2_DEVICE_SLOT_CALLBACK = "testv2:mydevices:slot"
V2_DEVICE_DELETE_PREFIX = "testv2:mydevices:delete:"
V2_BALANCE_TOPUP_AMOUNT_PREFIX = "testv2:balance:amount:"
V2_KEY_MENU_CALLBACK = "testv2:subscription:keymenu"
V2_COPY_KEY_CALLBACK = "testv2:subscription:key"
V2_BACK_TO_SUBSCRIPTION_CALLBACK = "testv2:subscription:back"
V2_BACK_TO_RENEW_CALLBACK = "testv2:renew:back"
V2_DEVICES_CALLBACK = "testv2:devices"
V2_BACK_TO_TRIAL_CALLBACK = "testv2:back:trial"
V2_BACK_TO_MENU_CALLBACK = "testv2:back:menu"
V2_GUIDE_PREFIX = "testv2:guide:"
V2_RENEW_METHOD_PREFIX = "testv2:pay:renew:"
V2_RENEW_MANUAL_PAID_PREFIX = "testv2:pay:renew:manual:paid:"
V2_RENEW_MANUAL_STATUS_PREFIX = "testv2:pay:renew:manual:status:"
V2_RENEW_MANUAL_CANCEL_PREFIX = "testv2:pay:renew:manual:cancel:"
V2_RENEW_EXTERNAL_CHECK_PREFIX = "testv2:pay:renew:external:check:"
V2_BALANCE_METHOD_PREFIX = "testv2:pay:balance:"
V2_BALANCE_MANUAL_PAID_PREFIX = "testv2:pay:balance:manual:paid:"
V2_BALANCE_MANUAL_STATUS_PREFIX = "testv2:pay:balance:manual:status:"
V2_BALANCE_MANUAL_CANCEL_PREFIX = "testv2:pay:balance:manual:cancel:"
V2_BALANCE_EXTERNAL_CHECK_PREFIX = "testv2:pay:balance:external:check:"
V2_DEVICE_SLOT_METHOD_PREFIX = "testv2:pay:slot:"
V2_DEVICE_SLOT_MANUAL_PAID_PREFIX = "testv2:pay:slot:manual:paid:"
V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX = "testv2:pay:slot:manual:status:"
V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX = "testv2:pay:slot:manual:cancel:"
V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX = "testv2:pay:slot:external:check:"

SCREEN_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "v2"
SCREEN_IMAGE_FILENAMES = {
    "agreement": "sakura_agreement.jpg",
    "trial": "sakura_trial.jpg",
    "first_connection": "sakura_emblem.jpg",
    "instruction": "sakura_instruction.jpg",
    "finish": "sakura_finish.jpg",
    "main_menu": "sakura_main_menu.jpg",
    "my_subscription": "sakura_my_subscription.jpg",
    "renew": "sakura_my_subscription.jpg",
    "support": "sakura_support.jpg",
    "info": "sakura_info.png",
    "documents": "sakura_info.png",
    "bonus": "sakura_bonus.jpg",
    "bonus_stats": "sakura_bonus.jpg",
    "promo": "sakura_bonus.jpg",
    "gift": "sakura_bonus.jpg",
    "my_devices": "sakura_my_subscription.jpg",
    "key": "sakura_my_subscription.jpg",
    "balance_topup": "sakura_my_subscription.jpg",
    "device_slot": "sakura_my_subscription.jpg",
}
AGREEMENT_TEXT = """Перед использованием нашего сервиса, просим Вас принять пользовательское соглашение.

Для активации пробного периода необходимо принять следующее условия:

<b>Пользовательское соглашение</b>

Нажимая <b>«Принимаю»</b>, Вы подтверждаете, что ознакомились и согласны с условиями."""

TRIAL_INTRO_TEXT = """🎁 Вам доступен бесплатный пробный период на 3 дня!

Что вы получите:
• 🌍 Полный доступ ко всем серверам
• 🚀 Безлимитный трафик
• 📱 Поддержку всех устройств
• 🔒 Максимальную защиту данных

💳 Без скрытых платежей и автосписаний — всё честно

👇 Чтобы активировать пробный доступ, подпишитесь на канал"""

TRIAL_READY_TEXT = """✅ <b>Пробный доступ активирован!</b>

Готово — теперь можно получить ключ и подключиться.

Что дальше:
• нажмите <b>«Ключ»</b>, чтобы открыть ссылку подключения
• обязательно установите приложение <b>Happ</b>
• если приложения <b>Happ</b> ещё нет, перейдите в <b>Инструкцию</b>, выберите свою ОС и установите его
• после установки вернитесь к кнопке <b>«Ключ»</b> и продолжите подключение

Если что-то не получится, напишите в <b>Поддержку</b> — поможем довести подключение до конца."""

TRIAL_ALREADY_USED_TEXT = """⏳ <b>Пробный период уже был использован</b>

Для этого аккаунта бесплатный пробный доступ больше недоступен.

Что можно сделать дальше:
• нажмите <b>«Купить подписку»</b>, чтобы выбрать тариф
• после оплаты откройте <b>Главное меню</b> и продолжите подключение
• если нужна помощь, напишите в <b>Поддержку</b>"""

MAIN_MENU_TEXT = """<b>Главное меню Amonora</b>

Здесь вы можете управлять подключением, подпиской и бонусами.

Что можно сделать дальше:
• открыть «Моя подписка»
• продлить доступ
• перейти в поддержку или в раздел с инструкциями"""

DEVICE_CHOICE_TEXT = "Выберите устройство для подключения:"

SUBSCRIPTION_ALERT_TEXT = "Вы не подписаны на канал.\nПожалуйста, подпишитесь и попробуйте снова."

CONNECT_PLACEHOLDER_TEMPLATE = """<b>Подключение для {device_title}</b>

Для этого устройства пока используйте сценарий через <b>Ключ</b> в разделе <b>Моя подписка</b>.

Если возникнут сложности, откройте <b>Инструкцию</b> или напишите в <b>Поддержку</b>."""

SUPPORT_SCREEN_TEXT = """🛟 <b>Поддержка Amonora</b>

Что-то не работает или есть вопрос? Мы рядом

Чтобы ускорить обработку, отправьте, пожалуйста:

• Ваш <b>ID</b> (раздел «Моя подписка»)
• Краткое <b>описание проблемы</b>
• <b>Скриншот</b> (желательно)
• <b>Чек об оплате</b> (если вопрос связан с оплатой)

Чем больше информации — тем быстрее мы сможем помочь 🙌"""

INFO_SCREEN_TEXT = """📚 <b>Информация</b>

Выберите нужный раздел 👇

📘 <b>Инструкция</b>
• подключение устройства
• установка приложения
• импорт ключа
• быстрый запуск

📜 <b>Документы</b>
• пользовательское соглашение
• политика конфиденциальности
• политика возврата"""

INFO_DOCUMENTS_TEXT = """📜 <b>Документы</b>

Здесь собрана вся юридическая информация о сервисе 👇

• Пользовательское соглашение
• Политика конфиденциальности
• Политика возврата

Рекомендуем ознакомиться перед использованием сервиса"""

BONUS_PROMO_TEXT = """🎫 <b>Есть промокод или подарок?</b>

Отправьте следующим сообщением промокод или код подарочной подписки 👇

Если код верный, бот сразу применит его к вашему аккаунту."""

BONUS_GIFT_TEXT = """🎁 <b>Подарить подписку другу</b>

Как это работает 👇

1️⃣ <b>Выбираете подписку</b>
• выберите тариф

2️⃣ <b>Оплачиваете</b>

3️⃣ <b>Отправляете код другу</b>
• передайте промокод
• друг вводит его в разделе
«🎁 Бонусная система» → «🎫 Ввести код»

4️⃣ <b>Подписка активируется</b>
• доступ включается автоматически
• срок добавляется к текущей подписке или создаётся новая

✨ Отличный способ порадовать друга полезным подарком"""

DEVICE_SLOT_PLACEHOLDER_TEXT = """📱 <b>Дополнительный слот</b>

Покупку дополнительного слота подключим следующим шагом.

Позже здесь можно будет оформить ещё одно устройство до конца текущей подписки."""

MY_DEVICES_EMPTY_TEXT = """<b>Мои устройства</b>

У вас пока нет созданных устройств.

Откройте раздел <b>Ключ</b>, чтобы добавить подписку и подключить первое устройство."""

PAYMENT_METHODS_TEMPLATE = """<b>{title}</b>

Выбери удобный способ оплаты:

• 💳 СБП
• 💳 СБП (ручная заявка)
• 💎 Криптовалюта"""

MANUAL_PAYMENT_METHODS = {"sbp_manual", "crypto_manual"}
OPEN_PAYMENT_STATUSES = ("awaiting_user_payment", "awaiting_admin_review", "pending")
BALANCE_TOPUP_PRODUCT_TYPE = "balance_topup"
BALANCE_TOPUP_TARIFF_CODE = "balance_topup"


def _callback_startswith(value: str | None, prefix: str) -> bool:
    return str(value or "").startswith(prefix)


def _callback_is_payment_method(
    value: str | None,
    *,
    method_prefix: str,
    excluded_prefixes: tuple[str, ...],
) -> bool:
    payload = str(value or "")
    if not payload.startswith(method_prefix):
        return False
    return not any(payload.startswith(excluded) for excluded in excluded_prefixes)


def _payment_metadata(record) -> dict:
    raw = getattr(record, "metadata_json", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _payment_breakdown_from_record(record, fallback_price: int) -> dict[str, int]:
    list_price_amount = int(getattr(record, "list_price_amount", 0) or fallback_price)
    balance_amount = int(getattr(record, "balance_applied_amount", 0) or getattr(record, "balance_reserved_amount", 0) or 0)
    paid_amount = int(getattr(record, "amount", 0) or 0)
    return {
        "list_price_amount": list_price_amount,
        "balance_amount": balance_amount,
        "paid_amount": paid_amount,
    }


def _device_slot_title() -> str:
    return device_slot_display_title(1)


def _prefix_payment_text(text: str, intro_note: str | None) -> str:
    if not intro_note:
        return text
    return f"{intro_note}\n\n{text}"


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


def _manual_payment_settings(method: str) -> tuple[str, str]:
    if method == "sbp":
        details = str(config.manual_sbp_details or "").strip() or "Реквизиты СБП временно не указаны. Напишите в поддержку."
        return "sbp_manual", details
    if method == "crypto":
        details = str(config.manual_crypto_details or "").strip() or "Крипто-реквизиты временно не указаны. Напишите в поддержку."
        return "crypto_manual", details
    raise ValueError(f"Unsupported manual payment method: {method}")


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
    current_limit = min(DEFAULT_DEVICE_LIMIT + active_slots, MAX_DEVICE_LIMIT)
    remaining_capacity = remaining_device_slot_capacity(user, base_limit=DEFAULT_DEVICE_LIMIT)
    expires_at = getattr(user, "subscription_expires_at", None)
    expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
    return {
        "active_slots": active_slots,
        "current_limit": current_limit,
        "next_limit": min(current_limit + 1, MAX_DEVICE_LIMIT),
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


def _split_callback_suffix(payload: str, *, context: str) -> tuple[str, str]:
    left, sep, right = str(payload or "").partition(":")
    if not sep or not right:
        raise ValueError(f"Malformed callback payload for {context}: {payload!r}")
    return left, right


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
    if str(payment_result.get("product_type") or "").strip().lower() == GIFT_SUBSCRIPTION_PRODUCT_TYPE:
        return _gift_success_text(
            gift_code=str(payment_result.get("gift_code") or "—"),
            gift_days=int(payment_result.get("gift_days") or 0),
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
    metadata = _payment_metadata(record)
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


def _balance_topup_manual_tariff_code(amount_rub: int) -> str:
    return f"balance_topup_manual_{int(amount_rub)}"


async def _find_open_balance_topup_intent(user_id: int, amount_rub: int) -> PaymentRecord | None:
    async with async_session() as session:
        result = await session.execute(
            select(PaymentRecord)
            .where(
                PaymentRecord.user_id == int(user_id),
                PaymentRecord.payment_status.in_(OPEN_PAYMENT_STATUSES),
            )
            .order_by(PaymentRecord.created_at.desc(), PaymentRecord.id.desc())
        )
        rows = list(result.scalars().all())

    for record in rows:
        metadata = _payment_metadata(record)
        payload_type = str(metadata.get("payload_type") or metadata.get("product_type") or "").strip().lower()
        record_price = int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or 0)
        if payload_type == BALANCE_TOPUP_PRODUCT_TYPE and record_price == int(amount_rub):
            return record
    return None


@dataclass(frozen=True)
class TestUserSummary:
    telegram_id: int
    access_active: bool
    status_label: str
    days_left_text: str
    expires_text: str
    balance_rub: int
    tariff_title: str
    devices_count: int
    device_limit: int
    devices: tuple[dict, ...]
    single_connection_uri: str | None
    subscription_page_url: str | None = None
    subscription_feed_url: str | None = None
    subscription_extended_feed_url: str | None = None
    happ_subscription_url: str | None = None
    manual_extension_label: str | None = None


@dataclass(frozen=True)
class TestBonusSummary:
    referral_link: str
    invited_count: int
    paid_count: int
    earned_total_rub: int
    balance_available_rub: int


@dataclass(frozen=True)
class DeviceGuide:
    key: str
    button_label: str
    title: str
    instruction_title: str
    instruction_description: str
    instruction_body: tuple[str, ...]
    install_links: tuple[tuple[str, str], ...]


DEVICE_GUIDES: dict[str, DeviceGuide] = {
    "android": DeviceGuide(
        key="android",
        button_label="Android",
        title="Android",
        instruction_title="Инструкция для Android",
        instruction_description=(
            "Откройте страницу Happ в Google Play и установите приложение. "
            "Если Google Play недоступен, используйте прямую установку из APK-файла."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и нажмите <b>+</b> в правом верхнем углу.",
            "Выберите добавление по ссылке или вставку из буфера обмена.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и продолжите подключение.",
        ),
        install_links=(
            ("Открыть в Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Скачать APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
    "ios": DeviceGuide(
        key="ios",
        button_label="iOS",
        title="iOS",
        instruction_title="Инструкция для iOS",
        instruction_description=(
            "Откройте Happ в App Store и установите приложение. "
            "После первого запуска подтвердите запрос на добавление системного профиля подключения "
            "и введите пароль устройства."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и нажмите <b>+</b> в правом верхнем углу.",
            "Добавьте ссылку подписки или вставьте ключ из буфера обмена.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("App Store (RU)", "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"),
            ("App Store (Global)", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ),
    ),
    "windows": DeviceGuide(
        key="windows",
        button_label="Windows",
        title="Windows",
        instruction_title="Инструкция для Windows",
        instruction_description=(
            "Скачайте установщик для Windows, запустите его и завершите установку Happ. "
            "После установки вернитесь к этой подписке и добавьте её в приложение."
        ),
        instruction_body=(
            "Запустите <b>Happ</b> и нажмите <b>+</b> для добавления подписки.",
            "Вставьте ссылку или импортируйте ключ из буфера обмена.",
            "Вернитесь в бот, откройте <b>«Ключ»</b> и продолжите подключение.",
        ),
        install_links=(
            ("Windows x64", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
        ),
    ),
    "macos": DeviceGuide(
        key="macos",
        button_label="macOS",
        title="macOS",
        instruction_title="Инструкция для macOS",
        instruction_description=(
            "Откройте страницу Happ в App Store, установите приложение и подтвердите "
            "разрешение на системный профиль подключения, если macOS покажет такой запрос."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> и создайте новое подключение через <b>+</b>.",
            "Добавьте ссылку подписки или вставьте ключ вручную.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите настройку.",
        ),
        install_links=(
            ("App Store (RU)", "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973"),
            ("App Store (Global)", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ),
    ),
    "tv": DeviceGuide(
        key="tv",
        button_label="TV",
        title="TV",
        instruction_title="Инструкция для TV",
        instruction_description=(
            "Если у вас Apple TV, используйте App Store. "
            "Если у вас Android TV, откройте Google Play или установите Happ через APK."
        ),
        instruction_body=(
            "Выберите подходящий магазин приложений или установочный файл ниже.",
            "Откройте <b>Happ</b> на телевизоре и добавьте новое подключение.",
            "Введите или импортируйте ссылку подписки.",
            "Вернитесь в бот, откройте <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("Apple TV App Store", "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274"),
            ("Android TV Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Android TV APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
    "linux": DeviceGuide(
        key="linux",
        button_label="Linux",
        title="Linux",
        instruction_title="Инструкция для Linux",
        instruction_description=(
            "Выберите пакет под вашу систему и архитектуру, установите Happ, "
            "затем вернитесь на страницу подписки и добавьте ссылку в приложение."
        ),
        instruction_body=(
            "Установите <b>Happ</b> из подходящего пакета ниже и запустите приложение.",
            "Импортируйте ссылку подписки или вставьте ключ вручную.",
            "Вернитесь в бот, нажмите <b>«Ключ»</b> и завершите подключение.",
        ),
        install_links=(
            ("Linux x64 (.deb)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb"),
            ("Linux arm64 (.deb)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.deb"),
            ("Linux x64 (.rpm)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm"),
            ("Linux arm64 (.rpm)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.rpm"),
            ("Arch Linux x64 (.pkg.tar.zst)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.pkg.tar.zst"),
            ("Arch Linux arm64 (.pkg.tar.zst)", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.pkg.tar.zst"),
        ),
    ),
    "apple_tv": DeviceGuide(
        key="apple_tv",
        button_label="Apple TV",
        title="Apple TV",
        instruction_title="Инструкция для Apple TV",
        instruction_description=(
            "Откройте страницу Happ в App Store на Apple TV, установите приложение "
            "и при необходимости подтвердите системный запрос на подключение."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> на Apple TV после установки.",
            "Добавьте подписку по ссылке или введите её вручную.",
            "Если появится системный запрос на подключение, подтвердите его.",
            "Вернитесь в бот к кнопке <b>«Ключ»</b>, если ссылка ещё не открыта.",
        ),
        install_links=(
            ("Магазин приложений", "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274"),
        ),
    ),
    "android_tv": DeviceGuide(
        key="android_tv",
        button_label="Android TV",
        title="Android TV",
        instruction_title="Инструкция для Android TV",
        instruction_description=(
            "Откройте страницу Happ в Google Play и установите приложение. "
            "Если магазин не работает, используйте прямую установку из APK."
        ),
        instruction_body=(
            "Откройте <b>Happ</b> на Android TV после установки.",
            "Добавьте новое подключение по ссылке или через буфер обмена.",
            "Если используете APK, сначала разрешите установку из внешнего источника.",
            "Вернитесь в бот к кнопке <b>«Ключ»</b>, чтобы продолжить подключение.",
        ),
        install_links=(
            ("Открыть в Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
            ("Скачать APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
        ),
    ),
}


def _legacy_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Germany Mobile Android", callback_data="testbot:profile:de_android")],
        [InlineKeyboardButton(text="Germany Mobile iPhone", callback_data="testbot:profile:de_iphone")],
        [InlineKeyboardButton(text="Denmark Mobile Android", callback_data="testbot:profile:dk_android")],
        [InlineKeyboardButton(text="Denmark Mobile iPhone", callback_data="testbot:profile:dk_iphone")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _legacy_profile_keyboard(profile_key: str, *, supports_transfer: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if supports_transfer:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Активировать на iPhone",
                    callback_data=f"testbot:activate:{profile_key}:iphone",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Активировать на Windows PC",
                    callback_data=f"testbot:activate:{profile_key}:windows",
                )
            ]
        )
        rows.append([InlineKeyboardButton(text="Обновить статус", callback_data=f"testbot:profile:{profile_key}")])
    rows.append([InlineKeyboardButton(text="Назад к профилям", callback_data="testbot:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _legacy_menu_text() -> str:
    lines = [
        "<b>Amonora Test Bot</b>",
        "",
        "Здесь лежат admin-only legacy тестовые профили для текущих рабочих регионов.",
        "Прод-бот, оплаты и обычная выдача здесь не затрагиваются.",
        "",
        "Доступные профили:",
    ]
    for profile in get_test_profiles():
        lines.append(f"• <b>{profile.title}</b> — {profile.protocol_label}")
    return "\n".join(lines)


def _legacy_profile_text(runtime) -> str:
    profile = runtime.profile
    if profile is None:
        return "Профиль не найден."
    link = runtime.link
    metadata = profile.metadata
    sni = metadata.get("reality_server_name") or metadata.get("server_name") or "-"
    lines = [
        f"<b>{profile.title}</b>",
        "",
        f"Платформа: <b>{profile.platform_label}</b>",
        f"Протокол: <b>{profile.protocol_label}</b>",
        f"База: <b>{profile.based_on}</b>",
        f"Порт: <code>{metadata.get('port')}</code>",
    ]
    if profile.delivery_kind == "config":
        lines.append(f"DNS: <code>{metadata.get('dns_mode', '-')}</code>")
        lines.append(f"Маршрутизация: <code>{metadata.get('allowed_ips', '-')}</code>")
        lines.append("Формат выдачи: <b>полный конфиг AmneziaWG</b>")
    else:
        lines.append(f"SNI: <code>{sni}</code>")
    if runtime.supports_transfer:
        if runtime.active_device_label:
            lines.append(f"Текущая привязка: <b>{runtime.active_device_label}</b>")
        else:
            lines.append("Текущая привязка: <b>ещё не активирован</b>")
        lines.append("Правило: <b>1 ключ = 1 устройство</b>")
        lines.append("При смене устройства бот перевыпускает UUID, и старый ключ перестаёт работать.")
    if metadata.get("fingerprint"):
        lines.append(f"Fingerprint: <code>{metadata.get('fingerprint')}</code>")
    if metadata.get("alpn"):
        lines.append(f"ALPN: <code>{', '.join(metadata.get('alpn'))}</code>")
    if metadata.get("stream_path"):
        lines.append(f"Path: <code>{metadata.get('stream_path')}</code>")
    lines.extend(
        [
            "",
            "Конфиг:" if profile.delivery_kind == "config" else "Ссылка:",
            f"<code>{link}</code>",
        ]
    )
    return "\n".join(lines)


def _agreement_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="Принимаю", callback_data=V2_ACCEPT_TERMS_CALLBACK)],
        ]
    )


def _trial_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data=V2_CHECK_SUBSCRIPTION_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_SHOW_AGREEMENT_CALLBACK)],
        ]
    )


def _trial_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ключ", callback_data=V2_KEY_MENU_CALLBACK)],
            [
                InlineKeyboardButton(text="Инструкция", callback_data=V2_GUIDES_CALLBACK),
                InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _trial_used_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить подписку", callback_data=V2_RENEW_CALLBACK)],
            [InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK)],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Моя подписка", callback_data=V2_MY_SUBSCRIPTION_CALLBACK),
                InlineKeyboardButton(text="Ключ", callback_data=V2_KEY_MENU_CALLBACK),
            ],
            [
                InlineKeyboardButton(text="Продлить", callback_data=V2_RENEW_CALLBACK),
                InlineKeyboardButton(text="Информация", callback_data=V2_INFO_CALLBACK),
            ],
            [
                InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK),
                InlineKeyboardButton(text="Бонусная система", callback_data=V2_BONUS_CALLBACK),
            ],
        ]
    )


def _devices_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android"].button_label, callback_data="testv2:device:android"),
            InlineKeyboardButton(text=DEVICE_GUIDES["ios"].button_label, callback_data="testv2:device:ios"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["windows"].button_label, callback_data="testv2:device:windows"),
            InlineKeyboardButton(text=DEVICE_GUIDES["macos"].button_label, callback_data="testv2:device:macos"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["tv"].button_label, callback_data="testv2:device:tv"),
            InlineKeyboardButton(text=DEVICE_GUIDES["linux"].button_label, callback_data="testv2:device:linux"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=V2_BACK_TO_MENU_CALLBACK)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _guides_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android"].button_label, callback_data=f"{V2_GUIDE_PREFIX}android"),
            InlineKeyboardButton(text=DEVICE_GUIDES["ios"].button_label, callback_data=f"{V2_GUIDE_PREFIX}ios"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["windows"].button_label, callback_data=f"{V2_GUIDE_PREFIX}windows"),
            InlineKeyboardButton(text=DEVICE_GUIDES["macos"].button_label, callback_data=f"{V2_GUIDE_PREFIX}macos"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["linux"].button_label, callback_data=f"{V2_GUIDE_PREFIX}linux"),
            InlineKeyboardButton(text=DEVICE_GUIDES["apple_tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}apple_tv"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android_tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}android_tv"),
            InlineKeyboardButton(text=DEVICE_GUIDES["tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}tv"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=back_callback)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscription_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    open_button = (
        InlineKeyboardButton(text="Открыть подписку", url=summary.subscription_page_url)
        if summary.subscription_page_url
        else InlineKeyboardButton(text="Открыть подписку", callback_data=V2_KEY_MENU_CALLBACK)
    )
    return InlineKeyboardMarkup(inline_keyboard=[[open_button], [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)]])


def _renew_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ 1 месяц — 149 ₽", callback_data="testv2:renew:tariff:1m")],
            [InlineKeyboardButton(text="🔥 3 месяца — 399 ₽ (-10%)", callback_data="testv2:renew:tariff:3m")],
            [InlineKeyboardButton(text="👑 6 месяцев — 749 ₽ (-15%)", callback_data="testv2:renew:tariff:6m")],
            [InlineKeyboardButton(text="💫 12 месяцев — 1390 ₽ (-20%)", callback_data="testv2:renew:tariff:12m")],
            [InlineKeyboardButton(text="⭐️ Пополнить баланс", callback_data="testv2:renew:tariff:balance")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _simple_back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=callback_data)]])


def _my_devices_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for device in summary.devices:
        kind = str(device.get("kind") or "vpn_client").strip().lower()
        callback_suffix = "public" if kind == "public_slot" else "vpn"
        rows.append(
            [InlineKeyboardButton(text=device["title"], callback_data=f"testv2:mydevices:view:{callback_suffix}:{device['id']}")]
        )
    rows.append([InlineKeyboardButton(text="Купить дополнительный слот", callback_data=V2_DEVICE_SLOT_CALLBACK)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscription_key_menu_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    stable_feed_url = _subscription_feed_url(summary)
    extended_feed_url = _subscription_feed_url(summary, include_extra=True)
    open_page_button = (
        InlineKeyboardButton(text="🌐 Страница", url=summary.subscription_page_url)
        if summary.subscription_page_url
        else InlineKeyboardButton(text="🌐 Страница", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)
    )
    open_happ_button = (
        InlineKeyboardButton(text="📲 Happ", url=summary.happ_subscription_url)
        if summary.happ_subscription_url
        else InlineKeyboardButton(text="📲 Happ", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)
    )
    rows: list[list[InlineKeyboardButton]] = [[open_page_button, open_happ_button]]
    if stable_feed_url:
        rows.append([
            InlineKeyboardButton(
                text="📋 Скопировать основную",
                copy_text=CopyTextButton(text=stable_feed_url),
            )
        ])
    if extended_feed_url:
        rows.append([
            InlineKeyboardButton(
                text="🌍 Скопировать расширенную",
                copy_text=CopyTextButton(text=extended_feed_url),
            )
        ])
    rows.append([InlineKeyboardButton(text="Мои устройства", callback_data=V2_MY_DEVICES_CALLBACK)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscription_key_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    open_page_button = (
        InlineKeyboardButton(text="Открыть подписку", url=summary.subscription_page_url)
        if summary.subscription_page_url
        else InlineKeyboardButton(text="Открыть подписку", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)
    )
    open_happ_button = (
        InlineKeyboardButton(text="Открыть в Happ", url=summary.happ_subscription_url)
        if summary.happ_subscription_url
        else InlineKeyboardButton(text="Открыть в Happ", callback_data=V2_MY_SUBSCRIPTION_CALLBACK)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [open_page_button, open_happ_button],
            [InlineKeyboardButton(text="Назад", callback_data=V2_KEY_MENU_CALLBACK)],
        ]
    )


def _device_detail_keyboard(device_kind: str, device_id: int, connection_uri: str | None) -> InlineKeyboardMarkup:
    del connection_uri
    delete_kind = "public" if str(device_kind or "").strip().lower() == "public_slot" else "vpn"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Удалить устройство", callback_data=f"{V2_DEVICE_DELETE_PREFIX}{delete_kind}:{device_id}")],
        [InlineKeyboardButton(text="Назад", callback_data=V2_MY_DEVICES_CALLBACK)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _renew_payment_methods_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_RENEW_METHOD_PREFIX}sbp:{tariff_code}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_RENEW_METHOD_PREFIX}sbp_manual:{tariff_code}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_RENEW_METHOD_PREFIX}crypto:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_RENEW_CALLBACK)],
        ]
    )


def _balance_payment_methods_keyboard(amount_rub: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_BALANCE_METHOD_PREFIX}sbp:{amount_rub}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_BALANCE_METHOD_PREFIX}sbp_manual:{amount_rub}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_BALANCE_METHOD_PREFIX}crypto:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _device_slot_payment_methods_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}sbp")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}sbp_manual")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}crypto")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MY_DEVICES_CALLBACK)],
        ]
    )


def _renew_manual_payment_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_RENEW_MANUAL_PAID_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_RENEW_MANUAL_STATUS_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_RENEW_MANUAL_CANCEL_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"testv2:renew:tariff:{tariff_code}")],
        ]
    )


def _renew_external_payment_keyboard(checkout_url: str, tariff_code: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_RENEW_EXTERNAL_CHECK_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"testv2:renew:tariff:{tariff_code}")],
        ]
    )


def _balance_manual_payment_keyboard(record_id: int, amount_rub: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_BALANCE_MANUAL_PAID_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_BALANCE_MANUAL_STATUS_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_BALANCE_MANUAL_CANCEL_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _balance_external_payment_keyboard(checkout_url: str, amount_rub: int, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_BALANCE_EXTERNAL_CHECK_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _device_slot_manual_payment_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_DEVICE_SLOT_MANUAL_PAID_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_DEVICE_SLOT_CALLBACK)],
        ]
    )


def _device_slot_external_payment_keyboard(checkout_url: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_DEVICE_SLOT_CALLBACK)],
        ]
    )


def _balance_topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="100 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}100")],
            [InlineKeyboardButton(text="300 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}300")],
            [InlineKeyboardButton(text="500 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}500")],
            [InlineKeyboardButton(text="1000 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}1000")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_RENEW_CALLBACK)],
        ]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть поддержку", url=SUPPORT_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Инструкции", callback_data=V2_INFO_GUIDES_CALLBACK)],
            [InlineKeyboardButton(text="Документы", callback_data=V2_INFO_DOCS_CALLBACK)],
            [InlineKeyboardButton(text="Канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _info_documents_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="Политика конфиденциальности", url=PRIVACY_URL)],
            [InlineKeyboardButton(text="Политика возврата", url=REFUNDS_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_INFO_CALLBACK)],
        ]
    )


def _bonus_keyboard(summary: TestBonusSummary) -> InlineKeyboardMarkup:
    invite_button: InlineKeyboardButton
    if summary.referral_link.startswith("https://"):
        invite_button = InlineKeyboardButton(text="Пригласить друга", url=referral_share_url(summary.referral_link))
    else:
        invite_button = InlineKeyboardButton(text="Пригласить друга", callback_data="testv2:bonus:no-link")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Моя статистика", callback_data=V2_BONUS_STATS_CALLBACK)],
            [invite_button],
            [InlineKeyboardButton(text="Ввести промокод", callback_data=V2_BONUS_PROMO_CALLBACK)],
            [InlineKeyboardButton(text="Подарить подписку", callback_data=V2_BONUS_GIFT_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _bonus_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)],
        ]
    )


def _bonus_promo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)],
        ]
    )


def _bonus_gift_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тариф", callback_data=V2_BONUS_GIFT_TARIFFS_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)],
        ]
    )


def _bonus_gift_tariffs_text() -> str:
    return (
        "🎁 <b>Выберите подарочный тариф</b>\n\n"
        "Подберите срок подписки, который хотите подарить другу.\n"
        "После оплаты система создаст уникальный код активации.\n\n"
        "👇 Ниже доступны готовые варианты подарка"
    )


def _bonus_gift_tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ 1 месяц — 149 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}1m")],
            [InlineKeyboardButton(text="🔥 3 месяца — 399 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}3m")],
            [InlineKeyboardButton(text="👑 6 месяцев — 749 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}6m")],
            [InlineKeyboardButton(text="💫 12 месяцев — 1390 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}12m")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_GIFT_CALLBACK)],
        ]
    )


def _bonus_gift_payment_text(tariff) -> str:
    title = _months_label_for_tariff(tariff)
    price = int(getattr(tariff, "rub_price", 0) or 0)
    return (
        "🎁 <b>Подарочная подписка</b>\n\n"
        f"⏳ Срок: <b>{title}</b>\n"
        f"💰 Стоимость: <b>{price} ₽</b>\n\n"
        "После оплаты Вы получите уникальный код.\n"
        "Передайте его другу — он сможет активировать подписку.\n\n"
        "Нажмите кнопку оплатить:"
    )


def _bonus_gift_payment_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить подарок", callback_data=f"{V2_BONUS_GIFT_PAY_PREFIX}{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_GIFT_TARIFFS_CALLBACK)],
        ]
    )


def _bonus_gift_payment_methods_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}sbp:{tariff_code}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}sbp_manual:{tariff_code}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}crypto:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _bonus_gift_manual_payment_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_BONUS_GIFT_MANUAL_PAID_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_BONUS_GIFT_MANUAL_STATUS_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _bonus_gift_external_payment_keyboard(checkout_url: str, tariff_code: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _device_guide_keyboard(device_key: str, *, back_callback: str) -> InlineKeyboardMarkup:
    del device_key
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=back_callback)],
        ]
    )


def _after_install_keyboard(device_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подключиться", callback_data=f"testv2:connect:{device_key}")],
            [
                InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL),
                InlineKeyboardButton(text="Инструкция", callback_data=f"testv2:device:{device_key}"),
            ],
        ]
    )


def _connect_placeholder_keyboard(device_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Инструкция", callback_data=f"testv2:device:{device_key}"),
                InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=f"testv2:installed:{device_key}")],
        ]
    )


def _device_instruction_text(device_key: str) -> str:
    guide = DEVICE_GUIDES[device_key]
    steps = "\n".join(f"• {line}" for line in guide.instruction_body)
    install_links = "\n".join(f"• <a href=\"{url}\">{label}</a>" for label, url in guide.install_links)
    return (
        f"<b>{guide.instruction_title}</b>\n\n"
        f"{guide.instruction_description}\n\n"
        f"<b>Что делать дальше:</b>\n{steps}\n\n"
        f"<b>Ссылки для установки:</b>\n{install_links}"
    )


GUIDES_CHOICE_TEXT = """📘 <b>Инструкция по подключению</b>

Выберите вашу ОС или устройство 👇

На следующем шаге откроется инструкция именно под ваше устройство и ссылки на установку <b>Happ</b>."""


def _after_install_text(device_key: str) -> str:
    guide = DEVICE_GUIDES[device_key]
    return (
        f"Готово! Теперь нажмите <b>«Подключиться»</b> для <b>{guide.title}</b>.\n"
        "Если возникнут трудности, обратитесь в <b>Поддержку</b> "
        "или ознакомьтесь с <b>Инструкцией</b>."
    )


def _format_status_label(user) -> str:
    return "✅ Подписка активна" if has_active_access_from_user(user) else "❌ Не активна"


def _format_expires_text(expires_at) -> str:
    if expires_at is None:
        return "—"
    return expires_at.strftime("%d.%m.%Y %H:%M")


def _format_days_left_text(expires_at) -> str:
    if expires_at is None:
        return "—"
    remaining_seconds = (expires_at - utcnow()).total_seconds()
    if remaining_seconds <= 0:
        return "0 дней"
    days_left = max(1, ceil(remaining_seconds / 86400))
    return f"{days_left} дн."


async def _subscription_billing_summary_for_user(user) -> tuple[str, str | None]:
    status = get_access_status_from_user(user)
    if status == "trial_active":
        return "Пробный период", None
    if status == "vip_active":
        return "Админ доступ", None
    if status != "paid_active":
        return "Без тарифа", None

    snapshot = await load_subscription_payment_snapshot(int(user.id))
    subscription_source = str(getattr(user, "subscription_source", "") or "").strip().lower()
    tariff_title = snapshot.latest_tariff_title
    if not tariff_title:
        if subscription_source in MANUAL_ACCESS_SOURCES:
            tariff_title = "Ручной доступ"
        elif subscription_source in ADMIN_ACCESS_SOURCES:
            tariff_title = "Админ доступ"
        else:
            tariff_title = "Платный доступ"

    manual_label: str | None = None
    if subscription_source in MANUAL_EXTENSION_SOURCES:
        extension_days = manual_extension_days(
            get_access_expires_at_from_user(user),
            snapshot.payment_only_expires_at,
        )
        if extension_days > 0:
            manual_label = humanize_extension_duration(extension_days)
    return tariff_title, manual_label


def _normalize_connection_uri(value: str | None) -> str | None:
    payload = str(value or "").strip()
    return payload or None


def _device_metadata(device) -> dict:
    raw_value = getattr(device, "client_data", None)
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _device_connection_uri(device, metadata: dict) -> str | None:
    if not metadata:
        return None
    if device.protocol == "trojan":
        return _normalize_connection_uri(metadata.get("connection_uri") or metadata.get("trojan_link"))
    return _normalize_connection_uri(metadata.get("connection_uri") or metadata.get("vless_link"))


def _device_display_row(device, metadata: dict) -> dict:
    device_name = str(metadata.get("device_name") or getattr(device, "email", f"Устройство #{device.id}"))
    country_name = str(metadata.get("country_name") or metadata.get("country_code") or "—")
    protocol = str(metadata.get("protocol") or getattr(device, "protocol", "vless")).upper()
    connection_uri = _device_connection_uri(device, metadata)
    device_type = _normalize_device_type(str(metadata.get("device_type") or "other").strip().lower()) or "other"
    device_model = str(
        metadata.get("device_model")
        or metadata.get("model")
        or metadata.get("hardware_model")
        or metadata.get("device_name")
        or getattr(device, "email", f"Устройство #{device.id}")
    )
    raw_os_version = (
        metadata.get("os_version")
        or metadata.get("platform_version")
        or metadata.get("system_version")
        or metadata.get("os_build")
    )
    os_version = str(
        _normalize_public_os_version(
            device_type=device_type,
            os_version=raw_os_version,
            user_agent=metadata.get("user_agent"),
        )
        or "—"
    )
    return {
        "kind": "vpn_client",
        "id": int(device.id),
        "title": device_name,
        "country_name": country_name,
        "protocol": protocol,
        "connection_uri": connection_uri,
        "device_type": device_type,
        "device_model": device_model,
        "os_version": os_version,
    }


def _public_subscription_device_row(device: dict) -> dict:
    device_title = str(device.get("title") or device.get("device_model") or f"Happ #{device.get('id') or '?'}").strip()
    return {
        "kind": "public_slot",
        "id": int(device.get("id") or 0),
        "title": device_title or f"Happ #{device.get('id') or '?'}",
        "country_name": "Единая ссылка",
        "protocol": "SUB",
        "connection_uri": None,
        "device_type": str(device.get("device_type") or "other").strip().lower() or "other",
        "device_model": str(device.get("device_model") or device_title or "Happ device").strip() or "Happ device",
        "os_version": str(device.get("os_version") or "—").strip() or "—",
    }


async def _load_test_user_summary(telegram_id: int) -> TestUserSummary:
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return TestUserSummary(
            telegram_id=int(telegram_id),
            access_active=False,
            status_label="❌ Не активна",
            days_left_text="—",
            expires_text="—",
            balance_rub=0,
            tariff_title="Без тарифа",
            devices_count=0,
            device_limit=1,
            devices=(),
            single_connection_uri=None,
        )

    expires_at = get_access_expires_at_from_user(user)
    tariff_title, manual_extension_label = await _subscription_billing_summary_for_user(user)
    subscription_page_url: str | None = None
    subscription_feed_url: str | None = None
    subscription_extended_feed_url: str | None = None
    happ_subscription_url: str | None = None
    try:
        subscription_page_url = await get_or_create_public_subscription_page_url_for_user(int(user.id))
        if subscription_page_url:
            token = extract_public_subscription_token_from_url(subscription_page_url)
            if token is not None:
                subscription_page_url = build_public_subscription_page_url(token)
                subscription_feed_url = build_public_subscription_feed_url(token)
                subscription_extended_feed_url = build_public_subscription_feed_url(token, include_extra=True)
            happ_subscription_url = build_public_subscription_happ_wrapper_url(subscription_page_url)
    except Exception:
        subscription_page_url = None
        subscription_feed_url = None
        subscription_extended_feed_url = None
        happ_subscription_url = None
    active_slot_counts = await get_active_device_slot_counts_for_users([int(user.id)])
    setattr(user, "active_device_slot_addons", int(active_slot_counts.get(int(user.id), 0)))
    device_limit = get_device_limit_for_user(user)
    balance_summary = await get_user_balance_summary(int(user.id))
    raw_vpn_devices = await get_user_vpn_clients(int(user.id))
    raw_vpn_devices = sorted(
        raw_vpn_devices,
        key=lambda item: (
            str(getattr(item, "created_at", "") or ""),
            int(getattr(item, "id", 0)),
        ),
    )
    vpn_devices = tuple(_device_display_row(device, _device_metadata(device)) for device in raw_vpn_devices)
    public_devices = tuple(
        _public_subscription_device_row(device)
        for device in await get_public_subscription_bound_devices_for_user(int(user.id))
    )
    devices = vpn_devices + public_devices
    single_connection_uri = devices[0]["connection_uri"] if len(devices) == 1 else None
    return TestUserSummary(
        telegram_id=int(telegram_id),
        access_active=has_active_access_from_user(user),
        status_label=_format_status_label(user),
        days_left_text=_format_days_left_text(expires_at),
        expires_text=_format_expires_text(expires_at),
        balance_rub=int(balance_summary.get("balance_available_rub", 0) or 0),
        tariff_title=tariff_title,
        devices_count=len(devices),
        device_limit=int(device_limit),
        devices=devices,
        single_connection_uri=single_connection_uri,
        subscription_page_url=subscription_page_url,
        subscription_feed_url=subscription_feed_url,
        subscription_extended_feed_url=subscription_extended_feed_url,
        happ_subscription_url=happ_subscription_url,
        manual_extension_label=manual_extension_label,
    )


async def _load_bonus_summary(telegram_id: int) -> TestBonusSummary:
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return TestBonusSummary(
            referral_link="Ссылка появится после активации аккаунта",
            invited_count=0,
            paid_count=0,
            earned_total_rub=0,
            balance_available_rub=0,
        )
    stats = await get_user_referral_stats(int(user.id))
    referral_link = str(stats.get("ref_link") or "").strip() or "Ссылка появится после активации аккаунта"
    return TestBonusSummary(
        referral_link=referral_link,
        invited_count=int(stats.get("invited_count", 0) or 0),
        paid_count=int(stats.get("paid_count", 0) or 0),
        earned_total_rub=int(stats.get("total_earned_rub", 0) or 0),
        balance_available_rub=int(stats.get("balance_available_rub", 0) or 0),
    )


def _main_menu_text(summary: TestUserSummary) -> str:
    return (
        f"📅 Статус: <b>{summary.status_label}</b>\n"
        f"⏳ Действует : <b>{summary.days_left_text}</b>\n"
        f"💰 Баланс: <b>{summary.balance_rub}</b> руб."
    )


def _subscription_text(summary: TestUserSummary) -> str:
    lines = [
        f"🆔 ID: <code>{summary.telegram_id}</code>",
        f"📅 Статус: <b>{summary.status_label}</b>",
        f"🏷 Тариф: <b>{summary.tariff_title}</b>",
    ]
    if summary.manual_extension_label:
        lines.append(f"🛠 Ручное продление: <b>на {summary.manual_extension_label}</b>")
    lines.extend(
        [
            f"⏳ Действует до: <b>{summary.expires_text}</b>",
            f"💰 Баланс: <b>{summary.balance_rub}</b> руб.",
            f"📱 Устройств: <b>{summary.devices_count}</b>",
        ]
    )
    return "\n".join(lines)


def _renew_text(summary: TestUserSummary) -> str:
    manual_note = (
        f"\n🛠 Ручное продление: <b>на {summary.manual_extension_label}</b>"
        if summary.manual_extension_label
        else ""
    )
    return (
        "💳 <b>Продлить доступ</b>\n\n"
        f"Текущий тариф: <b>{summary.tariff_title}</b>"
        f"{manual_note}\n"
        f"Баланс: <b>{summary.balance_rub} ₽</b>\n\n"
        "Выберите срок продления ниже."
    )


def _months_label_for_tariff(tariff) -> str:
    if tariff is None:
        return "Тариф"
    return tariff.title


async def _load_pending_discount_payload(user_id: int) -> dict | None:
    redemption = await get_user_pending_discount(int(user_id))
    if redemption is None:
        return None
    discount_percent = max(int(getattr(redemption, "discount_percent", 0) or 0), 0)
    if discount_percent <= 0:
        return None
    return {
        "redemption_id": int(redemption.id),
        "discount_percent": discount_percent,
    }


def _pending_discount_note(discount: dict | None) -> str:
    if not discount:
        return ""
    return f"\n🎟 Активная скидка: <b>{int(discount['discount_percent'])}%</b> на ближайшую оплату подписки."


def _effective_tariff_price(tariff, discount: dict | None) -> dict:
    original_price = int(getattr(tariff, "rub_price", 0) or 0)
    if not discount:
        return {
            "original_price": original_price,
            "payable_price": original_price,
            "discount_percent": 0,
        }
    return {
        "original_price": original_price,
        "payable_price": apply_discount_percent(original_price, int(discount["discount_percent"])),
        "discount_percent": int(discount["discount_percent"]),
    }


def _subscription_payment_metadata(*, tariff, user, discount: dict | None = None, method: str | None = None) -> dict:
    metadata = {
        "tariff_title": tariff.title,
        "telegram_id": getattr(user, "telegram_id", None),
    }
    if method:
        metadata["method"] = method
    if discount:
        metadata["promo_redemption_id"] = int(discount["redemption_id"])
        metadata["discount_percent"] = int(discount["discount_percent"])
        metadata["original_list_price_amount"] = int(getattr(tariff, "rub_price", 0) or 0)
    return metadata


def _gift_payment_metadata(*, tariff, user, method: str | None = None) -> dict:
    metadata = {
        "product_type": GIFT_SUBSCRIPTION_PRODUCT_TYPE,
        "payload_type": GIFT_SUBSCRIPTION_PRODUCT_TYPE,
        "gift_days": int(getattr(tariff, "duration_days", 0) or 0),
        "gift_title": f"Подарок: {tariff.title}",
        "tariff_title": f"Подарок: {tariff.title}",
        "telegram_id": getattr(user, "telegram_id", None),
    }
    if method:
        metadata["method"] = method
    return metadata


def _gift_success_text(*, gift_code: str, gift_days: int) -> str:
    return (
        "🎁 <b>Подарочный код готов</b>\n\n"
        f"Срок подарка: <b>{gift_days} дн.</b>\n\n"
        "Передайте этот код другу:\n\n"
        f"<code>{gift_code}</code>\n\n"
        "Друг сможет ввести его в разделе «Бонусная система» → «Ввести промокод»."
    )


async def _gift_success_text_from_record(record) -> str:
    promo = await get_promo_code_by_payment_record_id(int(record.id))
    metadata = _payment_metadata(record)
    if promo is None:
        promo = await create_gift_promo_code_for_payment(
            buyer_user_id=int(record.user_id or 0),
            payment_record_id=int(record.id),
            grant_days=int(metadata.get("gift_days") or getattr(record, "duration_days", 0) or 0),
            tariff_code=getattr(record, "tariff_code", None),
            title=str(metadata.get("gift_title") or metadata.get("tariff_title") or "Подарочная подписка"),
        )
    return _gift_success_text(
        gift_code=str(promo.code or "—"),
        gift_days=max(int(getattr(promo, "grant_days", 0) or metadata.get("gift_days") or 0), 0),
    )


def _devices_page_text(summary: TestUserSummary) -> str:
    lines = [
        "📱 <b>Мои устройства</b>",
        "",
        f"Сейчас подключено: <b>{summary.devices_count} из {summary.device_limit}</b>",
        "",
        "Здесь ты можешь:",
        "• посмотреть информацию об устройстве",
        "• удалить лишние подключения",
        "",
        "👇 Выбери нужное устройство",
    ]
    if not summary.devices:
        lines.extend(["", "У тебя пока нет подключённых устройств."])
    return "\n".join(lines)


def _subscription_connection_uri(summary: TestUserSummary) -> str | None:
    if summary.subscription_page_url:
        return summary.subscription_page_url
    if summary.single_connection_uri:
        return summary.single_connection_uri
    for device in summary.devices:
        connection_uri = str(device.get("connection_uri") or "").strip()
        if connection_uri:
            return connection_uri
    return None


def _subscription_feed_url(summary: TestUserSummary, *, include_extra: bool = False) -> str | None:
    configured_url = summary.subscription_extended_feed_url if include_extra else summary.subscription_feed_url
    if configured_url:
        return configured_url
    token = extract_public_subscription_token_from_url(summary.subscription_page_url)
    if token is None:
        return None
    return build_public_subscription_feed_url(token, include_extra=include_extra)


def _subscription_key_text(summary: TestUserSummary) -> str:
    connection_uri = _subscription_connection_uri(summary) or "Ссылка пока недоступна"
    return (
        "📋 <b>Ссылка для ручного подключения:</b>\n\n"
        f"<code>{connection_uri}</code>\n"
        "(нажмите на ссылку, чтобы скопировать)\n\n"
        "Что делать дальше:\n"
        "1) Откройте Happ\n"
        "2) Нажмите «+» в правом верхнем углу\n"
        "3) Выберите «Вставить из буфера обмена»\n"
        "4) Сохраните подключение"
    )


def _subscription_key_menu_text(summary: TestUserSummary) -> str:
    lines = [
        "🔑 <b>Ваш ключ подключения</b>",
        "",
        "Есть 2 варианта подписки:",
        "",
        "✅ <b>Основная подписка</b> — самый стабильный вариант для Happ.",
        "Используйте её, если приложение не импортирует ссылку или подключение работает нестабильно.",
        "",
        "🌍 <b>Расширенная подписка</b> — больше серверов и стран.",
        "Если она импортируется с ошибкой, используйте основную.",
        "",
        "🌐 <b>Страница подписки</b> — откроет QR-код и инструкцию в браузере.",
    ]
    if summary.subscription_page_url:
        lines.extend(["", "<b>Страница подписки:</b>", summary.subscription_page_url])
    else:
        lines.extend(["", "Ссылка появится после подготовки подключения."])
    return "\n".join(lines)


def _device_os_label(device_type: str | None) -> str:
    return OS_LABELS.get(str(device_type or "other").strip().lower(), "🧩 Другое")


def _device_os_icon(device_type: str | None) -> str:
    return _device_os_label(device_type).split(" ", 1)[0]


def _device_detail_text(device: dict) -> str:
    os_label = _device_os_label(str(device.get("device_type") or "other"))
    os_name = os_label.split(" ", 1)[1] if " " in os_label else os_label
    os_version = str(device.get("os_version") or device.get("os_name") or os_name or "—").strip() or "—"
    return (
        f"{_device_os_icon(device.get('device_type'))} <b>Информация об устройстве</b>\n\n"
        f"Модель: <b>{device.get('device_model') or device.get('title') or '—'}</b>\n"
        f"ОС: <b>{os_name}</b>\n"
        f"Версия ОС: <b>{os_version}</b>"
    )


async def _get_owned_test_device_for_telegram(telegram_id: int, device_id: int):
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return None, None
    device = await get_vpn_client_by_id(int(device_id))
    if device is None or int(device.user_id) != int(user.id):
        return user, None
    return user, device


def _renew_payment_methods_text(tariff) -> str:
    title = _months_label_for_tariff(tariff)
    price = int(getattr(tariff, "rub_price", 0) or 0)
    return (
        f"💸 <b>{title}</b>\n\n"
        f"Полная стоимость: <b>{price} ₽</b>\n\n"
        "Выберите удобный способ оплаты 👇\n\n"
        "💳 <b>СБП</b> — автоматическое подтверждение\n"
        "💳 <b>СБП (ручная)</b> — подтверждение администратором\n"
        "💎 <b>Криптовалюта</b> — автоматическое подтверждение"
    )


def _renew_payment_methods_text_with_discount(tariff, discount: dict | None) -> str:
    pricing = _effective_tariff_price(tariff, discount)
    title = _months_label_for_tariff(tariff)
    lines = [f"💸 <b>{title}</b>", ""]
    if pricing["discount_percent"] > 0:
        lines.append(f"Полная стоимость: <s>{pricing['original_price']} ₽</s>")
        lines.append(f"Скидка по промокоду: <b>{pricing['discount_percent']}%</b>")
        lines.append(f"К оплате: <b>{pricing['payable_price']} ₽</b>")
    else:
        lines.append(f"Полная стоимость: <b>{pricing['payable_price']} ₽</b>")
    lines.extend(
        [
            "",
            "Выберите удобный способ оплаты 👇",
            "",
            "💳 <b>СБП</b> — автоматическое подтверждение",
            "💳 <b>СБП (ручная)</b> — подтверждение администратором",
            "💎 <b>Криптовалюта</b> — автоматическое подтверждение",
        ]
    )
    return "\n".join(lines)


def _bonus_gift_payment_methods_text(tariff) -> str:
    title = _months_label_for_tariff(tariff)
    price = int(getattr(tariff, "rub_price", 0) or 0)
    return (
        f"🎁 <b>{title}</b>\n\n"
        f"Полная стоимость: <b>{price} ₽</b>\n\n"
        "После оплаты бот создаст подарочный код, который можно передать другу.\n\n"
        "Выберите удобный способ оплаты 👇\n\n"
        "💳 <b>СБП</b> — автоматическое подтверждение\n"
        "💳 <b>СБП (ручная)</b> — подтверждение администратором\n"
        "💎 <b>Криптовалюта</b> — автоматическое подтверждение"
    )


def _device_slot_methods_text(price_rub: int) -> str:
    return (
        f"Полная стоимость: <b>{int(price_rub)} ₽</b>\n\n"
        "Выберите удобный способ оплаты 👇\n\n"
        "💳 <b>СБП</b> — автоматическое подтверждение\n"
        "💳 <b>СБП (ручная)</b> — подтверждение администратором\n"
        "💎 <b>Криптовалюта</b> — автоматическое подтверждение"
    )


def _balance_topup_text(summary: TestUserSummary) -> str:
    return (
        "Добавьте средства на баланс для оплаты и продления 👇\n\n"
        f"Текущий баланс: <b>{summary.balance_rub} ₽</b>\n\n"
        "🔒 Безопасная оплата • Быстрое зачисление\n\n"
        "Выберите  сумму пополнения"
    )


def _balance_payment_methods_text(summary: TestUserSummary, amount_rub: int) -> str:
    return (
        f"💸 Текущий баланс: <b>{summary.balance_rub} ₽</b>\n\n"
        f"Полная стоимость: <b>{int(amount_rub)} ₽</b>\n\n"
        "Выберите удобный способ оплаты 👇\n\n"
        "💳 <b>СБП</b> — автоматическое подтверждение\n"
        "💳 <b>СБП (ручная)</b> — подтверждение администратором\n"
        "💎 <b>Криптовалюта</b> — автоматическое подтверждение"
    )


async def _finish_balance_only_subscription_payment(callback: CallbackQuery, *, user, tariff, discount: dict | None = None) -> bool:
    pricing = _effective_tariff_price(tariff, discount)
    if pricing["discount_percent"] > 0:
        record = await create_balance_only_custom_payment_record(
            user_id=user.id,
            tariff_code=tariff.code,
            list_price_amount=pricing["payable_price"],
            duration_days=tariff.duration_days,
            payment_source="balance_rub",
            currency="RUB",
            note=tariff.title,
            metadata=_subscription_payment_metadata(tariff=tariff, user=user, discount=discount),
        )
    else:
        record = await create_balance_only_payment_record(
            user_id=user.id,
            tariff_code=tariff.code,
            duration_days=tariff.duration_days,
        )
    if record is None:
        return False

    payment_result = await finalize_subscription_payment(
        user_id=user.id,
        tariff_code=tariff.code,
        payment_id=record.external_payment_id or f"balance_{record.id}",
        payment_source="balance_rub",
        payment_record_id=record.id,
    )
    if payment_result is None:
        return False

    await _edit_screen(
        callback,
        _payment_result_text(payment_result),
        _renew_payment_methods_keyboard(tariff.code),
        screen_key="renew",
        answer_first=False,
    )
    if payment_result["sync_failed"]:
        await callback.message.answer(PAYMENT_SYNC_WARNING_TEXT, parse_mode="HTML")
    await notify_referral_bonus(callback.bot, payment_record_id=record.id)
    return True


async def _show_manual_subscription_payment(
    callback: CallbackQuery,
    *,
    method: str,
    tariff,
    user,
    discount: dict | None = None,
    intro_note: str | None = None,
) -> None:
    payment_method, details = _manual_payment_settings(method)
    pricing = _effective_tariff_price(tariff, discount)
    record = await create_balance_aware_manual_payment_record(
        user_id=user.id,
        tariff_code=tariff.code,
        payment_method=payment_method,
        list_price_amount=pricing["payable_price"],
        currency="RUB",
        duration_days=tariff.duration_days,
        metadata=_subscription_payment_metadata(tariff=tariff, user=user, discount=discount, method=method),
        expires_at=utcnow() + timedelta(hours=config.manual_payment_review_hours),
    )
    text = manual_payment_details_text(
        tariff_title=tariff.title,
        amount_rub=record.amount,
        list_price_amount=record.list_price_amount or pricing["payable_price"],
        balance_reserved_amount=record.balance_reserved_amount or 0,
        method_label=payment_method,
        request_id=record.id,
        details=details,
        review_hours=config.manual_payment_review_hours,
    )
    await _edit_screen(
        callback,
        _prefix_payment_text(text, intro_note),
        _renew_manual_payment_keyboard(record.id, tariff.code),
        screen_key="renew",
        answer_first=False,
    )


async def _show_platega_subscription_payment(
    callback: CallbackQuery,
    *,
    method: str,
    tariff,
    user,
    discount: dict | None = None,
    breakdown: dict[str, int],
) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _renew_payment_methods_keyboard(tariff.code),
            screen_key="renew",
            answer_first=False,
        )
        return
    client = PlategaClient()
    if not client.configured:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _renew_payment_methods_keyboard(tariff.code),
            screen_key="renew",
            answer_first=False,
        )
        return

    pricing = _effective_tariff_price(tariff, discount)
    record = await ensure_platega_payment_record(
        user_id=user.id,
        telegram_id=user.telegram_id,
        tariff_code=tariff.code,
        payment_method=payment_method,
        list_price_amount=pricing["payable_price"],
        duration_days=tariff.duration_days,
        tariff_title=tariff.title,
        payable_amount=breakdown["payable_amount"],
        metadata_extra=_subscription_payment_metadata(tariff=tariff, user=user, discount=discount, method=method),
    )
    metadata = _payment_metadata(record)
    checkout_url = str(metadata.get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            _renew_payment_methods_keyboard(tariff.code),
            screen_key="renew",
            answer_first=False,
        )
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=tariff.title,
            amount_rub=record.amount,
            method_label=payment_method,
            checkout_label="страница оплаты",
            list_price_amount=record.list_price_amount or pricing["payable_price"],
            balance_reserved_amount=record.balance_reserved_amount or 0,
            extra_hint="После оплаты можно нажать «Проверить оплату», если подтверждение немного задержится.",
        ),
        _renew_external_payment_keyboard(checkout_url, tariff.code, record.id),
        screen_key="renew",
        answer_first=False,
    )


async def _show_existing_subscription_payment_intent(callback: CallbackQuery, *, record, tariff, discount: dict | None = None) -> None:
    intro_note = _existing_open_payment_intro(record)
    payment_method = str(getattr(record, "payment_method", "") or "").strip().lower()
    pricing = _effective_tariff_price(tariff, discount)
    if payment_method in MANUAL_PAYMENT_METHODS:
        if record.payment_status == "awaiting_admin_review":
            text = manual_payment_waiting_review_text(
                tariff_title=tariff.title,
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or pricing["payable_price"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            )
        else:
            _, details = _manual_payment_settings("sbp" if payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title=tariff.title,
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or pricing["payable_price"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                method_label=record.payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await _edit_screen(
            callback,
            _prefix_payment_text(text, intro_note),
            _renew_manual_payment_keyboard(record.id, tariff.code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            _prefix_payment_text(
                "Активный счёт уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            _renew_payment_methods_keyboard(tariff.code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await _edit_screen(
        callback,
        _prefix_payment_text(
            platega_payment_text(
                tariff_title=tariff.title,
                amount_rub=record.amount,
                method_label=record.payment_method,
                checkout_label="страница оплаты",
                list_price_amount=record.list_price_amount or pricing["payable_price"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                extra_hint="После оплаты можно нажать «Проверить оплату», если подтверждение немного задержится.",
            ),
            intro_note,
        ),
        _renew_external_payment_keyboard(checkout_url, tariff.code, record.id),
        screen_key="renew",
        answer_first=False,
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


async def _finish_balance_only_gift_payment(callback: CallbackQuery, *, user, tariff) -> bool:
    record = await create_balance_only_custom_payment_record(
        user_id=user.id,
        tariff_code=tariff.code,
        list_price_amount=int(getattr(tariff, "rub_price", 0) or 0),
        duration_days=int(getattr(tariff, "duration_days", 0) or 0),
        payment_source="balance_rub",
        currency="RUB",
        note=f"Подарок: {tariff.title}",
        metadata=_gift_payment_metadata(tariff=tariff, user=user),
    )
    if record is None:
        return False

    payment_result = await finalize_payment_record_product(
        user_id=user.id,
        payment_source="balance_rub",
        payment_record_id=record.id,
        tariff_code=tariff.code,
        payment_id=record.external_payment_id or f"balance_{record.id}",
    )
    if payment_result is None:
        return False
    await sync_income_entry_for_payment_record(record.id)
    await _edit_screen(
        callback,
        _payment_result_text(payment_result, fallback_title=f"Подарок: {tariff.title}"),
        _bonus_gift_payment_methods_keyboard(tariff.code),
        screen_key="gift",
        answer_first=False,
    )
    return True


async def _show_manual_gift_payment(
    callback: CallbackQuery,
    *,
    method: str,
    tariff,
    user,
    intro_note: str | None = None,
) -> None:
    payment_method, details = _manual_payment_settings(method)
    record = await create_balance_aware_manual_payment_record(
        user_id=user.id,
        tariff_code=tariff.code,
        payment_method=payment_method,
        list_price_amount=int(getattr(tariff, "rub_price", 0) or 0),
        currency="RUB",
        duration_days=int(getattr(tariff, "duration_days", 0) or 0),
        metadata=_gift_payment_metadata(tariff=tariff, user=user, method=method),
        expires_at=utcnow() + timedelta(hours=config.manual_payment_review_hours),
    )
    text = manual_payment_details_text(
        tariff_title=f"Подарок: {tariff.title}",
        amount_rub=record.amount,
        list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
        balance_reserved_amount=record.balance_reserved_amount or 0,
        method_label=payment_method,
        request_id=record.id,
        details=details,
        review_hours=config.manual_payment_review_hours,
    )
    await _edit_screen(
        callback,
        _prefix_payment_text(text, intro_note),
        _bonus_gift_manual_payment_keyboard(record.id, tariff.code),
        screen_key="gift",
        answer_first=False,
    )


async def _show_platega_gift_payment(
    callback: CallbackQuery,
    *,
    method: str,
    tariff,
    user,
    breakdown: dict[str, int],
) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _bonus_gift_payment_methods_keyboard(tariff.code),
            screen_key="gift",
            answer_first=False,
        )
        return
    client = PlategaClient()
    if not client.configured:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _bonus_gift_payment_methods_keyboard(tariff.code),
            screen_key="gift",
            answer_first=False,
        )
        return

    record = await ensure_platega_payment_record(
        user_id=user.id,
        telegram_id=user.telegram_id,
        tariff_code=tariff.code,
        payment_method=payment_method,
        list_price_amount=int(getattr(tariff, "rub_price", 0) or 0),
        duration_days=int(getattr(tariff, "duration_days", 0) or 0),
        tariff_title=f"Подарок: {tariff.title}",
        payable_amount=breakdown["payable_amount"],
        payload_type=GIFT_SUBSCRIPTION_PRODUCT_TYPE,
        metadata_extra=_gift_payment_metadata(tariff=tariff, user=user, method=method),
        description=f"Amonora - Подарок {tariff.title}",
    )
    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            _bonus_gift_payment_methods_keyboard(tariff.code),
            screen_key="gift",
            answer_first=False,
        )
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=f"Подарок: {tariff.title}",
            amount_rub=record.amount,
            method_label=record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
            balance_reserved_amount=record.balance_reserved_amount or 0,
        ),
        _bonus_gift_external_payment_keyboard(checkout_url, tariff.code, record.id),
        screen_key="gift",
        answer_first=False,
    )


async def _show_existing_gift_payment_intent(callback: CallbackQuery, *, record, tariff) -> None:
    intro_note = _existing_open_payment_intro(record)
    payment_method = str(getattr(record, "payment_method", "") or "").strip().lower()
    if payment_method in MANUAL_PAYMENT_METHODS:
        if record.payment_status == "awaiting_admin_review":
            text = manual_payment_waiting_review_text(
                tariff_title=f"Подарок: {tariff.title}",
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            )
        else:
            _, details = _manual_payment_settings("sbp" if payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title=f"Подарок: {tariff.title}",
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
                balance_reserved_amount=record.balance_reserved_amount or 0,
                method_label=record.payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await _edit_screen(
            callback,
            _prefix_payment_text(text, intro_note),
            _bonus_gift_manual_payment_keyboard(record.id, tariff.code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            _prefix_payment_text(
                "Активный счёт уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            _bonus_gift_payment_methods_keyboard(tariff.code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await _edit_screen(
        callback,
        _prefix_payment_text(
            platega_payment_text(
                tariff_title=f"Подарок: {tariff.title}",
                amount_rub=record.amount,
                method_label=record.payment_method,
                checkout_label="страница оплаты",
                list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
                balance_reserved_amount=record.balance_reserved_amount or 0,
            ),
            intro_note,
        ),
        _bonus_gift_external_payment_keyboard(checkout_url, tariff.code, record.id),
        screen_key="gift",
        answer_first=False,
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


async def _show_manual_balance_topup_payment(
    callback: CallbackQuery,
    *,
    method: str,
    amount_rub: int,
    user,
    intro_note: str | None = None,
) -> None:
    payment_method, details = _manual_payment_settings(method)
    record = await create_balance_aware_manual_payment_record(
        user_id=user.id,
        tariff_code=_balance_topup_manual_tariff_code(amount_rub),
        payment_method=payment_method,
        list_price_amount=amount_rub,
        currency="RUB",
        duration_days=0,
        metadata={
            "payload_type": BALANCE_TOPUP_PRODUCT_TYPE,
            "product_type": BALANCE_TOPUP_PRODUCT_TYPE,
            "tariff_title": "Пополнение баланса",
            "telegram_id": user.telegram_id,
            "topup_amount": amount_rub,
            "method": method,
        },
        expires_at=utcnow() + timedelta(hours=config.manual_payment_review_hours),
    )
    text = manual_payment_details_text(
        tariff_title="Пополнение баланса",
        amount_rub=record.amount,
        list_price_amount=record.list_price_amount or amount_rub,
        balance_reserved_amount=0,
        method_label=payment_method,
        request_id=record.id,
        details=details,
        review_hours=config.manual_payment_review_hours,
    )
    await _edit_screen(
        callback,
        _prefix_payment_text(text, intro_note),
        _balance_manual_payment_keyboard(record.id, amount_rub),
        screen_key="balance_topup",
        answer_first=False,
    )


async def _show_platega_balance_topup_payment(callback: CallbackQuery, *, method: str, amount_rub: int, user) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _balance_payment_methods_keyboard(amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        return
    client = PlategaClient()
    if not client.configured:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _balance_payment_methods_keyboard(amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        return

    record = await ensure_platega_balance_topup_record(
        user_id=user.id,
        telegram_id=user.telegram_id,
        payment_method=payment_method,
        amount_rub=amount_rub,
    )
    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            _balance_payment_methods_keyboard(amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        return
    await _edit_screen(
        callback,
        balance_topup_payment_text(
            amount_rub=amount_rub,
            method_label=payment_method,
            checkout_label="страницу оплаты",
        ),
        _balance_external_payment_keyboard(checkout_url, amount_rub, record.id),
        screen_key="balance_topup",
        answer_first=False,
    )


async def _show_existing_balance_topup_payment_intent(callback: CallbackQuery, *, record, amount_rub: int) -> None:
    intro_note = _existing_open_payment_intro(record)
    payment_method = str(getattr(record, "payment_method", "") or "").strip().lower()
    if payment_method in MANUAL_PAYMENT_METHODS:
        if record.payment_status == "awaiting_admin_review":
            text = manual_payment_waiting_review_text(
                tariff_title="Пополнение баланса",
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or amount_rub,
                balance_reserved_amount=0,
                paid_amount=record.amount,
            )
        else:
            _, details = _manual_payment_settings("sbp" if payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title="Пополнение баланса",
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or amount_rub,
                balance_reserved_amount=0,
                method_label=record.payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await _edit_screen(
            callback,
            _prefix_payment_text(text, intro_note),
            _balance_manual_payment_keyboard(record.id, amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            _prefix_payment_text(
                "Активный счёт на пополнение уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            _balance_payment_methods_keyboard(amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return
    await _edit_screen(
        callback,
        _prefix_payment_text(
            balance_topup_payment_text(
                amount_rub=int(getattr(record, "list_price_amount", 0) or getattr(record, "amount", 0) or amount_rub),
                method_label=record.payment_method,
                checkout_label="страницу оплаты",
            ),
            intro_note,
        ),
        _balance_external_payment_keyboard(checkout_url, amount_rub, record.id),
        screen_key="balance_topup",
        answer_first=False,
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


async def _finish_device_slot_balance_only_payment(callback: CallbackQuery, *, user, context: dict) -> bool:
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
    await _edit_screen(
        callback,
        _payment_result_text(payment_result, fallback_title=_device_slot_title()),
        _device_slot_payment_methods_keyboard(),
        screen_key="device_slot",
        answer_first=False,
    )
    return True


async def _show_manual_device_slot_payment(
    callback: CallbackQuery,
    *,
    method: str,
    user,
    context: dict,
    intro_note: str | None = None,
) -> None:
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
    await _edit_screen(
        callback,
        _prefix_payment_text(text, intro_note),
        _device_slot_manual_payment_keyboard(record.id),
        screen_key="device_slot",
        answer_first=False,
    )


async def _show_platega_device_slot_payment(
    callback: CallbackQuery,
    *,
    method: str,
    user,
    context: dict,
    breakdown: dict[str, int],
) -> None:
    payment_method = platega_payment_method_for_choice(method)
    if payment_method is None:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        return
    client = PlategaClient()
    if not client.configured:
        await _edit_screen(
            callback,
            PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT,
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        return

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
    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            "Ссылка на оплату не пришла от провайдера. Попробуй создать счёт ещё раз.",
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=_device_slot_title(),
            amount_rub=record.amount,
            method_label=record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=record.list_price_amount or context["price_rub"],
            balance_reserved_amount=record.balance_reserved_amount or 0,
        ),
        _device_slot_external_payment_keyboard(checkout_url, record.id),
        screen_key="device_slot",
        answer_first=False,
    )


async def _show_existing_device_slot_payment_intent(callback: CallbackQuery, *, record, context: dict) -> None:
    intro_note = _existing_open_payment_intro(record)
    payment_method = str(getattr(record, "payment_method", "") or "").strip().lower()
    if payment_method in MANUAL_PAYMENT_METHODS:
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
            _, details = _manual_payment_settings("sbp" if payment_method == "sbp_manual" else "crypto")
            text = manual_payment_details_text(
                tariff_title=_device_slot_title(),
                amount_rub=record.amount,
                list_price_amount=record.list_price_amount or context["price_rub"],
                balance_reserved_amount=record.balance_reserved_amount or 0,
                method_label=record.payment_method,
                request_id=record.id,
                details=details,
                review_hours=config.manual_payment_review_hours,
            )
        await _edit_screen(
            callback,
            _prefix_payment_text(text, intro_note),
            _device_slot_manual_payment_keyboard(record.id),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Уже есть активная заявка", show_alert=True)
        return

    checkout_url = str(_payment_metadata(record).get("checkout_url") or "").strip()
    if not checkout_url:
        await _edit_screen(
            callback,
            _prefix_payment_text(
                "Активный счёт уже существует, но ссылка на оплату сейчас недоступна. Попробуй позже.",
                intro_note,
            ),
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Уже есть активный счёт", show_alert=True)
        return

    await _edit_screen(
        callback,
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
        _device_slot_external_payment_keyboard(checkout_url, record.id),
        screen_key="device_slot",
        answer_first=False,
    )
    await callback.answer("Уже есть активный счёт", show_alert=True)


def _screen_photo(screen_key: str) -> FSInputFile:
    filename = SCREEN_IMAGE_FILENAMES[screen_key]
    path = SCREEN_ASSETS_DIR / filename
    return FSInputFile(path=path, filename=filename)


async def _send_screen(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    screen_key: str,
) -> None:
    await message.answer_photo(
        photo=_screen_photo(screen_key),
        caption=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _remove_legacy_reply_keyboard(message: Message) -> None:
    try:
        await message.answer(
            "✅ Нижнее меню отключено. Используйте кнопки в карточке ниже.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except TelegramBadRequest:
        pass


async def _send_main_menu(message: Message, telegram_id: int) -> None:
    PROMO_INPUT_WAITERS.discard(int(telegram_id))
    summary = await _load_test_user_summary(telegram_id)
    await _send_screen(message, _main_menu_text(summary), _main_menu_keyboard(), screen_key="main_menu")


async def _send_trial_used_screen(message: Message) -> None:
    await _send_screen(message, TRIAL_ALREADY_USED_TEXT, _trial_used_keyboard(), screen_key="renew")


async def _send_support_screen(message: Message) -> None:
    await _send_screen(message, SUPPORT_SCREEN_TEXT, _support_keyboard(), screen_key="support")


async def _send_info_screen(message: Message) -> None:
    await _send_screen(message, INFO_SCREEN_TEXT, _info_keyboard(), screen_key="info")


async def _send_renew_screen(message: Message, telegram_id: int) -> None:
    summary = await _load_test_user_summary(telegram_id)
    user = await get_user_by_telegram_id(int(telegram_id))
    discount = await _load_pending_discount_payload(int(user.id)) if user is not None else None
    await _send_screen(
        message,
        f"{_renew_text(summary)}{_pending_discount_note(discount)}",
        _renew_keyboard(),
        screen_key="renew",
    )


async def _send_bonus_screen(message: Message, telegram_id: int) -> None:
    summary = await _load_bonus_summary(telegram_id)
    await _send_screen(message, _bonus_text(summary), _bonus_keyboard(summary), screen_key="bonus")


async def _send_my_subscription_screen(message: Message, telegram_id: int) -> None:
    summary = await _load_test_user_summary(telegram_id)
    await _send_screen(
        message,
        _subscription_text(summary),
        _subscription_keyboard(summary),
        screen_key="my_subscription",
    )


async def _send_my_devices_screen(message: Message, telegram_id: int) -> None:
    summary = await _load_test_user_summary(telegram_id)
    await _send_screen(
        message,
        _devices_page_text(summary),
        _my_devices_keyboard(summary),
        screen_key="my_devices",
    )


async def _show_returning_user_screen(message: Message, telegram_id: int) -> bool:
    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return False
    if has_active_access_from_user(user) or not getattr(user, "trial_used", False):
        await _send_main_menu(message, int(telegram_id))
        return True
    await _send_trial_used_screen(message)
    return True


def _extract_start_tracking(command: CommandObject | None) -> tuple[str | None, str | None]:
    if command is None or not command.args:
        return None, None
    raw_args = str(command.args).strip()
    if not raw_args:
        return None, None
    if raw_args.startswith("ref_"):
        referral_token = raw_args.split("_", 1)[1].strip() or None
        return referral_token, None
    return None, parse_channel_post_start_token(raw_args)


async def _track_start_attribution(telegram_user, command: CommandObject | None) -> None:
    telegram_id = int(telegram_user.id)
    referral_token, channel_post_token = _extract_start_tracking(command)
    if channel_post_token is None and referral_token is None:
        return

    user, _ = await get_or_create_user(
        telegram_id=telegram_id,
        username=getattr(telegram_user, "username", None),
        referred_by_telegram_id=None,
        skip_initial_analytics_attribution=bool(channel_post_token),
    )
    source_type = "organic_bot"
    source_key = "organic_bot"
    channel_item_id = None
    if channel_post_token:
        touch = await register_channel_post_touch(
            channel_post_token,
            user_id=int(user.id),
            telegram_id=telegram_id,
        )
        if touch is not None:
            source_type = "channel_post"
            raw_source_key = getattr(touch, "source_key", None)
            if raw_source_key is None and isinstance(touch, dict):
                raw_source_key = touch.get("source_key")
            source_key = str(raw_source_key or channel_post_token).strip().lower() or channel_post_token
            raw_channel_item_id = getattr(touch, "item_id", None)
            if raw_channel_item_id is None and isinstance(touch, dict):
                raw_channel_item_id = touch.get("item_id")
            if isinstance(raw_channel_item_id, (str, int)):
                channel_item_id = int(raw_channel_item_id) or None
    else:
        await safe_upsert_user_attribution(
            user_id=int(user.id),
            telegram_id=telegram_id,
            source_type="organic_bot",
            source_key="organic_bot",
            seen_at=getattr(user, "created_at", None),
        )

    await emit_bot_start_event(
        user_id=int(user.id),
        telegram_id=telegram_id,
        source_type=source_type,
        source_key=source_key,
        channel_item_id=channel_item_id,
    )

    referral_binding = await bind_referrer_by_token(int(user.id), referral_token)
    if referral_binding.get("bound") and referral_binding.get("referrer_telegram_id"):
        await send_user_message(int(referral_binding["referrer_telegram_id"]), referral_registered_text())


async def _edit_trial_used_screen(callback: CallbackQuery) -> None:
    PROMO_INPUT_WAITERS.discard(int(callback.from_user.id))
    await _edit_screen(callback, TRIAL_ALREADY_USED_TEXT, _trial_used_keyboard(), screen_key="renew")


async def _redirect_if_returning_user(callback: CallbackQuery) -> bool:
    user = await get_user_by_telegram_id(int(callback.from_user.id))
    if user is None:
        return False
    if has_active_access_from_user(user) or not getattr(user, "trial_used", False):
        summary = await _load_test_user_summary(int(callback.from_user.id))
        await _edit_screen(
            callback,
            _main_menu_text(summary),
            _main_menu_keyboard(),
            screen_key="main_menu",
        )
        return True
    await _edit_trial_used_screen(callback)
    return True


async def _activate_test_bot_trial(telegram_user) -> object | None:
    user, _ = await get_or_create_user(
        telegram_id=int(telegram_user.id),
        username=getattr(telegram_user, "username", None),
        referred_by_telegram_id=None,
    )
    if has_active_access_from_user(user):
        return user
    if getattr(user, "trial_used", False):
        return user
    try:
        activated_user = await activate_trial(int(user.id))
    except ValueError:
        activated_user = await get_user_by_telegram_id(int(telegram_user.id))
    return activated_user or user


async def _is_trial_channel_subscription_confirmed(bot: Bot, user_id: int) -> bool:
    if await is_user_subscribed(bot, config.channel_id, user_id):
        return True

    main_bot_token = (config.bot_token or "").strip()
    current_bot_token = (getattr(bot, "token", None) or "").strip()
    if not main_bot_token or main_bot_token == current_bot_token:
        return False

    try:
        fallback_bot = Bot(token=main_bot_token)
    except Exception:
        return False
    try:
        return await is_user_subscribed(fallback_bot, config.channel_id, user_id)
    finally:
        await fallback_bot.session.close()


async def _edit_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    screen_key: str,
    answer_first: bool = True,
) -> None:
    if answer_first:
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=_screen_photo(screen_key),
                caption=text,
                parse_mode="HTML",
            ),
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        lowered = str(exc).lower()
        if "message is not modified" not in lowered:
            await callback.message.answer_photo(
                photo=_screen_photo(screen_key),
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    except Exception:
        logger.exception("Failed to render v2 screen: screen_key=%s", screen_key)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)


async def _ack_callback_quietly(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass


async def _send_legacy_profile(callback: CallbackQuery, profile_key: str, runtime) -> None:
    profile = runtime.profile
    if profile.delivery_kind == "config":
        config_file = BufferedInputFile(runtime.link.encode("utf-8"), filename=f"{profile.key}.conf")
        await callback.message.answer_document(
            document=config_file,
            caption=_legacy_profile_text(runtime),
            parse_mode="HTML",
            reply_markup=_legacy_profile_keyboard(profile_key, supports_transfer=runtime.supports_transfer),
        )
        return

    qr_buffer = generate_qr_image(runtime.link)
    qr_file = BufferedInputFile(qr_buffer.getvalue(), filename=f"{runtime.profile.key}.png")
    await callback.message.answer_photo(
        photo=qr_file,
        caption=_legacy_profile_text(runtime),
        parse_mode="HTML",
        reply_markup=_legacy_profile_keyboard(profile_key, supports_transfer=runtime.supports_transfer),
    )


async def _deny_if_needed(target: Message | CallbackQuery) -> bool:
    telegram_id = getattr(getattr(target, "from_user", None), "id", None)
    if is_test_bot_allowed(telegram_id):
        return False
    if isinstance(target, CallbackQuery):
        await target.answer("Доступ ограничен", show_alert=True)
    else:
        await target.answer(DENIED_TEXT)
    return True


@router.message(CommandStart())
async def v2_start_handler(message: Message, command: CommandObject | None = None) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _track_start_attribution(message.from_user, command)
    if await _show_returning_user_screen(message, int(message.from_user.id)):
        return
    await _send_screen(message, AGREEMENT_TEXT, _agreement_keyboard(), screen_key="agreement")


@router.callback_query(F.data == V2_SHOW_AGREEMENT_CALLBACK)
async def v2_show_agreement_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, AGREEMENT_TEXT, _agreement_keyboard(), screen_key="agreement")


@router.message(Command("menu"))
async def v2_menu_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_main_menu(message, int(message.from_user.id))


@router.message(Command("support"))
@router.message(F.text.in_({"🛟 Поддержка", "Поддержка"}))
async def v2_support_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_support_screen(message)


@router.message(F.text.in_({"📚 Информация", "Информация", "📡 Канал", "Канал"}))
async def v2_info_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_info_screen(message)


@router.message(F.text.in_({"💳 Купить", "Продлить", "💳 Продлить"}))
async def v2_renew_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_renew_screen(message, int(message.from_user.id))


@router.message(F.text.in_({"🎁 Реферальная система", "🎁 Бонусная система", "Бонусная система"}))
async def v2_bonus_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_bonus_screen(message, int(message.from_user.id))


@router.message(F.text.in_({"👤 Личный кабинет", "Кабинет", "🏠 Главная"}))
async def v2_legacy_home_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_main_menu(message, int(message.from_user.id))


@router.message(F.text == "📱 Устройства")
async def v2_legacy_devices_message_handler(message: Message) -> None:
    await _remove_legacy_reply_keyboard(message)
    await _send_my_devices_screen(message, int(message.from_user.id))


@router.message(AwaitingPromoInputFilter())
async def v2_bonus_promo_message_handler(message: Message) -> None:
    telegram_id = int(message.from_user.id)
    if telegram_id not in PROMO_INPUT_WAITERS:
        return
    PROMO_INPUT_WAITERS.discard(telegram_id)
    user = await get_user_by_telegram_id(telegram_id)
    if user is None:
        await message.answer("Пользователь не найден. Нажмите /start")
        return
    result = await redeem_promo_code_for_user(int(user.id), message.text or "")
    if not result.get("ok"):
        await _send_screen(
            message,
            (
                "❌ <b>Не удалось применить код</b>\n\n"
                f"{result.get('error') or 'Попробуйте ещё раз позже.'}"
            ),
            _bonus_promo_keyboard(),
            screen_key="promo",
        )
        return
    if str(result.get("kind") or "").strip().lower() == PROMO_KIND_DISCOUNT_PERCENT:
        await _send_screen(
            message,
            (
                "✅ <b>Промокод применён</b>\n\n"
                f"Активирована скидка <b>{int(result.get('discount_percent') or 0)}%</b> "
                "на ближайшую оплату подписки.\n\n"
                "Теперь откройте «Продлить» и оформите оплату со скидкой."
            ),
            _bonus_promo_keyboard(),
            screen_key="promo",
        )
        return
    expires_at = result.get("expires_at")
    expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at is not None else "—"
    await _send_screen(
        message,
        (
            "✅ <b>Код применён</b>\n\n"
            f"Доступ продлён на <b>{int(result.get('grant_days') or 0)} дн.</b>\n"
            f"Новый срок действия: <b>{expires_text}</b>"
            + ("\n\n⚠️ Доступ продлён, но синхронизация подключения завершилась с предупреждением." if result.get("sync_failed") else "")
        ),
        _bonus_promo_keyboard(),
        screen_key="promo",
    )


@router.callback_query(F.data == V2_ACCEPT_TERMS_CALLBACK)
async def v2_accept_terms_callback(callback: CallbackQuery) -> None:
    if await _redirect_if_returning_user(callback):
        return
    await _edit_screen(callback, TRIAL_INTRO_TEXT, _trial_keyboard(), screen_key="trial")


@router.callback_query(F.data == V2_CHECK_SUBSCRIPTION_CALLBACK)
async def v2_check_subscription_callback(callback: CallbackQuery) -> None:
    if await _redirect_if_returning_user(callback):
        return
    if not await _is_trial_channel_subscription_confirmed(callback.bot, callback.from_user.id):
        await callback.answer(SUBSCRIPTION_ALERT_TEXT, show_alert=True)
        return
    await _activate_test_bot_trial(callback.from_user)
    await _edit_screen(callback, TRIAL_READY_TEXT, _trial_ready_keyboard(), screen_key="finish")


@router.callback_query(F.data == V2_TRIAL_READY_CALLBACK)
async def v2_trial_ready_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, TRIAL_READY_TEXT, _trial_ready_keyboard(), screen_key="finish")


@router.callback_query(F.data == V2_GUIDES_CALLBACK)
async def v2_guides_callback(callback: CallbackQuery) -> None:
    await _edit_screen(
        callback,
        GUIDES_CHOICE_TEXT,
        _guides_keyboard(back_callback=V2_TRIAL_READY_CALLBACK),
        screen_key="instruction",
    )


@router.callback_query(F.data == V2_INFO_GUIDES_CALLBACK)
async def v2_info_guides_callback(callback: CallbackQuery) -> None:
    await _edit_screen(
        callback,
        GUIDES_CHOICE_TEXT,
        _guides_keyboard(back_callback=V2_INFO_CALLBACK),
        screen_key="instruction",
    )


@router.callback_query(F.data == V2_MENU_CALLBACK)
async def v2_main_menu_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(callback, _main_menu_text(summary), _main_menu_keyboard(), screen_key="main_menu", answer_first=False)


@router.callback_query(F.data == V2_BACK_TO_MENU_CALLBACK)
async def v2_back_to_menu_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(callback, _main_menu_text(summary), _main_menu_keyboard(), screen_key="main_menu", answer_first=False)


@router.callback_query(F.data == "home:cabinet")
async def v2_legacy_home_cabinet_callback(callback: CallbackQuery) -> None:
    await v2_main_menu_callback(callback)


@router.callback_query(F.data == "home:devices")
async def v2_legacy_home_devices_callback(callback: CallbackQuery) -> None:
    await v2_my_devices_callback(callback)


@router.callback_query(F.data == "home:tariffs")
@router.callback_query(F.data == "home:balance")
async def v2_legacy_home_renew_callback(callback: CallbackQuery) -> None:
    await v2_renew_callback(callback)


@router.callback_query(F.data == "home:subscription_page")
async def v2_legacy_home_subscription_page_callback(callback: CallbackQuery) -> None:
    await v2_key_menu_callback(callback)


@router.callback_query(F.data == "home:info")
async def v2_legacy_home_info_callback(callback: CallbackQuery) -> None:
    await v2_info_callback(callback)


@router.callback_query(F.data == "home:referrals")
async def v2_legacy_home_referrals_callback(callback: CallbackQuery) -> None:
    await v2_bonus_callback(callback)


@router.callback_query(F.data == V2_MY_SUBSCRIPTION_CALLBACK)
async def v2_my_subscription_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(
        callback,
        _subscription_text(summary),
        _subscription_keyboard(summary),
        screen_key="my_subscription",
        answer_first=False,
    )


@router.callback_query(F.data == V2_KEY_MENU_CALLBACK)
async def v2_key_menu_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    if not summary.subscription_page_url and not summary.happ_subscription_url and not _subscription_feed_url(summary):
        await callback.answer("Ссылка пока недоступна.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _subscription_key_menu_text(summary),
        _subscription_key_menu_keyboard(summary),
        screen_key="key",
        answer_first=False,
    )


@router.callback_query(F.data == V2_RENEW_CALLBACK)
async def v2_renew_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    user = await get_user_by_telegram_id(int(callback.from_user.id))
    discount = await _load_pending_discount_payload(int(user.id)) if user is not None else None
    await _edit_screen(
        callback,
        f"{_renew_text(summary)}{_pending_discount_note(discount)}",
        _renew_keyboard(),
        screen_key="renew",
        answer_first=False,
    )


@router.callback_query(F.data == V2_SUPPORT_CALLBACK)
async def v2_support_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, SUPPORT_SCREEN_TEXT, _support_keyboard(), screen_key="support")


@router.callback_query(F.data == V2_BONUS_CALLBACK)
async def v2_bonus_callback(callback: CallbackQuery) -> None:
    PROMO_INPUT_WAITERS.discard(int(callback.from_user.id))
    summary = await _load_bonus_summary(int(callback.from_user.id))
    await _edit_screen(callback, _bonus_text(summary), _bonus_keyboard(summary), screen_key="bonus")


@router.callback_query(F.data == V2_BONUS_STATS_CALLBACK)
async def v2_bonus_stats_callback(callback: CallbackQuery) -> None:
    summary = await _load_bonus_summary(int(callback.from_user.id))
    await _edit_screen(callback, _bonus_stats_text(summary), _bonus_stats_keyboard(), screen_key="bonus_stats")


@router.callback_query(F.data == V2_BONUS_PROMO_CALLBACK)
async def v2_bonus_promo_callback(callback: CallbackQuery) -> None:
    PROMO_INPUT_WAITERS.add(int(callback.from_user.id))
    await _edit_screen(callback, BONUS_PROMO_TEXT, _bonus_promo_keyboard(), screen_key="promo")


@router.callback_query(F.data == V2_BONUS_GIFT_CALLBACK)
async def v2_bonus_gift_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, BONUS_GIFT_TEXT, _bonus_gift_keyboard(), screen_key="gift")


@router.callback_query(F.data == V2_BONUS_GIFT_TARIFFS_CALLBACK)
async def v2_bonus_gift_tariffs_callback(callback: CallbackQuery) -> None:
    await _edit_screen(
        callback,
        _bonus_gift_tariffs_text(),
        _bonus_gift_tariffs_keyboard(),
        screen_key="gift",
    )


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_TARIFF_PREFIX))
async def v2_bonus_gift_tariff_callback(callback: CallbackQuery) -> None:
    tariff_code = callback.data.rsplit(":", 1)[-1]
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф пока не настроен.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _bonus_gift_payment_text(tariff),
        _bonus_gift_payment_keyboard(tariff_code),
        screen_key="gift",
    )


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_PAY_PREFIX))
async def v2_bonus_gift_pay_callback(callback: CallbackQuery) -> None:
    tariff_code = callback.data.removeprefix(V2_BONUS_GIFT_PAY_PREFIX)
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф пока не настроен.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _bonus_gift_payment_methods_text(tariff),
        _bonus_gift_payment_methods_keyboard(tariff_code),
        screen_key="gift",
    )


@router.callback_query(
    F.data.startswith(V2_BONUS_GIFT_METHOD_PREFIX)
    & ~F.data.startswith(V2_BONUS_GIFT_MANUAL_PAID_PREFIX)
    & ~F.data.startswith(V2_BONUS_GIFT_MANUAL_STATUS_PREFIX)
    & ~F.data.startswith(V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX)
    & ~F.data.startswith(V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX)
)
async def v2_bonus_gift_payment_method_callback(callback: CallbackQuery) -> None:
    method, tariff_code = str(callback.data or "").removeprefix(V2_BONUS_GIFT_METHOD_PREFIX).split(":", 1)
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден.", show_alert=True)
        return
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start", show_alert=True)
        return

    price_rub = int(getattr(tariff, "rub_price", 0) or 0)
    duration_days = int(getattr(tariff, "duration_days", 0) or 0)
    breakdown = await build_balance_breakdown_for_price(user.id, price_rub)
    if breakdown["payable_amount"] <= 0:
        finished = await _finish_balance_only_gift_payment(callback, user=user, tariff=tariff)
        await callback.answer("Подарок уже оплачен с Баланса" if finished else "Не удалось оформить оплату", show_alert=not finished)
        return

    existing_record = await get_open_payment_intent_for_user(
        user_id=user.id,
        tariff_code=tariff.code,
        list_price_amount=price_rub,
        duration_days=duration_days,
        product_type=GIFT_SUBSCRIPTION_PRODUCT_TYPE,
    )
    if existing_record is not None:
        await _show_existing_gift_payment_intent(callback, record=existing_record, tariff=tariff)
        return

    try:
        if method == "sbp":
            if sbp_tariff_uses_platega():
                await _show_platega_gift_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    breakdown=breakdown,
                )
                return
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Автоматический QR через СБП временно недоступен.</b>\n"
                    "Мы сразу переключили оплату на ручную заявку, чтобы подарок всё равно можно было купить."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_gift_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    intro_note=intro_note,
                )
                return
            await callback.answer("СБП сейчас недоступна", show_alert=True)
            return

        if method == "sbp_manual":
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Если автоматический QR по СБП не сработал, используй эту ручную заявку.</b>\n"
                    "После перевода администратор подтвердит покупку подарка вручную."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_gift_payment(
                    callback,
                    method="sbp",
                    tariff=tariff,
                    user=user,
                    intro_note=intro_note,
                )
                return
            await callback.answer("Ручная СБП сейчас недоступна", show_alert=True)
            return

        if method == "crypto":
            if config.enable_platega_crypto_user_flow:
                await _show_platega_gift_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    breakdown=breakdown,
                )
                return
            if config.enable_manual_crypto_user_flow:
                await _show_manual_gift_payment(callback, method=method, tariff=tariff, user=user)
                return
            await callback.answer("Криптовалюта сейчас недоступна", show_alert=True)
            return
    except PlategaError as exc:
        logger.warning("Failed to create gift payment in test bot: %s", exc)
        await callback.answer("Не удалось создать оплату. Попробуйте ещё раз позже.", show_alert=True)
        return
    await callback.answer("Способ оплаты не поддерживается. Откройте экран заново.", show_alert=True)


@router.callback_query(F.data == "testv2:bonus:no-link")
async def v2_bonus_no_link_callback(callback: CallbackQuery) -> None:
    await callback.answer("Ссылка появится после активации аккаунта.", show_alert=True)


@router.callback_query(F.data == V2_INFO_CALLBACK)
async def v2_info_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, INFO_SCREEN_TEXT, _info_keyboard(), screen_key="info")


@router.callback_query(F.data == "info:root")
@router.callback_query(F.data == "info:faq")
async def v2_legacy_info_root_callback(callback: CallbackQuery) -> None:
    await v2_info_callback(callback)


@router.callback_query(F.data == "info:instructions")
async def v2_legacy_info_instructions_callback(callback: CallbackQuery) -> None:
    await v2_info_guides_callback(callback)


@router.callback_query(F.data == V2_INFO_DOCS_CALLBACK)
@router.callback_query(F.data == "info:docs")
async def v2_info_docs_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, INFO_DOCUMENTS_TEXT, _info_documents_keyboard(), screen_key="documents")


@router.callback_query(F.data == V2_DEVICES_CALLBACK)
async def v2_devices_callback(callback: CallbackQuery) -> None:
    await _edit_screen(callback, DEVICE_CHOICE_TEXT, _devices_keyboard(), screen_key="first_connection")


@router.callback_query(F.data.startswith("testv2:device:"))
async def v2_device_instruction_callback(callback: CallbackQuery) -> None:
    device_key = callback.data.split(":")[-1]
    if device_key not in DEVICE_GUIDES:
        await callback.answer("Устройство пока не настроено.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _device_instruction_text(device_key),
        _device_guide_keyboard(device_key, back_callback=V2_DEVICES_CALLBACK),
        screen_key="instruction",
    )


@router.callback_query(F.data.startswith(V2_GUIDE_PREFIX))
async def v2_guide_instruction_callback(callback: CallbackQuery) -> None:
    device_key = callback.data.removeprefix(V2_GUIDE_PREFIX)
    if device_key not in DEVICE_GUIDES:
        await callback.answer("Устройство пока не настроено.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _device_instruction_text(device_key),
        _device_guide_keyboard(device_key, back_callback=V2_GUIDES_CALLBACK),
        screen_key="instruction",
    )


@router.callback_query(F.data.startswith("testv2:installed:"))
async def v2_installed_callback(callback: CallbackQuery) -> None:
    device_key = callback.data.split(":")[-1]
    if device_key not in DEVICE_GUIDES:
        await callback.answer("Устройство пока не настроено.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _after_install_text(device_key),
        _after_install_keyboard(device_key),
        screen_key="finish",
    )


@router.callback_query(F.data == V2_MY_DEVICES_CALLBACK)
async def v2_my_devices_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(
        callback,
        _devices_page_text(summary),
        _my_devices_keyboard(summary),
        screen_key="my_devices",
        answer_first=False,
    )


@router.callback_query(F.data == V2_DEVICE_SLOT_CALLBACK)
async def v2_device_slot_callback(callback: CallbackQuery) -> None:
    await _edit_screen(
        callback,
        _device_slot_methods_text(device_slot_unit_price_rub()),
        _device_slot_payment_methods_keyboard(),
        screen_key="device_slot",
    )


@router.callback_query(F.data.startswith("testv2:mydevices:view:"))
async def v2_my_device_detail_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    parts = str(callback.data or "").split(":")
    if len(parts) >= 5:
        kind_suffix = parts[-2]
        device_raw_id = parts[-1]
    else:
        kind_suffix = "vpn"
        device_raw_id = parts[-1]
    device_id = int(device_raw_id)
    device_kind = "public_slot" if kind_suffix == "public" else "vpn_client"
    summary = await _load_test_user_summary(int(callback.from_user.id))
    device = next(
        (
            item
            for item in summary.devices
            if str(item.get("kind") or "vpn_client").strip().lower() == device_kind and int(item["id"]) == device_id
        ),
        None,
    )
    if device is None:
        await callback.answer("Устройство не найдено.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _device_detail_text(device),
        _device_detail_keyboard(device_kind, device_id, device.get("connection_uri")),
        screen_key="my_devices",
        answer_first=False,
    )


@router.callback_query(F.data.startswith(V2_DEVICE_DELETE_PREFIX))
async def v2_my_device_delete_callback(callback: CallbackQuery) -> None:
    parts = str(callback.data or "").split(":")
    if len(parts) >= 5:
        delete_kind = parts[-2]
        device_raw_id = parts[-1]
    else:
        delete_kind = "vpn"
        device_raw_id = parts[-1]
    device_id = int(device_raw_id)
    if delete_kind == "public":
        user = await get_user_by_telegram_id(int(callback.from_user.id))
        if user is None:
            await callback.answer(USER_NOT_FOUND_TEXT, show_alert=True)
            return
        cleared = await clear_public_subscription_device_slot_binding(
            int(user.id),
            slot_index=device_id,
            binding_keys={
                "feed_device_fingerprint_hash",
                "feed_device_label",
                "device_name",
                "device_model",
                "device_type",
                "platform_name",
                "os_name",
                "os_version",
                "app_version",
                "source_ip",
                "user_agent",
                "install_id",
                "feed_device_bound_at",
                "feed_device_last_seen_at",
                "subscription_client",
            },
        )
        if not cleared:
            await callback.answer(delete_device_not_found_text(), show_alert=True)
            return
        refreshed_summary = await _load_test_user_summary(int(callback.from_user.id))
        await _edit_screen(
            callback,
            _devices_page_text(refreshed_summary),
            _my_devices_keyboard(refreshed_summary),
            screen_key="my_devices",
        )
        return
    user, vpn_client = await _get_owned_test_device_for_telegram(int(callback.from_user.id), device_id)
    if user is None:
        await callback.answer(USER_NOT_FOUND_TEXT, show_alert=True)
        return
    if vpn_client is None:
        await callback.answer(delete_device_not_found_text(), show_alert=True)
        return

    client_data = json.loads(vpn_client.client_data) if vpn_client.client_data else {}
    country_code = str(client_data.get("country_code") or "de").strip().lower() or "de"
    try:
        inbound_id = client_data.get("inbound_id")

        if vpn_client.protocol == "vless":
            provisioner = get_vless_provisioner(country_code, client_data.get("provider_type"))
            try:
                result = await provisioner.delete_vless_client(
                    client_uuid=vpn_client.xui_client_id or vpn_client.client_uuid,
                    email=vpn_client.email,
                    metadata=client_data,
                )
            finally:
                await provisioner.close()
        elif vpn_client.protocol == "trojan":
            xui_client = XUIClient(country_code=country_code)
            try:
                success = await xui_client.login()
                if not success:
                    await callback.answer(PANEL_CONNECTION_ERROR_TEXT, show_alert=True)
                    return
                result = await xui_client.delete_trojan_client(
                    inbound_id=inbound_id or 4,
                    client_uuid=vpn_client.xui_client_id or vpn_client.client_uuid,
                    email=vpn_client.email,
                )
            finally:
                await xui_client.close()
        else:
            await callback.answer(PANEL_OPERATION_ERROR_TEXT, show_alert=True)
            return

        if not result.get("success"):
            await callback.answer(PANEL_OPERATION_ERROR_TEXT, show_alert=True)
            return

        deleted = await delete_vpn_client_and_return(device_id)
        if deleted is None:
            await callback.answer(delete_device_not_found_text(), show_alert=True)
            return
    except Exception:
        await callback.answer(PANEL_OPERATION_ERROR_TEXT, show_alert=True)
        return

    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(
        callback,
        _devices_page_text(summary),
        _my_devices_keyboard(summary),
        screen_key="my_devices",
    )


@router.callback_query(F.data == V2_COPY_KEY_CALLBACK)
async def v2_copy_key_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    summary = await _load_test_user_summary(int(callback.from_user.id))
    if not _subscription_connection_uri(summary):
        await callback.answer("Ссылка пока недоступна.", show_alert=True)
        return
    await _edit_screen(
        callback,
        _subscription_key_text(summary),
        _subscription_key_keyboard(summary),
        screen_key="key",
        answer_first=False,
    )


@router.callback_query(F.data.startswith("testv2:renew:tariff:"))
async def v2_renew_methods_callback(callback: CallbackQuery) -> None:
    tariff_code = callback.data.rsplit(":", 1)[-1]
    if tariff_code == "balance":
        await _ack_callback_quietly(callback)
        summary = await _load_test_user_summary(int(callback.from_user.id))
        await _edit_screen(
            callback,
            _balance_topup_text(summary),
            _balance_topup_keyboard(),
            screen_key="balance_topup",
            answer_first=False,
        )
        return

    tariff = get_tariff(tariff_code)
    user = await get_user_by_telegram_id(int(callback.from_user.id))
    discount = await _load_pending_discount_payload(int(user.id)) if user is not None else None
    await _edit_screen(
        callback,
        _renew_payment_methods_text_with_discount(tariff, discount),
        _renew_payment_methods_keyboard(tariff.code),
        screen_key="renew",
    )


@router.callback_query(F.data.startswith(V2_BALANCE_TOPUP_AMOUNT_PREFIX))
async def v2_balance_topup_amount_callback(callback: CallbackQuery) -> None:
    amount_rub = int(callback.data.rsplit(":", 1)[-1])
    summary = await _load_test_user_summary(int(callback.from_user.id))
    await _edit_screen(
        callback,
        _balance_payment_methods_text(summary, amount_rub),
        _balance_payment_methods_keyboard(amount_rub),
        screen_key="balance_topup",
    )


@router.callback_query(
    F.data.startswith(V2_RENEW_METHOD_PREFIX)
    & ~F.data.startswith(V2_RENEW_MANUAL_PAID_PREFIX)
    & ~F.data.startswith(V2_RENEW_MANUAL_STATUS_PREFIX)
    & ~F.data.startswith(V2_RENEW_MANUAL_CANCEL_PREFIX)
    & ~F.data.startswith(V2_RENEW_EXTERNAL_CHECK_PREFIX)
)
async def v2_renew_payment_method_callback(callback: CallbackQuery) -> None:
    await _ack_callback_quietly(callback)
    try:
        method, tariff_code = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_RENEW_METHOD_PREFIX),
            context="renew method",
        )
    except ValueError:
        await callback.answer("Не удалось распознать способ оплаты. Откройте экран заново.", show_alert=True)
        return
    tariff = get_tariff(tariff_code)
    if tariff is None:
        await callback.answer("Тариф не найден.", show_alert=True)
        return
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start", show_alert=True)
        return
    discount = await _load_pending_discount_payload(int(user.id))
    pricing = _effective_tariff_price(tariff, discount)
    breakdown = await build_balance_breakdown_for_price(user.id, pricing["payable_price"])
    if breakdown["payable_amount"] <= 0:
        finished = await _finish_balance_only_subscription_payment(callback, user=user, tariff=tariff, discount=discount)
        await callback.answer("Тариф уже оплачен с Баланса" if finished else "Не удалось оформить оплату", show_alert=not finished)
        return

    existing_record = await get_open_payment_intent_for_user(
        user_id=user.id,
        tariff_code=tariff.code,
        list_price_amount=pricing["payable_price"],
        duration_days=tariff.duration_days,
    )
    existing_method = str(getattr(existing_record, "payment_method", "") or "").strip().lower() if existing_record is not None else ""
    should_reuse_existing = existing_record is not None
    if method == "sbp_manual" and existing_method not in MANUAL_PAYMENT_METHODS:
        should_reuse_existing = False
    if should_reuse_existing:
        await _show_existing_subscription_payment_intent(callback, record=existing_record, tariff=tariff, discount=discount)
        return

    try:
        if method == "sbp":
            if sbp_tariff_uses_platega():
                await _show_platega_subscription_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    discount=discount,
                    breakdown=breakdown,
                )
                return
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Автоматический QR через СБП временно недоступен.</b>\n"
                    "Мы сразу переключили оплату на ручную заявку, чтобы покупка всё равно прошла."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_subscription_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    discount=discount,
                    intro_note=intro_note,
                )
                return
            await callback.answer("СБП сейчас недоступна", show_alert=True)
            return

        if method == "sbp_manual":
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Если автоматический QR по СБП не сработал, используй эту ручную заявку.</b>\n"
                    "После перевода администратор подтвердит оплату вручную."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_subscription_payment(
                    callback,
                    method="sbp",
                    tariff=tariff,
                    user=user,
                    discount=discount,
                    intro_note=intro_note,
                )
                return
            await callback.answer("Ручная СБП сейчас недоступна", show_alert=True)
            return

        if method == "crypto":
            if config.enable_platega_crypto_user_flow:
                await _show_platega_subscription_payment(
                    callback,
                    method=method,
                    tariff=tariff,
                    user=user,
                    discount=discount,
                    breakdown=breakdown,
                )
                return
            if config.enable_manual_crypto_user_flow:
                await _show_manual_subscription_payment(callback, method=method, tariff=tariff, user=user, discount=discount)
                return
            await callback.answer("Криптовалюта сейчас недоступна", show_alert=True)
            return
    except PlategaError as exc:
        logger.warning("Failed to create renew payment in test bot: %s", exc)
        await callback.answer("Не удалось создать оплату. Попробуйте ещё раз позже.", show_alert=True)
        return
    except Exception:
        logger.exception("Unhandled error in renew payment method callback: data=%s", callback.data)
        await callback.answer("Не удалось обработать оплату. Попробуйте ещё раз.", show_alert=True)
        return
    await callback.answer("Способ оплаты не поддерживается. Откройте экран заново.", show_alert=True)


@router.callback_query(
    F.data.startswith(V2_BALANCE_METHOD_PREFIX)
    & ~F.data.startswith(V2_BALANCE_MANUAL_PAID_PREFIX)
    & ~F.data.startswith(V2_BALANCE_MANUAL_STATUS_PREFIX)
    & ~F.data.startswith(V2_BALANCE_MANUAL_CANCEL_PREFIX)
    & ~F.data.startswith(V2_BALANCE_EXTERNAL_CHECK_PREFIX)
)
async def v2_balance_payment_method_callback(callback: CallbackQuery) -> None:
    try:
        method, amount_raw = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_BALANCE_METHOD_PREFIX),
            context="balance method",
        )
    except ValueError:
        await callback.answer("Не удалось распознать способ оплаты. Откройте экран заново.", show_alert=True)
        return
    amount_rub = int(amount_raw)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start", show_alert=True)
        return

    existing_record = await _find_open_balance_topup_intent(user.id, amount_rub)
    if existing_record is not None:
        await _show_existing_balance_topup_payment_intent(callback, record=existing_record, amount_rub=amount_rub)
        return

    try:
        if method == "sbp":
            if sbp_balance_topup_uses_platega():
                await _show_platega_balance_topup_payment(callback, method=method, amount_rub=amount_rub, user=user)
                return
            if sbp_tariff_uses_manual():
                await _show_manual_balance_topup_payment(callback, method="sbp", amount_rub=amount_rub, user=user)
                return
            await callback.answer("СБП для пополнения баланса сейчас недоступна", show_alert=True)
            return

        if method == "sbp_manual":
            if sbp_tariff_uses_manual():
                await _show_manual_balance_topup_payment(callback, method="sbp", amount_rub=amount_rub, user=user)
                return
            await callback.answer("Ручная СБП для пополнения пока недоступна", show_alert=True)
            return

        if method == "crypto":
            if config.enable_platega_crypto_user_flow:
                await _show_platega_balance_topup_payment(callback, method=method, amount_rub=amount_rub, user=user)
                return
            if config.enable_manual_crypto_user_flow:
                await _show_manual_balance_topup_payment(callback, method=method, amount_rub=amount_rub, user=user)
                return
            await callback.answer("Криптовалюта для пополнения сейчас недоступна", show_alert=True)
            return
    except PlategaError as exc:
        logger.warning("Failed to create balance top-up payment in test bot: %s", exc)
        await callback.answer("Не удалось создать оплату. Попробуйте ещё раз позже.", show_alert=True)
        return
    await callback.answer("Способ оплаты не поддерживается. Откройте экран заново.", show_alert=True)


@router.callback_query(
    F.data.startswith(V2_DEVICE_SLOT_METHOD_PREFIX)
    & ~F.data.startswith(V2_DEVICE_SLOT_MANUAL_PAID_PREFIX)
    & ~F.data.startswith(V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX)
    & ~F.data.startswith(V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX)
    & ~F.data.startswith(V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX)
)
async def v2_device_slot_payment_method_callback(callback: CallbackQuery) -> None:
    method = str(callback.data or "").removeprefix(V2_DEVICE_SLOT_METHOD_PREFIX)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажмите /start", show_alert=True)
        return
    context = await _device_slot_context_for_user(user)
    if context is None or not context["eligible"]:
        await _edit_screen(
            callback,
            _device_slot_unavailable_text(),
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Доп. устройства недоступны", show_alert=True)
        return
    if context["remaining_capacity"] <= 0:
        await callback.answer("Максимальный лимит устройств уже достигнут", show_alert=True)
        return

    breakdown = await build_balance_breakdown_for_price(user.id, context["price_rub"])
    if breakdown["payable_amount"] <= 0:
        finished = await _finish_device_slot_balance_only_payment(callback, user=user, context=context)
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

    try:
        if method == "sbp":
            if sbp_tariff_uses_platega():
                await _show_platega_device_slot_payment(callback, method=method, user=user, context=context, breakdown=breakdown)
                return
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Автоматический QR через СБП временно недоступен.</b>\n"
                    "Мы сразу переключили оплату на ручную заявку, чтобы слот всё равно можно было купить."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_device_slot_payment(callback, method=method, user=user, context=context, intro_note=intro_note)
                return
            await callback.answer("СБП сейчас недоступна", show_alert=True)
            return

        if method == "sbp_manual":
            if sbp_tariff_uses_manual():
                intro_note = (
                    "⚠️ <b>Если автоматический QR по СБП не сработал, используй эту ручную заявку.</b>\n"
                    "После перевода администратор подтвердит покупку слота вручную."
                    if sbp_manual_emergency_fallback_active()
                    else None
                )
                await _show_manual_device_slot_payment(callback, method="sbp", user=user, context=context, intro_note=intro_note)
                return
            await callback.answer("Ручная СБП сейчас недоступна", show_alert=True)
            return

        if method == "crypto":
            if config.enable_platega_crypto_user_flow:
                await _show_platega_device_slot_payment(callback, method=method, user=user, context=context, breakdown=breakdown)
                return
            if config.enable_manual_crypto_user_flow:
                await _show_manual_device_slot_payment(callback, method=method, user=user, context=context)
                return
            await callback.answer("Криптовалюта сейчас недоступна", show_alert=True)
            return
    except PlategaError as exc:
        logger.warning("Failed to create device-slot payment in test bot: %s", exc)
        await callback.answer("Не удалось создать оплату. Попробуйте ещё раз позже.", show_alert=True)
        return
    await callback.answer("Способ оплаты не поддерживается. Откройте экран заново.", show_alert=True)


@router.callback_query(F.data.startswith(V2_RENEW_MANUAL_PAID_PREFIX))
async def v2_renew_manual_paid_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, tariff_code = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_RENEW_MANUAL_PAID_PREFIX),
            context="renew manual paid",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    record_before = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record_before is None or user is None or tariff is None or int(record_before.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)
    await _edit_screen(
        callback,
        manual_payment_waiting_review_text(
            tariff_title=tariff.title,
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or tariff.rub_price,
            balance_reserved_amount=updated.balance_reserved_amount or 0,
            paid_amount=updated.amount,
        ),
        _renew_manual_payment_keyboard(updated.id, tariff_code),
        screen_key="renew",
        answer_first=False,
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith(V2_RENEW_MANUAL_STATUS_PREFIX))
async def v2_renew_manual_status_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, tariff_code = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_RENEW_MANUAL_STATUS_PREFIX),
            context="renew manual status",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record.payment_status == "confirmed":
        refreshed_user = await get_user_by_telegram_id(callback.from_user.id)
        expires_at = get_access_expires_at_from_user(refreshed_user) if refreshed_user is not None else None
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        breakdown = _payment_breakdown_from_record(record, tariff.rub_price)
        await _edit_screen(
            callback,
            payment_success_text(
                tariff.title,
                expires_text,
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=int(getattr(record, "balance_applied_amount", 0) or 0),
                paid_amount=breakdown["paid_amount"],
            ),
            _renew_payment_methods_keyboard(tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Оплата уже подтверждена", show_alert=True)
        return
    if record.payment_status == "rejected":
        await _edit_screen(
            callback,
            manual_payment_rejected_text(
                tariff_title=tariff.title,
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            _renew_manual_payment_keyboard(record.id, tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return
    if record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=tariff.title,
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            _renew_payment_methods_keyboard(tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return
    if record.payment_status == "awaiting_admin_review":
        await _edit_screen(
            callback,
            manual_payment_waiting_review_text(
                tariff_title=tariff.title,
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or tariff.rub_price,
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            ),
            _renew_manual_payment_keyboard(record.id, tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return
    _, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _edit_screen(
        callback,
        manual_payment_details_text(
            tariff_title=tariff.title,
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or tariff.rub_price,
            balance_reserved_amount=record.balance_reserved_amount or 0,
            method_label=record.payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        _renew_manual_payment_keyboard(record.id, tariff_code),
        screen_key="renew",
        answer_first=False,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(V2_RENEW_MANUAL_CANCEL_PREFIX))
async def v2_renew_manual_cancel_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, tariff_code = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_RENEW_MANUAL_CANCEL_PREFIX),
            context="renew manual cancel",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await _edit_screen(
        callback,
        manual_payment_inactive_text(
            tariff_title=tariff.title,
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        _renew_payment_methods_keyboard(tariff_code),
        screen_key="renew",
        answer_first=False,
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith(V2_RENEW_EXTERNAL_CHECK_PREFIX))
async def v2_renew_external_check_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, tariff_code = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_RENEW_EXTERNAL_CHECK_PREFIX),
            context="renew external check",
        )
    except ValueError:
        await callback.answer("Счёт не найден", show_alert=True)
        return
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Счёт не найден", show_alert=True)
        return
    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=callback.bot)
    except PlategaError as exc:
        logger.warning("Failed to sync renew payment #%s in v2 router: %s", record.id, exc)
        await callback.answer("Не удалось проверить оплату", show_alert=True)
        return
    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    if refreshed_record.payment_status == "confirmed":
        refreshed_user = await get_user_by_telegram_id(callback.from_user.id)
        expires_at = get_access_expires_at_from_user(refreshed_user) if refreshed_user is not None else None
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        breakdown = _payment_breakdown_from_record(refreshed_record, tariff.rub_price)
        await _edit_screen(
            callback,
            payment_success_text(
                tariff.title,
                expires_text,
                list_price_amount=breakdown["list_price_amount"],
                balance_applied_amount=int(getattr(refreshed_record, "balance_applied_amount", 0) or 0),
                paid_amount=breakdown["paid_amount"],
            ),
            _renew_payment_methods_keyboard(tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Оплата подтверждена", show_alert=True)
        return
    checkout_url = str(_payment_metadata(refreshed_record).get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=tariff.title,
                request_id=refreshed_record.id,
                status=refreshed_record.payment_status,
                reason=f"Статус провайдера: {provider_status}",
            ),
            _renew_payment_methods_keyboard(tariff_code),
            screen_key="renew",
            answer_first=False,
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return
    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напишите в поддержку.", show_alert=True)
        return
    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуйте позже.", show_alert=True)
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=tariff.title,
            amount_rub=refreshed_record.amount,
            method_label=refreshed_record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=refreshed_record.list_price_amount or tariff.rub_price,
            balance_reserved_amount=refreshed_record.balance_reserved_amount or 0,
        ),
        _renew_external_payment_keyboard(checkout_url, tariff_code, refreshed_record.id) if checkout_url else _renew_payment_methods_keyboard(tariff_code),
        screen_key="renew",
        answer_first=False,
    )
    await callback.answer(_external_payment_status_notice(refreshed_record.payment_status, provider_status), show_alert=True)


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_MANUAL_PAID_PREFIX))
async def v2_bonus_gift_manual_paid_callback(callback: CallbackQuery) -> None:
    record_id_str, tariff_code = str(callback.data or "").removeprefix(V2_BONUS_GIFT_MANUAL_PAID_PREFIX).split(":")
    record_id = int(record_id_str)
    record_before = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record_before is None or user is None or tariff is None or int(record_before.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)
    await _edit_screen(
        callback,
        manual_payment_waiting_review_text(
            tariff_title=f"Подарок: {tariff.title}",
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
            balance_reserved_amount=updated.balance_reserved_amount or 0,
            paid_amount=updated.amount,
        ),
        _bonus_gift_manual_payment_keyboard(updated.id, tariff_code),
        screen_key="gift",
        answer_first=False,
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_MANUAL_STATUS_PREFIX))
async def v2_bonus_gift_manual_status_callback(callback: CallbackQuery) -> None:
    record_id_str, tariff_code = str(callback.data or "").removeprefix(V2_BONUS_GIFT_MANUAL_STATUS_PREFIX).split(":")
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record.payment_status == "confirmed":
        await _edit_screen(
            callback,
            await _gift_success_text_from_record(record),
            _bonus_gift_payment_methods_keyboard(tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Подарок уже подтверждён", show_alert=True)
        return
    if record.payment_status == "rejected":
        await _edit_screen(
            callback,
            manual_payment_rejected_text(
                tariff_title=f"Подарок: {tariff.title}",
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            _bonus_gift_manual_payment_keyboard(record.id, tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return
    if record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=f"Подарок: {tariff.title}",
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            _bonus_gift_payment_methods_keyboard(tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return
    if record.payment_status == "awaiting_admin_review":
        await _edit_screen(
            callback,
            manual_payment_waiting_review_text(
                tariff_title=f"Подарок: {tariff.title}",
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            ),
            _bonus_gift_manual_payment_keyboard(record.id, tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return
    _, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _edit_screen(
        callback,
        manual_payment_details_text(
            tariff_title=f"Подарок: {tariff.title}",
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
            balance_reserved_amount=record.balance_reserved_amount or 0,
            method_label=record.payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        _bonus_gift_manual_payment_keyboard(record.id, tariff_code),
        screen_key="gift",
        answer_first=False,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX))
async def v2_bonus_gift_manual_cancel_callback(callback: CallbackQuery) -> None:
    record_id_str, tariff_code = str(callback.data or "").removeprefix(V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX).split(":")
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await _edit_screen(
        callback,
        manual_payment_inactive_text(
            tariff_title=f"Подарок: {tariff.title}",
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        _bonus_gift_payment_methods_keyboard(tariff_code),
        screen_key="gift",
        answer_first=False,
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith(V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX))
async def v2_bonus_gift_external_check_callback(callback: CallbackQuery) -> None:
    record_id_str, tariff_code = str(callback.data or "").removeprefix(V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX).split(":")
    record_id = int(record_id_str)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    tariff = get_tariff(tariff_code)
    if record is None or user is None or tariff is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Счёт не найден", show_alert=True)
        return
    sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=callback.bot)
    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    payment_result = sync_result.get("payment_result")
    if refreshed_record.payment_status == "confirmed":
        text = (
            _payment_result_text(payment_result, fallback_title=f"Подарок: {tariff.title}")
            if payment_result is not None
            else await _gift_success_text_from_record(refreshed_record)
        )
        await _edit_screen(
            callback,
            text,
            _bonus_gift_payment_methods_keyboard(tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Оплата подтверждена", show_alert=True)
        return
    checkout_url = str(_payment_metadata(refreshed_record).get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=f"Подарок: {tariff.title}",
                request_id=refreshed_record.id,
                status=refreshed_record.payment_status,
                reason=f"Статус провайдера: {provider_status}",
            ),
            _bonus_gift_payment_methods_keyboard(tariff_code),
            screen_key="gift",
            answer_first=False,
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return
    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напишите в поддержку.", show_alert=True)
        return
    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуйте позже.", show_alert=True)
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=f"Подарок: {tariff.title}",
            amount_rub=refreshed_record.amount,
            method_label=refreshed_record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=refreshed_record.list_price_amount or int(getattr(tariff, "rub_price", 0) or 0),
            balance_reserved_amount=refreshed_record.balance_reserved_amount or 0,
        ),
        _bonus_gift_external_payment_keyboard(checkout_url, tariff_code, refreshed_record.id)
        if checkout_url
        else _bonus_gift_payment_methods_keyboard(tariff_code),
        screen_key="gift",
        answer_first=False,
    )
    await callback.answer(_external_payment_status_notice(refreshed_record.payment_status, provider_status), show_alert=True)


@router.callback_query(F.data.startswith(V2_BALANCE_MANUAL_PAID_PREFIX))
async def v2_balance_manual_paid_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, amount_raw = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_BALANCE_MANUAL_PAID_PREFIX),
            context="balance manual paid",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    amount_rub = int(amount_raw)
    record_before = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record_before is None or user is None or int(record_before.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)
    await _edit_screen(
        callback,
        manual_payment_waiting_review_text(
            tariff_title="Пополнение баланса",
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or amount_rub,
            balance_reserved_amount=0,
            paid_amount=updated.amount,
        ),
        _balance_manual_payment_keyboard(updated.id, amount_rub),
        screen_key="balance_topup",
        answer_first=False,
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith(V2_BALANCE_MANUAL_STATUS_PREFIX))
async def v2_balance_manual_status_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, amount_raw = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_BALANCE_MANUAL_STATUS_PREFIX),
            context="balance manual status",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    amount_rub = int(amount_raw)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record.payment_status == "confirmed":
        balance = await get_user_balance_summary(user.id)
        await _edit_screen(
            callback,
            balance_topup_success_text(
                amount_rub=int(getattr(record, "amount", 0) or getattr(record, "list_price_amount", 0) or amount_rub),
                balance_rub=int(balance["balance_rub"]),
            ),
            _balance_topup_keyboard(),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Баланс пополнен", show_alert=True)
        return
    if record.payment_status == "rejected":
        await _edit_screen(
            callback,
            manual_payment_rejected_text(
                tariff_title="Пополнение баланса",
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            _balance_manual_payment_keyboard(record.id, amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return
    if record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title="Пополнение баланса",
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            _balance_payment_methods_keyboard(amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return
    if record.payment_status == "awaiting_admin_review":
        await _edit_screen(
            callback,
            manual_payment_waiting_review_text(
                tariff_title="Пополнение баланса",
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or amount_rub,
                balance_reserved_amount=0,
                paid_amount=record.amount,
            ),
            _balance_manual_payment_keyboard(record.id, amount_rub),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return
    _, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _edit_screen(
        callback,
        manual_payment_details_text(
            tariff_title="Пополнение баланса",
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or amount_rub,
            balance_reserved_amount=0,
            method_label=record.payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        _balance_manual_payment_keyboard(record.id, amount_rub),
        screen_key="balance_topup",
        answer_first=False,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(V2_BALANCE_MANUAL_CANCEL_PREFIX))
async def v2_balance_manual_cancel_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, amount_raw = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_BALANCE_MANUAL_CANCEL_PREFIX),
            context="balance manual cancel",
        )
    except ValueError:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    record_id = int(record_id_str)
    amount_rub = int(amount_raw)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await _edit_screen(
        callback,
        manual_payment_inactive_text(
            tariff_title="Пополнение баланса",
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        _balance_payment_methods_keyboard(amount_rub),
        screen_key="balance_topup",
        answer_first=False,
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith(V2_BALANCE_EXTERNAL_CHECK_PREFIX))
async def v2_balance_external_check_callback(callback: CallbackQuery) -> None:
    try:
        record_id_str, amount_raw = _split_callback_suffix(
            str(callback.data or "").removeprefix(V2_BALANCE_EXTERNAL_CHECK_PREFIX),
            context="balance external check",
        )
    except ValueError:
        await callback.answer("Счёт не найден", show_alert=True)
        return
    record_id = int(record_id_str)
    amount_rub = int(amount_raw)
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Счёт не найден", show_alert=True)
        return
    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=callback.bot)
    except PlategaError as exc:
        logger.warning("Failed to sync balance top-up payment #%s in v2 router: %s", record.id, exc)
        await callback.answer("Не удалось проверить оплату", show_alert=True)
        return
    refreshed_record = sync_result["record"]
    provider_status = sync_result["provider_status"]
    if refreshed_record.payment_status == "confirmed":
        balance = await get_user_balance_summary(user.id)
        await _edit_screen(
            callback,
            balance_topup_success_text(
                amount_rub=int(getattr(refreshed_record, "amount", 0) or amount_rub),
                balance_rub=int(balance["balance_rub"]),
            ),
            _balance_topup_keyboard(),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Баланс пополнен", show_alert=True)
        return
    checkout_url = str(_payment_metadata(refreshed_record).get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            (
                "⌛ <b>Счёт на пополнение больше не активен</b>\n\n"
                f"Статус провайдера: <b>{provider_status or refreshed_record.payment_status}</b>\n\n"
                "Создайте новый счёт на нужную сумму."
            ),
            _balance_topup_keyboard(),
            screen_key="balance_topup",
            answer_first=False,
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return
    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напишите в поддержку.", show_alert=True)
        return
    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуйте позже.", show_alert=True)
        return
    await _edit_screen(
        callback,
        balance_topup_payment_text(
            amount_rub=amount_rub,
            method_label=refreshed_record.payment_method,
            checkout_label="страницу оплаты",
        ),
        _balance_external_payment_keyboard(checkout_url, amount_rub, refreshed_record.id) if checkout_url else _balance_payment_methods_keyboard(amount_rub),
        screen_key="balance_topup",
        answer_first=False,
    )
    await callback.answer(_external_payment_status_notice(refreshed_record.payment_status, provider_status), show_alert=True)


@router.callback_query(F.data.startswith(V2_DEVICE_SLOT_MANUAL_PAID_PREFIX))
async def v2_device_slot_manual_paid_callback(callback: CallbackQuery) -> None:
    record_id = int(str(callback.data or "").removeprefix(V2_DEVICE_SLOT_MANUAL_PAID_PREFIX))
    record_before = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record_before is None or user is None or int(record_before.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await mark_manual_payment_record_submitted(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record_before.payment_status != "awaiting_admin_review" and updated.payment_status == "awaiting_admin_review":
        await notify_support_admins_about_manual_payment(record_id)
    await _edit_screen(
        callback,
        manual_payment_waiting_review_text(
            tariff_title=_device_slot_title(),
            request_id=updated.id,
            method_label=updated.payment_method,
            list_price_amount=updated.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=updated.balance_reserved_amount or 0,
            paid_amount=updated.amount,
        ),
        _device_slot_manual_payment_keyboard(updated.id),
        screen_key="device_slot",
        answer_first=False,
    )
    await callback.answer("Заявка отправлена на проверку")


@router.callback_query(F.data.startswith(V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX))
async def v2_device_slot_manual_status_callback(callback: CallbackQuery) -> None:
    record_id = int(str(callback.data or "").removeprefix(V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX))
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if record.payment_status == "confirmed":
        await _edit_screen(
            callback,
            await _device_slot_success_text_from_record(user, record),
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Покупка уже подтверждена", show_alert=True)
        return
    if record.payment_status == "rejected":
        await _edit_screen(
            callback,
            manual_payment_rejected_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                reason=record.rejection_reason,
            ),
            _device_slot_manual_payment_keyboard(record.id),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Заявка отклонена", show_alert=True)
        return
    if record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                status=record.payment_status,
                reason=record.rejection_reason,
            ),
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Заявка больше не активна", show_alert=True)
        return
    if record.payment_status == "awaiting_admin_review":
        await _edit_screen(
            callback,
            manual_payment_waiting_review_text(
                tariff_title=_device_slot_title(),
                request_id=record.id,
                method_label=record.payment_method,
                list_price_amount=record.list_price_amount or device_slot_unit_price_rub(),
                balance_reserved_amount=record.balance_reserved_amount or 0,
                paid_amount=record.amount,
            ),
            _device_slot_manual_payment_keyboard(record.id),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Заявка ещё на проверке", show_alert=True)
        return
    _, details = _manual_payment_settings("sbp" if record.payment_method == "sbp_manual" else "crypto")
    await _edit_screen(
        callback,
        manual_payment_details_text(
            tariff_title=_device_slot_title(),
            amount_rub=record.amount,
            list_price_amount=record.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=record.balance_reserved_amount or 0,
            method_label=record.payment_method,
            request_id=record.id,
            details=details,
            review_hours=config.manual_payment_review_hours,
        ),
        _device_slot_manual_payment_keyboard(record.id),
        screen_key="device_slot",
        answer_first=False,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX))
async def v2_device_slot_manual_cancel_callback(callback: CallbackQuery) -> None:
    record_id = int(str(callback.data or "").removeprefix(V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX))
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    updated = await cancel_manual_payment_record(record_id)
    if updated is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await _edit_screen(
        callback,
        manual_payment_inactive_text(
            tariff_title=_device_slot_title(),
            request_id=updated.id,
            status=updated.payment_status,
            reason=updated.rejection_reason,
        ),
        _device_slot_payment_methods_keyboard(),
        screen_key="device_slot",
        answer_first=False,
    )
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith(V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX))
async def v2_device_slot_external_check_callback(callback: CallbackQuery) -> None:
    record_id = int(str(callback.data or "").removeprefix(V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX))
    record = await get_payment_record_by_id(record_id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if record is None or user is None or int(record.user_id or 0) != int(user.id):
        await callback.answer("Счёт не найден", show_alert=True)
        return
    try:
        sync_result = await sync_platega_record_by_id(record.id, notify_user=False, bot=callback.bot)
    except PlategaError as exc:
        logger.warning("Failed to sync device-slot payment #%s in v2 router: %s", record.id, exc)
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
        await _edit_screen(
            callback,
            text,
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Оплата подтверждена", show_alert=True)
        return
    checkout_url = str(_payment_metadata(refreshed_record).get("checkout_url") or "").strip()
    if refreshed_record.payment_status in {"expired", "cancelled"}:
        await _edit_screen(
            callback,
            manual_payment_inactive_text(
                tariff_title=_device_slot_title(),
                request_id=refreshed_record.id,
                status=refreshed_record.payment_status,
                reason=f"Статус провайдера: {provider_status}",
            ),
            _device_slot_payment_methods_keyboard(),
            screen_key="device_slot",
            answer_first=False,
        )
        await callback.answer("Счёт больше не активен", show_alert=True)
        return
    if refreshed_record.payment_status == "disputed":
        await callback.answer("Провайдер вернул спорный статус. Напишите в поддержку.", show_alert=True)
        return
    if refreshed_record.payment_status == "error":
        await callback.answer("Провайдер вернул ошибку. Попробуйте позже.", show_alert=True)
        return
    await _edit_screen(
        callback,
        platega_payment_text(
            tariff_title=_device_slot_title(),
            amount_rub=refreshed_record.amount,
            method_label=refreshed_record.payment_method,
            checkout_label="страница оплаты",
            list_price_amount=refreshed_record.list_price_amount or device_slot_unit_price_rub(),
            balance_reserved_amount=refreshed_record.balance_reserved_amount or 0,
        ),
        _device_slot_external_payment_keyboard(checkout_url, refreshed_record.id) if checkout_url else _device_slot_payment_methods_keyboard(),
        screen_key="device_slot",
        answer_first=False,
    )
    await callback.answer(_external_payment_status_notice(refreshed_record.payment_status, provider_status), show_alert=True)


@router.callback_query(F.data.startswith("testv2:connect:"))
async def v2_connect_placeholder_callback(callback: CallbackQuery) -> None:
    device_key = callback.data.split(":")[-1]
    guide = DEVICE_GUIDES.get(device_key)
    if guide is None:
        await callback.answer("Устройство пока не настроено.", show_alert=True)
        return
    await _edit_screen(
        callback,
        CONNECT_PLACEHOLDER_TEMPLATE.format(device_title=guide.title),
        _connect_placeholder_keyboard(device_key),
        screen_key="finish",
    )


@router.message(Command("profiles"))
@router.message(Command("legacy_profiles"))
async def legacy_profiles_handler(message: Message) -> None:
    if await _deny_if_needed(message):
        return
    await message.answer(_legacy_menu_text(), parse_mode="HTML", reply_markup=_legacy_menu_keyboard())


@router.callback_query(F.data == "testbot:menu")
async def legacy_menu_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    await callback.message.answer(_legacy_menu_text(), parse_mode="HTML", reply_markup=_legacy_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("testbot:profile:"))
async def legacy_profile_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    profile_key = callback.data.split(":")[-1]
    try:
        runtime = await get_test_profile_runtime(profile_key)
    except (FileNotFoundError, ValueError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    if runtime is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await _send_legacy_profile(callback, profile_key, runtime)
    await callback.answer()


@router.callback_query(F.data.startswith("testbot:activate:"))
async def legacy_activate_device_callback(callback: CallbackQuery) -> None:
    if await _deny_if_needed(callback):
        return
    _, _, profile_key, device_key = callback.data.split(":")
    try:
        result = await activate_test_profile_device(
            profile_key,
            device_key,
            actor_telegram_id=getattr(callback.from_user, "id", None),
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    runtime = result["runtime"]
    await _send_legacy_profile(callback, profile_key, runtime)
    if result["status"] == "transferred":
        previous = result.get("previous_device_label") or "предыдущее устройство"
        await callback.answer(f"Ключ перевыпущен. {previous} отключено.", show_alert=True)
        return
    target = TEST_SWITCH_DEVICE_CHOICES[device_key]["label"]
    await callback.answer(f"Ключ привязан к {target}.", show_alert=True)
