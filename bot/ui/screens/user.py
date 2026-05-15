from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile

from bot.services.user.models import DEVICE_GUIDES, TestBonusSummary, TestUserSummary
from bot.utils.texts import CHANNEL_URL, OS_LABELS, PRIVACY_URL, REFUNDS_URL, SUPPORT_URL, TERMS_URL


SCREEN_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "v2"
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

GUIDES_CHOICE_TEXT = """📘 <b>Инструкция по подключению</b>

Выберите вашу ОС или устройство 👇

На следующем шаге откроется инструкция именно под ваше устройство и ссылки на установку <b>Happ</b>."""


def _screen_photo(screen_key: str) -> FSInputFile:
    filename = SCREEN_IMAGE_FILENAMES[screen_key]
    path = SCREEN_ASSETS_DIR / filename
    if not path.exists():
        fallback_path = SCREEN_ASSETS_DIR / SCREEN_IMAGE_FILENAMES["main_menu"]
        return FSInputFile(path=fallback_path, filename=fallback_path.name)
    return FSInputFile(path=path, filename=filename)


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


def _after_install_text(device_key: str) -> str:
    guide = DEVICE_GUIDES[device_key]
    return (
        f"Готово! Теперь нажмите <b>«Подключиться»</b> для <b>{guide.title}</b>.\n"
        "Если возникнут трудности, обратитесь в <b>Поддержку</b> "
        "или ознакомьтесь с <b>Инструкцией</b>."
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
            f"📱 Устройств: <b>{summary.devices_count}</b> из <b>{summary.device_limit}</b>",
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


def _bonus_text(summary: TestBonusSummary) -> str:
    return (
        "🔥 <b>Бонусы и скидки</b>\n\n"
        "💸 <b>50 ₽ тебе за каждого приглашённого друга</b>\n\n"
        "🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{summary.referral_link}</code>\n\n"
        "👥 <b>Приглашай друзей:</b> отправь ссылку, и после оплаты вы оба получите бонус.\n"
        "🎁 <b>Подарок:</b> оформи подписку другу за пару кликов.\n"
        "🏷 <b>Промокоды:</b> активируй и получай дополнительные скидки.\n"
        "📊 <b>Статистика:</b> отслеживай бонусы в своём профиле."
    )


def _bonus_stats_text(summary: TestBonusSummary) -> str:
    return (
        "📊 <b>Моя статистика</b>\n\n"
        f"👥 Приглашено: <b>{summary.invited_count}</b>\n"
        f"💳 Оплатили: <b>{summary.paid_count}</b>\n"
        f"💰 Заработано: <b>{summary.earned_total_rub} ₽</b>\n"
        f"🏦 Доступно на балансе: <b>{summary.balance_available_rub} ₽</b>"
    )
