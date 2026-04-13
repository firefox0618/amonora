import logging

from aiogram import Bot
from aiogram.types import ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.config import config
from bot.db import count_user_vpn_clients, get_user_by_telegram_id
from bot.keyboards.home import home_keyboard_for_user
from bot.utils.texts import home_text


logger = logging.getLogger(__name__)


async def _send_message(bot: Bot, chat_id: int, text: str, *, reply_markup=None) -> bool:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        logger.warning("Failed to send user notification to telegram_id=%s", chat_id)
        return False


async def send_user_message(telegram_id: int, text: str, *, reply_markup=None) -> bool:
    token = config.bot_token
    if not token or not telegram_id:
        return False
    bot = Bot(token)
    try:
        return await _send_message(bot, telegram_id, text, reply_markup=reply_markup)
    finally:
        await bot.session.close()


async def send_user_message_and_refresh_home(telegram_id: int, text: str) -> bool:
    token = config.bot_token
    if not token or not telegram_id:
        return False

    user = await get_user_by_telegram_id(int(telegram_id))
    if user is None:
        return False
    devices_count = await count_user_vpn_clients(user.id)

    bot = Bot(token)
    try:
        delivered = await _send_message(
            bot,
            int(telegram_id),
            text,
            reply_markup=ReplyKeyboardRemove(),
        )
        refreshed = await _send_message(
            bot,
            int(telegram_id),
            home_text(user, devices_count),
            reply_markup=home_keyboard_for_user(user),
        )
        return delivered and refreshed
    finally:
        await bot.session.close()
