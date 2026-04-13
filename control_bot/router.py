from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from backend.core.database import async_session
from bot.manual_payments import confirm_manual_payment, reject_manual_payment
from control_bot.channel_content import (
    CHANNEL_CONTENT_TYPE_EDUCATION,
    CHANNEL_CONTENT_TYPE_ENGAGEMENT,
    CHANNEL_CONTENT_TYPE_OFFER,
    CHANNEL_DEFAULT_CTA_LABEL,
    build_channel_item_screen,
    build_channel_list_screen,
    build_channel_root_screen,
    build_channel_stats_screen,
    channel_content_type_label,
    create_channel_content_item,
    default_channel_scheduled_at,
    generate_channel_content_item,
    get_channel_content_focus,
    parse_channel_schedule_input,
    publish_channel_content_item,
    reject_channel_content_item,
    approve_channel_content_item,
    update_channel_content_body,
)
from control_bot.channel_posts import extract_channel_post_target, parse_channel_post_buttons
from control_bot.access import (
    CONTROL_ROLE_OPERATOR,
    CONTROL_ROLE_ADMIN,
    CONTROL_ROLE_OWNER,
    control_role_allows,
    control_role_label,
    control_role_for_telegram_id,
    is_control_admin,
)
from control_bot.keyboards import control_menu_keyboard, control_secondary_keyboard
from control_bot.messaging import dispatch_campaign
from control_bot.queries import (
    CTA_ACTIONS,
    build_admin_push_screen,
    build_alerts_screen,
    build_broadcast_root_screen,
    build_broadcast_stats_screen,
    build_campaign_focus_screen,
    build_help_screen,
    build_last_events_screen,
    build_login_codes_screen,
    build_node_focus,
    build_nodes_screen,
    build_payment_focus,
    build_payments_screen_for,
    build_problems_screen,
    build_settings_screen,
    build_start_screen,
    build_status_screen,
    build_support_focus,
    build_support_screen,
    build_template_focus_screen,
    build_templates_screen,
    build_trigger_center_screen,
    build_trigger_rule_screen,
    build_user_focus,
    build_user_search_screen,
    build_user_broadcast_screen,
    build_users_screen,
)
from control_bot.storage import (
    CAMPAIGN_SCOPE_ADMIN,
    CAMPAIGN_SCOPE_TRIGGER,
    CAMPAIGN_SCOPE_USER,
    create_broadcast_campaign,
    delete_message_template,
    get_message_template,
    get_trigger_rule,
    is_notification_category_mandatory,
    save_message_template,
    serialize_template_buttons,
    terminate_all_dashboard_sessions,
    toggle_notification_preference,
    toggle_trigger_rule,
    update_trigger_rule,
)
from dashboard.models import DashboardAdmin
from dashboard.services import (
    assign_support_ticket_dashboard,
    close_support_ticket,
    deep_repair_user_access,
    extend_subscription_for_user,
    get_support_admin_choices,
    grant_trial_to_user,
    remove_user_tariff,
    run_server_action,
    send_support_reply,
    set_user_block_state,
    sync_user_access_state,
    transfer_support_ticket_dashboard,
)


router = Router()


class ComposeStates(StatesGroup):
    waiting_message = State()
    waiting_schedule = State()
    waiting_template_name = State()
    waiting_trigger_text = State()


class SupportReplyStates(StatesGroup):
    waiting_reply = State()


class ChannelPostStates(StatesGroup):
    waiting_buttons = State()


class ChannelContentStates(StatesGroup):
    waiting_topic = State()
    waiting_schedule = State()
    waiting_cta_label = State()
    waiting_edit_body = State()


def _role(message: Message | CallbackQuery) -> str | None:
    user = message.from_user
    return control_role_for_telegram_id(user.id)


def _is_allowed(message: Message | CallbackQuery) -> bool:
    return is_control_admin(message.from_user.id)


def _is_owner(message: Message | CallbackQuery) -> bool:
    return _role(message) == CONTROL_ROLE_OWNER


def _can_manage_channel(message: Message | CallbackQuery) -> bool:
    return control_role_allows(_role(message), CONTROL_ROLE_ADMIN)


async def _send_access_denied(message: Message | CallbackQuery) -> None:
    if isinstance(message, CallbackQuery):
        await message.answer("Доступ ограничен", show_alert=True)
        return
    await message.answer("Доступ ограничен")


def _channel_post_help_text() -> str:
    return (
        "📣 <b>ПОСТ КАНАЛА С КНОПКАМИ</b>\n\n"
        "1. Перешлите сюда пост из канала.\n"
        "2. Следующим сообщением отправьте кнопки в формате <code>Текст | URL</code>.\n\n"
        "Примеры:\n"
        "<code>Подключиться | https://t.me/amonora_bot</code>\n"
        "<code>Поддержка | https://t.me/amonora_support_bot</code>\n\n"
        "Если нужны две или три кнопки в одну строку, разделяйте их через <code>||</code>:\n"
        "<code>Бот | https://t.me/amonora_bot || Канал | https://t.me/amonora_new</code>\n\n"
        "Чтобы убрать текущие кнопки у выбранного поста, отправьте <code>очистить</code>."
    )


def _channel_content_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📘 {channel_content_type_label(CHANNEL_CONTENT_TYPE_EDUCATION)}",
                    callback_data=f"control:channel:type:{CHANNEL_CONTENT_TYPE_EDUCATION}",
                ),
                InlineKeyboardButton(
                    text=f"🎯 {channel_content_type_label(CHANNEL_CONTENT_TYPE_OFFER)}",
                    callback_data=f"control:channel:type:{CHANNEL_CONTENT_TYPE_OFFER}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💬 {channel_content_type_label(CHANNEL_CONTENT_TYPE_ENGAGEMENT)}",
                    callback_data=f"control:channel:type:{CHANNEL_CONTENT_TYPE_ENGAGEMENT}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel")],
        ]
    )


def _channel_schedule_keyboard() -> InlineKeyboardMarkup:
    default_slot = default_channel_scheduled_at()
    tomorrow_slot = default_slot + timedelta(days=1)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🕛 {default_slot.strftime('%d.%m %H:%M')}",
                    callback_data="control:channel:schedule:default",
                ),
                InlineKeyboardButton(
                    text=f"📅 {tomorrow_slot.strftime('%d.%m %H:%M')}",
                    callback_data="control:channel:schedule:tomorrow",
                ),
            ],
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="control:channel:schedule:manual")],
            [InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel")],
        ]
    )


