import asyncio

from aiogram import Bot

from bot.config import config
from bot.utils.subscription import is_user_subscribed


async def main():
    bot = Bot(token=config.bot_token)

    try:
        result = await is_user_subscribed(
            bot,
            config.channel_id,
            7650618403,
        )

        print("Subscribed:", result)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())