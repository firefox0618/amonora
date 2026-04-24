from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.referrals import referral_share_url
from bot.services.user.models import DEVICE_GUIDES, TestBonusSummary, TestUserSummary
from bot.services.user.summary import _subscription_connection_uri
from bot.ui.screens.user import CHANNEL_URL, PRIVACY_URL, REFUNDS_URL, SUPPORT_URL, TERMS_URL
from bot.user_flow.constants import (
    V2_ACCEPT_TERMS_CALLBACK,
    V2_BACK_TO_MENU_CALLBACK,
    V2_BALANCE_EXTERNAL_CHECK_PREFIX,
    V2_BALANCE_MANUAL_CANCEL_PREFIX,
    V2_BALANCE_MANUAL_PAID_PREFIX,
    V2_BALANCE_MANUAL_STATUS_PREFIX,
    V2_BALANCE_METHOD_PREFIX,
    V2_BALANCE_TOPUP_AMOUNT_PREFIX,
    V2_BONUS_CALLBACK,
    V2_BONUS_GIFT_CALLBACK,
    V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX,
    V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX,
    V2_BONUS_GIFT_MANUAL_PAID_PREFIX,
    V2_BONUS_GIFT_MANUAL_STATUS_PREFIX,
    V2_BONUS_GIFT_METHOD_PREFIX,
    V2_BONUS_GIFT_PAY_PREFIX,
    V2_BONUS_GIFT_TARIFF_PREFIX,
    V2_BONUS_GIFT_TARIFFS_CALLBACK,
    V2_BONUS_NO_LINK_CALLBACK,
    V2_BONUS_PROMO_CALLBACK,
    V2_BONUS_STATS_CALLBACK,
    V2_CHECK_SUBSCRIPTION_CALLBACK,
    V2_CONNECT_PREFIX,
    V2_COPY_KEY_CALLBACK,
    V2_DEVICE_CALLBACK_PREFIX,
    V2_DEVICE_DELETE_PREFIX,
    V2_DEVICE_SLOT_CALLBACK,
    V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX,
    V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX,
    V2_DEVICE_SLOT_MANUAL_PAID_PREFIX,
    V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX,
    V2_DEVICE_SLOT_METHOD_PREFIX,
    V2_DEVICE_VIEW_PREFIX,
    V2_DEVICES_CALLBACK,
    V2_GUIDE_PREFIX,
    V2_GUIDES_CALLBACK,
    V2_INFO_CALLBACK,
    V2_INFO_DOCS_CALLBACK,
    V2_INFO_GUIDES_CALLBACK,
    V2_INSTALLED_PREFIX,
    V2_KEY_MENU_CALLBACK,
    V2_MENU_CALLBACK,
    V2_MY_DEVICES_CALLBACK,
    V2_MY_SUBSCRIPTION_CALLBACK,
    V2_RENEW_CALLBACK,
    V2_RENEW_EXTERNAL_CHECK_PREFIX,
    V2_RENEW_MANUAL_CANCEL_PREFIX,
    V2_RENEW_MANUAL_PAID_PREFIX,
    V2_RENEW_MANUAL_STATUS_PREFIX,
    V2_RENEW_METHOD_PREFIX,
    V2_RENEW_TARIFF_PREFIX,
    V2_SHOW_AGREEMENT_CALLBACK,
    V2_SUPPORT_CALLBACK,
    V2_TRIAL_READY_CALLBACK,
)


def _agreement_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="Принимаю", callback_data=V2_ACCEPT_TERMS_CALLBACK)],
        ]
    )


def _trial_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data=V2_CHECK_SUBSCRIPTION_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_SHOW_AGREEMENT_CALLBACK)],
        ]
    )


