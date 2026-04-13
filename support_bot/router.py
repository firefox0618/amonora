from html import escape
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import config
from bot.db import touch_user_activity
from control_bot.dispatcher import create_control_event
from support_bot.storage import (
    assign_ticket,
    close_ticket,
    get_history,
    get_ticket,
    get_ticket_counts,
    list_tickets,
    register_admin_card,
    register_admin_reply,
    register_user_message,
    replace_admin_cards,
    transfer_ticket,
)


router = Router()
SUPPORT_PANEL_TICKET_LIMIT = 5
SUPPORTED_USER_MEDIA_CONTENT_TYPES = {"photo", "video", "audio"}
SUPPORTED_USER_CONTENT_TYPES = SUPPORTED_USER_MEDIA_CONTENT_TYPES | {"text"}
USER_MEDIA_RESTRICTION_TEXT = (
    "Сейчас поддержка принимает текст, фото, видео и аудио.\n\n"
    "Видеокружки, документы, GIF, стикеры и голосовые сообщения пока не поддерживаются."
)

FILTER_LABELS = {
    "all": "Все обращения",
    "new": "Новые",
    "in_progress": "В работе",
    "mine": "Мои диалоги",
    "closed": "Закрытые",
}

STATUS_LABELS = {
    "new": "🆕 Новый",
    "in_progress": "🟡 В работе",
    "closed": "🔒 Закрыт",
}

STATUS_ICONS = {
    "new": "🆕",
    "in_progress": "🟡",
    "closed": "🔒",
}


class ReplyStates(StatesGroup):
    waiting_reply = State()


def _normalized_content_type(raw_value: object) -> str:
    value = getattr(raw_value, "value", raw_value)
    text = str(value or "").strip()
    if text.startswith("ContentType."):
        text = text.split(".", 1)[1]
    return text.lower()


def _is_admin(user_id: int) -> bool:
    return user_id in config.support_admin_ids


def _admin_label(message: Message | CallbackQuery) -> str:
    user = message.from_user
    username = f"@{user.username}" if user.username else ""
    name = escape(user.full_name)
    return f"{name} {escape(username)}".strip()


def _normalize_filter(filter_mode: str | None) -> str:
    if filter_mode in FILTER_LABELS:
        return filter_mode
    return "all"


def _status_label(ticket: dict) -> str:
    return STATUS_LABELS.get(ticket.get("status"), STATUS_LABELS["new"])


def _status_icon(ticket: dict) -> str:
    return STATUS_ICONS.get(ticket.get("status"), STATUS_ICONS["new"])


def _assigned_label(ticket: dict) -> str:
    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id is None:
        return "Свободен"
    return ticket.get("assigned_admin_name") or f"ID {assigned_admin_id}"


def _assigned_line(ticket: dict, viewer_admin_id: int | None = None) -> str:
    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id is None:
        return "🙋 <b>Ответственный:</b> <i>Свободен</i>"
    if viewer_admin_id is not None and assigned_admin_id == viewer_admin_id:
        return "🙋 <b>Ответственный:</b> <b>ты</b>"
    return f"🙋 <b>Ответственный:</b> <b>{escape(_assigned_label(ticket))}</b>"


def _ticket_heading(ticket: dict) -> str:
    status = ticket.get("status")
    if status == "closed":
        return "🔒 <b>Обращение закрыто</b>"
    if status == "in_progress":
        return "🛟 <b>Обращение в работе</b>"
    return "🛟 <b>Новое сообщение в поддержку</b>"


def _ticket_text(ticket: dict, viewer_admin_id: int | None = None) -> str:
    username = f"@{ticket['username']}" if ticket.get("username") else "без username"
    user_preview = escape(ticket.get("last_user_message_preview") or ticket.get("last_message_preview") or "—")
    admin_preview = escape(ticket.get("last_admin_reply_preview") or "")
    base_text = (
        f"{_ticket_heading(ticket)}\n\n"
        f"👤 Клиент: <b>{escape(ticket.get('full_name', 'Неизвестно'))}</b>\n"
        f"🆔 ID: <code>{ticket['user_id']}</code>\n"
        f"🔗 Username: {escape(username)}\n"
        f"📌 Статус: <b>{_status_label(ticket)}</b>\n"
        f"{_assigned_line(ticket, viewer_admin_id)}\n"
        f"🕒 Обновлено: <code>{ticket.get('updated_at', '—')}</code>\n\n"
        f"❓ Вопрос:\n<blockquote>{user_preview}</blockquote>"
    )
    if admin_preview:
        base_text += f"\n\n✅ Последний ответ:\n<blockquote>{admin_preview}</blockquote>"
    return base_text


