from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.texts import MANUAL_URL, TERMS_URL


def info_root_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Инструкция", url=MANUAL_URL)],
            [InlineKeyboardButton(text="📜 Документы", callback_data="info:docs")],
            [InlineKeyboardButton(text="📡 Канал", url="https://t.me/amonora_new")],
            [InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/amonora_support_bot")],
        ]
    )


def info_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data="info:root")],
            [InlineKeyboardButton(text="📘 Полная инструкция", url=MANUAL_URL)],
            [InlineKeyboardButton(text="📡 Канал", url="https://t.me/amonora_new")],
            [InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/amonora_support_bot")],
        ]
    )


def info_documents_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="🔐 Политика конфиденциальности", url="https://www.amonoraconnect.com/legal/privacy")],
            [InlineKeyboardButton(text="↩ Политика возврата", url="https://www.amonoraconnect.com/legal/refunds")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="info:root")],
        ]
    )