def _trial_ready_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ключ", callback_data=V2_KEY_MENU_CALLBACK)],
            [
                InlineKeyboardButton(text="Инструкция", callback_data=V2_GUIDES_CALLBACK),
                InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _trial_used_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить подписку", callback_data=V2_RENEW_CALLBACK)],
            [InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK)],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Моя подписка", callback_data=V2_MY_SUBSCRIPTION_CALLBACK),
                InlineKeyboardButton(text="Ключ", callback_data=V2_KEY_MENU_CALLBACK),
            ],
            [
                InlineKeyboardButton(text="Продлить", callback_data=V2_RENEW_CALLBACK),
                InlineKeyboardButton(text="Информация", callback_data=V2_INFO_CALLBACK),
            ],
            [
                InlineKeyboardButton(text="Поддержка", callback_data=V2_SUPPORT_CALLBACK),
                InlineKeyboardButton(text="Бонусная система", callback_data=V2_BONUS_CALLBACK),
            ],
        ]
    )


def _devices_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}android"),
            InlineKeyboardButton(text=DEVICE_GUIDES["ios"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}ios"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["windows"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}windows"),
            InlineKeyboardButton(text=DEVICE_GUIDES["macos"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}macos"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["tv"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}tv"),
            InlineKeyboardButton(text=DEVICE_GUIDES["linux"].button_label, callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}linux"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=V2_BACK_TO_MENU_CALLBACK)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _guides_keyboard(*, back_callback: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android"].button_label, callback_data=f"{V2_GUIDE_PREFIX}android"),
            InlineKeyboardButton(text=DEVICE_GUIDES["ios"].button_label, callback_data=f"{V2_GUIDE_PREFIX}ios"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["windows"].button_label, callback_data=f"{V2_GUIDE_PREFIX}windows"),
            InlineKeyboardButton(text=DEVICE_GUIDES["macos"].button_label, callback_data=f"{V2_GUIDE_PREFIX}macos"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["linux"].button_label, callback_data=f"{V2_GUIDE_PREFIX}linux"),
            InlineKeyboardButton(text=DEVICE_GUIDES["apple_tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}apple_tv"),
        ],
        [
            InlineKeyboardButton(text=DEVICE_GUIDES["android_tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}android_tv"),
            InlineKeyboardButton(text=DEVICE_GUIDES["tv"].button_label, callback_data=f"{V2_GUIDE_PREFIX}tv"),
        ],
        [InlineKeyboardButton(text="Назад", callback_data=back_callback)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscription_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    open_button = (
        InlineKeyboardButton(text="Открыть подписку", url=summary.subscription_page_url)
        if summary.subscription_page_url
        else InlineKeyboardButton(text="Открыть подписку", callback_data=V2_KEY_MENU_CALLBACK)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[[open_button], [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)]]
    )


def _renew_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ 1 месяц — 149 ₽", callback_data=f"{V2_RENEW_TARIFF_PREFIX}1m")],
            [InlineKeyboardButton(text="🔥 3 месяца — 399 ₽ (-10%)", callback_data=f"{V2_RENEW_TARIFF_PREFIX}3m")],
            [InlineKeyboardButton(text="👑 6 месяцев — 749 ₽ (-15%)", callback_data=f"{V2_RENEW_TARIFF_PREFIX}6m")],
            [InlineKeyboardButton(text="💫 12 месяцев — 1390 ₽ (-20%)", callback_data=f"{V2_RENEW_TARIFF_PREFIX}12m")],
            [InlineKeyboardButton(text="⭐️ Пополнить баланс", callback_data=f"{V2_RENEW_TARIFF_PREFIX}balance")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _my_devices_keyboard(
    summary: TestUserSummary,
    *,
    back_callback: str = V2_KEY_MENU_CALLBACK,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for device in summary.devices:
        kind = str(device.get("kind") or "vpn_client").strip().lower()
        callback_suffix = "public" if kind == "public_slot" else "vpn"
        rows.append(
            [InlineKeyboardButton(text=device["title"], callback_data=f"{V2_DEVICE_VIEW_PREFIX}{callback_suffix}:{device['id']}")]
        )
    rows.append([InlineKeyboardButton(text="Купить дополнительный слот", callback_data=V2_DEVICE_SLOT_CALLBACK)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _subscription_key_menu_keyboard(summary: TestUserSummary) -> InlineKeyboardMarkup:
    connection_uri = _subscription_connection_uri(summary)
    open_page_button = (
        InlineKeyboardButton(text="Подписка", url=summary.subscription_page_url)
        if summary.subscription_page_url
        else InlineKeyboardButton(text="Подписка", callback_data=V2_MENU_CALLBACK)
    )
    open_happ_button = (
        InlineKeyboardButton(text="Happ", url=summary.happ_subscription_url)
        if summary.happ_subscription_url
        else InlineKeyboardButton(text="Happ", callback_data=V2_MENU_CALLBACK)
    )
    rows: list[list[InlineKeyboardButton]] = [[open_page_button, open_happ_button]]
    if connection_uri:
        rows.append([InlineKeyboardButton(text="📋 Скопировать", copy_text=CopyTextButton(text=connection_uri))])
    rows.append([InlineKeyboardButton(text="Мои устройства", callback_data=V2_MY_DEVICES_CALLBACK)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _device_detail_keyboard(device_kind: str, device_id: int, connection_uri: str | None) -> InlineKeyboardMarkup:
    del connection_uri
    delete_kind = "public" if str(device_kind or "").strip().lower() == "public_slot" else "vpn"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить устройство", callback_data=f"{V2_DEVICE_DELETE_PREFIX}{delete_kind}:{device_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MY_DEVICES_CALLBACK)],
        ]
    )


def _renew_payment_methods_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_RENEW_METHOD_PREFIX}sbp:{tariff_code}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_RENEW_METHOD_PREFIX}sbp_manual:{tariff_code}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_RENEW_METHOD_PREFIX}crypto:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_RENEW_CALLBACK)],
        ]
    )


