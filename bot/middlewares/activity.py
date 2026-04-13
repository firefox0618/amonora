from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.db import touch_user_activity


logger = logging.getLogger(__name__)


class UserActivityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message) and event.from_user and not event.from_user.is_bot:
                await touch_user_activity(telegram_id=event.from_user.id)
            elif isinstance(event, CallbackQuery) and event.from_user and not event.from_user.is_bot:
                await touch_user_activity(telegram_id=event.from_user.id)
        except Exception:
            logger.exception("Failed to touch user activity")
        return await handler(event, data)