def _short_admin_name(ticket: dict) -> str:
    assigned = _assigned_label(ticket)
    assigned = assigned.replace("@", "").strip()
    if " " in assigned:
        assigned = assigned.split(" ")[0]
    return assigned[:12]


def _ticket_button_label(ticket: dict, viewer_admin_id: int) -> str:
    label = f"{_status_icon(ticket)} {ticket.get('full_name', 'Неизвестно')}"
    if ticket.get("status") == "in_progress":
        if ticket.get("assigned_admin_id") == viewer_admin_id:
            label += " · ты"
        else:
            short_admin = _short_admin_name(ticket)
            if short_admin:
                label += f" · {short_admin}"
    return label[:60]


def _dashboard_text(counts: dict[str, int], filter_mode: str, tickets: list[dict]) -> str:
    lines = [
        "🛟 <b>Панель поддержки Amonora</b>",
        "",
        f"📂 Фильтр: <b>{escape(FILTER_LABELS[filter_mode])}</b>",
        "",
        f"🆕 Новые: <b>{counts.get('new', 0)}</b>   🟡 В работе: <b>{counts.get('in_progress', 0)}</b>",
        f"🙋 Мои: <b>{counts.get('mine', 0)}</b>   🔒 Закрытые: <b>{counts.get('closed', 0)}</b>",
        "",
    ]
    if tickets:
        lines.append("Выбери обращение ниже.")
        hidden = max(int(counts.get(filter_mode, counts.get("all", len(tickets))) or 0) - len(tickets), 0)
        if hidden > 0:
            lines.append(f"Показаны последние <b>{len(tickets)}</b>. Ещё в очереди: <b>{hidden}</b>.")
    else:
        lines.append("По этому фильтру обращений пока нет.")
    return "\n".join(lines)