def _balance_payment_methods_keyboard(amount_rub: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_BALANCE_METHOD_PREFIX}sbp:{amount_rub}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_BALANCE_METHOD_PREFIX}sbp_manual:{amount_rub}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_BALANCE_METHOD_PREFIX}crypto:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _device_slot_payment_methods_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}sbp")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}sbp_manual")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_DEVICE_SLOT_METHOD_PREFIX}crypto")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MY_DEVICES_CALLBACK)],
        ]
    )


def _renew_manual_payment_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_RENEW_MANUAL_PAID_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_RENEW_MANUAL_STATUS_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_RENEW_MANUAL_CANCEL_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_RENEW_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _renew_external_payment_keyboard(checkout_url: str, tariff_code: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_RENEW_EXTERNAL_CHECK_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_RENEW_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _balance_manual_payment_keyboard(record_id: int, amount_rub: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_BALANCE_MANUAL_PAID_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_BALANCE_MANUAL_STATUS_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_BALANCE_MANUAL_CANCEL_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _balance_external_payment_keyboard(checkout_url: str, amount_rub: int, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_BALANCE_EXTERNAL_CHECK_PREFIX}{record_id}:{amount_rub}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}{amount_rub}")],
        ]
    )


def _device_slot_manual_payment_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_DEVICE_SLOT_MANUAL_PAID_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_DEVICE_SLOT_MANUAL_STATUS_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_DEVICE_SLOT_MANUAL_CANCEL_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_DEVICE_SLOT_CALLBACK)],
        ]
    )


def _device_slot_external_payment_keyboard(checkout_url: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_DEVICE_SLOT_EXTERNAL_CHECK_PREFIX}{record_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_DEVICE_SLOT_CALLBACK)],
        ]
    )


def _balance_topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="100 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}100")],
            [InlineKeyboardButton(text="300 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}300")],
            [InlineKeyboardButton(text="500 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}500")],
            [InlineKeyboardButton(text="1000 р", callback_data=f"{V2_BALANCE_TOPUP_AMOUNT_PREFIX}1000")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_RENEW_CALLBACK)],
        ]
    )


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть поддержку", url=SUPPORT_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Инструкции", callback_data=V2_INFO_GUIDES_CALLBACK)],
            [InlineKeyboardButton(text="Документы", callback_data=V2_INFO_DOCS_CALLBACK)],
            [InlineKeyboardButton(text="Канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _info_documents_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пользовательское соглашение", url=TERMS_URL)],
            [InlineKeyboardButton(text="Политика конфиденциальности", url=PRIVACY_URL)],
            [InlineKeyboardButton(text="Политика возврата", url=REFUNDS_URL)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_INFO_CALLBACK)],
        ]
    )


