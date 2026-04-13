from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.modes import format_mode, get_mode_keys


def modes_keyboard(*, telegram_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=format_mode(mode), callback_data=f"mode:{mode}")]
            for mode in get_mode_keys(telegram_id=telegram_id)
        ]
    )

protocols_keyboard = modes_keyboard
