import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands

from backend.core.schema import ensure_schema
from bot.config import config
from bot.utils.logging_setup import configure_logging
from support_bot.storage import bootstrap_storage
from support_bot.router import router


async def main() -> None:
    configure_logging()
    await ensure_schema()
    await bootstrap_storage()
    if not config.support_bot_token:
        raise ValueError("Environment variable SUPPORT_BOT_TOKEN is not set")

    bot = Bot(token=config.support_bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть поддержку"),
            BotCommand(command="tickets", description="Панель обращений"),
            BotCommand(command="cancel", description="Отменить текущий ответ"),
        ]
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