def _bonus_keyboard(summary: TestBonusSummary) -> InlineKeyboardMarkup:
    invite_button: InlineKeyboardButton
    if summary.referral_link.startswith("https://"):
        invite_button = InlineKeyboardButton(text="Пригласить друга", url=referral_share_url(summary.referral_link))
    else:
        invite_button = InlineKeyboardButton(text="Пригласить друга", callback_data=V2_BONUS_NO_LINK_CALLBACK)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Моя статистика", callback_data=V2_BONUS_STATS_CALLBACK)],
            [invite_button],
            [InlineKeyboardButton(text="Ввести промокод", callback_data=V2_BONUS_PROMO_CALLBACK)],
            [InlineKeyboardButton(text="Подарить подписку", callback_data=V2_BONUS_GIFT_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_MENU_CALLBACK)],
        ]
    )


def _bonus_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)]])


def _bonus_promo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)]])


def _bonus_gift_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тариф", callback_data=V2_BONUS_GIFT_TARIFFS_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_CALLBACK)],
        ]
    )


def _bonus_gift_tariffs_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ 1 месяц — 149 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}1m")],
            [InlineKeyboardButton(text="🔥 3 месяца — 399 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}3m")],
            [InlineKeyboardButton(text="👑 6 месяцев — 749 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}6m")],
            [InlineKeyboardButton(text="💫 12 месяцев — 1390 ₽", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}12m")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_GIFT_CALLBACK)],
        ]
    )


def _bonus_gift_payment_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить подарок", callback_data=f"{V2_BONUS_GIFT_PAY_PREFIX}{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=V2_BONUS_GIFT_TARIFFS_CALLBACK)],
        ]
    )


def _bonus_gift_payment_methods_keyboard(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}sbp:{tariff_code}")],
            [InlineKeyboardButton(text="СБП(ручная)", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}sbp_manual:{tariff_code}")],
            [InlineKeyboardButton(text="Криптовалюта", callback_data=f"{V2_BONUS_GIFT_METHOD_PREFIX}crypto:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _bonus_gift_manual_payment_keyboard(record_id: int, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил(а)", callback_data=f"{V2_BONUS_GIFT_MANUAL_PAID_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Проверить статус", callback_data=f"{V2_BONUS_GIFT_MANUAL_STATUS_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Отменить заявку", callback_data=f"{V2_BONUS_GIFT_MANUAL_CANCEL_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _bonus_gift_external_payment_keyboard(checkout_url: str, tariff_code: str, record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=checkout_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"{V2_BONUS_GIFT_EXTERNAL_CHECK_PREFIX}{record_id}:{tariff_code}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_BONUS_GIFT_TARIFF_PREFIX}{tariff_code}")],
        ]
    )


def _device_guide_keyboard(device_key: str, *, back_callback: str) -> InlineKeyboardMarkup:
    del device_key
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=back_callback)],
        ]
    )


def _after_install_keyboard(device_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подключиться", callback_data=f"{V2_CONNECT_PREFIX}{device_key}")],
            [
                InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL),
                InlineKeyboardButton(text="Инструкция", callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}{device_key}"),
            ],
        ]
    )


def _connect_placeholder_keyboard(device_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Инструкция", callback_data=f"{V2_DEVICE_CALLBACK_PREFIX}{device_key}"),
                InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL),
            ],
            [InlineKeyboardButton(text="Главное меню", callback_data=V2_MENU_CALLBACK)],
            [InlineKeyboardButton(text="Назад", callback_data=f"{V2_INSTALLED_PREFIX}{device_key}")],
        ]
    )
