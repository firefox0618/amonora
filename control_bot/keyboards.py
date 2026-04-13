from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from control_bot.access import CONTROL_ROLE_ADMIN, CONTROL_ROLE_OWNER


def control_menu_keyboard(role: str | None = None) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Дашборд"), KeyboardButton(text="Ноды")],
        [KeyboardButton(text="Платежи"), KeyboardButton(text="Пользователи")],
        [KeyboardButton(text="Проблемы"), KeyboardButton(text="Поддержка")],
        [KeyboardButton(text="Коды входа"), KeyboardButton(text="Уведомления")],
        [KeyboardButton(text="События"), KeyboardButton(text="Помощь")],
    ]
    if role in {CONTROL_ROLE_ADMIN, CONTROL_ROLE_OWNER}:
        keyboard.append([KeyboardButton(text="Канал")])
    if role == CONTROL_ROLE_OWNER:
        keyboard.append([KeyboardButton(text="Рассылка / Триггеры")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Amonora Control",
    )


def control_secondary_keyboard(role: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📊 Дашборд", callback_data="control:dashboard"),
            InlineKeyboardButton(text="🌍 Ноды", callback_data="control:nodes"),
        ],
        [
            InlineKeyboardButton(text="💳 Платежи", callback_data="control:payments"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="control:users"),
        ],
        [
            InlineKeyboardButton(text="⚠️ Проблемы", callback_data="control:problems"),
            InlineKeyboardButton(text="💬 Поддержка", callback_data="control:support"),
        ],
        [
            InlineKeyboardButton(text="🔐 Коды входа", callback_data="control:login_codes"),
            InlineKeyboardButton(text="⚙️ Уведомления", callback_data="control:notifications"),
        ],
        [InlineKeyboardButton(text="🧾 События", callback_data="control:events")],
    ]
    if role in {CONTROL_ROLE_ADMIN, CONTROL_ROLE_OWNER}:
        rows.append([InlineKeyboardButton(text="📣 Канал", callback_data="control:channel")])
    if role == CONTROL_ROLE_OWNER:
        rows.append([InlineKeyboardButton(text="📢 Рассылка / Триггеры", callback_data="control:broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
