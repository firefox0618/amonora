from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.info import info_detail_keyboard, info_documents_keyboard, info_root_keyboard
from bot.utils.texts import info_faq_text, info_instructions_text, info_root_text


router = Router()


async def _show_info_root(message_target) -> None:
    await message_target.answer(
        info_root_text(),
        parse_mode="HTML",
        reply_markup=info_root_keyboard(),
    )


@router.message(F.text == "📚 Информация")
@router.message(F.text == "Информация")
@router.message(F.text == "📡 Канал")
@router.message(F.text == "Канал")
async def info_handler(message: Message) -> None:
    await _show_info_root(message)


@router.callback_query(F.data == "info:root")
async def info_root_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        info_root_text(),
        parse_mode="HTML",
        reply_markup=info_root_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:instructions")
async def info_instructions_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        info_instructions_text(),
        parse_mode="HTML",
        reply_markup=info_detail_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:faq")
async def info_faq_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        info_faq_text(),
        parse_mode="HTML",
        reply_markup=info_detail_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:docs")
async def info_docs_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📜 <b>Документы</b>\n\nВыбери нужный документ ниже.",
        parse_mode="HTML",
        reply_markup=info_documents_keyboard(),
    )
    await callback.answer()