def _dashboard_keyboard(tickets: list[dict], filter_mode: str, viewer_admin_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📂 Все", callback_data="support:panel:all"),
            InlineKeyboardButton(text="🆕 Новые", callback_data="support:panel:new"),
        ],
        [
            InlineKeyboardButton(text="🟡 В работе", callback_data="support:panel:in_progress"),
            InlineKeyboardButton(text="🙋 Мои", callback_data="support:panel:mine"),
        ],
        [
            InlineKeyboardButton(text="🔒 Закрытые", callback_data="support:panel:closed"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"support:panel:{filter_mode}"),
        ],
    ]

    for ticket in tickets[:SUPPORT_PANEL_TICKET_LIMIT]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_ticket_button_label(ticket, viewer_admin_id),
                    callback_data=f"support:open:{ticket['user_id']}:{filter_mode}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ticket_keyboard(ticket: dict, viewer_admin_id: int, panel_filter: str = "all") -> InlineKeyboardMarkup:
    user_id = ticket["user_id"]
    assigned_admin_id = ticket.get("assigned_admin_id")
    is_closed = ticket.get("status") == "closed"

    first_row_text = "✅ Взять диалог" if assigned_admin_id is None else f"🙋 {_assigned_label(ticket)}"
    rows = [
        [InlineKeyboardButton(text=first_row_text, callback_data=f"support:take:{user_id}:{panel_filter}")],
        [
            InlineKeyboardButton(text="✉ Ответить", callback_data=f"support:reply:{user_id}:{panel_filter}"),
            InlineKeyboardButton(text="📜 История", callback_data=f"support:history:{user_id}:{panel_filter}"),
        ],
        [
            InlineKeyboardButton(text="🔁 Передать", callback_data=f"support:transfer:{user_id}:{panel_filter}"),
            InlineKeyboardButton(
                text="🔒 Закрыто" if is_closed else "🔒 Закрыть",
                callback_data=f"support:close:{user_id}:{panel_filter}",
            ),
        ],
        [
            InlineKeyboardButton(text="⬅ К списку", callback_data=f"support:panel:{panel_filter}"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"support:refresh:{user_id}:{panel_filter}"),
        ],
    ]

    if assigned_admin_id == viewer_admin_id:
        rows[0][0] = InlineKeyboardButton(text="🙋 Диалог на тебе", callback_data=f"support:take:{user_id}:{panel_filter}")

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _transfer_keyboard(bot: Bot, user_id: int, current_admin_id: int | None, panel_filter: str) -> InlineKeyboardMarkup:
    rows = []
    for admin_id in config.support_admin_ids:
        if admin_id == current_admin_id:
            continue
        label = f"ID {admin_id}"
        try:
            chat = await bot.get_chat(admin_id)
            username = f"@{chat.username}" if getattr(chat, "username", None) else ""
            full_name = " ".join(
                part for part in [getattr(chat, "first_name", ""), getattr(chat, "last_name", "")] if part
            )
            label = f"{full_name} {username}".strip() or label
        except TelegramBadRequest:
            pass

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"➡ {label}",
                    callback_data=f"support:transferto:{user_id}:{admin_id}:{panel_filter}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"support:refresh:{user_id}:{panel_filter}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _message_preview(message: Message) -> tuple[str, str]:
    content_type = _normalized_content_type(message.content_type)
    raw_text = message.text or message.caption
    if raw_text:
        normalized = " ".join(raw_text.split())
        return normalized[:700], content_type

    labels = {
        "photo": "📷 Фото",
        "document": "📄 Документ",
        "video": "🎬 Видео",
        "voice": "🎤 Голосовое сообщение",
        "audio": "🎵 Аудио",
        "sticker": "🙂 Стикер",
        "video_note": "🎥 Видеосообщение",
        "animation": "GIF / анимация",
    }
    return labels.get(content_type, f"Сообщение типа {content_type}"), content_type


def _is_supported_user_message(message: Message) -> bool:
    return _normalized_content_type(message.content_type) in SUPPORTED_USER_CONTENT_TYPES


def _extract_attachment(message: Message) -> dict | None:
    if message.photo:
        photo = message.photo[-1]
        return {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "kind": "photo",
            "name": "photo.jpg",
            "mime_type": "image/jpeg",
            "size": photo.file_size,
        }
    if message.document:
        document = message.document
        return {
            "file_id": document.file_id,
            "file_unique_id": document.file_unique_id,
            "kind": "document",
            "name": document.file_name,
            "mime_type": document.mime_type,
            "size": document.file_size,
        }
    if message.video:
        video = message.video
        return {
            "file_id": video.file_id,
            "file_unique_id": video.file_unique_id,
            "kind": "video",
            "name": video.file_name,
            "mime_type": video.mime_type,
            "size": video.file_size,
        }
    if message.voice:
        voice = message.voice
        return {
            "file_id": voice.file_id,
            "file_unique_id": voice.file_unique_id,
            "kind": "voice",
            "name": "voice.ogg",
            "mime_type": voice.mime_type,
            "size": voice.file_size,
        }
    if message.audio:
        audio = message.audio
        return {
            "file_id": audio.file_id,
            "file_unique_id": audio.file_unique_id,
            "kind": "audio",
            "name": audio.file_name,
            "mime_type": audio.mime_type,
            "size": audio.file_size,
        }
    if message.animation:
        animation = message.animation
        return {
            "file_id": animation.file_id,
            "file_unique_id": animation.file_unique_id,
            "kind": "animation",
            "name": animation.file_name,
            "mime_type": animation.mime_type,
            "size": animation.file_size,
        }
    if message.sticker:
        sticker = message.sticker
        return {
            "file_id": sticker.file_id,
            "file_unique_id": sticker.file_unique_id,
            "kind": "sticker",
            "name": "sticker.webp",
            "mime_type": "image/webp",
            "size": sticker.file_size,
        }
    if message.video_note:
        video_note = message.video_note
        return {
            "file_id": video_note.file_id,
            "file_unique_id": video_note.file_unique_id,
            "kind": "video_note",
            "name": "video_note.mp4",
            "mime_type": "video/mp4",
            "size": video_note.file_size,
        }
    return None


