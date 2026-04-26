from html import escape

from bot.config import config
from bot.utils.access import get_access_expires_at_from_user, get_access_status_from_user
from bot.utils.modes import (
    format_mode,
    get_mode_description,
    get_mode_keys,
    infer_mode_from_protocol,
)
from bot.utils.payment_options import sbp_tariff_uses_manual, sbp_tariff_uses_platega
from bot.utils.tariffs import (
    PROMO_DATE_RANGE_LABEL,
    get_tariffs_list,
    marketing_tariff_title,
    promo_active,
    promo_tariff_offer_block,
    tariff_duration_badge,
)


SEP = "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
SURFACE_SEP = "━━━━━━━━━━━━━━━━━━━"
CHANNEL_URL = "https://t.me/amonora_new"
SUPPORT_URL = "https://t.me/amonora_support_bot"
TERMS_URL = "https://www.amonoraconnect.com/legal/terms"
MANUAL_URL = "https://www.amonoraconnect.com/manual"

OS_LABELS = {
    "android": "🤖 Android",
    "ios": "🍎 iPhone / iPad",
    "windows": "🪟 Windows",
    "macos": "💻 macOS",
    "linux": "🐧 Linux",
    "tv": "🤖 Android",
    "other": "🧩 Другое",
}

COUNTRY_LABELS = {
    "de": "🇩🇪 Германия",
    "ee": "🇪🇪 Эстония",
    "dk": "🇩🇰 Дания",
    "se": "🇸🇪 Швеция",
}

def _safe(value: object) -> str:
    return escape(str(value))


def _format_rub(amount: int) -> str:
    return f"{int(amount)} ₽"


