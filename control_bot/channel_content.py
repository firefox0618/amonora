from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from html import escape
from secrets import token_hex
from zoneinfo import ZoneInfo

import httpx
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from backend.core.database import async_session
from backend.core.analytics import emit_link_touched_event, safe_upsert_user_attribution
from backend.core.models import ChannelContentItem, ChannelPostTouch
from backend.core.schema import ensure_schema
from bot.config import config
from bot.utils.access import utcnow
from control_bot.dispatcher import create_control_event


logger = logging.getLogger(__name__)

CHANNEL_CONTENT_TYPE_EDUCATION = "education"
CHANNEL_CONTENT_TYPE_OFFER = "offer"
CHANNEL_CONTENT_TYPE_ENGAGEMENT = "engagement"
CHANNEL_CONTENT_TYPES = (
    CHANNEL_CONTENT_TYPE_EDUCATION,
    CHANNEL_CONTENT_TYPE_OFFER,
    CHANNEL_CONTENT_TYPE_ENGAGEMENT,
)
CHANNEL_CONTENT_TYPE_LABELS = {
    CHANNEL_CONTENT_TYPE_EDUCATION: "Обучение",
    CHANNEL_CONTENT_TYPE_OFFER: "Оффер",
    CHANNEL_CONTENT_TYPE_ENGAGEMENT: "Вовлечение",
}

CHANNEL_STATUS_QUEUED = "queued"
CHANNEL_STATUS_GENERATING = "generating"
CHANNEL_STATUS_DRAFT = "draft"
CHANNEL_STATUS_APPROVED = "approved"
CHANNEL_STATUS_PUBLISHING = "publishing"
CHANNEL_STATUS_PUBLISHED = "published"
CHANNEL_STATUS_REJECTED = "rejected"
CHANNEL_STATUS_FAILED = "failed"
CHANNEL_CONTENT_STATUSES = (
    CHANNEL_STATUS_QUEUED,
    CHANNEL_STATUS_GENERATING,
    CHANNEL_STATUS_DRAFT,
    CHANNEL_STATUS_APPROVED,
    CHANNEL_STATUS_PUBLISHING,
    CHANNEL_STATUS_PUBLISHED,
    CHANNEL_STATUS_REJECTED,
    CHANNEL_STATUS_FAILED,
)
CHANNEL_CONTENT_STATUS_LABELS = {
    CHANNEL_STATUS_QUEUED: "В очереди",
    CHANNEL_STATUS_GENERATING: "Генерируется",
    CHANNEL_STATUS_DRAFT: "Черновик",
    CHANNEL_STATUS_APPROVED: "Одобрено",
    CHANNEL_STATUS_PUBLISHING: "Публикуется",
    CHANNEL_STATUS_PUBLISHED: "Опубликовано",
    CHANNEL_STATUS_REJECTED: "Отклонено",
    CHANNEL_STATUS_FAILED: "Ошибка",
}
CHANNEL_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    CHANNEL_STATUS_QUEUED: {CHANNEL_STATUS_GENERATING, CHANNEL_STATUS_REJECTED, CHANNEL_STATUS_DRAFT},
    CHANNEL_STATUS_GENERATING: {CHANNEL_STATUS_DRAFT, CHANNEL_STATUS_FAILED},
    CHANNEL_STATUS_DRAFT: {CHANNEL_STATUS_APPROVED, CHANNEL_STATUS_REJECTED, CHANNEL_STATUS_GENERATING},
    CHANNEL_STATUS_APPROVED: {CHANNEL_STATUS_PUBLISHING, CHANNEL_STATUS_DRAFT, CHANNEL_STATUS_REJECTED},
    CHANNEL_STATUS_PUBLISHING: {CHANNEL_STATUS_PUBLISHED, CHANNEL_STATUS_FAILED},
    CHANNEL_STATUS_PUBLISHED: set(),
    CHANNEL_STATUS_REJECTED: {CHANNEL_STATUS_GENERATING, CHANNEL_STATUS_DRAFT},
    CHANNEL_STATUS_FAILED: {CHANNEL_STATUS_GENERATING, CHANNEL_STATUS_DRAFT, CHANNEL_STATUS_PUBLISHING, CHANNEL_STATUS_REJECTED},
}

CHANNEL_PROMPT_VERSION = "channel-v1"
CHANNEL_DEFAULT_CTA_LABEL = "Подключиться"
CHANNEL_START_PREFIX = "post_"
CHANNEL_START_LINK_PREFIX = "https://t.me/amonora_bot?start="
CHANNEL_MAX_TOPIC_LENGTH = 400
CHANNEL_MAX_BODY_LENGTH = 3800
CHANNEL_MAX_CTA_LABEL_LENGTH = 80
CHANNEL_INTERNAL_HEADER = "x-amonora-internal-secret"
CHANNEL_LOCAL_TZ = ZoneInfo("Asia/Yekaterinburg")
CHANNEL_SURFACE_SEP = "━━━━━━━━━━━━━━━━━━"
CHANNEL_MISSING_COVERAGE_STATUSES = {
    CHANNEL_STATUS_QUEUED,
    CHANNEL_STATUS_DRAFT,
    CHANNEL_STATUS_APPROVED,
    CHANNEL_STATUS_PUBLISHING,
    CHANNEL_STATUS_PUBLISHED,
}
CHANNEL_RISKY_COPY_RULES: tuple[tuple[str, str], ...] = (
    ("обход блокировок", "Нельзя использовать публичную формулировку про обход блокировок."),
    ("обходить блокировки", "Нельзя использовать публичную формулировку про обход блокировок."),
    ("заблокированн", "Нельзя обещать доступ к заблокированным ресурсам."),
    ("legally restricted resources", "Нельзя упоминать legally restricted resources в публичном контенте."),
    ("полная анонимность", "Нельзя обещать полную анонимность."),
    ("полный иммунитет", "Нельзя обещать полный иммунитет."),
    ("гарантированная анонимность", "Нельзя обещать гарантированную анонимность."),
    ("полная защита", "Нельзя обещать абсолютную защиту."),
    ("без жалоб", "Нельзя обещать отсутствие жалоб или претензий."),
    ("без ограничений закона", "Нельзя обещать работу вне правовых ограничений."),
)