def _history_text(ticket: dict, history: list[dict]) -> str:
    if not history:
        return "📜 История пуста."

    lines = [
        "📜 <b>История обращения</b>",
        "",
        f"👤 Клиент: <b>{escape(ticket.get('full_name', 'Неизвестно'))}</b>",
        f"🆔 ID: <code>{ticket['user_id']}</code>",
        "",
    ]

    for item in history[-15:]:
        role = "Клиент" if item.get("role") == "user" else "Поддержка"
        sender_name = escape(item.get("sender_name") or role)
        text = escape((item.get("text") or "—")[:220])
        attachment = item.get("attachment") or {}
        lines.append(f"<b>{role}</b> · {sender_name}")
        lines.append(f"<code>{item.get('timestamp', '—')}</code>")
        lines.append(text)
        if attachment.get("kind"):
            lines.append(f"📎 Вложение: {escape(str(attachment.get('kind')))}")
        lines.append("")

    return "\n".join(lines).strip()


async def _refresh_admin_cards(bot: Bot, ticket: dict) -> None:
    admin_cards = ticket.get("admin_cards", {})
    new_cards: dict[str, list[int]] = {}

    for admin_id_str, message_ids in admin_cards.items():
        admin_id = int(admin_id_str)
        valid_ids: list[int] = []
        for message_id in message_ids:
            try:
                await bot.edit_message_text(
                    chat_id=admin_id,
                    message_id=message_id,
                    text=_ticket_text(ticket, admin_id),
                    parse_mode="HTML",
                    reply_markup=_ticket_keyboard(ticket, admin_id),
                )
                valid_ids.append(message_id)
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    valid_ids.append(message_id)
                    continue
                continue

        if valid_ids:
            new_cards[admin_id_str] = valid_ids

    await replace_admin_cards(ticket["user_id"], new_cards)


async def _edit_message_safely(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _render_ticket_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    ticket: dict,
    viewer_admin_id: int,
    panel_filter: str,
) -> None:
    await _edit_message_safely(
        bot,
        chat_id,
        message_id,
        _ticket_text(ticket, viewer_admin_id),
        _ticket_keyboard(ticket, viewer_admin_id, panel_filter),
    )


async def _render_admin_panel(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    viewer_admin_id: int,
    filter_mode: str,
) -> None:
    safe_filter = _normalize_filter(filter_mode)
    counts = await get_ticket_counts(viewer_admin_id, exclude_synthetic=True)
    tickets = await list_tickets(
        safe_filter,
        admin_id=viewer_admin_id,
        limit=SUPPORT_PANEL_TICKET_LIMIT,
        exclude_synthetic=True,
    )
    text = _dashboard_text(counts, safe_filter, tickets)
    keyboard = _dashboard_keyboard(tickets, safe_filter, viewer_admin_id)

    if message_id is None:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
        return

    await _edit_message_safely(bot, chat_id, message_id, text, keyboard)