def _configured_copy(value: str | None, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = default
    return raw.replace("\\n", "\n")


def _payment_breakdown_text(
    *,
    list_price_amount: int | None,
    balance_applied_amount: int = 0,
    paid_amount: int | None = None,
    reserved_amount: int = 0,
) -> str:
    base_amount = int(list_price_amount or 0)
    if base_amount <= 0 and paid_amount is None and balance_applied_amount <= 0 and reserved_amount <= 0:
        return ""

    real_amount = int(paid_amount if paid_amount is not None else max(base_amount - balance_applied_amount, 0))
    lines = [f"Полная стоимость: <b>{_format_rub(base_amount)}</b>"]
    if balance_applied_amount > 0:
        lines.append(f"Списано с Баланса: <b>{_format_rub(balance_applied_amount)}</b>")
    if reserved_amount > 0:
        lines.append(f"Зарезервировано с Баланса: <b>{_format_rub(reserved_amount)}</b>")
    lines.append(f"К оплате деньгами: <b>{_format_rub(real_amount)}</b>")
    return "\n".join(lines)


MOBILE_KEY_IMPORT_TEXT = (
    "1. Скачайте подходящее приложение\n"
    "(например v2box, v2run, Happ)\n\n"
    "2. Скопируйте ключ\n"
    "Ключ выглядит как длинная строка или ссылка для импорта. Выделите её и нажмите «Копировать».\n\n"
    "3. Добавьте ключ в приложение\n"
    "✅ Откройте приложение.\n"
    "✅ Найдите кнопку добавления (обычно + или значок «плюс»).\n"
    "✅ Выберите пункт «Импорт из буфера обмена» или «Вставить URL».\n"
    "✅ Если приложение не распознало ключ автоматически, попробуйте создать новое подключение вручную и вставить скопированные данные в соответствующие поля.\n\n"
    "4. Пользуйтесь\n"
    "Если всё сделано верно, интернет начнёт работать через подключение.\n"
    "В списке подключений нажмите на добавленное, чтобы оно стало активным. Обычно рядом появляется галочка или переключатель.\n\n"
    "Если возникнут сложности, то можете написать нам в поддержку 😊"
)


def start_new_user_text(first_name: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "Добро пожаловать в <b>Amonora</b>.\n"
        "Мы сделали бота так, чтобы ты мог быстро получить доступ и управлять устройствами прямо из Telegram.\n\n"
        "Продолжая пользоваться ботом, ты соглашаешься с "
        "<b>Пользовательским соглашением</b>.\n\n"
        f"{SEP}\n"
        "Следующий шаг: открой <b>🏠 Меню</b> и создай своё первое устройство."
    )


def start_new_user_trial_activated_text(first_name: str, expires_at: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "Добро пожаловать в <b>Amonora</b>.\n"
        "Мы сделали бота так, чтобы ты мог быстро получить доступ и управлять устройствами прямо из Telegram.\n\n"
        "Продолжая пользоваться ботом, ты соглашаешься с "
        "<b>Пользовательским соглашением</b>.\n\n"
        f"Твой <b>пробный доступ активирован</b>.\n"
        f"Доступ действует до: <b>{_safe(expires_at)}</b>\n\n"
        f"{SEP}\n"
        "Открой <b>🏠 Меню</b> и создай своё первое устройство."
    )


def start_trial_subscription_required_text(first_name: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "Добро пожаловать в <b>Amonora</b>.\n"
        "\n"
        "Здесь ты можешь:\n"
        "• подключить интернет без ограничений\n"
        "• управлять устройствами в 1 клик\n"
        "• получить стабильную и быструю сеть\n\n"
        "Продолжая пользоваться ботом,\n"
        "ты соглашаешься с <b>Пользовательским соглашением</b>.\n\n"
        "🎁 <b>Активируй пробный доступ бесплатно:</b>\n\n"
        "1. Подпишись на канал\n"
        "2. Нажми <b>«Подписался»</b>\n\n"
        "После этого откроется доступ к первому устройству."
    )


def trial_subscription_paused_text(first_name: str, expires_at: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "Твой <b>пробный доступ приостановлен</b>, потому что во время пробного доступа нужна активная подписка на канал.\n\n"
        f"Текущий пробный доступ сохранён до: <b>{_safe(expires_at)}</b>\n"
        "Новый пробный доступ заново не выдаётся: после возвращения в канал у тебя продолжится оставшееся время.\n\n"
        f"{SEP}\n"
        "Подпишись на канал и нажми <b>✅ Подписался</b>, чтобы вернуть оставшееся время пробного доступа."
    )


def trial_channel_pause_notice_text(expires_at: str) -> str:
    return (
        "⏸ <b>Пробный доступ приостановлен</b>\n\n"
        "Во время пробного доступа нужно оставаться подписанным на канал проекта.\n"
        "Сейчас мы увидели, что подписка на канал отключена, поэтому доступ временно остановлен.\n\n"
        f"Оставшееся время пробного доступа сохранено до: <b>{_safe(expires_at)}</b>\n"
        "Новый пробный доступ заново не выдаётся.\n\n"
        "Вернись в канал, затем открой <b>@amonora_bot</b> и нажми <b>/start</b> или кнопку <b>✅ Подписался</b>, чтобы продолжить оставшееся время."
    )


def trial_channel_resume_notice_text(expires_at: str) -> str:
    return (
        "✅ <b>Пробный доступ снова активен</b>\n\n"
        "Мы увидели, что ты снова подписан на канал, и вернули оставшееся время пробного доступа.\n"
        f"Доступ действует до: <b>{_safe(expires_at)}</b>\n\n"
        "Новый пробный доступ не выдавался заново — продолжилось именно оставшееся время."
    )


USER_NOT_FOUND_TEXT = (
    "Пользователь не найден в базе.\n"
    "Нажми /start, чтобы пройти регистрацию."
)


def info_root_text() -> str:
    return (
        "📚 <b>ИНФОРМАЦИЯ</b>\n\n"
        f"{SURFACE_SEP}\n"
        "Выберите нужный раздел:\n"
        f"{SURFACE_SEP}\n\n"
        "📘 <b>Инструкция</b>\n"
        "• Подключение устройства\n"
        "• Установка клиента\n"
        "• Импорт ключа\n"
        "• Базовые шаги по запуску\n\n"
        "📜 <b>Документы</b>\n"
        "• Пользовательское соглашение\n"
        "• Политика конфиденциальности\n"
        "• Политика возврата"
    )


def info_instructions_text() -> str:
    return (
        "📖 <b>Инструкции</b>\n\n"
        f"{SURFACE_SEP}\n"
        "1. Создай устройство в разделе <b>📱 Устройства</b>.\n"
        "2. Получи ключ или открой QR-код.\n"
        "3. Открой полную инструкцию по кнопке ниже.\n"
        "4. Подключи устройство по шагам из руководства.\n"
        f"{SURFACE_SEP}\n"
        f"Полная инструкция: {_safe(MANUAL_URL)}"
    )


def info_faq_text() -> str:
    return (
        "❓ <b>FAQ</b>\n\n"
        f"{SURFACE_SEP}\n"
        "• <b>Не работает подключение</b> — запроси новый ключ и проверь клиент.\n"
        "• <b>Медленная скорость</b> — попробуй сменить страну или режим.\n"
        "• <b>Не пришел ключ</b> — открой устройство и нажми <b>🔑 Получить ключ</b> ещё раз.\n"
        "• <b>Как сменить тариф</b> — открой раздел <b>💳 Купить</b> и выбери новый срок доступа."
    )


def support_intro_text() -> str:
    return (
        "🛟 <b>ПОДДЕРЖКА AMONORA</b>\n\n"
        "📝 <b>С какими вопросами помочь?</b>\n"
        f"{SURFACE_SEP}\n"
        "🔌 Проблемы с подключением\n"
        "❌ Ошибки после оплаты\n"
        "🔑 Вопросы по ключам\n"
        "⚙️ Технические сложности\n"
        "💡 Общие вопросы\n\n"
        f"{SURFACE_SEP}\n"
        "⏱ <b>Время ответа:</b> обычно до 45 минут"
    )


CHANNEL_SUBSCRIPTION_REQUIRED_TEXT = (
    "📢 <b>Чтобы получить пробный доступ, подпишись на канал</b>\n\n"
    "После подписки нажми кнопку «✅ Подписался»."
)


def trial_activated_text(first_name: str, expires_at: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "Твой <b>пробный доступ активирован</b>.\n"
        f"Доступ действует до: <b>{_safe(expires_at)}</b>\n\n"
        f"{SEP}\n"
        "Теперь открой <b>📱 Устройства</b>, чтобы создать первое подключение."
    )


def active_access_text(first_name: str, expires_at: str) -> str:
    return (
        f"Привет, {_safe(first_name)}! 👋\n\n"
        "У тебя уже есть <b>активный доступ</b>.\n"
        f"Доступ действует до: <b>{_safe(expires_at)}</b>\n\n"
        f"{SEP}\n"
        "Открой <b>📱 Устройства</b>, чтобы управлять своими подключениями."
    )


def access_expired_text() -> str:
    return (
        "⛔ <b>Доступ истёк</b>\n\n"
        "Чтобы продолжить пользоваться Amonora, нажми <b>💳 Купить</b> и выбери тариф."
    )


def access_required_text() -> str:
    return (
        "⛔ <b>Нет активного доступа</b>\n\n"
        "Новые устройства выдаются только при активном пробном доступе или оплаченной подписке."
    )


def no_access_reminder_text() -> str:
    if not promo_active():
        return (
            "💳 <b>Доступ к Amonora сейчас не активен</b>\n\n"
            "Если хочешь снова пользоваться Amonora, нажми <b>Купить</b> и выбери подходящий тариф.\n\n"
            "После оплаты доступ включится автоматически."
        )
    return (
        "🎁 <b>Спецпредложение Amonora действует только "
        f"{PROMO_DATE_RANGE_LABEL}</b>\n\n"
        "Сейчас можно подключиться на выгодных условиях:\n"
        f"{promo_tariff_offer_block(bullets=True, html=True)}\n\n"
        "Нажми <b>Купить</b> и зафиксируй выгодный тариф, пока акция активна."
    )


def trial_ends_today_reminder_text() -> str:
    if not promo_active():
        return (
            "⏳ <b>Пробный доступ заканчивается сегодня</b>\n\n"
            "Чтобы не потерять доступ к Amonora, нажми <b>Купить</b> и выбери тариф заранее.\n\n"
            "После оплаты мы сразу откроем платный доступ."
        )
    return (
        "⏳ <b>Пробный доступ заканчивается сегодня</b>\n\n"
        f"Только {PROMO_DATE_RANGE_LABEL} можно подключить тариф с подарочными месяцами:\n"
        f"{promo_tariff_offer_block(bullets=True, html=True, include_gift_wording=False)}\n\n"
        "Нажми <b>Купить</b> сейчас, чтобы не потерять доступ и забрать бонусные месяцы."
    )


def trial_expired_reminder_text() -> str:
    if not promo_active():
        return (
            "🔒 <b>Пробный доступ закончился</b>\n\n"
            "Если хочешь продолжить пользоваться Amonora, нажми <b>Купить</b> и выбери тариф.\n\n"
            "Доступ вернётся сразу после оплаты."
        )
    return (
        "🔒 <b>Пробный доступ закончился</b>\n\n"
        f"Акция с подарочными месяцами действует только {PROMO_DATE_RANGE_LABEL}:\n"
        f"{promo_tariff_offer_block(bullets=True, html=True)}\n\n"
        "Нажми <b>Купить</b>, чтобы вернуть доступ сразу после оплаты и подключиться выгоднее."
    )


def tariffs_text() -> str:
    tariff_markers = {
        "1 месяц": "⚡",
        "3 месяца": "🔥",
        "6 месяцев": "👑",
        "12 месяцев": "💫",
    }
    lines = ["💳 <b>Купить доступ</b>\n", SURFACE_SEP]
    for tariff in get_tariffs_list():
        marker = tariff_markers.get(tariff.title, "💳")
        display_title = marketing_tariff_title(tariff.title, tariff.code)
        line = f"{marker} <b>{display_title}</b> — {tariff.rub_price} ₽"
        duration_badge = tariff_duration_badge(tariff.title, tariff.code)
        if duration_badge:
            line = f"{line}\n   {duration_badge}"
        lines.append(line)
    lines.append(SURFACE_SEP)
    lines.append("")
    if promo_active():
        lines.append(f"🎁 Акция действует {PROMO_DATE_RANGE_LABEL}.")
        lines.append("")
    lines.append("Выбери тариф, а затем удобный способ оплаты.")
    lines.append("")
    lines.append("Способы оплаты:")
    lines.append("• ⭐ Telegram Stars")
    if sbp_tariff_uses_platega():
        lines.append("• 💳 СБП")
    if sbp_tariff_uses_manual():
        lines.append("• 💳 СБП (ручная заявка)")
    if config.enable_platega_crypto_user_flow:
        lines.append("• 💎 Криптовалюта")
    elif config.enable_manual_crypto_user_flow:
        lines.append("• 💎 Крипта (ручная заявка)")
    return "\n".join(lines)


def device_slot_methods_text(
    *,
    title: str,
    amount_rub: int,
    expires_at: str,
    current_limit: int,
    next_limit: int,
    max_limit: int,
    list_price_amount: int | None = None,
    balance_amount: int = 0,
    payable_amount: int | None = None,
) -> str:
    payable_total = max(int(payable_amount if payable_amount is not None else int(amount_rub) - int(balance_amount)), 0)
    lines = [
        f"📱 <b>{_safe(title)}</b>",
        "",
        f"Цена: <b>{_format_rub(amount_rub)}</b>",
        f"Действует до: <b>{_safe(expires_at)}</b>",
        f"Сейчас доступно: <b>{current_limit}</b> устройств",
        f"После оплаты станет: <b>{next_limit}</b> из <b>{max_limit}</b>",
        "Этот доп. слот работает до конца текущей оплаченной подписки.",
        "Если у тебя подписка на 6 или 12 месяцев, устройство будет активно весь этот срок, а не 30 дней.",
    ]
    if list_price_amount is not None:
        lines.extend(
            [
                "",
                f"Полная стоимость: <b>{_format_rub(int(list_price_amount))}</b>",
            ]
        )
        if balance_amount > 0:
            lines.extend(
                [
                    f"С баланса спишется: <b>{_format_rub(balance_amount)}</b>",
                    f"Останется оплатить деньгами: <b>{_format_rub(payable_total)}</b>",
                ]
            )
    lines.extend(
        [
            "",
            SEP,
            "Доступны RUB-оплаты через СБП и криптовалюту.",
            "Telegram Stars для доп. устройств не используются.",
        ]
    )
    if sbp_tariff_uses_platega():
        lines.append("💳 <b>СБП</b> — автоматическое подтверждение")
    if sbp_tariff_uses_manual():
        lines.append("💳 <b>СБП (ручная)</b> — заявка с подтверждением администратора")
    if config.enable_platega_crypto_user_flow:
        lines.append("💎 <b>Криптовалюта</b> — автоматическое подтверждение")
    elif config.enable_manual_crypto_user_flow:
        lines.append("💎 <b>Крипта (ручная)</b> — заявка с подтверждением администратора")
    return "\n".join(lines)


def tariff_methods_text(
    tariff_title: str,
    *,
    list_price_amount: int | None = None,
    balance_amount: int = 0,
    payable_amount: int | None = None,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    lines = [
        f"💸 <b>{_safe(display_title)}</b>",
        "",
        "Выбери способ оплаты.",
    ]
    duration_badge = tariff_duration_badge(tariff_title)
    if duration_badge:
        lines.extend(["", duration_badge])
    if list_price_amount is not None:
        payable_total = max(int(payable_amount if payable_amount is not None else int(list_price_amount) - int(balance_amount)), 0)
        lines.extend(
            [
                "",
                f"Полная стоимость: <b>{_format_rub(int(list_price_amount))}</b>",
            ]
        )
        if balance_amount > 0:
            lines.extend(
                [
                    f"С баланса спишется: <b>{_format_rub(balance_amount)}</b>",
                    f"Останется оплатить деньгами: <b>{_format_rub(payable_total)}</b>",
                    "Баланс автоматически учитывается в RUB-оплате через СБП и криптовалюту.",
                    "Telegram Stars оплачиваются отдельно, без смешивания с балансом.",
                ]
            )
    lines.extend(
        [
            "",
            SEP,
            "⭐ <b>Telegram Stars</b> — уже работает",
        ]
    )
    if sbp_tariff_uses_platega():
        lines.append("💳 <b>СБП</b> — автоматическое подтверждение после оплаты")
    if sbp_tariff_uses_manual():
        lines.append("💳 <b>СБП (ручная)</b> — заявка с подтверждением администратора")
    if config.enable_platega_crypto_user_flow:
        lines.append("💎 <b>Криптовалюта</b> — автоматическое подтверждение после оплаты")
    elif config.enable_manual_crypto_user_flow:
        lines.append("💎 <b>Крипта</b> — ручная заявка с подтверждением администратора")
    return "\n".join(lines)


def coming_soon_payment_text(method_name: str, tariff_title: str) -> str:
    return (
        f"💸 <b>{_safe(tariff_title)}</b>\n\n"
        f"{_safe(method_name)} пока в разработке.\n\n"
        "Кнопку уже оставили в интерфейсе, а сам способ оплаты подключим следующим этапом."
    )


def crypto_invoice_text(
    tariff_title: str,
    amount_rub: int,
    accepted_assets: str,
    expires_minutes: int,
    *,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
) -> str:
    assets = ", ".join(asset.strip() for asset in accepted_assets.split(",") if asset.strip()) or "USDT, TON"
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount if list_price_amount is not None else amount_rub,
        paid_amount=amount_rub,
        reserved_amount=balance_reserved_amount,
    )
    return (
        f"💎 <b>{_safe(tariff_title)}</b>\n\n"
        f"{breakdown}\n\n"
        f"{SEP}\n"
        f"Доступные активы: <b>{_safe(assets)}</b>\n"
        f"Счёт действует около <b>{expires_minutes} мин</b>.\n\n"
        "Открой счёт по кнопке ниже. После оплаты доступ включится автоматически."
    )


CRYPTO_PAYMENT_NOT_CONFIGURED_TEXT = (
    "💎 Крипта ещё не настроена на стороне сервиса.\n\n"
    "Напиши в поддержку или попробуй оплату через Telegram Stars."
)


PLATEGA_PAYMENT_NOT_CONFIGURED_TEXT = (
    "💳 Автоматическая оплата ещё не настроена на стороне сервиса.\n\n"
    "Попробуй позже или временно используй Telegram Stars."
)


def platega_payment_text(
    *,
    tariff_title: str,
    amount_rub: int,
    method_label: str,
    checkout_label: str,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
    extra_hint: str | None = None,
) -> str:
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount if list_price_amount is not None else amount_rub,
        paid_amount=amount_rub,
        reserved_amount=balance_reserved_amount,
    )
    lines = [
        f"{manual_payment_method_label(method_label)} <b>{_safe(tariff_title)}</b>",
        "",
        breakdown,
        "",
        SEP,
        f"Способ: <b>{_safe(checkout_label)}</b>",
    ]
    if extra_hint:
        lines.append(_safe(extra_hint))
    lines.extend(
        [
            "",
            "Открой оплату по кнопке ниже. После подтверждения доступ включится автоматически.",
        ]
    )
    return "\n".join(lines)


