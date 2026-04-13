import logging


NOISY_LOGGERS = [
    "aiogram",
    "aiogram.event",
    "aiogram.dispatcher",
    "aiohttp",
    "aiohttp.access",
    "httpx",
    "httpcore",
    "asyncio",
    "asyncpg",
    "sqlalchemy",
]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    logging.getLogger("bot").setLevel(logging.WARNING)
    logging.getLogger("support_bot").setLevel(logging.WARNING)
    logging.getLogger("backend").setLevel(logging.WARNING)