def channel_content_type_label(content_type: str | None) -> str:
    return CHANNEL_CONTENT_TYPE_LABELS.get(str(content_type or "").strip().lower(), "Контент")


def channel_content_status_label(status: str | None) -> str:
    return CHANNEL_CONTENT_STATUS_LABELS.get(str(status or "").strip().lower(), status or "—")


def normalize_channel_content_type(content_type: str | None) -> str:
    value = str(content_type or "").strip().lower()
    if value not in CHANNEL_CONTENT_TYPES:
        raise ValueError("Неизвестный тип контента")
    return value


def parse_channel_post_start_token(payload: str | None) -> str | None:
    raw = str(payload or "").strip()
    if not raw.startswith(CHANNEL_START_PREFIX):
        return None
    token = raw.split("_", 1)[1].strip().lower()
    return token or None


def build_channel_post_start_token(token: str) -> str:
    return f"{CHANNEL_START_PREFIX}{str(token or '').strip().lower()}"


def build_channel_cta_url(token: str) -> str:
    return f"{CHANNEL_START_LINK_PREFIX}{build_channel_post_start_token(token)}"


def can_transition_channel_status(current_status: str | None, next_status: str | None) -> bool:
    current = str(current_status or "").strip().lower()
    target = str(next_status or "").strip().lower()
    if current == target and current in CHANNEL_CONTENT_STATUSES:
        return True
    return target in CHANNEL_ALLOWED_TRANSITIONS.get(current, set())


def default_channel_scheduled_at(now: datetime | None = None) -> datetime:
    reference = _coerce_local_naive(now) or _local_now()
    slot_hour = max(min(int(getattr(config, "channel_default_post_hour", 12) or 12), 23), 0)
    slot = reference.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
    if reference >= slot:
        slot += timedelta(days=1)
    return slot


