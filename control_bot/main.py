import asyncio
import logging
from datetime import date, datetime

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands

from backend.core.schema import ensure_schema
from bot.config import config
from bot.utils.logging_setup import configure_logging
from control_bot.dispatcher import create_control_event, get_unresolved_event_count
from control_bot.router import router


logger = logging.getLogger(__name__)


async def _daily_summary_loop() -> None:
    while True:
        try:
            if config.control_daily_summary_enabled and config.control_bot_token:
                current_hour = datetime.now().hour
                if current_hour == config.control_daily_summary_hour:
                    unresolved = await get_unresolved_event_count(severities={"CRITICAL", "WARNING"})
                    await create_control_event(
                        category="system",
                        severity="INFO",
                        event_type="daily_summary",
                        title="Ежедневная системная сводка",
                        message=f"Нерешённых WARNING/CRITICAL событий: <b>{unresolved}</b>",
                        dedupe_key=f"daily-summary:{date.today().isoformat()}",
                        cooldown_seconds=3600,
                    )
            await asyncio.sleep(60)
        except Exception:
            logger.exception("Control bot daily summary loop failed")
            await asyncio.sleep(60)


async def main() -> None:
    configure_logging()
    await ensure_schema()
    if not config.control_bot_token:
        raise ValueError("Environment variable AMONORA_CONTROL_BOT_TOKEN is not set")

    bot = Bot(token=config.control_bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть Amonora Control"),
            BotCommand(command="dashboard", description="Операционный дашборд"),
            BotCommand(command="status", description="Статус системы"),
            BotCommand(command="nodes", description="Список нод"),
            BotCommand(command="payments", description="Платежи"),
            BotCommand(command="users", description="Пользователи"),
            BotCommand(command="user", description="Открыть пользователя"),
            BotCommand(command="problems", description="Проблемы и инциденты"),
            BotCommand(command="support", description="Поддержка"),
            BotCommand(command="alerts", description="Ошибки и предупреждения"),
            BotCommand(command="login_codes", description="Коды входа"),
            BotCommand(command="notifications", description="Уведомления"),
            BotCommand(command="events", description="Последние события"),
            BotCommand(command="settings", description="Настройки уведомлений"),
            BotCommand(command="broadcast", description="Рассылка и триггеры"),
            BotCommand(command="help", description="Справка"),
        ]
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    asyncio.create_task(_daily_summary_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
