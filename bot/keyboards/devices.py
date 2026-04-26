from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.modes import format_mode, get_mode_keys, get_mode_region_codes
from bot.utils.regions import get_region, get_user_selectable_region_codes
from bot.utils.texts import MANUAL_URL

OS_OPTIONS = [
    ("android", "🤖 Android"),
    ("ios", "🍎 iPhone / iPad"),
    ("windows", "🪟 Windows"),
    ("macos", "💻 macOS"),
    ("linux", "🐧 Linux"),
]

HAPP_STORE_URLS = {
    "android": "https://play.google.com/store/apps/details?id=com.happproxy",
    "ios": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
}

COPY_TEXT_BUTTON_MAX_LENGTH = 256


def add_device_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать устройство",
                    callback_data="device:add",
                )
            ],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="device:back")],
        ]
    )


def devices_list_keyboard(
    devices: list,
    *,
    allow_add: bool = True,
    can_buy_more: bool = False,
    price_rub: int = 49,
) -> InlineKeyboardMarkup:
    rows = []
    for device in devices:
        rows.append(
            [
                InlineKeyboardButton(
                    text=device["title"],
                    callback_data=device.get("callback_data") or f"device:view:{device['id']}",
                )
            ]
        )

    if allow_add:
        rows.append([InlineKeyboardButton(text="➕ Создать устройство", callback_data="device:add")])
    elif can_buy_more:
        rows.append([InlineKeyboardButton(text=f"🛒 Купить +1 устройство за {price_rub} ₽", callback_data="device-slot:buy")])
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="device:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_limit_reached_keyboard(*, can_buy_more: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_buy_more:
        rows.append([InlineKeyboardButton(text="🛒 Купить +1 устройство за 49 ₽", callback_data="device-slot:buy")])
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="device:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_card_keyboard(device_id: int, protocol: str = "vless") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🔌 Режим", callback_data=f"device:location:{device_id}"),
        ],
        [
            InlineKeyboardButton(text="⚙ Настройки устройства", callback_data=f"device:settings:{device_id}"),
        ],
        [
            InlineKeyboardButton(text="🔑 Получить ключ", callback_data=f"device:config:{device_id}"),
            InlineKeyboardButton(text="📷 QR-код", callback_data=f"device:qr:{device_id}"),
        ],
        [
            InlineKeyboardButton(text="📘 Инструкция", callback_data=f"device:guide:{device_id}"),
            InlineKeyboardButton(text="🧭 Маршруты РФ", callback_data=f"device:routing:{device_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def public_device_card_keyboard(slot_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♻ Освободить слот", callback_data=f"device:public:delete:{slot_index}")],
            [InlineKeyboardButton(text="⬅ К списку устройств", callback_data="device:back")],
        ]
    )


def device_settings_keyboard(device_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏ Переименовать", callback_data=f"device:rename:{device_id}"),
            InlineKeyboardButton(text="🖥 Сменить ОС", callback_data=f"device:oschange:{device_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить устройство", callback_data=f"device:delete:{device_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть настройки", callback_data=f"device:settings:close:{device_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_os_keyboard(prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for value, label in OS_OPTIONS:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"{prefix}:{value}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_protocol_keyboard(*, telegram_id: int | None = None, country_code: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=format_mode(mode, country_code=country_code), callback_data=f"device:mode:{mode}")]
            for mode in get_mode_keys(telegram_id=telegram_id, country_code=country_code)
        ]
    )


def device_protocol_keyboard_for_existing(
    device_id: int,
    country_code: str | None = None,
    *,
    telegram_id: int | None = None,
) -> InlineKeyboardMarkup:
    def _callback(mode: str) -> str:
        if country_code:
            return f"device:remode:{device_id}:{country_code}:{mode}"
        return f"device:remode:{device_id}:{mode}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=format_mode(mode, country_code=country_code), callback_data=_callback(mode))]
            for mode in get_mode_keys(telegram_id=telegram_id, country_code=country_code)
        ]
    )


def device_country_keyboard(prefix: str, *, telegram_id: int | None = None, mode: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    region_codes = get_mode_region_codes(telegram_id=telegram_id, mode=mode) if mode else get_user_selectable_region_codes(telegram_id=telegram_id)
    for value in region_codes:
        region = get_region(value)
        rows.append([InlineKeyboardButton(text=f"{region.flag} {region.name_ru}", callback_data=f"{prefix}:{value}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_happ_question_keyboard(device_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, установлен", callback_data=f"device:happ:installed:{device_id}")],
            [InlineKeyboardButton(text="📲 Нет, не установлен", callback_data=f"device:happ:notinstalled:{device_id}")],
            [InlineKeyboardButton(text="↩ К устройству", callback_data=f"device:view:{device_id}")],
        ]
    )


def device_happ_install_keyboard(device_id: int, os_type: str) -> InlineKeyboardMarkup:
    rows = []
    store_url = HAPP_STORE_URLS.get(os_type)
    if store_url:
        rows.append([InlineKeyboardButton(text="📥 Открыть магазин", url=store_url)])
        rows.extend(
        [
            [InlineKeyboardButton(text="✅ Установил Happ", callback_data=f"device:happ:ready:{device_id}")],
            [InlineKeyboardButton(text="📘 Полная инструкция", url=MANUAL_URL)],
            [InlineKeyboardButton(text="↩ Назад", callback_data=f"device:happ:prompt:{device_id}")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_instruction_keyboard(device_id: int, protocol: str = "vless") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Получить ключ ещё раз", callback_data=f"device:config:{device_id}"),
                InlineKeyboardButton(text="📷 QR-код", callback_data=f"device:qr:{device_id}"),
            ],
            [InlineKeyboardButton(text="📘 Полная инструкция", url=MANUAL_URL)],
            [InlineKeyboardButton(text="🧭 Маршруты РФ", callback_data=f"device:routing:{device_id}")],
            [InlineKeyboardButton(text="↩ К устройству", callback_data=f"device:view:{device_id}")],
        ]
    )


def device_credential_keyboard(device_id: int, connection_uri: str, *, allow_copy: bool = True) -> InlineKeyboardMarkup:
    first_row: list[InlineKeyboardButton] = []
    if allow_copy and 1 <= len(connection_uri) <= COPY_TEXT_BUTTON_MAX_LENGTH:
        first_row.append(
            InlineKeyboardButton(
                text="📋 Скопировать ключ",
                copy_text=CopyTextButton(text=connection_uri),
            )
        )
    first_row.append(InlineKeyboardButton(text="📷 Показать QR", callback_data=f"device:qr:{device_id}"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            first_row,
            [
                InlineKeyboardButton(text="📘 Инструкция", callback_data=f"device:guide:{device_id}"),
                InlineKeyboardButton(text="🔄 Сменить режим", callback_data=f"device:location:{device_id}"),
            ],
        ]
    )
