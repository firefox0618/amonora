from bot.config import config


def test_bot_allowed_telegram_ids() -> set[int]:
    return set(config.test_bot_allowed_telegram_ids)


def is_test_bot_allowed(telegram_id: int | None) -> bool:
    return telegram_id in test_bot_allowed_telegram_ids()
