import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.config import config
from ops.access_reminders import _deliver_reminder, classify_access_reminder, record_delivery_result


@dataclass
class DummyUser:
    telegram_id: int | None = 1001
    username: str | None = "real_user"
    trial_expires_at: object = None
    trial_used: bool = False
    trial_channel_unsubscribed_at: object = None
    subscription_expires_at: object = None
    subscription_status: str = "inactive"
    subscription_source: str | None = None
    is_blocked: bool = False


class OkBot:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


class ForbiddenBot:
    async def send_message(self, **kwargs):
        raise TelegramForbiddenError(SendMessage(chat_id=kwargs["chat_id"], text=kwargs["text"]), "forbidden")


class BadRequestBot:
    async def send_message(self, **kwargs):
        raise TelegramBadRequest(SendMessage(chat_id=kwargs["chat_id"], text=kwargs["text"]), "bad request")


async def _test_delivery() -> None:
    ok_bot = OkBot()
    assert await _deliver_reminder(ok_bot, 3001, "no_access") == "sent"
    assert ok_bot.calls and ok_bot.calls[0]["reply_markup"] is not None

    assert await _deliver_reminder(ForbiddenBot(), 3002, "trial_expired") == "forbidden"
    assert await _deliver_reminder(BadRequestBot(), 3003, "trial_ends_today") == "bad_request"


def main() -> None:
    now = datetime(2026, 3, 18, 12, 0, 0)
    config.admin_ids = [9999]
    config.support_admin_ids = [8888]

    trial_today = DummyUser(
        telegram_id=2001,
        trial_used=True,
        trial_expires_at=datetime(2026, 3, 18, 16, 0, 0),
    )
    assert classify_access_reminder(trial_today, {}, now) == "trial_ends_today"

    sent_today_state = {"events": {"2001": {"trial_ends_today": {"last_sent_local_date": "2026-03-18"}}}}
    assert classify_access_reminder(trial_today, sent_today_state, now) is None

    expired_trial = DummyUser(
        telegram_id=2002,
        trial_used=True,
        trial_expires_at=now - timedelta(hours=2),
    )
    assert classify_access_reminder(expired_trial, {}, now) == "trial_expired"

    expired_state: dict = {}
    record_delivery_result(expired_state, 2002, "trial_expired", result="sent", now_utc=now)
    assert classify_access_reminder(expired_trial, expired_state, now) is None
    assert classify_access_reminder(expired_trial, expired_state, now + timedelta(days=3)) == "no_access"

    inactive_user = DummyUser(telegram_id=2003)
    assert classify_access_reminder(inactive_user, {}, now) == "no_access"

    no_access_state: dict = {}
    record_delivery_result(no_access_state, 2003, "no_access", result="sent", now_utc=now)
    assert classify_access_reminder(inactive_user, no_access_state, now + timedelta(days=1)) is None
    assert classify_access_reminder(inactive_user, no_access_state, now + timedelta(days=3)) == "no_access"

    paid_user = DummyUser(
        telegram_id=2004,
        subscription_status="active",
        subscription_source="telegram_stars",
        subscription_expires_at=now + timedelta(days=30),
    )
    assert classify_access_reminder(paid_user, {}, now) is None

    vip_user = DummyUser(
        telegram_id=2005,
        subscription_status="active",
        subscription_source="manual_vip",
        subscription_expires_at=now + timedelta(days=30),
    )
    assert classify_access_reminder(vip_user, {}, now) is None

    blocked_user = DummyUser(
        telegram_id=2006,
        is_blocked=True,
        trial_used=True,
        trial_expires_at=now - timedelta(days=1),
    )
    assert classify_access_reminder(blocked_user, {}, now) is None

    complimentary_admin = DummyUser(telegram_id=9999)
    assert classify_access_reminder(complimentary_admin, {}, now) is None

    asyncio.run(_test_delivery())

    print("Access reminders tests passed")


if __name__ == "__main__":
    main()
