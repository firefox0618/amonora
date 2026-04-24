from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="👤 Личный кабинет"),
            KeyboardButton(text="📱 Устройства"),
        ],
        [
            KeyboardButton(text="💳 Купить"),
            KeyboardButton(text="🛟 Поддержка"),
        ],
        [
            KeyboardButton(text="📚 Информация"),
            KeyboardButton(text="🎁 Реферальная система"),
        ],
        [KeyboardButton(text="Главное меню")],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Amonora",
)


blocked_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Личный кабинет")],
        [
            KeyboardButton(text="🛟 Поддержка"),
            KeyboardButton(text="📚 Информация"),
        ],
        [KeyboardButton(text="Главное меню")],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Amonora",
)


def main_menu_for_user(user) -> ReplyKeyboardMarkup:
    return blocked_main_menu if getattr(user, "is_blocked", False) else main_menu
