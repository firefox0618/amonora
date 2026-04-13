from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db import get_user_by_telegram_id, get_user_referral_stats
from bot.keyboards.referrals import referral_keyboard, referral_share_url
from bot.utils.texts import blocked_user_action_text, configured_referral_share_text, referral_copy_message_text, referrals_text


router = Router()


def _referral_share_url(referral_link: str) -> str:
    return referral_share_url(referral_link)


async def _show_referrals(message_target: Message, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(telegram_id)
    if user is None:
        await message_target.answer("Пользователь не найден. Нажми /start")
        return
    if getattr(user, "is_blocked", False):
        await message_target.answer(blocked_user_action_text(), parse_mode="HTML")
        return

    stats = await get_user_referral_stats(user.id)
    await message_target.answer(
        referrals_text(
            referral_link=stats["ref_link"],
            balance_rub=stats["balance_rub"],
            earned_total_rub=stats["total_earned_rub"],
            invited_count=stats["invited_count"],
            paid_count=stats["paid_count"],
            current_level_name=stats["current_level_name"],
            next_level_name=stats["next_level_name"],
            left_to_next_level=stats["left_to_next_level"],
            progress_bar=stats["progress_bar"],
        ),
        parse_mode="HTML",
        reply_markup=referral_keyboard(stats["ref_link"]),
    )


async def _edit_referrals(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return
    if getattr(user, "is_blocked", False):
        await callback.answer("Реферальная система недоступна: доступ заблокирован.", show_alert=True)
        return

    stats = await get_user_referral_stats(user.id)
    await callback.message.edit_text(
        referrals_text(
            referral_link=stats["ref_link"],
            balance_rub=stats["balance_rub"],
            earned_total_rub=stats["total_earned_rub"],
            invited_count=stats["invited_count"],
            paid_count=stats["paid_count"],
            current_level_name=stats["current_level_name"],
            next_level_name=stats["next_level_name"],
            left_to_next_level=stats["left_to_next_level"],
            progress_bar=stats["progress_bar"],
        ),
        parse_mode="HTML",
        reply_markup=referral_keyboard(stats["ref_link"]),
    )
    await callback.answer()


@router.message(F.text == "🎁 Реферальная система")
@router.message(F.text == "Реферальная система")
@router.message(F.text == "🎁 Рефералы")
@router.message(F.text == "Рефералы")
async def referral_program_handler(message: Message) -> None:
    await _show_referrals(message, message.from_user.id)


@router.callback_query(F.data == "referrals:refresh")
async def referral_refresh_callback(callback: CallbackQuery) -> None:
    await _edit_referrals(callback)


@router.callback_query(F.data == "referrals:copy")
async def referral_copy_callback(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден. Нажми /start", show_alert=True)
        return
    stats = await get_user_referral_stats(user.id)
    await callback.message.answer(
        referral_copy_message_text(
            referral_link=stats["ref_link"],
            share_text=configured_referral_share_text(),
        ),
        parse_mode="HTML",
    )
    await callback.answer("Ссылка отправлена отдельным сообщением.", show_alert=True)
