from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, Message

from backend.core.analytics import (
    EVENT_CHANNEL_MEMBERSHIP_CONFIRMED,
    emit_bot_start_event,
    safe_emit_analytics_event,
    safe_upsert_user_attribution,
)
from bot.config import config
from bot.db import (
    activate_trial,
    bind_referrer_by_token,
    count_user_account_devices,
    get_or_create_user,
    get_user_balance_summary,
    get_user_by_telegram_id,
    resume_trial_after_channel_resubscribe,
)
from bot.keyboards.home import home_keyboard_for_user
from bot.keyboards.main_menu import main_menu_for_user
from bot.keyboards.tariffs import balance_topup_amounts_keyboard, tariffs_keyboard
from bot.public_subscription import (
    build_public_subscription_feed_url,
    build_public_subscription_happ_wrapper_url,
    build_public_subscription_page_url,
    get_or_create_public_subscription_page_url_for_user,
)
from bot.user_notifications import send_user_message
from bot.payment_flow import sync_user_vpn_access_with_single_retry
from bot.utils.access import (
    get_access_expires_at_from_user,
    has_active_access_from_user,
    has_trial_window_from_user,
    trial_is_paused_by_channel_from_user,
)
from bot.utils.subscription import is_user_subscribed
from bot.utils.texts import (
    CHANNEL_URL,
    SUPPORT_URL,
    TERMS_URL,
    access_expired_text,
    active_access_text,
    blocked_user_action_text,
    balance_topup_intro_text,
    home_text,
    referral_registered_text,
    start_new_user_trial_activated_text,
    start_trial_subscription_required_text,
    trial_subscription_paused_text,
    trial_activated_text,
)
from control_bot.channel_content import parse_channel_post_start_token, register_channel_post_touch
from control_bot.storage import mark_delivery_clicked


router = Router()
TRIAL_SUBSCRIPTION_CONFIRMED_CALLBACK = "start:trial:subscribed"


def _start_offer_keyboard(
    include_channel: bool = False,
    include_subscription_check: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if include_channel:
        rows.append([InlineKeyboardButton(text="📡 Подписаться на канал", url=CHANNEL_URL)])
        if include_subscription_check:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ Подписался",
                        callback_data=TRIAL_SUBSCRIPTION_CONFIRMED_CALLBACK,
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="📜 Пользовательское соглашение", url=TERMS_URL)])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