async def _push_ticket_to_admins(bot: Bot, ticket: dict) -> None:
    admin_cards = ticket.get("admin_cards", {})
    for admin_id in config.support_admin_ids:
        existing_cards = admin_cards.get(str(admin_id), [])
        if existing_cards:
            continue
        try:
            panel_message = await bot.send_message(
                chat_id=admin_id,
                text=_ticket_text(ticket, admin_id),
                parse_mode="HTML",
                reply_markup=_ticket_keyboard(ticket, admin_id),
            )
            await register_admin_card(ticket["user_id"], admin_id, panel_message.message_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            continue

    refreshed_ticket = await get_ticket(ticket["user_id"])
    if refreshed_ticket is not None:
        await _refresh_admin_cards(bot, refreshed_ticket)


async def _notify_admins_about_user_message(bot: Bot, ticket: dict, reopened: bool = False) -> None:
    assigned_admin_id = ticket.get("assigned_admin_id")
    admin_cards = ticket.get("admin_cards", {})
    if not assigned_admin_id and not admin_cards:
        return

    target_admin_ids = [assigned_admin_id] if assigned_admin_id else list(config.support_admin_ids)
    preview = escape(ticket.get("last_user_message_preview") or ticket.get("last_message_preview") or "—")
    full_name = escape(ticket.get("full_name") or "Неизвестно")
    username = f"@{ticket.get('username')}" if ticket.get("username") else "без username"
    heading = "🛟 <b>Клиент написал снова</b>" if reopened or ticket.get("status") == "in_progress" else "🆕 <b>Новое сообщение клиента</b>"

    for admin_id in target_admin_ids:
        if not admin_id:
            continue
        panel_filter = "mine" if assigned_admin_id == admin_id else "all"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть диалог", callback_data=f"support:open:{ticket['user_id']}:{panel_filter}")]
            ]
        )
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"{heading}\n\n"
                    f"👤 <b>{full_name}</b>\n"
                    f"🔗 {escape(username)}\n"
                    f"🆔 <code>{ticket['user_id']}</code>\n\n"
                    f"<blockquote>{preview}</blockquote>"
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            continue


