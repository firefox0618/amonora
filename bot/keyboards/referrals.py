from urllib.parse import quote, urlencode

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.texts import configured_referral_share_text


def referral_share_url(referral_link: str) -> str:
    return f"https://t.me/share/url?{urlencode({'url': referral_link, 'text': configured_referral_share_text()}, quote_via=quote)}"


def referral_keyboard(referral_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Пригласить друга",
                    url=referral_share_url(referral_link),
                )
            ],
            [
                InlineKeyboardButton(text="🔗 Скопировать ссылку", callback_data="referrals:copy"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="referrals:refresh"),
            ],
            [
                InlineKeyboardButton(text="↩ В кабинет", callback_data="home:cabinet"),
            ],
        ]
    )
