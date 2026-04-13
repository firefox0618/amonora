from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


home_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Подключить устройство", callback_data="home:devices"),
        ],
        [
            InlineKeyboardButton(text="💳 Купить доступ", callback_data="home:tariffs"),
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="home:balance"),
        ],
        [
            InlineKeyboardButton(text="🔗 Единая ссылка", callback_data="home:subscription_page"),
        ],
        [
            InlineKeyboardButton(text="🎁 Реферальная система", callback_data="home:referrals"),
        ],
        [
            InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/amonora_support_bot"),
        ],
        [
            InlineKeyboardButton(text="📚 Информация", callback_data="home:info"),
        ],
    ]
)


blocked_home_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/amonora_support_bot"),
        ],
        [
            InlineKeyboardButton(text="📚 Информация", callback_data="home:info"),
        ],
    ]
)


def home_keyboard_for_user(user) -> InlineKeyboardMarkup:
    return blocked_home_keyboard if getattr(user, "is_blocked", False) else home_keyboard
