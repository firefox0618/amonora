from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from backend.core.database import async_session
from backend.core.models import DailyNewsReviewItem
from backend.core.schema import ensure_schema
from bot.config import config
from control_bot.channel_content import validate_channel_copy
from control_bot.dispatcher import create_control_event


DAILY_NEWS_ALLOWED_STATUSES = {"pending", "approved", "posted", "rejected", "failed"}
DAILY_NEWS_HISTORY_LOOKBACK_DAYS = 14
DAILY_NEWS_HISTORY_LIMIT = 400
logger = logging.getLogger(__name__)


def _normalize_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_status(value: object | None) -> str:
    status = str(value or "pending").strip().lower()
    if status not in DAILY_NEWS_ALLOWED_STATUSES:
        raise ValueError("Unsupported daily news status")
    return status


def serialize_daily_news_item(item: DailyNewsReviewItem) -> dict[str, object]:
    published_at = item.source_published_at.isoformat() if item.source_published_at else None
    return {
        "id": item.id,
        "source_url": item.source_url or "",
        "source_title": item.source_title or "",
        "title": item.source_title or "",
        "source_summary": item.source_summary or "",
        "summary": item.source_summary or "",
        "source_published_at": published_at,
        "published_at": published_at,
        "source_provider": item.source_provider or "",
        "topic_key": item.topic_key or "",
        "status": item.status,
        "post_text": item.post_text or "",
        "image_url": item.image_url or "",
        "review_requested_at": item.review_requested_at.isoformat() if item.review_requested_at else None,
        "review_message_id": item.review_message_id,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        "posted_at": item.posted_at.isoformat() if item.posted_at else None,
        "reject_reason": item.reject_reason or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


async def list_daily_news_history(*, limit: int = DAILY_NEWS_HISTORY_LIMIT) -> list[dict[str, object]]:
    await ensure_schema()
    lookback = datetime.utcnow() - timedelta(days=DAILY_NEWS_HISTORY_LOOKBACK_DAYS)
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DailyNewsReviewItem)
                    .where(
                        (DailyNewsReviewItem.review_requested_at.is_(None))
                        | (DailyNewsReviewItem.review_requested_at >= lookback)
                    )
                    .order_by(DailyNewsReviewItem.review_requested_at.desc(), DailyNewsReviewItem.created_at.desc())
                    .limit(max(int(limit or DAILY_NEWS_HISTORY_LIMIT), 1))
                )
            ).scalars().all()
        )
    return [serialize_daily_news_item(row) for row in rows]


async def upsert_daily_news_item(payload: dict[str, object]) -> dict[str, object]:
    await ensure_schema()
    item_id = str(payload.get("id") or "").strip()
    if not item_id:
        raise ValueError("Daily news item id is required")
    now = datetime.utcnow()
    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, item_id)
        if row is None:
            row = DailyNewsReviewItem(
                id=item_id,
                created_at=now,
            )
            session.add(row)
        row.source_url = str(payload.get("source_url") or "").strip() or None
        row.source_title = str(payload.get("source_title") or payload.get("title") or "").strip() or None
        row.source_summary = str(payload.get("source_summary") or payload.get("summary") or "").strip() or None
        row.source_published_at = _normalize_datetime(payload.get("source_published_at") or payload.get("published_at"))
        row.source_provider = str(payload.get("source_provider") or "").strip() or None
        row.topic_key = str(payload.get("topic_key") or "").strip() or None
        row.status = _normalize_status(payload.get("status"))
        row.post_text = str(payload.get("post_text") or "").strip() or None
        row.image_url = str(payload.get("image_url") or "").strip() or None
        row.review_requested_at = _normalize_datetime(payload.get("review_requested_at")) or row.review_requested_at or now
        row.updated_at = now
        await session.commit()
        await session.refresh(row)
    return serialize_daily_news_item(row)


async def update_daily_news_review_message(item_id: str, review_message_id: int | None) -> dict[str, object]:
    await ensure_schema()
    normalized_id = str(item_id or "").strip()
    if not normalized_id:
        raise ValueError("Daily news item id is required")
    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, normalized_id)
        if row is None:
            raise ValueError("Daily news item not found")
        row.review_message_id = int(review_message_id) if review_message_id is not None else None
        row.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)
    return serialize_daily_news_item(row)


