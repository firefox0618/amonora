from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db import get_user_by_telegram_id, set_user_preferred_mode
from bot.keyboards.protocols import modes_keyboard
from bot.utils.modes import (
    format_mode,
    get_auto_mode,
    get_mode_description,
    get_mode_keys,
    infer_mode_from_protocol,
    is_mode_key,
    mode_available_for_user,
    normalize_mode,
)
from bot.utils.texts import mobile_mode_placeholder_text


router = Router()


@router.message(F.text == "🔌 Режим")
@router.message(F.text == "Режим")
@router.message(F.text == "🔐 Протокол")
@router.message(F.text == "Протокол")
async def protocol_handler(message: Message) -> None:
    lines = [
        f"<b>{format_mode(mode)}</b> — {get_mode_description(mode, telegram_id=message.from_user.id)}"
        for mode in get_mode_keys(telegram_id=message.from_user.id)
    ]
    await message.answer(
        "🔌 <b>Режим подключения</b>\n\n"
        "Выбери подходящий режим:\n\n"
        + "\n".join(lines)
        + "\n\n🛡 <b>Рекомендуем Стабильный</b>\n"
        "Это основной режим по умолчанию для большинства подключений.",
        reply_markup=modes_keyboard(telegram_id=message.from_user.id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mode:"))
@router.callback_query(F.data.startswith("protocol:"))
async def protocol_callback_handler(callback: CallbackQuery) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)

    if user is None:
        await callback.message.answer("Пользователь не найден. Нажми /start")
        await callback.answer()
        return

    raw_mode = callback.data.split(":")[1]
    mode = normalize_mode(raw_mode, default="") if is_mode_key(raw_mode) else infer_mode_from_protocol(raw_mode)
    if mode not in set(get_mode_keys(telegram_id=callback.from_user.id)):
        mode = get_auto_mode()
    if not mode_available_for_user(mode, telegram_id=callback.from_user.id):
        await callback.message.answer(
            mobile_mode_placeholder_text(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    updated_user = await set_user_preferred_mode(user.id, mode)

    if updated_user is None:
        await callback.message.answer("Не удалось сохранить режим.")
        await callback.answer()
        return

    await callback.message.answer(
        f"✅ <b>Режим изменён</b>\n\nТекущий режим: {format_mode(mode)}",
        parse_mode="HTML",
    )
    await callback.answer()
