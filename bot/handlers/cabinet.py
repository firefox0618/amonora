from aiogram import F, Router
from aiogram.types import Message

from bot.db import count_user_vpn_clients, get_user_by_telegram_id
from bot.keyboards.home import home_keyboard_for_user
from bot.keyboards.tariffs import tariffs_keyboard
from bot.utils.access import has_active_access_from_user
from bot.utils.texts import access_expired_text, blocked_user_action_text, cabinet_text


router = Router()


@router.message(F.text == "🏠 Главная")
async def cabinet_handler(message: Message):
    user = await get_user_by_telegram_id(message.from_user.id)

    if not user:
        await message.answer("Пользователь не найден.")
        return

    devices_count = await count_user_vpn_clients(user.id)
    await message.answer(
        cabinet_text(user, devices_count),
        parse_mode="HTML",
        reply_markup=home_keyboard_for_user(user),
    )

    if getattr(user, "is_blocked", False):
        await message.answer(blocked_user_action_text(), parse_mode="HTML")
        return

    if not has_active_access_from_user(user):
        await message.answer(
            access_expired_text(),
            parse_mode="HTML",
            reply_markup=tariffs_keyboard(),
        )