async def update_daily_news_status(item_id: str, payload: dict[str, object]) -> dict[str, object]:
    await ensure_schema()
    normalized_id = str(item_id or "").strip()
    if not normalized_id:
        raise ValueError("Daily news item id is required")
    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, normalized_id)
        if row is None:
            raise ValueError("Daily news item not found")
        row.status = _normalize_status(payload.get("status"))
        row.approved_at = _normalize_datetime(payload.get("approved_at")) or row.approved_at
        row.posted_at = _normalize_datetime(payload.get("posted_at")) or row.posted_at
        row.reject_reason = str(payload.get("reject_reason") or "").strip() or None
        row.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)
    return serialize_daily_news_item(row)


async def publish_daily_news_item(item_id: str) -> dict[str, object]:
    await ensure_schema()
    normalized_id = str(item_id or "").strip()
    if not normalized_id:
        raise ValueError("Daily news item id is required")

    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, normalized_id)
        if row is None:
            raise ValueError("Daily news item not found")
        if row.status == "posted":
            return serialize_daily_news_item(row)
        if row.status not in {"pending", "approved", "failed"}:
            raise ValueError("Only pending or approved daily news items can be published")
        post_text = str(row.post_text or "").strip()
        if not post_text:
            raise ValueError("Daily news item has empty post text")
        ok, reason = validate_channel_copy(post_text)
        if not ok:
            raise ValueError(reason or "Daily news copy did not pass safety validation")
        token = str(config.control_bot_token or config.bot_token or "").strip()
        if not token:
            raise ValueError("No bot token available for daily news publishing")
        channel_id = str(config.channel_id or "").strip()
        if not channel_id:
            raise ValueError("CHANNEL_ID is not configured")

        row.status = "approved"
        row.approved_at = row.approved_at or datetime.utcnow()
        row.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)

    bot = Bot(token=token)
    now = datetime.utcnow()
    try:
        if str(row.image_url or "").strip():
            try:
                message = await bot.send_photo(
                    chat_id=channel_id,
                    photo=str(row.image_url).strip(),
                    caption=post_text,
                    parse_mode="HTML",
                )
            except TelegramBadRequest as exc:
                logger.warning("Daily news photo publish failed for %s, falling back to text: %s", normalized_id, exc)
                message = await bot.send_message(
                    chat_id=channel_id,
                    text=post_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
        else:
            message = await bot.send_message(
                chat_id=channel_id,
                text=post_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    except TelegramForbiddenError as exc:
        await _mark_daily_news_failed(normalized_id, "Bot cannot publish to the channel. Check channel admin rights.")
        await _emit_daily_news_publish_failure(normalized_id, str(exc))
        raise ValueError("Bot cannot publish to the channel. Check channel admin rights.") from exc
    except TelegramBadRequest as exc:
        await _mark_daily_news_failed(normalized_id, f"Telegram rejected the post: {exc}")
        await _emit_daily_news_publish_failure(normalized_id, str(exc))
        raise ValueError(f"Telegram rejected the post: {exc}") from exc
    finally:
        await bot.session.close()

    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, normalized_id)
        if row is None:
            raise ValueError("Daily news item not found after publish")
        row.status = "posted"
        row.approved_at = row.approved_at or now
        row.posted_at = now
        row.reject_reason = None
        row.updated_at = now
        await session.commit()
        await session.refresh(row)
        payload = serialize_daily_news_item(row)
    payload["telegram_chat_id"] = int(message.chat.id)
    payload["telegram_message_id"] = int(message.message_id)
    return payload


async def _mark_daily_news_failed(item_id: str, error_text: str) -> None:
    async with async_session() as session:
        row = await session.get(DailyNewsReviewItem, item_id)
        if row is None:
            return
        row.status = "failed"
        row.reject_reason = str(error_text or "").strip()[:500] or None
        row.updated_at = datetime.utcnow()
        await session.commit()


async def _emit_daily_news_publish_failure(item_id: str, error_text: str) -> None:
    await create_control_event(
        category="system",
        severity="WARNING",
        event_type="daily_news_publish_failed",
        title="Не удалось опубликовать daily news пост",
        message=(
            f"Элемент: <code>{item_id}</code>\n"
            f"Ошибка: <b>{str(error_text or '').strip()[:300]}</b>"
        ),
        entity_type="daily_news_item",
        entity_id=str(item_id),
        payload={"item_id": str(item_id), "status": "failed"},
        dedupe_key=f"daily-news-publish-failed:{item_id}",
    )
