from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest


async def is_user_subscribed(bot: Bot, channel_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)

        return member.status in [
            "creator",
            "administrator",
            "member",
        ]

    except TelegramBadRequest:
        return False