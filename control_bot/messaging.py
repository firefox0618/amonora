from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import config
from bot.utils.access import utcnow
from control_bot.storage import (
    CAMPAIGN_SCOPE_ADMIN,
    CAMPAIGN_SCOPE_TRIGGER,
    CAMPAIGN_SCOPE_USER,
    build_campaign_recipients,
    create_broadcast_deliveries,
    get_broadcast_campaign,
    get_control_admin_profile,
    list_active_dashboard_sessions,
    list_pending_broadcast_campaigns,
    render_template_body,
    serialize_campaign_metadata,
    serialize_template_buttons,
    update_broadcast_campaign,
    update_delivery_status,
)


logger = logging.getLogger(__name__)


def build_user_cta_keyboard(delivery_id: int, buttons: list[dict[str, str]]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for button in buttons[:4]:
        action = (button.get("action") or "").strip()
        label = (button.get("label") or "").strip()
        if not action or not label:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:40],
                    callback_data=f"campaign:cta:{delivery_id}:{action}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def dispatch_campaign(campaign_id: int, *, test_telegram_id: int | None = None) -> dict[str, int]:
    campaign = await get_broadcast_campaign(campaign_id)
    if campaign is None:
        return {"target_count": 0, "sent": 0, "failed": 0}

    if campaign.status == "completed":
        return {
            "target_count": int(campaign.target_count or 0),
            "sent": int(campaign.sent_count or 0),
            "failed": int(campaign.failed_count or 0),
        }

    now = utcnow()
    if campaign.scheduled_at is not None and campaign.scheduled_at > now and test_telegram_id is None:
        return {"target_count": int(campaign.target_count or 0), "sent": 0, "failed": 0}

    deliveries = await _ensure_campaign_deliveries(campaign_id, test_telegram_id=test_telegram_id)
    if not deliveries:
        await update_broadcast_campaign(campaign_id, status="completed", completed_at=utcnow())
        return {"target_count": 0, "sent": 0, "failed": 0}

    await update_broadcast_campaign(campaign_id, status="processing", started_at=campaign.started_at or now)
    sent = 0
    failed = 0
    for delivery in deliveries:
        if delivery.status == "sent":
            sent += 1
            continue
        result = await _deliver_one(campaign_id, delivery.id)
        if result == "sent":
            sent += 1
        else:
            failed += 1
    return {"target_count": len(deliveries), "sent": sent, "failed": failed}


async def process_pending_campaigns() -> dict[str, int]:
    campaigns = await list_pending_broadcast_campaigns()
    processed = 0
    sent = 0
    failed = 0
    for campaign in campaigns:
        result = await dispatch_campaign(campaign.id)
        if result["target_count"] > 0:
            processed += 1
        sent += result["sent"]
        failed += result["failed"]
    return {"processed": processed, "sent": sent, "failed": failed}


async def _ensure_campaign_deliveries(campaign_id: int, *, test_telegram_id: int | None = None):
    campaign = await get_broadcast_campaign(campaign_id)
    if campaign is None:
        return []
    from control_bot.storage import list_broadcast_deliveries

    existing = await list_broadcast_deliveries(campaign_id)
    if existing:
        return existing

    buttons = serialize_template_buttons(campaign)
    cta_action = buttons[0]["action"] if buttons else None
    metadata = serialize_campaign_metadata(campaign)
    explicit_recipients = metadata.get("recipients")
    if explicit_recipients:
        recipients = [
            {
                "user_id": item.get("user_id"),
                "telegram_id": int(item["telegram_id"]),
            }
            for item in explicit_recipients
            if item.get("telegram_id")
        ]
        bot_key = "control" if campaign.scope == CAMPAIGN_SCOPE_ADMIN else "bot"
        return await create_broadcast_deliveries(campaign_id, recipients=recipients, bot_key=bot_key, cta_action=cta_action)

    if campaign.scope == CAMPAIGN_SCOPE_ADMIN:
        if test_telegram_id is not None:
            recipients = [{"user_id": None, "telegram_id": int(test_telegram_id)}]
        else:
            profiles = await list_active_dashboard_sessions()
            if profiles:
                recipients = [{"user_id": None, "telegram_id": int(row["telegram_id"])} for row in profiles if row.get("telegram_id")]
            else:
                from control_bot.storage import list_control_admin_profiles

                recipients = [{"user_id": None, "telegram_id": int(row.telegram_id)} for row in await list_control_admin_profiles()]
        return await create_broadcast_deliveries(campaign_id, recipients=recipients, bot_key="control", cta_action=None)

    recipients = await build_campaign_recipients(campaign.audience_key or "all", test_telegram_id=test_telegram_id)
    return await create_broadcast_deliveries(campaign_id, recipients=recipients, bot_key="bot", cta_action=cta_action)


async def _deliver_one(campaign_id: int, delivery_id: int) -> str:
    campaign = await get_broadcast_campaign(campaign_id)
    if campaign is None:
        return "failed"
    from control_bot.storage import get_delivery

    delivery = await get_delivery(delivery_id)
    if delivery is None:
        return "failed"

    token = config.control_bot_token if campaign.scope == CAMPAIGN_SCOPE_ADMIN else config.bot_token
    if not token:
        await update_delivery_status(delivery_id, status="failed", error_text="bot token missing")
        return "failed"

    text = campaign.message_body
    if campaign.scope in {CAMPAIGN_SCOPE_USER, CAMPAIGN_SCOPE_TRIGGER}:
        text = await render_template_body(campaign.message_body, delivery.user_id, delivery.telegram_id)
    reply_markup = None
    if campaign.scope in {CAMPAIGN_SCOPE_USER, CAMPAIGN_SCOPE_TRIGGER}:
        reply_markup = build_user_cta_keyboard(delivery.id, serialize_template_buttons(campaign))

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=delivery.telegram_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning("Campaign delivery failed campaign=%s delivery=%s: %s", campaign_id, delivery_id, exc)
        await update_delivery_status(delivery_id, status="failed", error_text=str(exc))
        return "failed"
    finally:
        await bot.session.close()

    await update_delivery_status(delivery_id, status="sent")
    return "sent"