def manual_payment_method_label(method: str) -> str:
    return {
        "sbp_manual": "💳 СБП",
        "crypto_manual": "💎 Крипта",
        "sbp_platega": "💳 СБП",
        "crypto_platega": "💎 Криптовалюта",
        "crypto_bot": "💎 Crypto Bot",
        "balance_rub": "💰 Баланс",
        "sbp": "💳 СБП",
        "crypto": "💎 Криптовалюта",
    }.get(method, "💳 Ручная оплата")


def manual_payment_details_text(
    *,
    tariff_title: str,
    amount_rub: int,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
    method_label: str,
    request_id: int,
    details: str,
    review_hours: int,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount if list_price_amount is not None else amount_rub,
        paid_amount=amount_rub,
        reserved_amount=balance_reserved_amount,
    )
    return (
        f"{manual_payment_method_label(method_label)} <b>{_safe(display_title)}</b>\n\n"
        f"{breakdown}\n"
        f"Номер заявки: <code>{request_id}</code>\n\n"
        f"{SEP}\n"
        "<b>Реквизиты:</b>\n"
        f"<blockquote>{_safe(details)}</blockquote>\n\n"
        "После перевода нажми <b>Я оплатил</b>.\n"
        f"Мы проверим заявку вручную, обычно в течение <b>{review_hours} ч</b>."
    )