async def _copy_user_media_to_admins(message: Message, ticket: dict) -> None:
    attachment = _extract_attachment(message)
    if attachment is None:
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    target_admin_ids = [assigned_admin_id] if assigned_admin_id else list(config.support_admin_ids)
    for admin_id in target_admin_ids:
        if not admin_id:
            continue
        try:
            await message.copy_to(admin_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            continue


async def _send_admin_reply(message: Message, user_id: int) -> None:
    if message.text:
        await message.bot.send_message(
            chat_id=user_id,
            text=f"💬 <b>Ответ поддержки Amonora</b>\n\n{escape(message.text)}",
            parse_mode="HTML",
        )
        return

    await message.bot.send_message(
        chat_id=user_id,
        text="💬 <b>Ответ поддержки Amonora</b>",
        parse_mode="HTML",
    )
    await message.copy_to(user_id)


def _extract_ticket_user_id(reply_message: Message | None) -> int | None:
    if reply_message is None:
        return None

    raw_text = reply_message.text or reply_message.caption or ""
    match = re.search(r"ID:\s*(\d+)", raw_text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


async def _notify_user_closed(bot: Bot, user_id: int) -> None:
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🔒 <b>Обращение закрыто</b>\n\n"
                "Если вопрос ещё остался, просто напиши в этот бот снова — обращение откроется заново."
            ),
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        return


async def _notify_admin_transfer(
    bot: Bot,
    user_id: int,
    target_admin_id: int,
    from_admin_name: str,
    ticket: dict,
) -> None:
    try:
        panel_message = await bot.send_message(
            chat_id=target_admin_id,
            text=(
                "🔁 <b>Тебе передали обращение</b>\n\n"
                f"Передал: <b>{escape(from_admin_name)}</b>\n\n"
                f"{_ticket_text(ticket, target_admin_id)}"
            ),
            parse_mode="HTML",
            reply_markup=_ticket_keyboard(ticket, target_admin_id, "mine"),
        )
        await register_admin_card(user_id, target_admin_id, panel_message.message_id)
    except (TelegramForbiddenError, TelegramBadRequest):
        return


async def _reply_started_message(message: Message) -> None:
    await message.answer(
        "✏ Напиши ответ пользователю одним сообщением.\n"
        "Если передумал, отправь /cancel."
    )


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    if _is_admin(message.from_user.id):
        await _render_admin_panel(message.bot, message.chat.id, None, message.from_user.id, "all")
        return

    await message.answer(
        "🛟 <b>Поддержка Amonora</b>\n\n"
        "Опиши проблему одним сообщением.\n"
        "Ответ поддержки придёт сюда же.",
        parse_mode="HTML",
    )


@router.message(Command("tickets"))
async def tickets_handler(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Команда доступна только поддержке.")
        return

    await _render_admin_panel(message.bot, message.chat.id, None, message.from_user.id, "all")


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Текущий ответ отменён.")


@router.callback_query(F.data.startswith("support:panel:"))
async def support_panel_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    filter_mode = _normalize_filter(parts[2] if len(parts) > 2 else "all")
    await _render_admin_panel(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        callback.from_user.id,
        filter_mode,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("support:open:"))
async def support_open_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    await _render_ticket_message(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        ticket,
        callback.from_user.id,
        panel_filter,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("support:take:"))
async def support_take_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    if ticket.get("status") == "closed":
        await callback.answer("Обращение закрыто. Если клиент напишет снова, оно откроется автоматически.", show_alert=True)
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id is not None and assigned_admin_id != callback.from_user.id:
        await callback.answer(f"Диалог уже взял {_assigned_label(ticket)}", show_alert=True)
        return

    updated_ticket = await assign_ticket(user_id, callback.from_user.id, _admin_label(callback))
    if updated_ticket is None:
        await callback.answer("Не удалось взять диалог", show_alert=True)
        return

    await _render_ticket_message(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        updated_ticket,
        callback.from_user.id,
        panel_filter,
    )
    await _refresh_admin_cards(callback.bot, updated_ticket)
    await callback.answer("Диалог закреплён за тобой", show_alert=False)


@router.callback_query(F.data.startswith("support:reply:"))
async def support_reply_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    if ticket.get("status") == "closed":
        await callback.answer("Обращение закрыто. Если клиент напишет снова, оно откроется автоматически.", show_alert=True)
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id not in (None, callback.from_user.id):
        await callback.answer(f"Диалог уже ведёт {_assigned_label(ticket)}", show_alert=True)
        return

    updated_ticket = await assign_ticket(user_id, callback.from_user.id, _admin_label(callback))
    if updated_ticket is not None:
        await _render_ticket_message(
            callback.bot,
            callback.message.chat.id,
            callback.message.message_id,
            updated_ticket,
            callback.from_user.id,
            panel_filter,
        )
        await _refresh_admin_cards(callback.bot, updated_ticket)

    await state.set_state(ReplyStates.waiting_reply)
    await state.update_data(
        target_user_id=user_id,
        source_chat_id=callback.message.chat.id,
        source_message_id=callback.message.message_id,
        panel_filter=panel_filter,
    )
    await _reply_started_message(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("support:history:"))
async def support_history_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    user_id = int(callback.data.split(":")[2])
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    history = await get_history(user_id)
    await callback.message.answer(_history_text(ticket, history), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("support:transfer:"))
async def support_transfer_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id is None:
        await callback.answer("Сначала возьми диалог на себя", show_alert=True)
        return

    if assigned_admin_id != callback.from_user.id:
        await callback.answer("Передавать диалог может только тот, кто его ведёт", show_alert=True)
        return

    await callback.message.edit_reply_markup(
        reply_markup=await _transfer_keyboard(callback.bot, user_id, callback.from_user.id, panel_filter)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("support:transferto:"))
async def support_transfer_to_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    target_admin_id = int(parts[3])
    panel_filter = _normalize_filter(parts[4] if len(parts) > 4 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    if ticket.get("assigned_admin_id") != callback.from_user.id:
        await callback.answer("Передавать диалог может только ответственный администратор", show_alert=True)
        return

    try:
        chat = await callback.bot.get_chat(target_admin_id)
        username = f"@{chat.username}" if getattr(chat, "username", None) else ""
        full_name = " ".join(part for part in [getattr(chat, "first_name", ""), getattr(chat, "last_name", "")] if part)
        target_name = f"{full_name} {username}".strip() or f"ID {target_admin_id}"
    except TelegramBadRequest:
        target_name = f"ID {target_admin_id}"

    updated_ticket = await transfer_ticket(user_id, target_admin_id, target_name)
    if updated_ticket is None:
        await callback.answer("Не удалось передать диалог", show_alert=True)
        return

    await _render_ticket_message(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        updated_ticket,
        callback.from_user.id,
        panel_filter,
    )
    await _refresh_admin_cards(callback.bot, updated_ticket)
    await _notify_admin_transfer(
        callback.bot,
        user_id,
        target_admin_id,
        _admin_label(callback),
        updated_ticket,
    )
    await callback.answer("Диалог передан", show_alert=False)


@router.callback_query(F.data.startswith("support:close:"))
async def support_close_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    if ticket.get("status") == "closed":
        await callback.answer("Обращение уже закрыто. Если клиент напишет снова, оно откроется автоматически.", show_alert=True)
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id not in (None, callback.from_user.id):
        await callback.answer("Закрыть диалог может только ответственный администратор", show_alert=True)
        return

    updated_ticket = await close_ticket(user_id)
    if updated_ticket is None:
        await callback.answer("Не удалось закрыть обращение", show_alert=True)
        return

    await _render_ticket_message(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        updated_ticket,
        callback.from_user.id,
        panel_filter,
    )
    await _refresh_admin_cards(callback.bot, updated_ticket)
    await _notify_user_closed(callback.bot, user_id)
    try:
        await create_control_event(
            category="support",
            severity="INFO",
            event_type="support_ticket_closed",
            title="Обращение закрыто",
            message=(
                f"Клиент: <b>{escape(ticket.get('full_name') or ticket.get('username') or str(user_id))}</b>\n"
                f"User ID: <code>{user_id}</code>\n"
                f"Закрыл: <b>{escape(_admin_label(callback))}</b>"
            ),
            entity_type="support_ticket",
            entity_id=str(user_id),
            dedupe_key=f"support-ticket:{user_id}:closed",
            resolve_dedupe_key=f"support-ticket:{user_id}:open",
            cooldown_seconds=0,
        )
    except Exception:
        pass
    await callback.answer("Обращение закрыто", show_alert=False)


@router.callback_query(F.data.startswith("support:refresh:"))
async def support_refresh_callback(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    parts = callback.data.split(":")
    user_id = int(parts[2])
    panel_filter = _normalize_filter(parts[3] if len(parts) > 3 else "all")
    ticket = await get_ticket(user_id)
    if ticket is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return

    await _render_ticket_message(
        callback.bot,
        callback.message.chat.id,
        callback.message.message_id,
        ticket,
        callback.from_user.id,
        panel_filter,
    )
    await callback.answer()


@router.message(ReplyStates.waiting_reply)
async def admin_reply_input(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await state.clear()
        await message.answer("Не найден пользователь для ответа.")
        return

    ticket = await get_ticket(target_user_id)
    if ticket is None:
        await state.clear()
        await message.answer("Обращение не найдено.")
        return

    assigned_admin_id = ticket.get("assigned_admin_id")
    if assigned_admin_id not in (None, message.from_user.id):
        await state.clear()
        await message.answer(f"Диалог уже ведёт {_assigned_label(ticket)}.")
        return

    try:
        await _send_admin_reply(message, target_user_id)
    except TelegramForbiddenError:
        await message.answer("Пользователь закрыл бота или запретил отправку сообщений.")
        await state.clear()
        return
    except TelegramBadRequest:
        await message.answer("Не удалось отправить ответ пользователю.")
        await state.clear()
        return

    preview, content_type = _message_preview(message)
    attachment = _extract_attachment(message)
    updated_ticket = await register_admin_reply(
        target_user_id,
        message.from_user.id,
        _admin_label(message),
        preview,
        content_type,
        attachment,
    )
    if updated_ticket is not None:
        await _refresh_admin_cards(message.bot, updated_ticket)

        source_chat_id = data.get("source_chat_id")
        source_message_id = data.get("source_message_id")
        panel_filter = _normalize_filter(data.get("panel_filter"))
        if source_chat_id and source_message_id:
            await _render_ticket_message(
                message.bot,
                int(source_chat_id),
                int(source_message_id),
                updated_ticket,
                message.from_user.id,
                panel_filter,
            )

    await message.answer(
        f"✅ Ответ отправлен пользователю <code>{target_user_id}</code>.",
        parse_mode="HTML",
    )
    await state.clear()


@router.message(F.chat.type == ChatType.PRIVATE)
async def private_message_handler(message: Message, state: FSMContext) -> None:
    if _is_admin(message.from_user.id):
        current_state = await state.get_state()
        if current_state == ReplyStates.waiting_reply:
            return

        target_user_id = _extract_ticket_user_id(message.reply_to_message)
        if target_user_id is not None:
            ticket = await get_ticket(target_user_id)
            if ticket is None:
                await message.answer("Обращение не найдено.")
                return

            if ticket.get("status") == "closed":
                await message.answer("Обращение уже закрыто. Если клиент напишет снова, оно откроется автоматически.")
                return

            assigned_admin_id = ticket.get("assigned_admin_id")
            if assigned_admin_id not in (None, message.from_user.id):
                await message.answer(f"Диалог уже ведёт {_assigned_label(ticket)}.")
                return

            updated_ticket = await assign_ticket(target_user_id, message.from_user.id, _admin_label(message))
            if updated_ticket is not None:
                await _refresh_admin_cards(message.bot, updated_ticket)

            try:
                await _send_admin_reply(message, target_user_id)
            except TelegramForbiddenError:
                await message.answer("Пользователь закрыл бота или запретил отправку сообщений.")
                return
            except TelegramBadRequest:
                await message.answer("Не удалось отправить ответ пользователю.")
                return

            preview, content_type = _message_preview(message)
            attachment = _extract_attachment(message)
            updated_ticket = await register_admin_reply(
                target_user_id,
                message.from_user.id,
                _admin_label(message),
                preview,
                content_type,
                attachment,
            )
            if updated_ticket is not None:
                await _refresh_admin_cards(message.bot, updated_ticket)

                if message.reply_to_message is not None:
                    try:
                        await _render_ticket_message(
                            message.bot,
                            message.chat.id,
                            message.reply_to_message.message_id,
                            updated_ticket,
                            message.from_user.id,
                            "all",
                        )
                    except TelegramBadRequest:
                        pass

            await message.answer(
                f"✅ Ответ отправлен пользователю <code>{target_user_id}</code>.",
                parse_mode="HTML",
            )
            return

        await _render_admin_panel(message.bot, message.chat.id, None, message.from_user.id, "all")
        return

    if not _is_supported_user_message(message):
        await message.answer(USER_MEDIA_RESTRICTION_TEXT)
        return

    preview, content_type = _message_preview(message)
    attachment = _extract_attachment(message)
    ticket, reopened = await register_user_message(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        preview,
        content_type,
        attachment,
    )
    await touch_user_activity(telegram_id=message.from_user.id)
    await _push_ticket_to_admins(message.bot, ticket)
    refreshed_ticket = await get_ticket(ticket["user_id"])
    await _copy_user_media_to_admins(message, refreshed_ticket or ticket)
    await _notify_admins_about_user_message(message.bot, refreshed_ticket or ticket, reopened)
    current_ticket = refreshed_ticket or ticket
    try:
        await create_control_event(
            category="support",
            severity="WARNING" if reopened else "INFO",
            event_type="support_ticket_reopened" if reopened else "support_ticket_opened",
            title="Обращение открыто заново" if reopened else "Новое обращение в поддержку",
            message=(
                f"Клиент: <b>{escape(current_ticket.get('full_name') or message.from_user.full_name)}</b>\n"
                f"Username: <b>{escape('@' + message.from_user.username if message.from_user.username else '—')}</b>\n"
                f"User ID: <code>{message.from_user.id}</code>\n"
                f"Сообщение: <blockquote>{escape(preview)}</blockquote>"
            ),
            entity_type="support_ticket",
            entity_id=str(message.from_user.id),
            payload={
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "full_name": message.from_user.full_name,
                "preview": preview,
                "reopened": reopened,
            },
            dedupe_key=f"support-ticket:{message.from_user.id}:open",
            cooldown_seconds=300,
        )
    except Exception:
        pass
    await message.answer(
        (
            "✅ Сообщение передано в поддержку.\n"
            "Мы ответим сюда же."
            if not reopened
            else "✅ Обращение открыто заново и передано в поддержку.\nМы ответим сюда же."
        )
    )
