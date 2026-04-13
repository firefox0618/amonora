from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message


MAX_CHANNEL_POST_BUTTONS = 8
MAX_BUTTONS_PER_ROW = 3
MAX_BUTTON_LABEL_LENGTH = 64


@dataclass(frozen=True)
class ChannelPostTarget:
    chat_id: int
    message_id: int
    chat_title: str | None = None


def extract_channel_post_target(message: Message) -> ChannelPostTarget | None:
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "type", None) == "channel":
        chat = getattr(origin, "chat", None)
        message_id = getattr(origin, "message_id", None)
        if chat is not None and message_id is not None:
            return ChannelPostTarget(
                chat_id=int(chat.id),
                message_id=int(message_id),
                chat_title=getattr(chat, "title", None),
            )

    legacy_chat = getattr(message, "forward_from_chat", None)
    legacy_message_id = getattr(message, "forward_from_message_id", None)
    if legacy_chat is not None and getattr(legacy_chat, "type", None) == "channel" and legacy_message_id is not None:
        return ChannelPostTarget(
            chat_id=int(legacy_chat.id),
            message_id=int(legacy_message_id),
            chat_title=getattr(legacy_chat, "title", None),
        )
    return None


def parse_channel_post_buttons(raw_text: str) -> tuple[InlineKeyboardMarkup, int]:
    rows: list[list[InlineKeyboardButton]] = []
    button_count = 0

    for line_index, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        raw_buttons = [item.strip() for item in line.split("||") if item.strip()]
        if not raw_buttons:
            continue
        if len(raw_buttons) > MAX_BUTTONS_PER_ROW:
            raise ValueError(f"строка {line_index}: максимум {MAX_BUTTONS_PER_ROW} кнопки в одном ряду")

        row: list[InlineKeyboardButton] = []
        for raw_button in raw_buttons:
            if "|" not in raw_button:
                raise ValueError(f"строка {line_index}: используйте формат `Текст | URL`")
            label_part, url_part = raw_button.split("|", 1)
            label = label_part.strip()
            if not label:
                raise ValueError(f"строка {line_index}: у кнопки должен быть текст")
            if len(label) > MAX_BUTTON_LABEL_LENGTH:
                raise ValueError(
                    f"строка {line_index}: текст кнопки длиннее {MAX_BUTTON_LABEL_LENGTH} символов"
                )
            url = _normalize_button_url(url_part.strip(), line_index=line_index)
            row.append(InlineKeyboardButton(text=label, url=url))
            button_count += 1
            if button_count > MAX_CHANNEL_POST_BUTTONS:
                raise ValueError(f"слишком много кнопок: максимум {MAX_CHANNEL_POST_BUTTONS}")
        rows.append(row)

    if not rows:
        raise ValueError("не найдено ни одной кнопки")

    return InlineKeyboardMarkup(inline_keyboard=rows), button_count


def _normalize_button_url(raw_url: str, *, line_index: int) -> str:
    value = raw_url.strip()
    if not value:
        raise ValueError(f"строка {line_index}: у кнопки должна быть ссылка")

    if value.startswith("@"):
        username = value[1:].strip()
        if not username:
            raise ValueError(f"строка {line_index}: после @ нужен username канала или бота")
        value = f"https://t.me/{username}"
    elif value.startswith("t.me/") or value.startswith("telegram.me/"):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https", "tg"}:
        raise ValueError(
            f"строка {line_index}: ссылка должна начинаться с https://, http://, t.me/, telegram.me/ или @username"
        )
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError(f"строка {line_index}: ссылка должна содержать домен")
    if parsed.scheme == "tg" and not (parsed.netloc or parsed.path):
        raise ValueError(f"строка {line_index}: некорректная tg:// ссылка")
    return value