def validate_channel_copy(text: str | None) -> tuple[bool, str | None]:
    normalized = re.sub(r"<[^>]+>", " ", str(text or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    if not normalized:
        return False, "Текст поста пустой."
    for needle, reason in CHANNEL_RISKY_COPY_RULES:
        if needle in normalized:
            return False, reason
    return True, None


def serialize_channel_content_item(
    item: ChannelContentItem,
    *,
    transitions_count: int = 0,
    conversions_count: int = 0,
) -> dict[str, object]:
    deep_link_token = str(item.deep_link_token or "").strip().lower() or None
    return {
        "id": int(item.id),
        "content_type": item.content_type,
        "content_type_label": channel_content_type_label(item.content_type),
        "topic_brief": item.topic_brief,
        "status": item.status,
        "status_label": channel_content_status_label(item.status),
        "scheduled_at": item.scheduled_at,
        "approved_at": item.approved_at,
        "approved_by_telegram_id": item.approved_by_telegram_id,
        "body_html": item.body_html or "",
        "cta_label": item.cta_label or CHANNEL_DEFAULT_CTA_LABEL,
        "deep_link_token": deep_link_token,
        "deep_link_url": build_channel_cta_url(deep_link_token) if deep_link_token else None,
        "telegram_chat_id": item.telegram_chat_id,
        "telegram_message_id": item.telegram_message_id,
        "published_at": item.published_at,
        "model_name": item.model_name,
        "prompt_version": item.prompt_version,
        "error_text": item.error_text,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "transitions_count": int(transitions_count),
        "conversions_count": int(conversions_count),
    }


async def create_channel_content_item(
    *,
    content_type: str,
    topic_brief: str,
    scheduled_at: datetime | None,
    cta_label: str | None = None,
) -> ChannelContentItem:
    await ensure_schema()

    row = ChannelContentItem(
        content_type=normalize_channel_content_type(content_type),
        topic_brief=_safe_topic_brief(topic_brief),
        status=CHANNEL_STATUS_QUEUED,
        scheduled_at=_normalize_scheduled_at(scheduled_at),
        cta_label=_safe_cta_label(cta_label) or CHANNEL_DEFAULT_CTA_LABEL,
        deep_link_token=_new_deep_link_token(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def list_channel_content_items(
    *,
    statuses: set[str] | None = None,
    limit: int = 10,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
) -> list[ChannelContentItem]:
    await ensure_schema()

    async with async_session() as session:
        query = select(ChannelContentItem)
        if statuses:
            query = query.where(ChannelContentItem.status.in_(sorted(statuses)))
        if scheduled_from is not None:
            query = query.where(ChannelContentItem.scheduled_at >= scheduled_from)
        if scheduled_to is not None:
            query = query.where(ChannelContentItem.scheduled_at <= scheduled_to)
        query = query.order_by(ChannelContentItem.scheduled_at.asc(), ChannelContentItem.id.desc()).limit(max(int(limit), 1))
        return list((await session.execute(query)).scalars().all())


async def get_channel_content_item(item_id: int) -> ChannelContentItem | None:
    await ensure_schema()

    async with async_session() as session:
        return (
            await session.execute(select(ChannelContentItem).where(ChannelContentItem.id == int(item_id)))
        ).scalar_one_or_none()


async def list_channel_content_item_summaries(
    *,
    statuses: set[str] | None = None,
    limit: int = 10,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
) -> list[dict[str, object]]:
    items = await list_channel_content_items(
        statuses=statuses,
        limit=limit,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
    )
    metrics = await _touch_counts_for_items([item.id for item in items])
    return [
        serialize_channel_content_item(
            item,
            transitions_count=metrics.get(item.id, {}).get("transitions", 0),
            conversions_count=metrics.get(item.id, {}).get("conversions", 0),
        )
        for item in items
    ]


async def get_channel_content_focus(item_id: int) -> dict[str, object] | None:
    item = await get_channel_content_item(item_id)
    if item is None:
        return None
    metrics = await _touch_counts_for_items([item.id])
    return serialize_channel_content_item(
        item,
        transitions_count=metrics.get(item.id, {}).get("transitions", 0),
        conversions_count=metrics.get(item.id, {}).get("conversions", 0),
    )


async def get_channel_content_counts() -> dict[str, int]:
    await ensure_schema()

    counts = {status: 0 for status in CHANNEL_CONTENT_STATUSES}
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(ChannelContentItem.status, func.count(ChannelContentItem.id)).group_by(ChannelContentItem.status)
                )
            ).all()
        )
    for status, total in rows:
        counts[str(status)] = int(total or 0)
    return counts


async def get_channel_content_stats(limit: int = 8) -> dict[str, object]:
    recent_items = await list_channel_content_item_summaries(limit=limit)
    counts = await get_channel_content_counts()
    total_transitions, total_conversions = await _touch_totals()
    return {
        "counts": counts,
        "recent_items": recent_items,
        "total_items": sum(counts.values()),
        "total_transitions": total_transitions,
        "total_conversions": total_conversions,
    }


def parse_channel_schedule_input(text: str | None, *, now: datetime | None = None) -> datetime:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    reference = _coerce_local_naive(now) or _local_now()
    if not raw:
        return default_channel_scheduled_at(reference)

    lowered = raw.lower()
    if lowered in {"default", "по умолчанию", "слот", "ближайший слот"}:
        return default_channel_scheduled_at(reference)
    if lowered in {"сейчас", "now"}:
        return reference.replace(second=0, microsecond=0)

    today_match = re.fullmatch(r"(сегодня|завтра)\s+(\d{1,2}):(\d{2})", lowered)
    if today_match:
        day_shift = 0 if today_match.group(1) == "сегодня" else 1
        target = reference.replace(
            hour=int(today_match.group(2)),
            minute=int(today_match.group(3)),
            second=0,
            microsecond=0,
        ) + timedelta(days=day_shift)
        if target < reference.replace(second=0, microsecond=0):
            raise ValueError("Время уже прошло. Выбери будущий слот.")
        return target

    local_time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", lowered)
    if local_time_match:
        target = reference.replace(
            hour=int(local_time_match.group(1)),
            minute=int(local_time_match.group(2)),
            second=0,
            microsecond=0,
        )
        if target < reference.replace(second=0, microsecond=0):
            target += timedelta(days=1)
        return target

    parsers = (
        ("%Y-%m-%d %H:%M", False),
        ("%d.%m.%Y %H:%M", False),
        ("%Y-%m-%d", True),
        ("%d.%m.%Y", True),
    )
    for fmt, date_only in parsers:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if date_only:
            parsed = parsed.replace(
                hour=max(min(int(getattr(config, "channel_default_post_hour", 12) or 12), 23), 0),
                minute=0,
                second=0,
                microsecond=0,
            )
        if parsed < reference.replace(second=0, microsecond=0):
            raise ValueError("Дата уже прошла. Выбери будущий слот.")
        return parsed

    raise ValueError("Не удалось распознать дату. Используй формат YYYY-MM-DD HH:MM, DD.MM.YYYY HH:MM или 'завтра 12:00'.")


async def build_channel_root_screen() -> tuple[str, InlineKeyboardMarkup]:
    stats = await get_channel_content_stats(limit=5)
    counts = stats["counts"]
    lines = [
        "📣 <b>КАНАЛ AMONORA</b>",
        "",
        "Контент-план канала: черновики, approve/publish flow и tracked CTA в бот.",
        "",
        CHANNEL_SURFACE_SEP,
        "📌 <b>СВОДКА</b>",
        CHANNEL_SURFACE_SEP,
        f"В очереди: <b>{int(counts.get(CHANNEL_STATUS_QUEUED, 0))}</b>",
        f"Черновики: <b>{int(counts.get(CHANNEL_STATUS_DRAFT, 0))}</b>",
        f"Одобрено: <b>{int(counts.get(CHANNEL_STATUS_APPROVED, 0))}</b>",
        f"Опубликовано: <b>{int(counts.get(CHANNEL_STATUS_PUBLISHED, 0))}</b>",
        f"Переходы в бот: <b>{int(stats['total_transitions'])}</b>",
        f"Конверсии: <b>{int(stats['total_conversions'])}</b>",
    ]
    recent_items = list(stats.get("recent_items") or [])[:3]
    if recent_items:
        lines.extend(["", CHANNEL_SURFACE_SEP, "🕓 <b>ПОСЛЕДНИЕ ЭЛЕМЕНТЫ</b>", CHANNEL_SURFACE_SEP])
        for item in recent_items:
            lines.append(_channel_item_compact_line(item))
    lines.extend(["", "Выбери действие кнопками ниже."])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Новая тема", callback_data="control:channel:new"),
                InlineKeyboardButton(text="📅 Ближайшие", callback_data="control:channel:list:upcoming"),
            ],
            [
                InlineKeyboardButton(text="📝 Черновики", callback_data="control:channel:list:drafts"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="control:channel:stats"),
            ],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="control:channel")],
        ]
    )
    return "\n".join(lines), keyboard