def manual_payment_waiting_review_text(
    *,
    tariff_title: str,
    request_id: int,
    method_label: str,
    list_price_amount: int | None = None,
    balance_reserved_amount: int = 0,
    paid_amount: int | None = None,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount if list_price_amount is not None else paid_amount,
        reserved_amount=balance_reserved_amount,
        paid_amount=paid_amount,
    )
    return (
        f"{manual_payment_method_label(method_label)} <b>{_safe(display_title)}</b>\n\n"
        f"{breakdown}\n\n"
        f"Заявка <code>{request_id}</code> отправлена на проверку.\n\n"
        f"{SEP}\n"
        "Администратор подтвердит оплату вручную. Как только проверка завершится, мы пришлём сюда результат."
    )


def manual_payment_reminder_text(
    *,
    tariff_title: str,
    request_id: int,
    method_label: str,
    payment_status: str,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    heading = f"{manual_payment_method_label(method_label)} <b>{_safe(display_title)}</b>"
    if payment_status == "awaiting_admin_review":
        return (
            f"{heading}\n\n"
            f"Напоминаем про заявку <code>{request_id}</code>.\n\n"
            "Если перевод уже сделан, нажми <b>Проверить статус</b>.\n"
            "Если кнопку <b>Я оплатил</b> нажали по ошибке и перевод ещё не делали, "
            "напиши в поддержку, чтобы мы повторно подсказали реквизиты, или нажми <b>Отменить заявку</b>."
        )
    return (
        f"{heading}\n\n"
        f"Напоминаем про заявку <code>{request_id}</code>.\n\n"
        "Если хочешь завершить покупку, напиши в поддержку, и мы повторно подскажем реквизиты для оплаты.\n"
        "После перевода нажми <b>Я оплатил</b>.\n"
        "Если заявка уже не нужна, нажми <b>Отменить заявку</b>."
    )


def manual_payment_rejected_text(
    *,
    tariff_title: str,
    request_id: int,
    reason: str | None = None,
) -> str:
    final_reason = reason or "Отклонено администратором"
    display_title = marketing_tariff_title(tariff_title)
    return (
        f"❌ <b>{_safe(display_title)}</b>\n\n"
        f"Заявка <code>{request_id}</code> отклонена администратором.\n"
        f"Причина: <b>{_safe(final_reason)}</b>\n\n"
        "Если это ошибка, напиши в поддержку."
    )


def manual_payment_inactive_text(
    *,
    tariff_title: str,
    request_id: int,
    status: str,
    reason: str | None = None,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    title = {
        "expired": "⌛",
        "cancelled": "🚫",
    }.get(status, "ℹ")
    status_label = {
        "expired": "истекла",
        "cancelled": "отменена",
    }.get(status, "неактивна")
    text = (
        f"{title} <b>{_safe(display_title)}</b>\n\n"
        f"Заявка <code>{request_id}</code> {status_label}.\n"
    )
    if reason:
        text += f"\nПричина: <blockquote>{_safe(reason)}</blockquote>\n"
    text += "\nЕсли всё ещё хочешь купить доступ, создай новую заявку."
    return text


def referrals_text(
    *,
    referral_link: str,
    balance_rub: int,
    earned_total_rub: int,
    invited_count: int,
    paid_count: int,
    current_level_name: str,
    next_level_name: str | None,
    left_to_next_level: int,
    progress_bar: str,
) -> str:
    next_level_block = (
        "🏁 Следующий уровень: <b>максимальный достигнут</b>"
        if next_level_name is None
        else f"🎯 До следующего уровня: <b>{left_to_next_level} чел.</b>"
    )
    idle_block = ""
    if invited_count <= 0 and paid_count <= 0 and earned_total_rub <= 0:
        idle_block = (
            "\n⚡️ У тебя уже есть реферальная ссылка, но пока нет бонусов.\n"
            "Пригласи друга и получи до <b>100 ₽</b> на внутренний баланс.\n"
        )

    return (
        "🎁 <b>Реферальная программа</b>\n\n"
        "Приглашай друзей и получай бонусы за их первую оплату.\n\n"
        "🔗 <b>Твоя ссылка</b>\n"
        f"{_safe(referral_link)}\n\n"
        f"💰 Баланс: <b>{_format_rub(balance_rub)}</b>\n"
        f"📈 Заработано всего: <b>{_format_rub(earned_total_rub)}</b>\n\n"
        "📊 <b>Сводка</b>\n"
        f"• Приглашено: <b>{invited_count}</b>\n"
        f"• Оплатили: <b>{paid_count}</b>\n\n"
        f"🏆 Уровень: <b>{_safe(current_level_name)}</b>\n"
        f"{next_level_block}\n"
        f"{_safe(progress_bar)}\n"
        f"{idle_block}\n"
        "✨ <b>Как это работает</b>\n"
        "• друг переходит по твоей ссылке\n"
        "• оплачивает первый тариф\n"
        "• вы оба получаете бонус на общий баланс\n\n"
        "Бонусы попадают в обычный баланс и автоматически учитываются при покупке или продлении тарифа.\n\n"
        "💡 За стандартный оплаченный тариф начисляется <b>50 ₽</b>.\n"
        "Если друг оплачивает <b>12 месяцев</b>, вы оба получаете <b>100 ₽</b>."
    )


def referrals_coming_soon_text() -> str:
    return (
        "🎁 <b>Реферальная система</b>\n\n"
        "Этот раздел пока в разработке.\n\n"
        "Скоро здесь появится обновлённый реферальный экран."
    )


def referral_bonus_text(first_name: str, bonus_rub: int, balance_rub: int) -> str:
    return (
        f"🎉 <b>{_safe(first_name)} начислен реферальный бонус</b>\n\n"
        f"Начислено на Баланс: <b>{bonus_rub} р</b>\n"
        f"Текущий Баланс: <b>{balance_rub} р</b>"
    )


def referral_registered_text() -> str:
    return (
        "👤 <b>Друг перешел по твоей ссылке</b>\n\n"
        "Остался один шаг: дождаться его первой оплаты."
    )


def referral_reward_referrer_text(*, bonus_rub: int, balance_rub: int, tariff_title: str | None = None) -> str:
    title = _configured_copy(
        getattr(config, "referral_reward_referrer_template", None),
        "Ваш друг оплатил, вам начислено {bonus_rub} бонусных рублей",
    ).format(bonus_rub=int(bonus_rub))
    tariff_block = f"Тариф друга: <b>{_safe(tariff_title)}</b>\n" if tariff_title else ""
    return (
        f"🎁 <b>{_safe(title)}</b>\n\n"
        f"{tariff_block}"
        f"Начислено: <b>{_format_rub(bonus_rub)}</b>\n"
        f"Текущий баланс: <b>{_format_rub(balance_rub)}</b>"
    )


def referral_reward_invited_text(*, bonus_rub: int, balance_rub: int, tariff_title: str | None = None) -> str:
    title = _configured_copy(
        getattr(config, "referral_reward_invited_text", None),
        "Вам начислены бонусные рубли",
    )
    tariff_block = f"Первый тариф: <b>{_safe(tariff_title)}</b>\n" if tariff_title else ""
    return (
        f"🎉 <b>{_safe(title)}</b>\n\n"
        f"{tariff_block}"
        f"Начислено: <b>{_format_rub(bonus_rub)}</b>\n"
        f"Текущий баланс: <b>{_format_rub(balance_rub)}</b>\n\n"
        "Теперь этот баланс можно использовать внутри сервиса при следующей оплате."
    )


def referral_copy_message_text(*, referral_link: str, share_text: str) -> str:
    return (
        "🔗 <b>Ссылка для друга</b>\n"
        f"<code>{_safe(referral_link)}</code>\n\n"
        "📝 <b>Текст приглашения</b>\n"
        f"{_safe(share_text)}\n\n"
        "Кнопка <b>📤 Пригласить друга</b> откроет Telegram и подставит этот текст вместе со ссылкой."
    )


def configured_referral_share_text() -> str:
    return _configured_copy(
        getattr(config, "referral_share_text", None),
        "Лучший сервис для доступа\nПереходи и получай бонусные рубли 👇",
    )


def payment_referral_hint_text() -> str:
    return (
        "💸 Хочешь окупить подписку?\n"
        "Приглашай друзей и получай бонусы за их первую оплату."
    )


def home_text(user, devices_count: int) -> str:
    status = get_access_status_from_user(user)
    access_expires_at = get_access_expires_at_from_user(user)
    expires_text = access_expires_at.strftime("%Y-%m-%d %H:%M") if access_expires_at else "—"

    if status == "vip_active":
        access_status = "🟣 VIP Активен"
        plan_label = "⭐ VIP"
    elif status == "paid_active":
        access_status = "🟢 Активен"
        plan_label = "💳 Платный доступ"
    elif status == "trial_active":
        access_status = "🔵 Тестовый доступ"
        plan_label = "🆓 Пробный доступ"
    elif status == "blocked":
        access_status = "🔴 Заблокирован"
        plan_label = "⛔ Заблокирован"
    elif status == "expired":
        access_status = "⚪ Истек"
        plan_label = "⌛ Истек"
    else:
        access_status = "🟡 Ожидает активации"
        plan_label = "—"

    preferred_mode = getattr(user, "preferred_mode", None)
    mode_name = format_mode(preferred_mode or infer_mode_from_protocol(user.preferred_protocol))

    balance_total = int(getattr(user, "balance_rub", 0))

    footer = (
        "Используй кнопки ниже для управления доступом и устройствами."
        if status != "blocked"
        else "Доступ ограничен. Остаются Личный кабинет, поддержка и информация."
    )

    return (
        "👤 <b>Личный кабинет</b>\n"
        f"{SURFACE_SEP}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📅 Статус: {access_status}\n"
        f"🏷 Тип доступа: <b>{plan_label}</b>\n"
        f"⏳ Действует до: <b>{_safe(expires_text)}</b>\n"
        f"🔌 Режим: {mode_name}\n"
        f"💰 Баланс: <b>{balance_total} р</b>\n"
        f"📱 Устройств: <b>{devices_count}</b>\n"
        f"{SURFACE_SEP}\n"
        f"{footer}"
    )


def blocked_user_action_text() -> str:
    return (
        "⛔ <b>Доступ ограничен</b>\n\n"
        "Сейчас доступны только Личный кабинет, поддержка и информация."
    )


def cabinet_text(user, devices_count: int) -> str:
    return home_text(user, devices_count)


def devices_overview_text(
    devices_count: int,
    device_rows_text: str,
    *,
    device_limit: int = 3,
    extra_slots_active: int = 0,
) -> str:
    body = (
        device_rows_text
        if device_rows_text
        else "Пока устройств нет.\nСоздай первое устройство кнопкой ниже."
    )
    extra_line = (
        f"➕ Доп. устройств активно: <b>{extra_slots_active}</b>\n"
        if extra_slots_active > 0
        else ""
    )
    return (
        "📱 <b>Управление подключениями</b>\n"
        f"{SURFACE_SEP}\n"
        f"🔢 Создано устройств: <b>{devices_count}</b> из <b>{device_limit}</b>\n"
        f"{extra_line}\n"
        f"{body}\n"
        f"{SURFACE_SEP}\n"
        "Выбери устройство ниже или создай новое."
    )


def device_list_summary_line(index: int, device_name: str, protocol: str, metadata: dict | None = None) -> str:
    payload = metadata or {}
    status_label = str(payload.get("status_label") or "Активно").strip() or "Активно"
    source_label = str(payload.get("source_label") or "").strip()
    country_name = str(payload.get("country_name") or "").strip()
    details = " • ".join(part for part in (source_label, country_name) if part)
    return (
        f"{index}. <b>{_safe(device_name)}</b>\n"
        f"   🟢 {_safe(status_label)}"
        + (f"\n   {_safe(details)}" if details else "")
    )


def device_list_title(device_name: str, os_type: str | None = None, protocol: str | None = None) -> str:
    return device_name


def device_card_text(device_data: dict, expires_at: str) -> str:
    mode_label = format_mode(infer_mode_from_protocol(device_data.get("protocol"), device_data))
    os_label = OS_LABELS.get(device_data.get("device_type", "other"), "🧩 Другое")
    return (
        f"📱 <b>{_safe(device_data.get('device_name', 'Устройство'))}</b>\n"
        f"{SURFACE_SEP}\n"
        f"{os_label}\n"
        f"{mode_label}\n"
        f"⏳ Доступ до: <b>{_safe(expires_at)}</b>\n"
        f"{SURFACE_SEP}\n"
        "Ниже можно выбрать режим, открыть настройки или повторно получить ключ."
    )


def device_settings_text(device_data: dict, expires_at: str) -> str:
    mode_label = format_mode(infer_mode_from_protocol(device_data.get("protocol"), device_data))
    os_label = OS_LABELS.get(device_data.get("device_type", "other"), "🧩 Другое")
    country_label = COUNTRY_LABELS.get(device_data.get("country_code", "de"), "🇩🇪 Германия")
    return (
        f"⚙ <b>Настройки устройства</b>\n"
        f"{SURFACE_SEP}\n"
        f"🏷 Название: <b>{_safe(device_data.get('device_name', 'Устройство'))}</b>\n"
        f"🖥 ОС: {os_label}\n"
        f"🔌 Режим: {mode_label}\n"
        f"🌍 Локация: {country_label}\n"
        f"⏳ Доступ до: <b>{_safe(expires_at)}</b>\n"
        f"{SURFACE_SEP}\n"
        "Можно переименовать устройство, сменить ОС или удалить его."
    )


def ask_device_name_text() -> str:
    return "✏ <b>Как назвать устройство?</b>\n\nНапример: <code>Телефон</code>"


def ask_device_os_text(device_name: str) -> str:
    return f"🖥 <b>{_safe(device_name)}</b>\n\nВыбери операционную систему устройства."


def _mode_description_block(*, telegram_id: int | None = None, country_code: str | None = None) -> str:
    return "\n".join(
        f"{format_mode(mode)} — {get_mode_description(mode, telegram_id=telegram_id)}"
        for mode in get_mode_keys(telegram_id=telegram_id, country_code=country_code)
    )


def ask_device_protocol_text(
    device_name: str,
    os_type: str,
    country_code: str | None = None,
    *,
    telegram_id: int | None = None,
) -> str:
    country_label = f"{COUNTRY_LABELS.get(country_code, country_code)}\n" if country_code else ""
    return (
        f"🔌 <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"{country_label}"
        f"{SURFACE_SEP}\n"
        "Выбери режим для нового подключения.\n\n"
        f"{_mode_description_block(telegram_id=telegram_id, country_code=country_code)}"
    )


def ask_device_country_text(device_name: str, os_type: str) -> str:
    return (
        f"🌍 <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"{SURFACE_SEP}\n"
        "Выбери страну подключения.\n\n"
        "🇩🇪 Германия — оптимальный выбор на каждый день\n"
        "🇩🇰 Дания — дополнительный маршрут"
    )


def vless_happ_question_text(
    device_name: str,
    os_type: str,
    country_name: str,
    protocol_name: str | None = None,
) -> str:
    resolved_protocol_name = protocol_name or format_mode("stable")
    return (
        f"✅ <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"{SEP}\n"
        "Устройство уже создано.\n\n"
        f"У тебя уже установлен <b>Happ</b> для подключения <b>{_safe(resolved_protocol_name)}</b>?"
    )


def vless_happ_download_text(
    device_name: str,
    os_type: str,
    country_name: str,
    protocol_name: str | None = None,
) -> str:
    store_label = "Google Play" if os_type == "android" else "App Store"
    resolved_protocol_name = protocol_name or format_mode("stable")
    return (
        f"📲 <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"{SEP}\n"
        "Сначала установи <b>Happ</b>.\n\n"
        "Что делать дальше:\n"
        f"1. Открой {store_label} по кнопке ниже.\n"
        "2. Установи Happ.\n"
        "3. Вернись в бот.\n"
        "4. Нажми <b>Установил Happ</b>.\n\n"
        f"После этого я сразу отправлю ключ для подключения <b>{_safe(resolved_protocol_name)}</b>.\n"
        "Если захочешь, QR-код можно будет открыть отдельной кнопкой."
    )


def vless_delivery_text(
    device_name: str,
    os_type: str,
    country_name: str,
    mobile_happ: bool,
    protocol_name: str | None = None,
) -> str:
    resolved_protocol_name = protocol_name or format_mode("stable")
    if mobile_happ:
        return (
            f"🔑 <b>{_safe(device_name)}</b>\n"
            f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
            f"🌍 <b>{_safe(country_name)}</b>\n"
            f"{SEP}\n"
            "Теперь подключаем устройство через клиент.\n\n"
            f"{MOBILE_KEY_IMPORT_TEXT}\n\n"
            "Если удобнее, можно отдельно открыть QR-код кнопкой в карточке устройства и отсканировать его в клиенте.\n\n"
            "Если Happ ещё не установлен, сначала установи его из магазина приложений."
        )
    return (
        f"🔑 <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"{SEP}\n"
        "Устройство создано.\n\n"
        f"Ниже придёт ключ <b>{_safe(resolved_protocol_name)}</b> для подключения.\n"
        "Импортируй его в совместимый клиент на своём устройстве.\n"
        "Если удобнее, можно открыть QR-код кнопкой ниже.\n\n"
        "Если что-то не сработает с первого раза, просто запроси ключ ещё раз или напиши в поддержку."
    )


def trojan_delivery_text(device_name: str, os_type: str, country_name: str) -> str:
    return (
        f"🔑 <b>{_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"{SEP}\n"
        "Устройство создано.\n\n"
        f"Ниже придёт ключ <b>{format_mode('reserve')}</b> для подключения.\n"
        "Импортируй его в совместимый клиент.\n"
        "Если удобнее, можно открыть QR-код отдельной кнопкой."
    )


def device_guide_text(protocol: str, os_type: str, device_name: str, country_name: str) -> str:
    if protocol == "trojan":
        if os_type in {"android", "ios"}:
            return (
                f"📘 <b>Как подключить {_safe(device_name)}</b>\n"
                f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
                f"🌍 <b>{_safe(country_name)}</b>\n"
                f"{SEP}\n"
                "1. Установи подходящее приложение.\n"
                "2. Скопируй ключ или открой QR-код.\n"
                "3. Импортируй ключ в приложение и включи подключение.\n\n"
                f"Полная инструкция: {_safe(MANUAL_URL)}"
            )
        return (
            f"📘 <b>Как подключить {_safe(device_name)}</b>\n"
            f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
            f"🌍 <b>{_safe(country_name)}</b>\n"
            f"{SEP}\n"
            "1. Установи совместимый клиент.\n"
            "2. Получи ключ для подключения кнопкой ниже.\n"
            "3. Импортируй ключ в клиент.\n"
            "4. Если удобнее, открой QR-код отдельной кнопкой и отсканируй его.\n"
            "5. Сохрани профиль и включи подключение.\n\n"
            "Если не знаешь, какой клиент выбрать, напиши в поддержку."
        )

    if os_type in {"android", "ios"}:
        return (
            f"📘 <b>Как подключить {_safe(device_name)}</b>\n"
            f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
            f"🌍 <b>{_safe(country_name)}</b>\n"
            f"{SEP}\n"
            "1. Установи подходящее приложение.\n"
            "2. Скопируй ключ или открой QR-код.\n"
            "3. Импортируй ключ в приложение и включи подключение.\n\n"
            f"Полная инструкция: {_safe(MANUAL_URL)}"
        )

    return (
        f"📘 <b>Как подключить {_safe(device_name)}</b>\n"
        f"{OS_LABELS.get(os_type, '🧩 Другое')}\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"{SEP}\n"
        "1. Установи совместимый клиент.\n"
        "2. Получи ключ для подключения кнопкой ниже.\n"
        "3. Импортируй ключ или QR-код в клиент.\n"
        "4. Сохрани профиль и включи его.\n\n"
        "Если не знаешь, какой клиент выбрать, напиши в поддержку."
    )


def ask_existing_device_country_text(device_name: str, current_country_code: str | None = None) -> str:
    current_country = COUNTRY_LABELS.get(current_country_code, current_country_code or "—")
    return (
        f"🔌 <b>{_safe(device_name)}</b>\n"
        f"🌍 Текущая страна: <b>{_safe(current_country)}</b>\n"
        f"{SURFACE_SEP}\n"
        "Выбери страну подключения.\n\n"
        "🇩🇪 Германия — оптимальный выбор на каждый день\n"
        "🇩🇰 Дания — дополнительный маршрут"
    )


def ask_existing_device_protocol_text(
    device_name: str,
    country_name: str | None = None,
    *,
    telegram_id: int | None = None,
    country_code: str | None = None,
) -> str:
    selected_country = f"{_safe(country_name)}\n" if country_name else ""
    return (
        f"🔌 <b>{_safe(device_name)}</b>\n"
        f"{selected_country}"
        f"{SURFACE_SEP}\n"
        "Выбери режим для этого подключения:\n\n"
        f"{_mode_description_block(telegram_id=telegram_id, country_code=country_code)}"
    )


def mobile_mode_placeholder_text(country_code: str | None = None) -> str:
    country_label = COUNTRY_LABELS.get(country_code, "выбранной стране")
    return (
        "📱 <b>Мобильный режим пока в подготовке</b>\n\n"
        f"Для обычных пользователей мы ещё не открыли его на направлении <b>{_safe(country_label)}</b>.\n"
        "Пока используй <b>🛡 Стабильный</b> или <b>🧰 Резерв</b>.\n\n"
        "Как только мобильный маршрут будет готов для всех, мы откроем его прямо в этом экране."
    )


def vpn_client_created_text(device_name: str, protocol: str, country_name: str, access_expires_at: str, connection_uri: str) -> str:
    del device_name
    return (
        "✅ <b>Доступ активен</b>\n\n"
        f"🔌 Режим: <b>{_safe(protocol)}</b>\n"
        f"🌍 <b>{_safe(country_name)}</b>\n"
        f"⏳ До: <b>{_safe(access_expires_at)}</b>\n\n"
        "<b>🔑 Ключ:</b>\n"
        f"<code>{_safe(connection_uri)}</code>\n\n"
        "Если не сработало — зажми ключ и скопируй вручную."
    )


def split_routing_pack_text(device_name: str, target_client: str) -> str:
    return (
        "🧭 <b>Раздельная маршрутизация</b>\n\n"
        f"Для устройства <b>{_safe(device_name)}</b> подготовлен JSON-пакет для <b>{_safe(target_client)}</b>.\n\n"
        "Что делает пакет:\n"
        "• российские ресурсы идут напрямую\n"
        "• зарубежные ресурсы идут через Amonora\n"
        "• локальные сети остаются прямыми\n"
        "• `bittorrent` блокируется\n\n"
        "Импортируй этот пакет в клиент, если он поддерживает routing/TUN-профили.\n"
        "Рекомендуемый MTU: <b>1400</b>, запасной вариант: <b>1420</b>."
    )


def payment_success_text(
    tariff_title: str,
    expires_at: str,
    *,
    list_price_amount: int | None = None,
    balance_applied_amount: int = 0,
    paid_amount: int | None = None,
) -> str:
    display_title = marketing_tariff_title(tariff_title)
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount,
        balance_applied_amount=balance_applied_amount,
        paid_amount=paid_amount,
    )
    text = (
        "💸 <b>Оплата успешно подтверждена</b>\n\n"
        f"Тариф: <b>{_safe(display_title)}</b>\n"
        f"Доступ активен до: <b>{_safe(expires_at)}</b>\n\n"
    )
    if breakdown:
        text += f"{breakdown}\n\n"
    text += (
        f"{SEP}\n"
        "Если у тебя уже были устройства, срок доступа для них синхронизирован.\n\n"
        "💸 Хочешь окупить подписку?\n"
        "Приглашай друзей и получай бонусы за их первую оплату."
    )
    return text


def device_slot_payment_success_text(
    *,
    title: str,
    expires_at: str,
    device_limit: int,
    slots_count: int = 1,
    list_price_amount: int | None = None,
    balance_applied_amount: int = 0,
    paid_amount: int | None = None,
) -> str:
    breakdown = _payment_breakdown_text(
        list_price_amount=list_price_amount,
        balance_applied_amount=balance_applied_amount,
        paid_amount=paid_amount,
    )
    lines = [
        "📱 <b>Дополнительное устройство активировано</b>",
        "",
        f"Пакет: <b>{_safe(title)}</b>",
        f"Добавлено слотов: <b>+{int(slots_count)}</b>",
        f"Новый лимит устройств: <b>{int(device_limit)}</b>",
        f"Действует до: <b>{_safe(expires_at)}</b>",
    ]
    if breakdown:
        lines.extend(["", breakdown])
    lines.extend(
        [
            "",
            SEP,
            "Теперь можно создать ещё одно устройство в разделе <b>📱 Устройства</b>.",
            "Если у тебя подписка на 6 или 12 месяцев, этот слот тоже будет работать весь оплаченный период.",
            "После окончания текущей подписки этот доп. слот сгорит и при следующем периоде покупается заново.",
        ]
    )
    return "\n".join(lines)


def balance_topup_intro_text(*, balance_rub: int, balance_available_rub: int) -> str:
    del balance_available_rub
    return (
        "💰 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{_format_rub(balance_rub)}</b>\n"
        f"\n{SEP}\n"
        "Выбери сумму пополнения. Деньги останутся на балансе и будут списываться при покупке или продлении тарифа."
    )


def balance_topup_methods_text(amount_rub: int) -> str:
    return (
        "💰 <b>Пополнение баланса</b>\n\n"
        f"Сумма: <b>{_format_rub(amount_rub)}</b>\n\n"
        "Выбери удобный способ оплаты."
    )


def balance_topup_payment_text(*, amount_rub: int, method_label: str, checkout_label: str = "страница оплаты") -> str:
    return (
        "💰 <b>Пополнение баланса</b>\n\n"
        f"Сумма: <b>{_format_rub(amount_rub)}</b>\n"
        f"Метод: <b>{_safe(method_label)}</b>\n\n"
        f"Открой <b>{_safe(checkout_label)}</b> и заверши платёж. "
        "Когда провайдер подтвердит оплату, мы автоматически зачислим деньги на баланс."
    )


def balance_topup_success_text(*, amount_rub: int, balance_rub: int) -> str:
    return (
        "💰 <b>Баланс пополнен</b>\n\n"
        f"Начислено: <b>{_format_rub(amount_rub)}</b>\n"
        f"Текущий баланс: <b>{_format_rub(balance_rub)}</b>\n\n"
        "Теперь баланс можно использовать при следующей покупке или продлении."
    )


def user_blocked_notification_text() -> str:
    return (
        "⛔ <b>Доступ временно заблокирован</b>\n\n"
        "Мы обновили статус аккаунта. Пока доступны только личный кабинет, поддержка и информация."
    )


def user_unblocked_notification_text() -> str:
    return (
        "✅ <b>Доступ восстановлен</b>\n\n"
        "Блокировка снята. Возвращаю обычное меню и актуальное состояние кабинета."
    )


def subscription_extended_notification_text(*, days: int, expires_at: str) -> str:
    return (
        "📅 <b>Подписка продлена</b>\n\n"
        f"Продление: <b>{days} дней</b>\n"
        f"Новый срок доступа: <b>{_safe(expires_at)}</b>"
    )


PAYMENT_SYNC_WARNING_TEXT = (
    "⚠️ Оплата прошла, но синхронизация доступа завершилась с ошибкой.\n"
    "Напиши в поддержку, если доступ не обновился в течение минуты."
)


PANEL_CONNECTION_ERROR_TEXT = (
    "Не удалось связаться с сервисом доступа. Попробуй ещё раз чуть позже."
)


PANEL_OPERATION_ERROR_TEXT = (
    "Операция в сервисе доступа завершилась ошибкой. Попробуй ещё раз позже."
)


def device_delivery_retry_text(device_name: str) -> str:
    return (
        "⚠️ <b>Подключение уже создано</b>\n\n"
        f"Для устройства <b>{_safe(device_name)}</b> выдача инструкции прервалась.\n"
        "Открой <b>📱 Устройства</b> и заново открой это подключение, чтобы получить ключ."
    )


def device_limit_text(limit: int = 3) -> str:
    return (
        "⚠️ <b>Лимит устройств достигнут</b>\n\n"
        f"На одном аккаунте доступно не более <b>{limit} устройств</b>."
    )


def device_limit_reached_text(
    *,
    devices_count: int,
    device_limit: int,
    max_limit: int,
    can_buy_more: bool,
    price_rub: int,
    expires_at: str | None = None,
    is_over_limit: bool = False,
) -> str:
    lines = [
        "⚠️ <b>Лимит устройств достигнут</b>",
        "",
        (
            f"Сейчас подключено <b>{devices_count}</b> устройств при активном лимите <b>{device_limit}</b>."
            if is_over_limit
            else f"Сейчас подключено <b>{devices_count}</b> из <b>{device_limit}</b> устройств."
        ),
    ]
    if can_buy_more:
        lines.extend(
            [
                "",
                f"Можно докупить <b>+1 устройство</b> за <b>{_format_rub(price_rub)}</b>.",
                f"Максимум на аккаунте доступно до <b>{max_limit}</b> устройств.",
            ]
        )
        if expires_at:
            lines.append(f"Доп. слот будет работать до: <b>{_safe(expires_at)}</b>")
    elif is_over_limit:
        lines.extend(
            [
                "",
                "Новые устройства пока недоступны.",
                "Удалите лишние устройства или восстановите доп. слот покупкой на текущий оплаченный период.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Чтобы подключить новое устройство, сначала отвяжите одно из текущих.",
            ]
        )
    return "\n".join(lines)


def device_deleted_text() -> str:
    return "✅ <b>Устройство удалено</b>"


def delete_device_not_found_text() -> str:
    return "⚠️ <b>Устройство не найдено</b>"


def renamed_device_text(new_name: str) -> str:
    return f"✅ Устройство переименовано в <b>{_safe(new_name)}</b>"


def changed_device_os_text(os_type: str) -> str:
    return f"✅ Новая ОС устройства: <b>{OS_LABELS.get(os_type, os_type)}</b>"


def changed_country_text(country_code: str) -> str:
    return f"✅ Активная страна: <b>{COUNTRY_LABELS.get(country_code, country_code)}</b>"


def device_region_recreate_required_text(current_country_code: str, target_country_code: str) -> str:
    current_label = COUNTRY_LABELS.get(current_country_code, current_country_code)
    target_label = COUNTRY_LABELS.get(target_country_code, target_country_code)
    return (
        "⚠️ <b>Готовое устройство нельзя просто перенести в другую страну</b>\n\n"
        f"Сейчас устройство привязано к: <b>{current_label}</b>\n"
        f"Выбрана новая страна: <b>{target_label}</b>\n\n"
        "Чтобы сменить страну подключения, удали текущее устройство и создай новое."
    )