def _channel_cta_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="control:channel:cta:skip")],
            [InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel")],
        ]
    )


async def _dashboard_admin_for_actor(telegram_id: int) -> DashboardAdmin | None:
    async with async_session() as session:
        result = await session.execute(
            select(DashboardAdmin).where(
                DashboardAdmin.telegram_id == int(telegram_id),
                DashboardAdmin.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


async def _render_message(target: Message, text: str, reply_markup=None) -> None:
    role = control_role_for_telegram_id(target.from_user.id)
    await target.answer(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup or control_menu_keyboard(role),
    )


async def _render_callback(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


def _compose_preview_text(data: dict) -> str:
    buttons = data.get("buttons") or []
    lines = [
        "📋 <b>ПРЕДПРОСМОТР</b>",
        "",
        f"Scope: <b>{data.get('scope')}</b>",
        f"Аудитория: <b>{data.get('audience_key') or 'admins'}</b>",
        f"Приоритет: <b>{data.get('priority_label') or 'medium'}</b>",
        f"План отправки: <b>{data.get('schedule_label') or 'сейчас'}</b>",
        "",
        data.get("message_body", ""),
    ]
    if buttons:
        lines.extend(["", "CTA:"])
        for button in buttons:
            lines.append(f"• {button.get('label') or CTA_ACTIONS.get(button.get('action', ''), button.get('action', '—'))}")
    return "\n".join(lines)


def _compose_preview_keyboard(data: dict) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📤 Отправить сейчас", callback_data="control:compose:send"),
            InlineKeyboardButton(text="📅 Отложить", callback_data="control:compose:schedule"),
        ],
        [
            InlineKeyboardButton(text="📋 Шаблон", callback_data="control:compose:save_template"),
            InlineKeyboardButton(text="Тест", callback_data="control:compose:test"),
        ],
    ]
    if data.get("scope") in {CAMPAIGN_SCOPE_USER, CAMPAIGN_SCOPE_TRIGGER}:
        rows.append(
            [
                InlineKeyboardButton(text="💳 CTA: Тарифы", callback_data="control:compose:cta:open_tariffs"),
                InlineKeyboardButton(text="📱 CTA: Устройства", callback_data="control:compose:cta:open_devices"),
                InlineKeyboardButton(text="🛟 CTA: Поддержка", callback_data="control:compose:cta:open_support"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="🎁 CTA: Trial", callback_data="control:compose:cta:start_trial"),
                InlineKeyboardButton(text="📡 CTA: Канал", callback_data="control:compose:cta:open_channel"),
            ]
        )
    if data.get("scope") == CAMPAIGN_SCOPE_ADMIN:
        rows.append(
            [
                InlineKeyboardButton(text="🔴 Высокий", callback_data="control:compose:priority:high"),
                InlineKeyboardButton(text="🟡 Средний", callback_data="control:compose:priority:medium"),
                InlineKeyboardButton(text="🔵 Низкий", callback_data="control:compose:priority:low"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_compose_preview(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = _compose_preview_text(data)
    keyboard = _compose_preview_keyboard(data)
    if isinstance(target, CallbackQuery):
        await _render_callback(target, text, keyboard)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=keyboard)


async def _send_campaign_from_state(actor_telegram_id: int, state: FSMContext, *, test: bool = False) -> ControlTuple:
    data = await state.get_data()
    scheduled_at = data.get("scheduled_at")
    status = "scheduled" if scheduled_at and not test else "queued"
    campaign = await create_broadcast_campaign(
        scope=data["scope"],
        name=data.get("template_name"),
        audience_key=data.get("audience_key"),
        message_body=data["message_body"],
        buttons=data.get("buttons") or [],
        metadata={
            "source": "control_bot_compose",
            "scope": data["scope"],
            "audience_key": data.get("audience_key"),
        },
        created_by_telegram_id=actor_telegram_id,
        priority_label=data.get("priority_label"),
        scheduled_at=scheduled_at,
        is_test=test,
        status=status,
    )
    if status == "queued":
        await dispatch_campaign(campaign.id, test_telegram_id=actor_telegram_id if test else None)
    await state.clear()
    return campaign.id, status


ControlTuple = tuple[int, str]


async def _handle_named_screen(message: Message, screen_name: str) -> None:
    if not _is_allowed(message):
        await _send_access_denied(message)
        return

    if screen_name in {"dashboard", "status"}:
        text, keyboard = await build_status_screen()
    elif screen_name == "nodes":
        text, keyboard = await build_nodes_screen()
    elif screen_name == "payments":
        text, keyboard = await build_payments_screen_for(message.from_user.id)
    elif screen_name == "users":
        text, keyboard = await build_users_screen()
    elif screen_name == "support":
        text, keyboard = await build_support_screen()
    elif screen_name == "problems":
        text, keyboard = await build_problems_screen()
    elif screen_name == "alerts":
        text, keyboard = await build_alerts_screen()
    elif screen_name == "login_codes":
        text, keyboard = await build_login_codes_screen(message.from_user.id)
    elif screen_name in {"notifications", "settings"}:
        text, keyboard = await build_settings_screen(message.from_user.id)
    elif screen_name == "events":
        text, keyboard = await build_last_events_screen()
    elif screen_name == "channel":
        if not _can_manage_channel(message):
            await _send_access_denied(message)
            return
        text, keyboard = await build_channel_root_screen()
    elif screen_name == "broadcast":
        if not _is_owner(message):
            await _send_access_denied(message)
            return
        text, keyboard = await build_broadcast_root_screen()
    else:
        text, keyboard = await build_help_screen(message.from_user.id)
    await _render_message(message, text, keyboard)


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext) -> None:
    del state
    if not _is_allowed(message):
        return
    text, keyboard = await build_start_screen(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard or control_menu_keyboard(_role(message)))


@router.message(Command("dashboard"))
@router.message(Command("status"))
@router.message(F.text == "Статус системы")
@router.message(F.text == "Дашборд")
async def status_handler(message: Message) -> None:
    await _handle_named_screen(message, "dashboard")


@router.message(Command("nodes"))
@router.message(F.text == "Ноды")
async def nodes_handler(message: Message) -> None:
    await _handle_named_screen(message, "nodes")


@router.message(Command("payments"))
@router.message(F.text == "Платежи")
async def payments_handler(message: Message) -> None:
    await _handle_named_screen(message, "payments")


@router.message(Command("users"))
@router.message(F.text == "Пользователи")
async def users_handler(message: Message) -> None:
    await _handle_named_screen(message, "users")


@router.message(Command("user"))
async def user_lookup_handler(message: Message) -> None:
    if not _is_allowed(message):
        await _send_access_denied(message)
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await _handle_named_screen(message, "users")
        return
    text, keyboard = await build_user_search_screen(parts[1].strip())
    await _render_message(message, text, keyboard)


@router.message(Command("support"))
@router.message(F.text == "Поддержка")
async def support_handler(message: Message) -> None:
    await _handle_named_screen(message, "support")


@router.message(Command("problems"))
@router.message(F.text == "Проблемы")
async def problems_handler(message: Message) -> None:
    await _handle_named_screen(message, "problems")


@router.message(Command("alerts"))
@router.message(F.text == "Ошибки")
async def alerts_handler(message: Message) -> None:
    await _handle_named_screen(message, "alerts")


@router.message(Command("login_codes"))
@router.message(F.text == "Авторизация")
@router.message(F.text == "Коды входа")
async def login_codes_handler(message: Message) -> None:
    await _handle_named_screen(message, "login_codes")


@router.message(Command("events"))
@router.message(F.text == "Последние события")
@router.message(F.text == "События")
async def last_events_handler(message: Message) -> None:
    await _handle_named_screen(message, "events")


@router.message(Command("notifications"))
@router.message(Command("settings"))
@router.message(F.text == "Настройки")
@router.message(F.text == "Уведомления")
async def settings_handler(message: Message) -> None:
    await _handle_named_screen(message, "notifications")


@router.message(Command("channel"))
@router.message(F.text == "Канал")
async def channel_handler(message: Message) -> None:
    await _handle_named_screen(message, "channel")


@router.message(Command("broadcast"))
@router.message(F.text == "Рассылка / Триггеры")
async def broadcast_handler(message: Message) -> None:
    await _handle_named_screen(message, "broadcast")


@router.message(Command("help"))
@router.message(F.text == "Помощь")
async def help_handler(message: Message) -> None:
    if not _is_allowed(message):
        await _send_access_denied(message)
        return
    text, keyboard = await build_help_screen(message.from_user.id)
    await _render_message(message, text, keyboard)


async def _create_channel_item_from_state(state: FSMContext, *, cta_label: str | None = None):
    data = await state.get_data()
    scheduled_at_raw = data.get("channel_scheduled_at")
    scheduled_at = datetime.fromisoformat(str(scheduled_at_raw)) if scheduled_at_raw else None
    item = await create_channel_content_item(
        content_type=str(data.get("channel_content_type") or ""),
        topic_brief=str(data.get("channel_topic_brief") or ""),
        scheduled_at=scheduled_at,
        cta_label=cta_label,
    )
    await state.clear()
    return item


async def _render_channel_item_callback(callback: CallbackQuery, item_id: int) -> None:
    text, keyboard = await build_channel_item_screen(item_id)
    await _render_callback(callback, text, keyboard)


async def _render_channel_item_message(message: Message, item_id: int) -> None:
    text, keyboard = await build_channel_item_screen(item_id)
    await _render_message(message, text, keyboard)


def _is_channel_cancel_text(text: str | None) -> bool:
    return str(text or "").strip().lower() in {"отмена", "/cancel", "cancel"}


@router.callback_query(F.data == "control:channel")
async def channel_root_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    await state.clear()
    text, keyboard = await build_channel_root_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:channel:new")
async def channel_new_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    await state.clear()
    await state.set_state(ChannelContentStates.waiting_topic)
    text = (
        "🆕 <b>НОВАЯ ТЕМА</b>\n\n"
        "Сначала выбери тип поста. После этого я попрошу тему, слот публикации и CTA."
    )
    await _render_callback(callback, text, _channel_content_type_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("control:channel:type:"))
async def channel_type_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    content_type = callback.data.split(":")[3]
    await state.set_state(ChannelContentStates.waiting_topic)
    await state.update_data(channel_content_type=content_type)
    await _render_callback(
        callback,
        (
            f"🧠 <b>{escape(channel_content_type_label(content_type))}</b>\n\n"
            "Отправь тему для поста одним сообщением.\n"
            "Пример: <code>Коротко объяснить, зачем нужен HTTP/3 и чем он полезен в мобильных сетях</code>\n\n"
            "Если передумал, отправь <code>отмена</code>."
        ),
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Канал", callback_data="control:channel")]]),
    )
    await callback.answer()


@router.message(ChannelContentStates.waiting_topic)
async def channel_topic_message(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message) or not _can_manage_channel(message):
        await _send_access_denied(message)
        return
    if _is_channel_cancel_text(message.text):
        await state.clear()
        await _handle_named_screen(message, "channel")
        return
    data = await state.get_data()
    if not data.get("channel_content_type"):
        await message.answer("Сначала выбери тип поста кнопками выше.")
        return
    await state.update_data(channel_topic_brief=(message.text or "").strip())
    await state.set_state(ChannelContentStates.waiting_schedule)
    default_slot = default_channel_scheduled_at()
    await message.answer(
        (
            "📅 <b>СЛОТ ПУБЛИКАЦИИ</b>\n\n"
            f"Ближайший слот по умолчанию: <b>{default_slot.strftime('%Y-%m-%d %H:%M')}</b>\n"
            "Выбери кнопку ниже или отправь дату вручную.\n"
            "Поддерживаемые форматы: <code>2026-04-01 12:00</code>, <code>01.04.2026 12:00</code>, <code>завтра 12:00</code>."
        ),
        parse_mode="HTML",
        reply_markup=_channel_schedule_keyboard(),
    )


@router.callback_query(F.data.startswith("control:channel:schedule:"))
async def channel_schedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    mode = callback.data.split(":")[3]
    if mode == "manual":
        await state.set_state(ChannelContentStates.waiting_schedule)
        await callback.message.answer(
            (
                "✍️ Отправь дату публикации текстом.\n"
                "Например: <code>2026-04-01 12:00</code> или <code>завтра 12:00</code>."
            ),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    scheduled_at = default_channel_scheduled_at()
    if mode == "tomorrow":
        scheduled_at = scheduled_at + timedelta(days=1)
    await state.update_data(channel_scheduled_at=scheduled_at.isoformat())
    await state.set_state(ChannelContentStates.waiting_cta_label)
    await callback.message.answer(
        (
            "🔘 <b>CTA-КНОПКА</b>\n\n"
            f"Отправь свой текст кнопки или пропусти шаг. По умолчанию будет <b>{escape(CHANNEL_DEFAULT_CTA_LABEL)}</b>."
        ),
        parse_mode="HTML",
        reply_markup=_channel_cta_keyboard(),
    )
    await callback.answer()


@router.message(ChannelContentStates.waiting_schedule)
async def channel_schedule_message(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message) or not _can_manage_channel(message):
        await _send_access_denied(message)
        return
    if _is_channel_cancel_text(message.text):
        await state.clear()
        await _handle_named_screen(message, "channel")
        return
    try:
        scheduled_at = parse_channel_schedule_input(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(channel_scheduled_at=scheduled_at.isoformat())
    await state.set_state(ChannelContentStates.waiting_cta_label)
    await message.answer(
        (
            "🔘 <b>CTA-КНОПКА</b>\n\n"
            f"Отправь свой текст кнопки или пропусти шаг. По умолчанию будет <b>{escape(CHANNEL_DEFAULT_CTA_LABEL)}</b>."
        ),
        parse_mode="HTML",
        reply_markup=_channel_cta_keyboard(),
    )


@router.callback_query(F.data == "control:channel:cta:skip")
async def channel_cta_skip_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    try:
        item = await _create_channel_item_from_state(state, cta_label=None)
        await _render_channel_item_callback(callback, item.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Тема добавлена")


@router.message(ChannelContentStates.waiting_cta_label)
async def channel_cta_message(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message) or not _can_manage_channel(message):
        await _send_access_denied(message)
        return
    if _is_channel_cancel_text(message.text):
        await state.clear()
        await _handle_named_screen(message, "channel")
        return
    cta_label = (message.text or "").strip() or None
    if cta_label and cta_label.lower() in {"пропустить", "skip"}:
        cta_label = None
    try:
        item = await _create_channel_item_from_state(state, cta_label=cta_label)
        await _render_channel_item_message(message, item.id)
    except ValueError as exc:
        await message.answer(str(exc))


@router.callback_query(F.data.startswith("control:channel:list:"))
async def channel_list_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    list_kind = callback.data.split(":")[3]
    text, keyboard = await build_channel_list_screen(list_kind)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:channel:stats")
async def channel_stats_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_channel_stats_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:channel:item:"))
async def channel_item_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    try:
        await _render_channel_item_callback(callback, item_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("control:channel:approve:"))
async def channel_approve_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    try:
        await approve_channel_content_item(item_id, callback.from_user.id)
        await _render_channel_item_callback(callback, item_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Черновик одобрен")


@router.callback_query(F.data.startswith("control:channel:reject:"))
async def channel_reject_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    try:
        await reject_channel_content_item(item_id)
        await _render_channel_item_callback(callback, item_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Элемент отклонён")


@router.callback_query(F.data.startswith("control:channel:retry:"))
async def channel_retry_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    try:
        await generate_channel_content_item(item_id)
        await _render_channel_item_callback(callback, item_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Черновик обновлён")


@router.callback_query(F.data.startswith("control:channel:publish:"))
async def channel_publish_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    try:
        await publish_channel_content_item(item_id)
        await _render_channel_item_callback(callback, item_id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Пост опубликован")


@router.callback_query(F.data.startswith("control:channel:edit:"))
async def channel_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_allowed(callback) or not _can_manage_channel(callback):
        await _send_access_denied(callback)
        return
    item_id = int(callback.data.split(":")[3])
    item = await get_channel_content_focus(item_id)
    if item is None:
        await callback.answer("Элемент канала не найден.", show_alert=True)
        return
    await state.set_state(ChannelContentStates.waiting_edit_body)
    await state.update_data(channel_edit_item_id=item_id)
    await callback.message.answer(
        (
            f"✏️ Редактирование post item <b>#{item_id}</b>\n\n"
            "Отправь новый HTML-текст поста одним сообщением.\n"
            "Если передумал, отправь <code>отмена</code>."
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ChannelContentStates.waiting_edit_body)
async def channel_edit_body_message(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message) or not _can_manage_channel(message):
        await _send_access_denied(message)
        return
    if _is_channel_cancel_text(message.text):
        await state.clear()
        await _handle_named_screen(message, "channel")
        return
    data = await state.get_data()
    item_id = int(data.get("channel_edit_item_id") or 0)
    body_html = getattr(message, "html_text", None) or (message.text or "")
    try:
        await update_channel_content_body(item_id, body_html)
        await state.clear()
        await _render_channel_item_message(message, item_id)
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(F.forward_origin)
@router.message(F.forward_from_chat)
async def channel_post_forward_handler(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message):
        await _send_access_denied(message)
        return
    role = _role(message)
    if not control_role_allows(role, CONTROL_ROLE_ADMIN):
        await _send_access_denied(message)
        return
    target = extract_channel_post_target(message)
    if target is None:
        await message.answer("Нужен именно пересланный пост из канала Telegram.")
        return
    await state.set_state(ChannelPostStates.waiting_buttons)
    await state.update_data(
        channel_post_chat_id=target.chat_id,
        channel_post_message_id=target.message_id,
        channel_post_chat_title=target.chat_title or "",
    )
    channel_label = escape(target.chat_title or str(target.chat_id))
    await message.answer(
        (
            f"Пост из канала <b>{channel_label}</b> принят.\n\n"
            f"{_channel_post_help_text()}"
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "control:dashboard")
@router.callback_query(F.data == "control:status")
async def status_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_status_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:nodes")
async def nodes_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_nodes_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:nodes:"))
async def nodes_filtered_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    filter_state = callback.data.split(":")[2]
    text, keyboard = await build_nodes_screen(filter_state)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:payments")
async def payments_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_payments_screen_for(callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:users")
async def users_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_users_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:support")
async def support_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_support_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.in_({"control:support:new", "control:support:in_progress", "control:support:mine", "control:support:closed"}))
async def support_filter_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    filter_mode = callback.data.split(":")[2]
    text, keyboard = await build_support_screen(filter_mode)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:problems")
async def problems_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_problems_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:alerts")
async def alerts_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_alerts_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:alerts:"))
async def alerts_filter_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    suffix = callback.data.split(":")[2]
    if suffix == "history":
        text, keyboard = await build_alerts_screen(history=True)
    else:
        text, keyboard = await build_alerts_screen(filter_severity=suffix)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:notifications")
@router.callback_query(F.data == "control:settings")
@router.callback_query(F.data == "control:settings:self")
async def settings_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_settings_screen(callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:login_codes")
async def login_codes_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_login_codes_screen(callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:login_codes:terminate")
async def login_codes_terminate_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    await terminate_all_dashboard_sessions()
    text, keyboard = await build_login_codes_screen(callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Сессии завершены")


@router.callback_query(F.data == "control:events")
async def events_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_last_events_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:events:"))
async def events_filter_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    suffix = callback.data.split(":")[2]
    category = None
    severity = None
    if suffix in {"CRITICAL", "WARNING", "INFO", "critical"}:
        severity = suffix.upper()
    if suffix in {"users", "access", "nodes", "payments", "support", "panel_auth", "errors", "system"}:
        category = suffix
    text, keyboard = await build_last_events_screen(category, severity)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:campaign:open:"))
async def campaign_open_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    campaign_id = int(callback.data.split(":")[3])
    text, keyboard = await build_campaign_focus_screen(campaign_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:settings:admin:"))
async def settings_admin_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    target_telegram_id = int(callback.data.split(":")[3])
    text, keyboard = await build_settings_screen(callback.from_user.id, target_telegram_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:settings:toggle:"))
async def settings_toggle_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    _, _, _, target_id, category = callback.data.split(":", 4)
    target_telegram_id = int(target_id)
    if callback.from_user.id != target_telegram_id and not _is_owner(callback):
        await _send_access_denied(callback)
        return
    await toggle_notification_preference(target_telegram_id, category)
    text, keyboard = await build_settings_screen(callback.from_user.id, target_telegram_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Настройка обновлена")


@router.callback_query(F.data.startswith("control:settings:locked:"))
async def settings_locked_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    _, _, _, target_id, category = callback.data.split(":", 4)
    target_telegram_id = int(target_id)
    if callback.from_user.id != target_telegram_id and not _is_owner(callback):
        await _send_access_denied(callback)
        return
    role = control_role_for_telegram_id(target_telegram_id)
    text, keyboard = await build_settings_screen(callback.from_user.id, target_telegram_id)
    await _render_callback(callback, text, keyboard)
    message = "Это обязательное уведомление для роли"
    if not is_notification_category_mandatory(role, category):
        message = "Категория недоступна для изменения"
    await callback.answer(message)


@router.callback_query(F.data == "control:broadcast")
async def broadcast_root_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_broadcast_root_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:admin")
async def broadcast_admin_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_admin_push_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:users")
async def broadcast_users_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_user_broadcast_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:triggers")
async def broadcast_triggers_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_trigger_center_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:stats")
async def broadcast_stats_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    text, keyboard = await build_broadcast_stats_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:templates")
@router.callback_query(F.data.startswith("control:broadcast:templates:"))
async def broadcast_templates_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    parts = callback.data.split(":")
    scope = None
    if len(parts) == 4:
        scope = parts[3]
    text, keyboard = await build_templates_screen(scope)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:admin:compose")
async def compose_admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    await state.set_state(ComposeStates.waiting_message)
    await state.update_data(scope=CAMPAIGN_SCOPE_ADMIN, audience_key=None, buttons=[], priority_label="medium")
    await callback.message.answer("Отправьте текст push-уведомления админам следующим сообщением.")
    await callback.answer()


@router.callback_query(F.data == "control:broadcast:admin:test")
async def compose_admin_test_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    await state.set_state(ComposeStates.waiting_message)
    await state.update_data(scope=CAMPAIGN_SCOPE_ADMIN, audience_key=None, buttons=[], priority_label="medium")
    await callback.message.answer("Отправьте текст тестового push-уведомления. Оно уйдёт только вам.")
    await state.update_data(test_only=True)
    await callback.answer()


@router.callback_query(F.data.startswith("control:broadcast:segment:"))
async def compose_user_segment_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    audience_key = callback.data.split(":")[3]
    await state.set_state(ComposeStates.waiting_message)
    await state.update_data(scope=CAMPAIGN_SCOPE_USER, audience_key=audience_key, buttons=[], priority_label="medium")
    await callback.message.answer(f"Сегмент <b>{audience_key}</b> выбран. Теперь отправьте текст рассылки следующим сообщением.", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("control:trigger:open:"))
async def trigger_open_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    rule_id = int(callback.data.split(":")[3])
    text, keyboard = await build_trigger_rule_screen(rule_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:trigger:toggle:"))
async def trigger_toggle_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    rule_id = int(callback.data.split(":")[3])
    await toggle_trigger_rule(rule_id)
    text, keyboard = await build_trigger_rule_screen(rule_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Триггер обновлён")


@router.callback_query(F.data.startswith("control:trigger:edit:"))
async def trigger_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    rule_id = int(callback.data.split(":")[3])
    await state.set_state(ComposeStates.waiting_trigger_text)
    await state.update_data(trigger_rule_id=rule_id)
    await callback.message.answer("Отправьте новый текст для этого trigger-сообщения следующим сообщением.")
    await callback.answer()


@router.callback_query(F.data.startswith("control:trigger:test:"))
async def trigger_test_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    rule_id = int(callback.data.split(":")[3])
    rule = await get_trigger_rule(rule_id)
    if rule is None:
        await callback.answer("Триггер не найден", show_alert=True)
        return
    campaign = await create_broadcast_campaign(
        scope=CAMPAIGN_SCOPE_TRIGGER,
        name=rule.title,
        audience_key="all",
        message_body=rule.template_body,
        buttons=serialize_template_buttons(rule),
        metadata={"trigger_rule_id": rule.id, "test": True},
        created_by_telegram_id=callback.from_user.id,
        trigger_rule_id=rule.id,
        is_test=True,
        status="queued",
    )
    await dispatch_campaign(campaign.id, test_telegram_id=callback.from_user.id)
    await callback.answer("Тест отправлен")


@router.callback_query(F.data.startswith("control:template:open:"))
async def template_open_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    template_id = int(callback.data.split(":")[3])
    text, keyboard = await build_template_focus_screen(template_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:template:use:"))
async def template_use_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    template_id = int(callback.data.split(":")[3])
    template = await get_message_template(template_id)
    if template is None:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    current = await state.get_data()
    scope = current.get("scope") or template.scope
    await state.update_data(
        scope=scope,
        audience_key=current.get("audience_key"),
        message_body=template.body,
        buttons=serialize_template_buttons(template),
        template_name=template.name,
    )
    await _show_compose_preview(callback, state)
    await callback.answer("Шаблон применён")


@router.callback_query(F.data.startswith("control:template:edit:"))
async def template_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    template_id = int(callback.data.split(":")[3])
    template = await get_message_template(template_id)
    if template is None:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    await state.set_state(ComposeStates.waiting_message)
    await state.update_data(
        template_edit_id=template.id,
        scope=template.scope,
        buttons=serialize_template_buttons(template),
        template_name=template.name,
    )
    await callback.message.answer(
        f"Отправьте новый текст для шаблона <b>{template.name}</b> следующим сообщением.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("control:template:delete:"))
async def template_delete_callback(callback: CallbackQuery) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    template_id = int(callback.data.split(":")[3])
    await delete_message_template(template_id)
    text, keyboard = await build_templates_screen()
    await _render_callback(callback, text, keyboard)
    await callback.answer("Шаблон удалён")


@router.callback_query(F.data.startswith("control:template:new:"))
async def template_new_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    scope = callback.data.split(":")[3]
    await state.update_data(scope=scope if scope != "all" else CAMPAIGN_SCOPE_USER, buttons=[])
    await state.set_state(ComposeStates.waiting_template_name)
    await callback.message.answer("Сначала отправьте название нового шаблона следующим сообщением.")
    await callback.answer()


@router.callback_query(F.data.startswith("control:payment:open:"))
async def payment_open_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    record_id = int(callback.data.split(":")[3])
    text, keyboard = await build_payment_focus(record_id, callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:payment:confirm:"))
async def payment_confirm_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    record_id = int(callback.data.split(":")[3])
    await confirm_manual_payment(
        record_id,
        reviewer_actor_id=f"control_bot:{callback.from_user.id}",
        reviewer_actor_name=callback.from_user.full_name,
    )
    text, keyboard = await build_payment_focus(record_id, callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Платёж подтверждён")


@router.callback_query(F.data.startswith("control:payment:reject:"))
async def payment_reject_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    record_id = int(callback.data.split(":")[3])
    await reject_manual_payment(
        record_id,
        reviewer_actor_id=f"control_bot:{callback.from_user.id}",
        reviewer_actor_name=callback.from_user.full_name,
        reason="Отклонено администратором",
    )
    text, keyboard = await build_payment_focus(record_id, callback.from_user.id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Платёж отклонён")


@router.callback_query(F.data.startswith("control:user:open:"))
async def user_open_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    user_id = int(callback.data.split(":")[3])
    text, keyboard = await build_user_focus(user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:user:noop:"))
async def user_noop_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    await callback.answer("Это действие сейчас недоступно для этого пользователя", show_alert=True)


@router.callback_query(F.data.startswith("control:user:sync:"))
@router.callback_query(F.data.startswith("control:user:repair:"))
@router.callback_query(F.data.startswith("control:user:extend30:"))
@router.callback_query(F.data.startswith("control:user:trial:"))
@router.callback_query(F.data.startswith("control:user:clear:"))
@router.callback_query(F.data.startswith("control:user:block:"))
@router.callback_query(F.data.startswith("control:user:unblock:"))
async def user_action_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Неизвестное действие", show_alert=True)
        return
    action = parts[2]
    if action in {"open", "noop"}:
        return
    user_id = int(parts[3])
    role = _role(callback)
    if action in {"repair"} and not control_role_allows(role, CONTROL_ROLE_ADMIN):
        await _send_access_denied(callback)
        return
    if action in {"sync", "extend30", "trial", "clear", "block", "unblock"} and not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return

    admin = await _dashboard_admin_for_actor(callback.from_user.id)
    if admin is None:
        await callback.answer("Telegram ID не привязан к dashboard-админу", show_alert=True)
        return

    try:
        if action == "sync":
            result = await sync_user_access_state(user_id, admin, None)
            notice = "Sync выполнен" if not result.get("sync_failed") else "Sync завершился с ошибкой"
        elif action == "repair":
            result = await deep_repair_user_access(user_id, admin, None)
            notice = "Deep repair выполнен" if not result.get("sync_failed") else "Deep repair не довёл пользователя до рабочего состояния"
        elif action == "extend30":
            result = await extend_subscription_for_user(user_id, 30, admin, None, source="control_bot_manual")
            notice = "Доступ продлён на 30 дней" if not result.get("sync_failed") else "Подписка продлена, но sync завершился с ошибкой"
        elif action == "trial":
            result = await grant_trial_to_user(user_id, admin, None)
            notice = "Пробный доступ выдан" if not result.get("sync_failed") else "Trial выдан, но sync завершился с ошибкой"
        elif action == "clear":
            result = await remove_user_tariff(user_id, admin, None)
            notice = "Доступ снят" if not result.get("sync_failed") else "Тариф снят, но часть устройств требует ручной проверки"
        elif action == "block":
            result = await set_user_block_state(user_id, True, admin, None)
            notice = "Пользователь заблокирован" if not result.get("sync_failed") else "Пользователь заблокирован, но часть remote-state требует проверки"
        elif action == "unblock":
            result = await set_user_block_state(user_id, False, admin, None)
            notice = "Пользователь разблокирован" if not result.get("sync_failed") else "Пользователь разблокирован, но часть remote-state требует проверки"
        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    text, keyboard = await build_user_focus(user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer(notice)


@router.callback_query(F.data.startswith("control:support:open:"))
async def support_open_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    ticket_user_id = int(callback.data.split(":")[3])
    text, keyboard = await build_support_focus(ticket_user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:support:assign:"))
async def support_assign_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    admin = await _dashboard_admin_for_actor(callback.from_user.id)
    if admin is None:
        await callback.answer("Telegram ID не привязан к dashboard-админу", show_alert=True)
        return
    ticket_user_id = int(callback.data.split(":")[3])
    try:
        await assign_support_ticket_dashboard(ticket_user_id, admin, None)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    text, keyboard = await build_support_focus(ticket_user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Обращение закреплено за тобой")


@router.callback_query(F.data.startswith("control:support:reply:"))
async def support_reply_callback(callback: CallbackQuery, state: FSMContext) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    ticket_user_id = int(callback.data.split(":")[3])
    await state.set_state(SupportReplyStates.waiting_reply)
    await state.update_data(ticket_user_id=ticket_user_id, source_message_id=callback.message.message_id)
    await callback.message.answer(
        "Отправьте следующий текст сообщением в этот чат. Он уйдёт пользователю через support bot и сохранится в истории.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("control:support:transfer:"))
async def support_transfer_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    ticket_user_id = int(callback.data.split(":")[3])
    admin_choices = await get_support_admin_choices()
    rows: list[list[InlineKeyboardButton]] = []
    for choice in admin_choices[:8]:
        if int(choice["telegram_id"]) == int(callback.from_user.id):
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"👤 {choice['display_name'][:18]}",
                    callback_data=f"control:support:transferto:{ticket_user_id}:{int(choice['telegram_id'])}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"control:support:open:{ticket_user_id}")])
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("control:support:transferto:"))
async def support_transfer_to_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    admin = await _dashboard_admin_for_actor(callback.from_user.id)
    if admin is None:
        await callback.answer("Telegram ID не привязан к dashboard-админу", show_alert=True)
        return
    parts = callback.data.split(":")
    ticket_user_id = int(parts[3])
    target_admin_id = int(parts[4])
    try:
        await transfer_support_ticket_dashboard(ticket_user_id, target_admin_id, admin, None)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    text, keyboard = await build_support_focus(ticket_user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Обращение передано")


@router.callback_query(F.data.startswith("control:support:close:"))
async def support_close_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await _send_access_denied(callback)
        return
    admin = await _dashboard_admin_for_actor(callback.from_user.id)
    if admin is None:
        await callback.answer("Telegram ID не привязан к dashboard-админу", show_alert=True)
        return
    ticket_user_id = int(callback.data.split(":")[3])
    try:
        result = await close_support_ticket(ticket_user_id, admin, None)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    text, keyboard = await build_support_focus(ticket_user_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer("Обращение закрыто" if result.get("user_notified") else "Обращение закрыто, уведомление не подтверждено")


@router.callback_query(F.data.startswith("control:node:open:"))
async def node_open_callback(callback: CallbackQuery) -> None:
    if not _is_allowed(callback):
        await _send_access_denied(callback)
        return
    server_id = int(callback.data.split(":")[3])
    text, keyboard = await build_node_focus(server_id)
    await _render_callback(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("control:node:action:"))
async def node_action_callback(callback: CallbackQuery) -> None:
    role = _role(callback)
    if not control_role_allows(role, CONTROL_ROLE_ADMIN):
        await _send_access_denied(callback)
        return
    admin = await _dashboard_admin_for_actor(callback.from_user.id)
    if admin is None:
        await callback.answer("Telegram ID не привязан к dashboard-админу", show_alert=True)
        return
    parts = callback.data.split(":")
    server_id = int(parts[3])
    action = parts[4]
    effective_action = "refresh" if action in {"refresh", "resync"} else action
    try:
        await run_server_action(server_id, effective_action, admin, None)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    text, keyboard = await build_node_focus(server_id)
    await _render_callback(callback, text, keyboard)
    if action in {"refresh", "resync"}:
        await callback.answer("Состояние ноды обновлено")
    else:
        await callback.answer(f"Действие выполнено: {action}")


@router.callback_query(F.data.startswith("control:compose:cta:"))
async def compose_cta_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    action = callback.data.split(":")[3]
    await state.update_data(buttons=[{"action": action, "label": CTA_ACTIONS.get(action, action)}])
    await _show_compose_preview(callback, state)
    await callback.answer("CTA обновлён")


@router.callback_query(F.data.startswith("control:compose:priority:"))
async def compose_priority_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    priority = callback.data.split(":")[3]
    await state.update_data(priority_label=priority)
    await _show_compose_preview(callback, state)
    await callback.answer("Приоритет обновлён")


@router.callback_query(F.data == "control:compose:schedule")
async def compose_schedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    await state.set_state(ComposeStates.waiting_schedule)
    await callback.message.answer("Отправьте дату и время в формате <code>YYYY-MM-DD HH:MM</code> по часовому поясу сервера.", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "control:compose:save_template")
async def compose_save_template_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Черновик не найден", show_alert=True)
        return
    await state.set_state(ComposeStates.waiting_template_name)
    await callback.message.answer("Отправьте название шаблона следующим сообщением.")
    await callback.answer()


@router.callback_query(F.data == "control:compose:test")
async def compose_test_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    data = await state.get_data()
    if not data or not data.get("message_body"):
        await callback.answer("Сначала отправьте текст сообщения", show_alert=True)
        return
    campaign_id, _ = await _send_campaign_from_state(callback.from_user.id, state, test=True)
    await callback.message.answer(f"Тестовая отправка выполнена. Кампания #{campaign_id}.", parse_mode="HTML", reply_markup=control_secondary_keyboard(_role(callback)))
    await callback.answer()


@router.callback_query(F.data == "control:compose:send")
async def compose_send_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback):
        await _send_access_denied(callback)
        return
    data = await state.get_data()
    if not data or not data.get("message_body"):
        await callback.answer("Сначала отправьте текст сообщения", show_alert=True)
        return
    campaign_id, status = await _send_campaign_from_state(callback.from_user.id, state, test=False)
    await callback.message.answer(
        f"📢 Кампания #{campaign_id} создана. Статус: <b>{status}</b>.",
        parse_mode="HTML",
        reply_markup=control_secondary_keyboard(_role(callback)),
    )
    await callback.answer("Кампания создана")


@router.message(ComposeStates.waiting_message)
async def compose_message_handler(message: Message, state: FSMContext) -> None:
    if not _is_owner(message):
        await _send_access_denied(message)
        return
    data = await state.get_data()
    template_edit_id = data.get("template_edit_id")
    if template_edit_id is not None:
        updated = await save_message_template(
            scope=data.get("scope") or CAMPAIGN_SCOPE_USER,
            name=data.get("template_name") or f"Template {template_edit_id}",
            body=message.html_text or message.text or "",
            buttons=data.get("buttons") or [],
            created_by_telegram_id=message.from_user.id,
            template_id=int(template_edit_id),
        )
        await state.clear()
        text, keyboard = await build_template_focus_screen(updated.id)
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return
    await state.update_data(
        message_body=message.html_text or message.text or "",
        schedule_label=data.get("schedule_label") or "сейчас",
        test_only=False,
    )
    await _show_compose_preview(message, state)


@router.message(ComposeStates.waiting_schedule)
async def compose_schedule_message_handler(message: Message, state: FSMContext) -> None:
    if not _is_owner(message):
        await _send_access_denied(message)
        return
    raw = (message.text or "").strip()
    try:
        scheduled_at = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Не удалось разобрать дату. Используйте формат <code>YYYY-MM-DD HH:MM</code>.", parse_mode="HTML")
        return
    await state.set_state(None)
    await state.update_data(scheduled_at=scheduled_at, schedule_label=scheduled_at.strftime("%Y-%m-%d %H:%M"))
    await _show_compose_preview(message, state)


@router.message(ComposeStates.waiting_template_name)
async def template_name_handler(message: Message, state: FSMContext) -> None:
    if not _is_owner(message):
        await _send_access_denied(message)
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название шаблона не должно быть пустым.")
        return
    data = await state.get_data()
    if data.get("message_body"):
        await save_message_template(
            scope=data.get("scope") or CAMPAIGN_SCOPE_USER,
            name=name,
            body=data.get("message_body") or "",
            buttons=data.get("buttons") or [],
            created_by_telegram_id=message.from_user.id,
        )
        await state.set_state(None)
        await message.answer("✅ Шаблон сохранён.", reply_markup=control_menu_keyboard(_role(message)))
        return
    await state.update_data(template_name=name)
    await state.set_state(ComposeStates.waiting_message)
    await message.answer("Теперь отправьте текст шаблона следующим сообщением.")


@router.message(ComposeStates.waiting_trigger_text)
async def trigger_text_handler(message: Message, state: FSMContext) -> None:
    if not _is_owner(message):
        await _send_access_denied(message)
        return
    data = await state.get_data()
    rule_id = data.get("trigger_rule_id")
    if rule_id is None:
        await state.clear()
        await message.answer("Триггер не найден.")
        return
    await update_trigger_rule(rule_id, template_body=message.html_text or message.text or "")
    await state.clear()
    text, keyboard = await build_trigger_rule_screen(int(rule_id))
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(ChannelPostStates.waiting_buttons)
async def channel_post_buttons_input_handler(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message):
        await state.clear()
        await _send_access_denied(message)
        return
    role = _role(message)
    if not control_role_allows(role, CONTROL_ROLE_ADMIN):
        await state.clear()
        await _send_access_denied(message)
        return

    target = extract_channel_post_target(message)
    if target is not None:
        await state.update_data(
            channel_post_chat_id=target.chat_id,
            channel_post_message_id=target.message_id,
            channel_post_chat_title=target.chat_title or "",
        )
        channel_label = escape(target.chat_title or str(target.chat_id))
        await message.answer(
            (
                f"Переключил редактирование на новый пост из канала <b>{channel_label}</b>.\n\n"
                f"{_channel_post_help_text()}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    data = await state.get_data()
    chat_id = data.get("channel_post_chat_id")
    message_id = data.get("channel_post_message_id")
    chat_title = data.get("channel_post_chat_title") or ""
    if chat_id is None or message_id is None:
        await state.clear()
        await message.answer("Не удалось определить пост канала. Перешлите его ещё раз.")
        return

    raw = (message.text or message.caption or "").strip()
    if not raw:
        await message.answer(
            "Нужно отправить список кнопок текстом. Пример: <code>Подключиться | https://t.me/amonora_bot</code>",
            parse_mode="HTML",
        )
        return

    lowered = raw.lower()
    if lowered in {"отмена", "/cancel", "cancel"}:
        await state.clear()
        await message.answer("Ок, редактирование поста отменено.", reply_markup=control_secondary_keyboard(role))
        return

    reply_markup = None
    button_count = 0
    if lowered not in {"очистить", "убрать", "remove"}:
        try:
            reply_markup, button_count = parse_channel_post_buttons(raw)
        except ValueError as exc:
            await message.answer(
                (
                    f"Не удалось разобрать кнопки: <b>{escape(str(exc))}</b>\n\n"
                    f"{_channel_post_help_text()}"
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return

    try:
        await message.bot.edit_message_reply_markup(
            chat_id=int(chat_id),
            message_id=int(message_id),
            reply_markup=reply_markup,
        )
    except TelegramForbiddenError:
        await message.answer(
            "Telegram не дал изменить пост. Проверьте, что `@amonora_control_bot` добавлен администратором канала.",
            parse_mode="HTML",
        )
        return
    except TelegramBadRequest as exc:
        await message.answer(
            (
                f"Не удалось обновить пост: <b>{escape(str(exc))}</b>\n\n"
                "Обычно это значит, что у бота нет права <code>can_edit_messages</code> "
                "или был переслан не тот пост."
            ),
            parse_mode="HTML",
        )
        return

    await state.clear()
    channel_label = escape(chat_title or str(chat_id))
    if reply_markup is None:
        await message.answer(
            f"✅ Кнопки у поста в канале <b>{channel_label}</b> удалены.",
            parse_mode="HTML",
            reply_markup=control_secondary_keyboard(role),
        )
        return

    await message.answer(
        f"✅ Кнопки обновлены у поста в канале <b>{channel_label}</b>. Всего кнопок: <b>{button_count}</b>.",
        parse_mode="HTML",
        reply_markup=control_secondary_keyboard(role),
    )


@router.message(SupportReplyStates.waiting_reply)
async def support_reply_input_handler(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message):
        await state.clear()
        await _send_access_denied(message)
        return
    role = _role(message)
    if not control_role_allows(role, CONTROL_ROLE_OPERATOR):
        await state.clear()
        await _send_access_denied(message)
        return

    data = await state.get_data()
    ticket_user_id = data.get("ticket_user_id")
    if not ticket_user_id:
        await state.clear()
        await message.answer("Не удалось определить обращение.")
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        await message.answer("Нужно отправить текст ответа.")
        return

    admin = await _dashboard_admin_for_actor(message.from_user.id)
    if admin is None:
        await state.clear()
        await message.answer("Telegram ID не привязан к dashboard-админу.")
        return

    try:
        await send_support_reply(int(ticket_user_id), text, admin, None)
    except Exception as exc:
        await state.clear()
        await message.answer(f"Не удалось отправить ответ: {exc}")
        return

    screen_text, keyboard = await build_support_focus(int(ticket_user_id))
    await message.answer("✅ Ответ отправлен пользователю.")
    await message.answer(screen_text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()