async def _send_home(message: Message, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(telegram_id)
    if user is None:
        await message.answer("Пользователь не найден. Нажми /start")
        return

    devices_count = await count_user_account_devices(user.id)
    await message.answer(
        home_text(user, devices_count),
        reply_markup=home_keyboard_for_user(user),
        parse_mode="HTML",
    )


async def _restore_main_menu(message: Message, telegram_id: int) -> bool:
    user = await get_user_by_telegram_id(telegram_id)
    if user is None:
        await message.answer("Пользователь не найден. Нажми /start")
        return False

    await message.answer(
        "⬇️ Главное меню снова закреплено снизу.",
        reply_markup=main_menu_for_user(user),
        parse_mode="HTML",
    )
    return True


async def _emit_channel_membership_confirmed(user_id: int, telegram_id: int) -> None:
    await safe_emit_analytics_event(
        event_name=EVENT_CHANNEL_MEMBERSHIP_CONFIRMED,
        user_id=int(user_id),
        telegram_id=int(telegram_id),
        dedupe_key=f"channel-membership-confirmed:{int(user_id)}",
        payload={"entrypoint": "start_flow"},
    )


async def _handle_start_flow(
    message_target: Message,
    *,
    bot: Bot,
    telegram_user,
    referral_token: str | None = None,
    channel_post_token: str | None = None,
) -> None:
    user, is_created = await get_or_create_user(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        referred_by_telegram_id=None,
        skip_initial_analytics_attribution=bool(channel_post_token),
    )
    source_type = "organic_bot"
    source_key = "organic_bot"
    channel_item_id = None
    if channel_post_token:
        touch = await register_channel_post_touch(
            channel_post_token,
            user_id=user.id,
            telegram_id=telegram_user.id,
        )
        if touch is not None:
            source_type = "channel_post"
            raw_source_key = getattr(touch, "source_key", None)
            if raw_source_key is None and isinstance(touch, dict):
                raw_source_key = touch.get("source_key")
            source_key = str(raw_source_key or channel_post_token).strip().lower() or channel_post_token
            raw_channel_item_id = getattr(touch, "item_id", None)
            if raw_channel_item_id is None and isinstance(touch, dict):
                raw_channel_item_id = touch.get("item_id")
            if isinstance(raw_channel_item_id, (str, int)):
                channel_item_id = int(raw_channel_item_id) or None
    else:
        await safe_upsert_user_attribution(
            user_id=int(user.id),
            telegram_id=int(telegram_user.id),
            source_type="organic_bot",
            source_key="organic_bot",
            seen_at=getattr(user, "created_at", None),
        )
    await emit_bot_start_event(
        user_id=int(user.id),
        telegram_id=int(telegram_user.id),
        source_type=source_type,
        source_key=source_key,
        channel_item_id=channel_item_id,
    )
    referral_binding = await bind_referrer_by_token(user.id, referral_token)
    if referral_binding.get("bound") and referral_binding.get("referrer_telegram_id"):
        await send_user_message(int(referral_binding["referrer_telegram_id"]), referral_registered_text())

    if getattr(user, "is_blocked", False):
        await message_target.answer(
            blocked_user_action_text(),
            reply_markup=main_menu_for_user(user),
            parse_mode="HTML",
        )
        await _send_home(message_target, telegram_user.id)
        return

    if trial_is_paused_by_channel_from_user(user):
        if config.channel_id and not await is_user_subscribed(bot, config.channel_id, telegram_user.id):
            expires_at = user.trial_expires_at.strftime("%Y-%m-%d %H:%M:%S") if user.trial_expires_at else "—"
            await message_target.answer(
                trial_subscription_paused_text(telegram_user.first_name, expires_at),
                reply_markup=_start_offer_keyboard(
                    include_channel=True,
                    include_subscription_check=True,
                ),
                parse_mode="HTML",
            )
            return
        await _emit_channel_membership_confirmed(int(user.id), int(telegram_user.id))
        resumed_user = await resume_trial_after_channel_resubscribe(user.id)
        if resumed_user is not None:
            user = resumed_user
            expires_at = get_access_expires_at_from_user(user)
            if expires_at is not None:
                await sync_user_vpn_access_with_single_retry(user.id, expires_at)

    if has_active_access_from_user(user):
        expires_at = get_access_expires_at_from_user(user)
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else "—"
        await message_target.answer(
            active_access_text(telegram_user.first_name, expires_text),
            reply_markup=main_menu_for_user(user),
            parse_mode="HTML",
        )
        await _send_home(message_target, telegram_user.id)
        return

    if user.trial_used and has_trial_window_from_user(user):
        expires_at = user.trial_expires_at.strftime("%Y-%m-%d %H:%M:%S") if user.trial_expires_at else "—"
        await message_target.answer(
            trial_subscription_paused_text(telegram_user.first_name, expires_at),
            reply_markup=_start_offer_keyboard(
                include_channel=True,
                include_subscription_check=True,
            ),
            parse_mode="HTML",
        )
        return

    if not user.trial_used:
        if config.channel_id and not await is_user_subscribed(bot, config.channel_id, telegram_user.id):
            await message_target.answer(
                start_trial_subscription_required_text(telegram_user.first_name),
                reply_markup=_start_offer_keyboard(
                    include_channel=True,
                    include_subscription_check=True,
                ),
                parse_mode="HTML",
            )
            return
        if config.channel_id:
            await _emit_channel_membership_confirmed(int(user.id), int(telegram_user.id))
        updated_user = await activate_trial(user.id)
        if updated_user is not None and updated_user.trial_expires_at is not None:
            expires_at = updated_user.trial_expires_at.strftime("%Y-%m-%d %H:%M:%S")
            if is_created:
                await message_target.answer(
                    start_new_user_trial_activated_text(telegram_user.first_name, expires_at),
                    reply_markup=_start_offer_keyboard(include_channel=True),
                    parse_mode="HTML",
                )
                await _send_home(message_target, telegram_user.id)
                return
            await message_target.answer(
                trial_activated_text(telegram_user.first_name, expires_at),
                reply_markup=main_menu_for_user(updated_user),
                parse_mode="HTML",
            )
            await _send_home(message_target, telegram_user.id)
            return

    await message_target.answer(
        access_expired_text(),
        reply_markup=tariffs_keyboard(),
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    referral_token = None
    channel_post_token = None
    if command and command.args:
        if command.args.startswith("ref_"):
            referral_token = command.args.split("_", 1)[1].strip() or None
        else:
            channel_post_token = parse_channel_post_start_token(command.args)

    await _handle_start_flow(
        message,
        bot=bot,
        telegram_user=message.from_user,
        referral_token=referral_token,
        channel_post_token=channel_post_token,
    )


@router.message(Command("menu"))
@router.message(F.text == "👤 Личный кабинет")
@router.message(F.text == "Кабинет")
async def menu_handler(message: Message) -> None:
    restored = await _restore_main_menu(message, message.from_user.id)
    if not restored:
        return
    await _send_home(message, message.from_user.id)


@router.callback_query(F.data == "home:cabinet")
async def home_cabinet_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    devices_count = await count_user_account_devices(user.id)
    await callback.message.edit_text(
        home_text(user, devices_count),
        parse_mode="HTML",
        reply_markup=home_keyboard_for_user(user),
    )
    await callback.answer()


@router.callback_query(F.data == "home:devices")
async def home_devices_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    from bot.handlers.devices import _show_devices_list

    await _show_devices_list(callback.message, user)
    await callback.answer()


@router.callback_query(F.data == "home:tariffs")
async def home_tariffs_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is not None and getattr(user, "is_blocked", False):
        await callback.answer("Оплата недоступна: доступ заблокирован.", show_alert=True)
        return
    await callback.message.edit_text(
        "💳 Открой один из тарифов ниже.",
        parse_mode="HTML",
        reply_markup=tariffs_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "home:balance")
async def home_balance_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return
    if getattr(user, "is_blocked", False):
        await callback.answer("Пополнение недоступно: доступ заблокирован.", show_alert=True)
        return

    balance = await get_user_balance_summary(user.id)
    await callback.message.edit_text(
        balance_topup_intro_text(
            balance_rub=balance["balance_rub"],
            balance_available_rub=balance["balance_available_rub"],
        ),
        parse_mode="HTML",
        reply_markup=balance_topup_amounts_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "home:subscription_page")
async def home_subscription_page_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    page_url = await get_or_create_public_subscription_page_url_for_user(int(user.id))
    token = page_url.rsplit("/", 1)[-1]
    page_url = build_public_subscription_page_url(token)
    feed_url = build_public_subscription_feed_url(token)
    happ_url = build_public_subscription_happ_wrapper_url(page_url)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📲 Открыть Happ", url=happ_url),
                InlineKeyboardButton(text="🌐 Страница подписки", url=page_url),
            ],
            [
                InlineKeyboardButton(
                    text="📋 Скопировать ссылку",
                    copy_text=CopyTextButton(text=feed_url),
                )
            ],
            [InlineKeyboardButton(text="↩ Назад", callback_data="home:cabinet")],
        ]
    )
    await callback.message.edit_text(
        (
            "🔗 <b>Единая ссылка на подписку</b>\n\n"
            "Одна ссылка открывает всю подписку целиком.\n"
            "Внутри уже собраны все доступные серверы и страны.\n\n"
            "Кнопка «Открыть Happ» и копирование используют один и тот же feed <code>?feed=1</code>.\n"
            "Это отдельный user-level contour: он не заменяет текущие устройства, а работает параллельно."
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "home:info")
async def home_info_callback(callback: CallbackQuery) -> None:
    from bot.handlers.info import info_root_callback

    await info_root_callback(callback)


@router.callback_query(F.data == "home:referrals")
async def home_referrals_callback(callback: CallbackQuery) -> None:
    from bot.handlers.referrals import _edit_referrals

    await _edit_referrals(callback)


@router.callback_query(F.data == TRIAL_SUBSCRIPTION_CONFIRMED_CALLBACK)
async def start_trial_subscription_confirmed_callback(callback: CallbackQuery) -> None:
    if config.channel_id and not await is_user_subscribed(callback.bot, config.channel_id, callback.from_user.id):
        await callback.answer(
            "Пока не вижу подписку на канал. Подпишись и нажми кнопку ещё раз.",
            show_alert=True,
        )
        return

    await callback.answer()
    await _handle_start_flow(
        callback.message,
        bot=callback.bot,
        telegram_user=callback.from_user,
        channel_post_token=None,
    )


@router.callback_query(F.data.startswith("campaign:cta:"))
async def campaign_cta_callback(callback: CallbackQuery) -> None:
    delivery_id = int(callback.data.split(":")[2])
    action = callback.data.split(":")[3]
    await mark_delivery_clicked(delivery_id)

    if action == "open_tariffs":
        await home_tariffs_callback(callback)
        return

    if action == "open_devices":
        await home_devices_callback(callback)
        return

    if action == "open_support":
        await callback.message.answer(
            "🛟 Поддержка Amonora доступна по кнопке ниже.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🛟 Открыть поддержку", url=SUPPORT_URL)]]
            ),
        )
        await callback.answer()
        return

    if action == "open_channel":
        await callback.message.answer(
            "📡 Канал проекта:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📡 Открыть канал", url=CHANNEL_URL)]]
            ),
        )
        await callback.answer()
        return

    if action == "start_trial":
        await callback.answer()
        await _handle_start_flow(
            callback.message,
            bot=callback.bot,
            telegram_user=callback.from_user,
            channel_post_token=None,
        )
        return

    await callback.answer()