async def build_channel_list_screen(list_kind: str) -> tuple[str, InlineKeyboardMarkup]:
    normalized = str(list_kind or "").strip().lower()
    if normalized == "drafts":
        title = "📝 <b>ЧЕРНОВИКИ КАНАЛА</b>"
        items = await list_channel_content_item_summaries(
            statuses={CHANNEL_STATUS_DRAFT, CHANNEL_STATUS_FAILED, CHANNEL_STATUS_REJECTED},
            limit=12,
        )
    else:
        title = "📅 <b>БЛИЖАЙШИЕ ПОСТЫ</b>"
        items = await list_channel_content_item_summaries(
            statuses={CHANNEL_STATUS_QUEUED, CHANNEL_STATUS_GENERATING, CHANNEL_STATUS_APPROVED, CHANNEL_STATUS_PUBLISHING},
            limit=12,
        )
        normalized = "upcoming"

    lines = [title, "", CHANNEL_SURFACE_SEP]
    if items:
        for item in items:
            lines.append(_channel_item_compact_line(item))
    else:
        lines.append("Список пока пуст.")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for item in items[:8]:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{int(item['id'])} {_shorten_text(str(item['topic_brief']), 28)}",
                    callback_data=f"control:channel:item:{int(item['id'])}",
                )
            ]
        )
    keyboard_rows.append(
        [
            InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"control:channel:list:{normalized}"),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def build_channel_stats_screen() -> tuple[str, InlineKeyboardMarkup]:
    stats = await get_channel_content_stats(limit=8)
    counts = stats["counts"]
    lines = [
        "📊 <b>СТАТИСТИКА КАНАЛА</b>",
        "",
        CHANNEL_SURFACE_SEP,
        f"Всего элементов: <b>{int(stats['total_items'])}</b>",
        f"Queued: <b>{int(counts.get(CHANNEL_STATUS_QUEUED, 0))}</b>",
        f"Draft: <b>{int(counts.get(CHANNEL_STATUS_DRAFT, 0))}</b>",
        f"Approved: <b>{int(counts.get(CHANNEL_STATUS_APPROVED, 0))}</b>",
        f"Published: <b>{int(counts.get(CHANNEL_STATUS_PUBLISHED, 0))}</b>",
        f"Failed: <b>{int(counts.get(CHANNEL_STATUS_FAILED, 0))}</b>",
        f"Transitions -> bot: <b>{int(stats['total_transitions'])}</b>",
        f"Conversions: <b>{int(stats['total_conversions'])}</b>",
    ]
    recent_items = list(stats.get("recent_items") or [])[:5]
    if recent_items:
        lines.extend(["", CHANNEL_SURFACE_SEP, "🕓 <b>ПОСЛЕДНИЕ</b>", CHANNEL_SURFACE_SEP])
        for item in recent_items:
            lines.append(
                f"• #{int(item['id'])} — {escape(str(item['topic_brief']))} "
                f"(переходы {int(item['transitions_count'])}, конверсии {int(item['conversions_count'])})"
            )
    keyboard_rows = [
        [InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="control:channel:stats")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def build_channel_item_screen(item_id: int) -> tuple[str, InlineKeyboardMarkup]:
    item = await get_channel_content_focus(item_id)
    if item is None:
        raise ValueError("Элемент канала не найден.")

    status = str(item["status"])
    lines = [
        f"📄 <b>POST ITEM #{int(item['id'])}</b>",
        "",
        CHANNEL_SURFACE_SEP,
        f"Тип: <b>{escape(str(item['content_type_label']))}</b>",
        f"Статус: <b>{escape(str(item['status_label']))}</b>",
        f"Слот: <b>{_fmt_channel_dt(item.get('scheduled_at'))}</b>",
        f"Тема: <b>{escape(_shorten_text(str(item['topic_brief']), 220))}</b>",
        f"CTA: <b>{escape(str(item['cta_label']))}</b>",
        f"Transitions: <b>{int(item['transitions_count'])}</b>",
        f"Conversions: <b>{int(item['conversions_count'])}</b>",
    ]
    if item.get("published_at"):
        lines.append(f"Опубликовано: <b>{_fmt_channel_dt(item.get('published_at'))}</b>")
    if item.get("approved_at"):
        approver = item.get("approved_by_telegram_id") or "—"
        lines.append(f"Approved: <b>{_fmt_channel_dt(item.get('approved_at'))}</b> · <code>{approver}</code>")
    if item.get("telegram_message_id"):
        lines.append(f"Message ID: <code>{int(item['telegram_message_id'])}</code>")
    if item.get("deep_link_url"):
        lines.append(f"CTA URL: <code>{escape(str(item['deep_link_url']))}</code>")
    if item.get("error_text"):
        lines.extend(["", "⚠️ <b>Ошибка</b>", escape(str(item["error_text"]))])
    if item.get("body_html"):
        lines.extend(["", CHANNEL_SURFACE_SEP, "📝 <b>ТЕКСТ</b>", CHANNEL_SURFACE_SEP, str(item["body_html"])])

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if status in {CHANNEL_STATUS_QUEUED, CHANNEL_STATUS_FAILED, CHANNEL_STATUS_REJECTED}:
        keyboard_rows.append(
            [InlineKeyboardButton(text="⚙️ Сгенерировать" if status == CHANNEL_STATUS_QUEUED else "🔁 Повторить генерацию", callback_data=f"control:channel:retry:{int(item_id)}")]
        )
    if status == CHANNEL_STATUS_DRAFT:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"control:channel:approve:{int(item_id)}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"control:channel:edit:{int(item_id)}"),
            ]
        )
        keyboard_rows.append(
            [InlineKeyboardButton(text="🗑 Отклонить", callback_data=f"control:channel:reject:{int(item_id)}")]
        )
    if status == CHANNEL_STATUS_APPROVED:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="📤 Опубликовать сейчас", callback_data=f"control:channel:publish:{int(item_id)}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"control:channel:edit:{int(item_id)}"),
            ]
        )
        keyboard_rows.append(
            [InlineKeyboardButton(text="🗑 Отклонить", callback_data=f"control:channel:reject:{int(item_id)}")]
        )
    if status == CHANNEL_STATUS_PUBLISHED and item.get("deep_link_url"):
        keyboard_rows.append(
            [InlineKeyboardButton(text="🔗 Открыть CTA", url=str(item["deep_link_url"]))]
        )
    keyboard_rows.append(
        [
            InlineKeyboardButton(text="⬅️ Ближайшие", callback_data="control:channel:list:upcoming"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"control:channel:item:{int(item_id)}"),
        ]
    )
    keyboard_rows.append([InlineKeyboardButton(text="🏠 Канал", callback_data="control:channel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def update_channel_content_body(item_id: int, body_html: str, *, cta_label: str | None = None) -> ChannelContentItem:
    await ensure_schema()

    safe_body = _safe_body_html(body_html)
    safe = validate_channel_copy(safe_body)
    if not safe[0]:
        raise ValueError(safe[1] or "Текст поста не прошёл safety-проверку.")

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Черновик не найден.")
        if row.status in {CHANNEL_STATUS_GENERATING, CHANNEL_STATUS_PUBLISHING, CHANNEL_STATUS_PUBLISHED}:
            raise ValueError("Этот элемент нельзя редактировать в текущем статусе.")

        row.body_html = safe_body
        row.cta_label = _safe_cta_label(cta_label or row.cta_label) or CHANNEL_DEFAULT_CTA_LABEL
        row.error_text = None
        row.updated_at = utcnow()
        if row.status != CHANNEL_STATUS_DRAFT:
            if not can_transition_channel_status(row.status, CHANNEL_STATUS_DRAFT):
                raise ValueError("Нельзя перевести элемент в черновик после редактирования.")
            row.status = CHANNEL_STATUS_DRAFT
            row.approved_at = None
            row.approved_by_telegram_id = None

        await session.commit()
        await session.refresh(row)
        return row


async def approve_channel_content_item(item_id: int, approved_by_telegram_id: int) -> ChannelContentItem:
    await ensure_schema()

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Черновик не найден.")
        if row.status != CHANNEL_STATUS_DRAFT:
            raise ValueError("Одобрять можно только черновики.")
        if not row.body_html:
            raise ValueError("Нельзя одобрить пустой черновик.")
        safe = validate_channel_copy(row.body_html)
        if not safe[0]:
            raise ValueError(safe[1] or "Текст поста не прошёл safety-проверку.")

        row.status = CHANNEL_STATUS_APPROVED
        row.approved_at = utcnow()
        row.approved_by_telegram_id = int(approved_by_telegram_id)
        row.error_text = None
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return row


async def reject_channel_content_item(item_id: int) -> ChannelContentItem:
    await ensure_schema()

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден.")
        if row.status in {CHANNEL_STATUS_PUBLISHING, CHANNEL_STATUS_PUBLISHED}:
            raise ValueError("Опубликованный пост нельзя отклонить.")
        if not can_transition_channel_status(row.status, CHANNEL_STATUS_REJECTED):
            raise ValueError("Этот элемент нельзя перевести в статус отклонённого.")

        row.status = CHANNEL_STATUS_REJECTED
        row.approved_at = None
        row.approved_by_telegram_id = None
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return row


async def generate_channel_content_item(item_id: int) -> dict[str, object]:
    await ensure_schema()

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден.")
        if row.status not in {CHANNEL_STATUS_QUEUED, CHANNEL_STATUS_DRAFT, CHANNEL_STATUS_REJECTED, CHANNEL_STATUS_FAILED}:
            raise ValueError("Генерация доступна только для очереди, черновика, отклонённого или failed-элемента.")
        if not can_transition_channel_status(row.status, CHANNEL_STATUS_GENERATING):
            raise ValueError("Нельзя перевести элемент в генерацию.")

        row.status = CHANNEL_STATUS_GENERATING
        row.error_text = None
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)

    try:
        generated = await _generate_channel_draft(
            content_type=row.content_type,
            topic_brief=row.topic_brief,
            current_cta_label=row.cta_label,
        )
    except Exception as exc:
        failed = await _mark_channel_item_failed(item_id, str(exc))
        await create_control_event(
            category="system",
            severity="WARNING",
            event_type="channel_content_generate_failed",
            title="Не удалось подготовить черновик канала",
            message=(
                f"Элемент: <code>{item_id}</code>\n"
                f"Тип: <b>{escape(channel_content_type_label(row.content_type))}</b>\n"
                f"Тема: <b>{escape(row.topic_brief[:180])}</b>\n"
                f"Ошибка: <b>{escape(str(exc)[:300])}</b>"
            ),
            entity_type="channel_content_item",
            entity_id=str(item_id),
            payload={"item_id": item_id, "topic_brief": row.topic_brief, "status": CHANNEL_STATUS_FAILED},
            dedupe_key=f"channel-generate-failed:{item_id}",
        )
        return serialize_channel_content_item(failed)

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден после генерации.")

        row.body_html = generated["body_html"]
        row.cta_label = _safe_cta_label(generated.get("cta_label")) or CHANNEL_DEFAULT_CTA_LABEL
        row.model_name = str(generated.get("model_name") or "")[:80] or None
        row.prompt_version = str(generated.get("prompt_version") or CHANNEL_PROMPT_VERSION)[:40]
        row.status = CHANNEL_STATUS_DRAFT
        row.error_text = None
        row.approved_at = None
        row.approved_by_telegram_id = None
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return serialize_channel_content_item(row)


async def generate_due_channel_content_items(*, notify_missing_content: bool = False) -> dict[str, object]:
    await ensure_schema()

    if notify_missing_content:
        await _emit_missing_content_reminder_if_needed()

    day_start, day_end = _today_schedule_window()
    items = await list_channel_content_items(
        statuses={CHANNEL_STATUS_QUEUED},
        limit=20,
        scheduled_from=day_start,
        scheduled_to=day_end,
    )
    processed: list[dict[str, object]] = []
    for item in items:
        processed.append(await generate_channel_content_item(item.id))
    return {"processed_count": len(processed), "items": processed}


async def publish_channel_content_item(item_id: int, *, allow_failed_retry: bool = False) -> dict[str, object]:
    await ensure_schema()

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден.")
        allowed_statuses = {CHANNEL_STATUS_APPROVED}
        if allow_failed_retry:
            allowed_statuses.add(CHANNEL_STATUS_FAILED)
        if row.status not in allowed_statuses:
            raise ValueError("Публиковать можно только approved-элементы или failed после ручного retry.")
        if not row.body_html:
            raise ValueError("Нельзя опубликовать элемент без текста.")
        safe = validate_channel_copy(row.body_html)
        if not safe[0]:
            raise ValueError(safe[1] or "Текст поста не прошёл safety-проверку.")

        row.status = CHANNEL_STATUS_PUBLISHING
        row.error_text = None
        row.updated_at = utcnow()
        if not row.deep_link_token:
            row.deep_link_token = _new_deep_link_token()
        await session.commit()
        await session.refresh(row)

    try:
        publish_result = await _publish_channel_message(row)
    except Exception as exc:
        failed = await _mark_channel_item_failed(item_id, str(exc))
        await create_control_event(
            category="system",
            severity="WARNING",
            event_type="channel_content_publish_failed",
            title="Не удалось опубликовать пост канала",
            message=(
                f"Элемент: <code>{item_id}</code>\n"
                f"Тема: <b>{escape(row.topic_brief[:180])}</b>\n"
                f"Ошибка: <b>{escape(str(exc)[:300])}</b>"
            ),
            entity_type="channel_content_item",
            entity_id=str(item_id),
            payload={"item_id": item_id, "topic_brief": row.topic_brief, "status": CHANNEL_STATUS_FAILED},
            dedupe_key=f"channel-publish-failed:{item_id}",
        )
        return serialize_channel_content_item(failed)

    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден после публикации.")

        row.status = CHANNEL_STATUS_PUBLISHED
        row.telegram_chat_id = publish_result["telegram_chat_id"]
        row.telegram_message_id = publish_result["telegram_message_id"]
        row.published_at = utcnow()
        row.error_text = None
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return serialize_channel_content_item(row)


async def publish_due_channel_content_items() -> dict[str, object]:
    await ensure_schema()

    now_local = _local_now()
    items = await list_channel_content_items(
        statuses={CHANNEL_STATUS_APPROVED},
        limit=20,
        scheduled_to=now_local,
    )
    processed: list[dict[str, object]] = []
    for item in items:
        processed.append(await publish_channel_content_item(item.id))
    return {"processed_count": len(processed), "items": processed}


async def register_channel_post_touch(post_token: str, *, user_id: int, telegram_id: int) -> dict[str, object] | None:
    await ensure_schema()

    normalized_token = str(post_token or "").strip().lower()
    if not normalized_token:
        return None

    async with async_session() as session:
        item = (
            await session.execute(
                select(ChannelContentItem).where(ChannelContentItem.deep_link_token == normalized_token)
            )
        ).scalar_one_or_none()
        if item is None:
            await safe_upsert_user_attribution(
                user_id=int(user_id),
                telegram_id=int(telegram_id),
                source_type="channel_post",
                source_key=normalized_token,
                channel_item_id=None,
                seen_at=utcnow(),
            )
            await emit_link_touched_event(
                user_id=int(user_id),
                telegram_id=int(telegram_id),
                source_type="channel_post",
                source_key=normalized_token,
                channel_item_id=None,
            )
            return {
                "touch_id": None,
                "item_id": None,
                "created": True,
                "first_seen_at": None,
                "last_seen_at": None,
                "source_key": normalized_token,
                "fallback_tracked": True,
            }

        row = (
            await session.execute(
                select(ChannelPostTouch).where(
                    ChannelPostTouch.item_id == int(item.id),
                    ChannelPostTouch.user_id == int(user_id),
                )
            )
        ).scalar_one_or_none()
        now = utcnow()
        created = False
        if row is None:
            row = ChannelPostTouch(
                item_id=int(item.id),
                user_id=int(user_id),
                telegram_id=int(telegram_id),
                first_seen_at=now,
                last_seen_at=now,
            )
            created = True
            session.add(row)
        else:
            row.telegram_id = int(telegram_id)
            row.last_seen_at = now
        await session.commit()
        await session.refresh(row)
        await safe_upsert_user_attribution(
            user_id=int(user_id),
            telegram_id=int(telegram_id),
            source_type="channel_post",
            source_key=normalized_token,
            channel_item_id=int(item.id),
            seen_at=row.first_seen_at if created else row.last_seen_at,
        )
        return {
            "touch_id": int(row.id),
            "item_id": int(item.id),
            "created": created,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "source_key": normalized_token,
            "fallback_tracked": False,
        }


async def mark_recent_channel_post_conversion(user_id: int, *, reason: str) -> dict[str, object] | None:
    await ensure_schema()

    now = utcnow()
    cutoff = now - timedelta(days=7)
    async with async_session() as session:
        row = (
            await session.execute(
                select(ChannelPostTouch)
                .where(
                    ChannelPostTouch.user_id == int(user_id),
                    ChannelPostTouch.converted_at.is_(None),
                    ChannelPostTouch.last_seen_at >= cutoff,
                )
                .order_by(ChannelPostTouch.last_seen_at.desc(), ChannelPostTouch.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        row.converted_at = now
        row.conversion_reason = str(reason or "").strip()[:80] or None
        await session.commit()
        await session.refresh(row)
        return {
            "touch_id": int(row.id),
            "item_id": int(row.item_id),
            "converted_at": row.converted_at,
            "conversion_reason": row.conversion_reason,
        }


async def _publish_channel_message(item: ChannelContentItem) -> dict[str, int]:
    channel_id = str(config.channel_id or "").strip()
    if not channel_id:
        raise ValueError("CHANNEL_ID is not configured.")
    token = str(config.control_bot_token or "").strip()
    if not token:
        raise ValueError("AMONORA_CONTROL_BOT_TOKEN is not configured.")

    bot = Bot(token=token)
    reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_safe_cta_label(item.cta_label) or CHANNEL_DEFAULT_CTA_LABEL,
                    url=build_channel_cta_url(item.deep_link_token),
                )
            ]
        ]
    )
    try:
        result = await bot.send_message(
            chat_id=channel_id,
            text=item.body_html or "",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    except TelegramForbiddenError as exc:
        raise ValueError("Control bot cannot publish to the channel. Check channel admin rights.") from exc
    except TelegramBadRequest as exc:
        raise ValueError(f"Telegram rejected the post: {exc}") from exc
    finally:
        await bot.session.close()

    return {
        "telegram_chat_id": int(result.chat.id),
        "telegram_message_id": int(result.message_id),
    }


async def _generate_channel_draft(
    *,
    content_type: str,
    topic_brief: str,
    current_cta_label: str | None = None,
) -> dict[str, str]:
    api_key = str(getattr(config, "openai_api_key", "") or "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    model = str(getattr(config, "openai_channel_model", "") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    system_prompt, user_prompt = _build_generation_prompts(
        content_type=content_type,
        topic_brief=topic_brief,
        cta_label=current_cta_label,
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 400:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {"error": {"message": response.text}}
        message = (
            error_payload.get("error", {}).get("message")
            if isinstance(error_payload, dict)
            else response.text
        )
        raise ValueError(f"OpenAI error {response.status_code}: {str(message or 'request failed')[:250]}")

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise ValueError("OpenAI returned non-JSON payload.") from exc

    raw_text = _extract_openai_output_text(response_payload)
    parsed = _parse_generation_output(raw_text)
    body_html = _safe_body_html(parsed.get("body_html"))
    cta_label = _safe_cta_label(parsed.get("cta_label")) or _safe_cta_label(current_cta_label) or CHANNEL_DEFAULT_CTA_LABEL
    safe = validate_channel_copy(body_html)
    if not safe[0]:
        raise ValueError(safe[1] or "Generated draft did not pass safety validation.")

    return {
        "body_html": body_html,
        "cta_label": cta_label,
        "model_name": str(response_payload.get("model") or model),
        "prompt_version": CHANNEL_PROMPT_VERSION,
    }


def _build_generation_prompts(
    *,
    content_type: str,
    topic_brief: str,
    cta_label: str | None,
) -> tuple[str, str]:
    goal = {
        CHANNEL_CONTENT_TYPE_EDUCATION: "сделай короткий обучающий пост с полезным объяснением",
        CHANNEL_CONTENT_TYPE_OFFER: "сделай аккуратный продуктовый пост с оффером без агрессивных обещаний",
        CHANNEL_CONTENT_TYPE_ENGAGEMENT: "сделай вовлекающий пост с вопросом или invitation to reply",
    }.get(content_type, "сделай короткий полезный пост")
    system_prompt = (
        "Ты пишешь посты для Telegram-канала Amonora на русском языке. "
        "Нужен короткий, чистый, законопослушный public-facing текст без серых обещаний. "
        "Не упоминай обход блокировок, legally restricted resources, абсолютную защиту, "
        "полную анонимность, иммунитет, гарантии или обещания вне правовых ограничений. "
        "Не используй Markdown. Разрешены только простые HTML-теги Telegram: <b>, <i>, <code>. "
        "Ответь только JSON-объектом без пояснений и без кодовых блоков. "
        "Формат: {\"body_html\": \"...\", \"cta_label\": \"...\"}."
    )
    user_prompt = (
        f"Тип поста: {channel_content_type_label(content_type)}.\n"
        f"Задача: {goal}.\n"
        f"Тема: {topic_brief.strip()}.\n"
        f"CTA-кнопка по умолчанию: {(_safe_cta_label(cta_label) or CHANNEL_DEFAULT_CTA_LABEL)}.\n"
        "Требования:\n"
        "1. 3-6 коротких строк.\n"
        "2. Тон спокойный, уверенный, без hype и серых обещаний.\n"
        "3. Подходи для канала @amonora_new.\n"
        "4. Не упоминай, что это AI-generated текст.\n"
        "5. Верни один готовый body_html и короткий cta_label."
    )
    return system_prompt, user_prompt


def _extract_openai_output_text(payload: dict) -> str:
    direct = str(payload.get("output_text") or "").strip()
    if direct:
        return direct
    for output_item in payload.get("output", []) or []:
        if not isinstance(output_item, dict):
            continue
        for content in output_item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            for key in ("text", "output_text"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    raise ValueError("OpenAI response did not contain text output.")


def _parse_generation_output(raw_text: str) -> dict[str, str]:
    cleaned = str(raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenAI returned invalid JSON for channel draft.") from exc
    if not isinstance(value, dict):
        raise ValueError("OpenAI returned non-object JSON for channel draft.")
    return value


async def _emit_missing_content_reminder_if_needed() -> None:
    await ensure_schema()

    day_start, day_end = _today_schedule_window()
    async with async_session() as session:
        count = int(
            (
                await session.execute(
                    select(func.count(ChannelContentItem.id)).where(
                        ChannelContentItem.scheduled_at >= day_start,
                        ChannelContentItem.scheduled_at <= day_end,
                        ChannelContentItem.status.in_(sorted(CHANNEL_MISSING_COVERAGE_STATUSES)),
                    )
                )
            ).scalar_one()
        )
    if count > 0:
        return

    await create_control_event(
        category="system",
        severity="WARNING",
        event_type="channel_content_missing",
        title="На сегодня нет контент-плана для канала",
        message=(
            "На текущую дату нет queued/draft/approved/published post item.\n"
            "Откройте /channel и добавьте тему для канала."
        ),
        entity_type="channel_content_day",
        entity_id=day_start.strftime("%Y-%m-%d"),
        payload={"scheduled_date": day_start.strftime("%Y-%m-%d")},
        dedupe_key=f"channel-content-gap:{day_start.strftime('%Y-%m-%d')}",
        cooldown_seconds=0,
    )


async def _mark_channel_item_failed(item_id: int, error_text: str) -> ChannelContentItem:
    async with async_session() as session:
        row = await _load_item_for_update(session, item_id)
        if row is None:
            raise ValueError("Элемент не найден.")
        row.status = CHANNEL_STATUS_FAILED
        row.error_text = _safe_error_text(error_text)
        row.updated_at = utcnow()
        await session.commit()
        await session.refresh(row)
        return row


async def _touch_counts_for_items(item_ids: list[int]) -> dict[int, dict[str, int]]:
    if not item_ids:
        return {}
    await ensure_schema()

    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(ChannelPostTouch).where(ChannelPostTouch.item_id.in_(item_ids))
                )
            ).scalars().all()
        )
    counts: dict[int, dict[str, int]] = {}
    for row in rows:
        current = counts.setdefault(int(row.item_id), {"transitions": 0, "conversions": 0})
        current["transitions"] += 1
        if row.converted_at is not None:
            current["conversions"] += 1
    return counts


async def _touch_totals() -> tuple[int, int]:
    await ensure_schema()

    async with async_session() as session:
        rows = list((await session.execute(select(ChannelPostTouch))).scalars().all())
    transitions = len(rows)
    conversions = sum(1 for row in rows if row.converted_at is not None)
    return transitions, conversions


async def _load_item_for_update(session, item_id: int) -> ChannelContentItem | None:
    return (
        await session.execute(
            select(ChannelContentItem)
            .where(ChannelContentItem.id == int(item_id))
            .with_for_update()
        )
    ).scalar_one_or_none()


def _normalize_scheduled_at(value: datetime | None) -> datetime:
    if value is None:
        return default_channel_scheduled_at()
    normalized = _coerce_local_naive(value)
    if normalized is None:
        return default_channel_scheduled_at()
    return normalized.replace(second=0, microsecond=0)


def _coerce_local_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(CHANNEL_LOCAL_TZ).replace(tzinfo=None)


def _local_now() -> datetime:
    return datetime.now(CHANNEL_LOCAL_TZ).replace(tzinfo=None)


def _today_schedule_window() -> tuple[datetime, datetime]:
    current = _local_now()
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end


def _new_deep_link_token() -> str:
    return token_hex(8)


def _safe_topic_brief(topic_brief: str | None) -> str:
    value = re.sub(r"\s+", " ", str(topic_brief or "")).strip()
    if not value:
        raise ValueError("Тема не должна быть пустой.")
    return value[:CHANNEL_MAX_TOPIC_LENGTH]


def _safe_body_html(body_html: str | None) -> str:
    value = str(body_html or "").strip()
    if not value:
        raise ValueError("Текст поста не должен быть пустым.")
    return value[:CHANNEL_MAX_BODY_LENGTH]


def _safe_cta_label(cta_label: str | None) -> str | None:
    value = re.sub(r"\s+", " ", str(cta_label or "")).strip()
    if not value:
        return None
    return value[:CHANNEL_MAX_CTA_LABEL_LENGTH]


def _safe_error_text(error_text: str | None) -> str | None:
    value = re.sub(r"\s+", " ", str(error_text or "")).strip()
    return value[:500] or None


def _fmt_channel_dt(value: object) -> str:
    if not isinstance(value, datetime):
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def _channel_status_icon(status: str | None) -> str:
    return {
        CHANNEL_STATUS_QUEUED: "🕒",
        CHANNEL_STATUS_GENERATING: "⚙️",
        CHANNEL_STATUS_DRAFT: "📝",
        CHANNEL_STATUS_APPROVED: "✅",
        CHANNEL_STATUS_PUBLISHING: "📤",
        CHANNEL_STATUS_PUBLISHED: "📣",
        CHANNEL_STATUS_REJECTED: "🗑",
        CHANNEL_STATUS_FAILED: "⚠️",
    }.get(str(status or "").strip().lower(), "•")


def _shorten_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return f"{text[: limit - 1].rstrip()}…"


def _channel_item_compact_line(item: dict[str, object]) -> str:
    return (
        f"{_channel_status_icon(str(item.get('status')))} "
        f"<b>#{int(item.get('id') or 0)}</b> · "
        f"{escape(str(item.get('content_type_label') or 'Контент'))} · "
        f"{escape(_shorten_text(str(item.get('topic_brief') or '—'), 84))}\n"
        f"   {_fmt_channel_dt(item.get('scheduled_at'))} · "
        f"{escape(str(item.get('status_label') or '—'))} · "
        f"бот {int(item.get('transitions_count') or 0)} / conv {int(item.get('conversions_count') or 0)}"
    )
