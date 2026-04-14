import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands

from backend.core.schema import ensure_schema
from bot.config import config
from bot.handlers.cabinet import router as cabinet_router
from bot.handlers.devices import router as devices_router
from bot.handlers.info import router as info_router
from bot.handlers.protocol import router as protocol_router
from bot.handlers.referrals import router as referrals_router
from bot.handlers.start import router as start_router
from bot.handlers.support import router as support_router
from bot.handlers.tariffs import router as tariffs_router
from bot.middlewares.activity import UserActivityMiddleware
from bot.router import router as main_router
from bot.utils.logging_setup import configure_logging


dp = Dispatcher()
dp.include_router(main_router)
dp.include_router(start_router)
dp.include_router(cabinet_router)
dp.include_router(devices_router)
dp.include_router(protocol_router)
dp.include_router(info_router)
dp.include_router(referrals_router)
dp.include_router(support_router)
dp.include_router(tariffs_router)


async def main() -> None:
    configure_logging()
    await ensure_schema()
    bot = Bot(token=config.bot_token)
    activity_middleware = UserActivityMiddleware()
    dp.message.middleware(activity_middleware)
    dp.callback_query.middleware(activity_middleware)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть Amonora"),
            BotCommand(command="menu", description="Главное меню"),
            BotCommand(command="support", description="Поддержка"),
        ]
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
