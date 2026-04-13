from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.utils.texts import support_intro_text


router = Router()


@router.message(F.text == "🛟 Поддержка")
@router.message(F.text == "Поддержка")
@router.message(Command("support"))
async def support_handler(message: Message) -> None:
    support_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛟 Открыть поддержку",
                    url="https://t.me/amonora_support_bot",
                )
            ]
        ]
    )

    await message.answer(
        support_intro_text(),
        reply_markup=support_keyboard,
        parse_mode="HTML",
    )
