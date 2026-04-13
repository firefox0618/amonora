from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import config
from bot.utils.payment_options import sbp_balance_topup_uses_platega, sbp_tariff_uses_manual, sbp_tariff_uses_platega
from bot.utils.tariffs import get_tariffs_list


def tariffs_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "1 месяц": "⚡ 1 месяц",
        "3 месяца": "🔥 3 месяца",
        "6 месяцев": "👑 6 месяцев",
        "12 месяцев": "💫 12 месяцев",
    }
    rows = []
    for tariff in get_tariffs_list():
        rows.append(
            [
                InlineKeyboardButton(
                    text=labels.get(tariff.title, tariff.title),
                    callback_data=f"tariff:buy:{tariff.code}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def balance_topup_amounts_keyboard() -> InlineKeyboardMarkup:
    amounts = (100, 300, 500, 1000, 2000)
    rows = [
        [
            InlineKeyboardButton(
                text=f"💰 {amount} ₽",
                callback_data=f"balance:amount:{amount}",
            )
        ]
        for amount in amounts
    ]
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="home:cabinet")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def balance_topup_methods_keyboard(amount_rub: int) -> InlineKeyboardMarkup:
    rows = []
    if sbp_balance_topup_uses_platega():
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 СБП",
                    callback_data=f"balance:method:sbp:{amount_rub}",
                )
            ]
        )
    if config.enable_platega_crypto_user_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💎 Криптовалюта",
                    callback_data=f"balance:method:crypto:{amount_rub}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅ Назад к суммам", callback_data="home:balance")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariff_methods_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="⭐ Telegram Stars",
                callback_data=f"tariff:method:stars:{tariff_code}",
            )
        ]
    ]
    if sbp_tariff_uses_platega():
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 СБП",
                    callback_data=f"tariff:method:sbp:{tariff_code}",
                )
            ]
        )
    if sbp_tariff_uses_manual():
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 СБП (ручная)",
                    callback_data=f"tariff:method:sbp_manual:{tariff_code}",
                )
            ]
        )
    if config.enable_platega_crypto_user_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💎 Криптовалюта",
                    callback_data=f"tariff:method:crypto:{tariff_code}",
                )
            ]
        )
    elif config.enable_manual_crypto_user_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💎 Крипта (ручная)",
                    callback_data=f"tariff:method:crypto:{tariff_code}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅ Назад к тарифам",
                callback_data="tariff:back",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def device_slot_methods_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if sbp_tariff_uses_platega():
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 СБП",
                    callback_data="device-slot:method:sbp",
                )
            ]
        )
    if sbp_tariff_uses_manual():
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 СБП (ручная)",
                    callback_data="device-slot:method:sbp_manual",
                )
            ]
        )
    if config.enable_platega_crypto_user_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💎 Криптовалюта",
                    callback_data="device-slot:method:crypto",
                )
            ]
        )
    elif config.enable_manual_crypto_user_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💎 Крипта (ручная)",
                    callback_data="device-slot:method:crypto",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅ Назад к устройствам",
                callback_data="device:back",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_payment_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"tariff:manual:paid:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить статус",
                    callback_data=f"tariff:manual:status:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить заявку",
                    callback_data=f"tariff:manual:cancel:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛟 Поддержка",
                    url="https://t.me/amonora_support_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам оплаты",
                    callback_data=f"tariff:buy:{tariff_code}",
                )
            ],
        ]
    )


def device_slot_manual_payment_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"device-slot:manual:paid:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить статус",
                    callback_data=f"device-slot:manual:status:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить заявку",
                    callback_data=f"device-slot:manual:cancel:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛟 Поддержка",
                    url="https://t.me/amonora_support_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам оплаты",
                    callback_data="device-slot:buy",
                )
            ],
        ]
    )


def manual_payment_reminder_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"tariff:manual:paid:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить статус",
                    callback_data=f"tariff:manual:status:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить заявку",
                    callback_data=f"tariff:manual:cancel:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛟 Поддержка",
                    url="https://t.me/amonora_support_bot",
                )
            ],
        ]
    )


def device_slot_manual_payment_reminder_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data=f"device-slot:manual:paid:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить статус",
                    callback_data=f"device-slot:manual:status:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить заявку",
                    callback_data=f"device-slot:manual:cancel:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛟 Поддержка",
                    url="https://t.me/amonora_support_bot",
                )
            ],
        ]
    )


def crypto_invoice_keyboard(invoice_url: str, tariff_code: str, invoice_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💎 Открыть счёт",
                    url=invoice_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"tariff:crypto:check:{tariff_code}:{invoice_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам оплаты",
                    callback_data=f"tariff:buy:{tariff_code}",
                )
            ],
        ]
    )


def external_payment_keyboard(checkout_url: str, tariff_code: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Открыть оплату",
                    url=checkout_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"tariff:external:check:{record_id}:{tariff_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам оплаты",
                    callback_data=f"tariff:buy:{tariff_code}",
                )
            ],
        ]
    )


def device_slot_external_payment_keyboard(checkout_url: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Открыть оплату",
                    url=checkout_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"device-slot:external:check:{record_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам оплаты",
                    callback_data="device-slot:buy",
                )
            ],
        ]
    )


def balance_external_payment_keyboard(checkout_url: str, amount_rub: int, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Открыть оплату",
                    url=checkout_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"balance:external:check:{record_id}:{amount_rub}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅ Назад к способам",
                    callback_data=f"balance:amount:{amount_rub}",
                )
            ],
        ]
    )
