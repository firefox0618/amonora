import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from bot.config import config
from bot.handlers import devices as device_handlers
from bot.handlers import start as start_handlers
from bot.handlers.start import _start_offer_keyboard
from bot.keyboards.devices import (
    HAPP_STORE_URLS,
    device_card_keyboard,
    device_credential_keyboard,
    device_os_keyboard,
    device_instruction_keyboard,
    devices_list_keyboard,
    device_protocol_keyboard,
    device_protocol_keyboard_for_existing,
)
from bot.keyboards.home import home_keyboard
from bot.keyboards.info import info_documents_keyboard, info_root_keyboard
from bot.keyboards.main_menu import main_menu
from bot.keyboards.tariffs import balance_topup_methods_keyboard, tariff_methods_keyboard, tariffs_keyboard
from bot.utils.tariffs import get_tariff
from bot.utils.texts import (
    MANUAL_URL,
    MOBILE_KEY_IMPORT_TEXT,
    active_access_text,
    balance_topup_methods_text,
    ask_device_country_text,
    ask_device_protocol_text,
    ask_existing_device_country_text,
    ask_existing_device_protocol_text,
    balance_topup_intro_text,
    devices_overview_text,
    device_guide_text,
    device_slot_methods_text,
    device_slot_payment_success_text,
    home_text,
    info_faq_text,
    info_instructions_text,
    info_root_text,
    mobile_mode_placeholder_text,
    referrals_text,
    start_new_user_text,
    start_new_user_trial_activated_text,
    start_trial_subscription_required_text,
    support_intro_text,
    TERMS_URL,
    tariff_methods_text,
    tariffs_text,
    no_access_reminder_text,
    trial_channel_pause_notice_text,
    trial_channel_resume_notice_text,
    trial_subscription_paused_text,
    trial_ends_today_reminder_text,
    trial_expired_reminder_text,
    trojan_delivery_text,
    vless_delivery_text,
    vpn_client_created_text,
)

config.admin_ids = [1]
config.support_admin_ids = [1]


class BotCopyUpdateTests(unittest.TestCase):
    def test_ios_happ_link_points_to_new_app_store_entry(self) -> None:
        self.assertEqual(
            HAPP_STORE_URLS["ios"],
            "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
        )

    def test_device_os_choices_hide_android_tv(self) -> None:
        labels = [button.text for row in device_os_keyboard("device:os").inline_keyboard for button in row]

        self.assertNotIn("📺 Android TV", labels)

    def test_uri_based_device_actions_use_key_wording(self) -> None:
        keyboard = device_card_keyboard(42, protocol="vless")
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🔑 Получить ключ", labels)
        self.assertIn("🔌 Режим", labels)
        self.assertIn("🧭 Маршруты РФ", labels)
        self.assertNotIn("📄 Получить конфиг", labels)
        self.assertNotIn("🌍 Страна и режим", labels)

        retry_keyboard = device_instruction_keyboard(42, protocol="trojan")
        retry_labels = [button.text for row in retry_keyboard.inline_keyboard for button in row]
        self.assertIn("🔁 Получить ключ ещё раз", retry_labels)
        self.assertIn("🧭 Маршруты РФ", retry_labels)

    def test_credential_keyboard_uses_copy_text_and_expected_layout(self) -> None:
        keyboard = device_credential_keyboard(42, "vless://example")
        self.assertEqual(len(keyboard.inline_keyboard), 2)
        first_row = keyboard.inline_keyboard[0]
        second_row = keyboard.inline_keyboard[1]

        self.assertEqual(first_row[0].text, "📋 Скопировать ключ")
        self.assertEqual(first_row[0].copy_text.text, "vless://example")
        self.assertEqual(first_row[1].text, "📷 Показать QR")
        self.assertEqual(first_row[1].callback_data, "device:qr:42")

        self.assertEqual(second_row[0].text, "📘 Инструкция")
        self.assertEqual(second_row[0].callback_data, "device:guide:42")
        self.assertEqual(second_row[1].text, "🔄 Сменить режим")
        self.assertEqual(second_row[1].callback_data, "device:location:42")

    def test_vpn_key_message_is_short_and_copy_friendly(self) -> None:
        rendered = vpn_client_created_text(
            "Телефон",
            "Стабильный",
            "Германия",
            "2026-04-06 12:00:00",
            "vless://example",
        )

        self.assertIn("✅ <b>Доступ активен</b>", rendered)
        self.assertIn("🔌 Режим: <b>Стабильный</b>", rendered)
        self.assertIn("🌍 <b>Германия</b>", rendered)
        self.assertIn("⏳ До: <b>2026-04-06 12:00:00</b>", rendered)
        self.assertIn("<code>vless://example</code>", rendered)
        self.assertIn("Если не сработало", rendered)
        self.assertNotIn("Телефон", rendered)

    def test_credential_keyboard_hides_copy_button_for_long_uri(self) -> None:
        keyboard = device_credential_keyboard(42, f"vless://{'a' * 300}")
        self.assertEqual(len(keyboard.inline_keyboard), 2)
        first_row = keyboard.inline_keyboard[0]

        self.assertEqual(len(first_row), 1)
        self.assertEqual(first_row[0].text, "📷 Показать QR")
        self.assertEqual(first_row[0].callback_data, "device:qr:42")

    def test_all_device_actions_use_key_wording(self) -> None:
        keyboard = device_card_keyboard(7, protocol="trojan")
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertIn("🔑 Получить ключ", labels)
        self.assertNotIn("📄 Получить конфиг", labels)

    def test_devices_list_shows_buy_slot_cta_when_limit_is_reached(self) -> None:
        keyboard = devices_list_keyboard(
            [{"id": 1, "title": "📱 iPhone"}],
            allow_add=False,
            can_buy_more=True,
            price_rub=49,
        )
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("🛒 Купить +1 устройство за 49 ₽", labels)
        self.assertNotIn("➕ Создать устройство", labels)

    def test_protocol_buttons_use_friendly_labels(self) -> None:
        create_labels = [button.text for row in device_protocol_keyboard().inline_keyboard for button in row]
        update_labels = [button.text for row in device_protocol_keyboard_for_existing(7).inline_keyboard for button in row]
        admin_labels = [button.text for row in device_protocol_keyboard(telegram_id=1, country_code="dk").inline_keyboard for button in row]
        regular_dk_labels = [button.text for row in device_protocol_keyboard(telegram_id=42, country_code="dk").inline_keyboard for button in row]

        self.assertIn("🛡 Стабильный", create_labels)
        self.assertIn("☁ Мобильный", create_labels)
        self.assertIn("🧰 Резерв", create_labels)
        self.assertIn("🛡 Стабильный", update_labels)
        self.assertIn("☁ Мобильный", update_labels)
        self.assertIn("🧰 Резерв", update_labels)
        self.assertIn("☁ Мобильный", admin_labels)
        self.assertIn("☁ Мобильный", regular_dk_labels)
        self.assertNotIn("VLESS", " ".join(create_labels + update_labels))
        self.assertNotIn("Trojan", " ".join(create_labels + update_labels))
        self.assertNotIn("NOVA", " ".join(create_labels + update_labels))
        self.assertNotIn("CORE", " ".join(create_labels + update_labels))
        self.assertNotIn("ORIGIN", " ".join(create_labels + update_labels))

    def test_device_country_screen_shows_country_first(self) -> None:
        text = ask_device_country_text("Телефон", "android")

        self.assertIn("Выбери страну подключения", text)
        self.assertIn("🇩🇪 Германия — оптимальный выбор на каждый день", text)
        self.assertIn("🇩🇰 Дания — дополнительный маршрут", text)

    def test_device_mode_screen_shows_mini_descriptions(self) -> None:
        text = ask_device_protocol_text("Телефон", "android", "de")

        self.assertIn("🇩🇪 Германия", text)
        self.assertIn("🛡 Стабильный — основной режим на каждый день", text)
        self.assertIn("☁ Мобильный — маршрут для сетей, где доступна только часть направлений", text)
        self.assertIn("🧰 Резерв — запасной режим, если основной не подошёл", text)

    def test_existing_device_country_screen_shows_country_first(self) -> None:
        text = ask_existing_device_country_text("Телефон", "de")

        self.assertIn("Выбери страну подключения", text)
        self.assertIn("🇩🇪 Германия — оптимальный выбор на каждый день", text)
        self.assertIn("🇩🇰 Дания — дополнительный маршрут", text)

    def test_existing_device_mode_screen_shows_mini_descriptions(self) -> None:
        text = ask_existing_device_protocol_text("Телефон", "Германия")

        self.assertIn("Выбери режим для этого подключения", text)
        self.assertIn("🛡 Стабильный — основной режим на каждый день", text)
        self.assertIn("☁ Мобильный — маршрут для сетей, где доступна только часть направлений", text)
        self.assertIn("🧰 Резерв — запасной режим, если основной не подошёл", text)

    def test_existing_device_mode_screen_shows_mobile_as_admin_experimental(self) -> None:
        admin_text = ask_existing_device_protocol_text("Телефон", "Дания", telegram_id=1, country_code="dk")
        regular_text = ask_existing_device_protocol_text("Телефон", "Дания", telegram_id=42, country_code="dk")

        self.assertIn("☁ Мобильный — маршрут для сетей с ограниченным набором доступных направлений", admin_text)
        self.assertIn("☁ Мобильный — маршрут для сетей, где доступна только часть направлений", regular_text)

    def test_mobile_mode_placeholder_text_is_honest_for_regular_users(self) -> None:
        text = mobile_mode_placeholder_text("dk")

        self.assertIn("Мобильный режим пока в подготовке", text)
        self.assertIn("🇩🇰 Дания", text)
        self.assertIn("🛡 Стабильный", text)
        self.assertIn("🧰 Резерв", text)

    def test_mobile_import_text_uses_new_generic_key_flow(self) -> None:
        self.assertIn("Скачайте подходящее приложение", MOBILE_KEY_IMPORT_TEXT)
        self.assertIn("Скопируйте ключ", MOBILE_KEY_IMPORT_TEXT)
        self.assertIn("Импорт из буфера обмена", MOBILE_KEY_IMPORT_TEXT)
        self.assertIn("Если возникнут сложности", MOBILE_KEY_IMPORT_TEXT)

    def test_trial_channel_notice_texts_explain_pause_and_resume(self) -> None:
        pause_text = trial_channel_pause_notice_text("2026-04-05 13:00:00")
        resume_text = trial_channel_resume_notice_text("2026-04-05 13:00:00")

        self.assertIn("Пробный доступ приостановлен", pause_text)
        self.assertIn("Оставшееся время пробного доступа сохранено", pause_text)
        self.assertIn("@amonora_bot", pause_text)
        self.assertIn("Пробный доступ снова активен", resume_text)
        self.assertIn("оставшееся время пробного доступа", resume_text)

    def test_device_guides_and_delivery_texts_use_key_wording(self) -> None:
        vless_text = vless_delivery_text("iPhone", "ios", "Германия", True, protocol_name="🛡 Стабильный")
        trojan_text = trojan_delivery_text("Android", "android", "Дания")
        guide_text = device_guide_text("vless", "windows", "Laptop", "Германия")

        self.assertIn("ключ", vless_text.lower())
        self.assertIn("ключ", trojan_text.lower())
        self.assertIn("Получи ключ", guide_text)
        self.assertNotIn("получить конфиг", vless_text.lower())
        self.assertNotIn("vless", vless_text.lower())
        self.assertNotIn("trojan", trojan_text.lower())
        self.assertNotIn("xhttp", guide_text.lower())

    def test_referral_screen_uses_live_summary_labels(self) -> None:
        text = referrals_text(
            referral_link="https://t.me/amonora_bot?start=ref_demo123",
            balance_rub=70,
            earned_total_rub=140,
            invited_count=5,
            paid_count=2,
            current_level_name="Новичок",
            next_level_name="Продвинутый",
            left_to_next_level=2,
            progress_bar="[██████░░░░]",
        )

        self.assertIn("🎁 <b>Реферальная программа</b>", text)
        self.assertIn("💰 Баланс", text)
        self.assertIn("📈 Заработано всего", text)
        self.assertIn("• Приглашено", text)
        self.assertIn("• Оплатили", text)
        self.assertIn("🏆 Уровень", text)
        self.assertNotIn("пока в разработке", text)

    def test_home_and_main_navigation_use_new_labels(self) -> None:
        home_labels = [button.text for row in home_keyboard.inline_keyboard for button in row]
        menu_labels = [button.text for row in main_menu.keyboard for button in row]

        self.assertIn("💳 Купить доступ", home_labels)
        self.assertIn("📚 Информация", home_labels)
        self.assertNotIn("📡 Канал", home_labels)

        self.assertIn("📚 Информация", menu_labels)
        self.assertIn("🎁 Реферальная система", menu_labels)
        self.assertNotIn("📡 Канал", menu_labels)
        self.assertTrue(main_menu.is_persistent)

    def test_home_text_uses_new_status_design(self) -> None:
        user = SimpleNamespace(
            telegram_id=7650618404,
            preferred_protocol="vless",
            balance_rub=125,
            balance_reserved_rub=25,
            is_blocked=False,
            trial_used=False,
            trial_expires_at=datetime.utcnow() + timedelta(days=1),
            subscription_status="inactive",
            subscription_expires_at=None,
            subscription_source=None,
        )

        text = home_text(user, 4)

        self.assertIn("👤 <b>Личный кабинет</b>", text)
        self.assertIn("🆔 ID: <code>7650618404</code>", text)
        self.assertIn("📅 Статус: 🔵 Тестовый доступ", text)
        self.assertIn("🏷 Тип доступа: <b>🆓 Пробный доступ</b>", text)
        self.assertIn("🔌 Режим: 🛡 Стабильный", text)
        self.assertIn("💰 Баланс: <b>125 р</b>", text)
        self.assertNotIn("Доступно к списанию", text)
        self.assertIn("📱 Устройств: <b>4</b>", text)

    def test_balance_topup_intro_shows_only_balance(self) -> None:
        text = balance_topup_intro_text(balance_rub=125, balance_available_rub=100)

        self.assertIn("Текущий баланс: <b>125 ₽</b>", text)
        self.assertNotIn("Доступно к списанию", text)
    def test_devices_overview_text_renders_device_summary_list(self) -> None:
        text = devices_overview_text(
            2,
            "1. <b>Телефон</b>\n   🟢 Активно\n\n2. <b>Ноутбук</b>\n   🟢 Активно",
        )

        self.assertIn("📱 <b>Управление подключениями</b>", text)
        self.assertIn("🔢 Создано устройств: <b>2</b> из <b>3</b>", text)
        self.assertIn("1. <b>Телефон</b>", text)
        self.assertIn("2. <b>Ноутбук</b>", text)
        self.assertIn("Выбери устройство ниже или создай новое.", text)

    def test_info_hub_copy_and_buttons_match_new_structure(self) -> None:
        root_text = info_root_text()
        instructions_text = info_instructions_text()
        root_labels = [button.text for row in info_root_keyboard().inline_keyboard for button in row]
        docs_labels = [button.text for row in info_documents_keyboard().inline_keyboard for button in row]
        doc_urls = [button.url for row in info_documents_keyboard().inline_keyboard for button in row if button.url]

        self.assertIn("📚 <b>ИНФОРМАЦИЯ</b>", root_text)
        self.assertIn("📜 <b>Документы</b>", root_text)
        self.assertIn("📘 <b>Инструкция</b>", root_text)
        self.assertNotIn("❓ <b>FAQ</b>", root_text)
        self.assertIn(MANUAL_URL, instructions_text)
        self.assertTrue(MANUAL_URL.startswith("https://amonora.ru/"))
        self.assertTrue(TERMS_URL.startswith("https://amonora.ru/"))
        self.assertIn("📘 Инструкция", root_labels)
        self.assertNotIn("❓ FAQ", root_labels)
        self.assertIn("📜 Документы", root_labels)
        self.assertIn("📜 Пользовательское соглашение", docs_labels)
        self.assertTrue(all(url.startswith("https://amonora.ru/") for url in doc_urls))

    def test_new_user_start_text_and_offer_button_show_terms_acceptance(self) -> None:
        text = start_new_user_text("Иван")
        keyboard = _start_offer_keyboard()
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        urls = [button.url for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Добро пожаловать в <b>Amonora</b>", text)
        self.assertIn("соглашаешься с <b>Пользовательским соглашением</b>", text)
        self.assertIn("📜 Пользовательское соглашение", labels)
        self.assertIn(TERMS_URL, urls)

    def test_trial_subscription_gate_copy_and_buttons_use_confirm_action(self) -> None:
        text = start_trial_subscription_required_text("Иван")
        keyboard = _start_offer_keyboard(include_channel=True, include_subscription_check=True)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Здесь ты можешь:", text)
        self.assertIn("• подключить интернет без ограничений", text)
        self.assertIn("• управлять устройствами в 1 клик", text)
        self.assertIn("• получить стабильную и быструю сеть", text)
        self.assertIn("🎁 <b>Активируй пробный доступ бесплатно:</b>", text)
        self.assertIn("Нажми <b>«Подписался»</b>", text)
        self.assertIn("После этого откроется доступ к первому устройству.", text)
        self.assertIn("📡 Подписаться на канал", labels)
        self.assertIn("✅ Подписался", labels)
        self.assertIn("📜 Пользовательское соглашение", labels)

    def test_new_user_trial_text_combines_welcome_offer_and_trial_status(self) -> None:
        text = start_new_user_trial_activated_text("Иван", "2026-03-25 18:18:57")

        self.assertIn("Добро пожаловать в <b>Amonora</b>", text)
        self.assertIn("соглашаешься с <b>Пользовательским соглашением</b>", text)
        self.assertIn("Твой <b>пробный доступ активирован</b>", text)
        self.assertIn("Доступ действует до: <b>2026-03-25 18:18:57</b>", text)
        self.assertIn("Открой <b>🏠 Меню</b> и создай своё первое устройство.", text)

    def test_trial_pause_text_explains_remaining_time_without_reissuing_trial(self) -> None:
        text = trial_subscription_paused_text("Иван", "2026-04-05 12:00:00")

        self.assertIn("пробный доступ приостановлен", text.lower())
        self.assertIn("Текущий пробный доступ сохранён до: <b>2026-04-05 12:00:00</b>", text)
        self.assertIn("Новый пробный доступ заново не выдаётся", text)
        self.assertIn("✅ Подписался", text)

    def test_active_access_text_mentions_terms_button(self) -> None:
        text = active_access_text("Иван", "2026-03-25 18:27:20")

        self.assertIn("У тебя уже есть <b>активный доступ</b>", text)
        self.assertIn("Открой <b>📱 Устройства</b>, чтобы управлять своими подключениями.", text)
        self.assertNotIn("Пользовательское соглашение", text)

    def test_support_and_tariff_text_use_plain_non_promo_tariff_copy(self) -> None:
        support_text = support_intro_text()
        buy_text = tariffs_text()
        methods_text = tariff_methods_text("3 месяца", list_price_amount=399, balance_amount=50, payable_amount=349)
        tariff_labels = [button.text for row in tariffs_keyboard().inline_keyboard for button in row]

        self.assertIn("🛟 <b>ПОДДЕРЖКА AMONORA</b>", support_text)
        self.assertIn("⏱ <b>Время ответа:</b> обычно до 45 минут", support_text)
        self.assertIn("💳 <b>Купить доступ</b>", buy_text)
        self.assertIn("🔥 <b>3 месяца</b> — 399 ₽", buy_text)
        self.assertIn("👑 <b>6 месяцев</b>", buy_text)
        self.assertIn("💫 <b>12 месяцев</b>", buy_text)
        self.assertNotIn("в подарок", buy_text)
        self.assertNotIn("Акция действует", buy_text)
        self.assertIn("Способы оплаты:", buy_text)
        self.assertIn("С баланса спишется: <b>50 ₽</b>", methods_text)
        self.assertIn("Останется оплатить деньгами: <b>349 ₽</b>", methods_text)
        self.assertNotIn("Итого:", methods_text)
        self.assertIn("Telegram Stars оплачиваются отдельно", methods_text)
        self.assertIn("⚡ 1 месяц", tariff_labels)
        self.assertIn("💫 12 месяцев", tariff_labels)

    def test_trial_and_no_access_reminders_use_plain_non_promo_copy(self) -> None:
        self.assertIn("нажми <b>Купить</b> и выбери подходящий тариф", no_access_reminder_text())
        self.assertIn("нажми <b>Купить</b> и выбери тариф заранее", trial_ends_today_reminder_text())
        self.assertIn("нажми <b>Купить</b> и выбери тариф", trial_expired_reminder_text())
        self.assertNotIn("подароч", no_access_reminder_text().lower())
        self.assertNotIn("подароч", trial_ends_today_reminder_text().lower())
        self.assertNotIn("подароч", trial_expired_reminder_text().lower())

    def test_device_slot_copy_explains_long_subscription_period(self) -> None:
        methods_text = device_slot_methods_text(
            title="+1 устройство до конца текущей подписки",
            amount_rub=49,
            expires_at="2026-10-03 12:00:00",
            current_limit=3,
            next_limit=4,
            max_limit=8,
        )
        success_text = device_slot_payment_success_text(
            title="+1 устройство до конца текущей подписки",
            expires_at="2026-10-03 12:00:00",
            device_limit=4,
        )

        self.assertIn("до конца текущей оплаченной подписки", methods_text)
        self.assertIn("Если у тебя подписка на 6 или 12 месяцев", methods_text)
        self.assertIn("весь этот срок, а не 30 дней", methods_text)
        self.assertIn("Если у тебя подписка на 6 или 12 месяцев", success_text)
        self.assertIn("весь оплаченный период", success_text)

    def test_tariffs_use_base_duration_days_after_promo_removal(self) -> None:
        self.assertEqual(get_tariff("1m").duration_days, 30)
        self.assertEqual(get_tariff("3m").duration_days, 90)
        self.assertEqual(get_tariff("6m").duration_days, 180)
        self.assertEqual(get_tariff("12m").duration_days, 365)

    def test_sbp_manual_emergency_fallback_keeps_auto_and_manual_tariff_options(self) -> None:
        with (
            patch.object(config, "enable_platega_sbp_user_flow", True),
            patch.object(config, "enable_manual_sbp_user_flow", True),
            patch.object(config, "force_manual_sbp_user_flow", True),
        ):
            buy_text = tariffs_text()
            methods_text = tariff_methods_text("1 месяц", list_price_amount=149, balance_amount=0, payable_amount=149)
            topup_text = balance_topup_methods_text(300)
            tariff_labels = [button.text for row in tariffs_keyboard().inline_keyboard for button in row]
            method_labels = [button.text for row in tariff_methods_keyboard("1m").inline_keyboard for button in row]
            topup_labels = [button.text for row in balance_topup_methods_keyboard(300).inline_keyboard for button in row]

        self.assertIn("• 💳 СБП", buy_text)
        self.assertIn("• 💳 СБП (ручная заявка)", buy_text)
        self.assertIn("💳 <b>СБП</b> — автоматическое подтверждение после оплаты", methods_text)
        self.assertIn("💳 <b>СБП (ручная)</b> — заявка с подтверждением администратора", methods_text)
        self.assertNotIn("СБП для пополнения баланса временно отключена", topup_text)
        self.assertIn("⚡ 1 месяц", tariff_labels)
        self.assertIn("💳 СБП", method_labels)
        self.assertIn("💳 СБП (ручная)", method_labels)
        self.assertIn("💳 СБП", topup_labels)


class FakeBotMessage:
    def __init__(self, telegram_id: int = 42) -> None:
        self.from_user = SimpleNamespace(id=telegram_id)
        self.answers: list[dict] = []

    async def answer(self, text: str, parse_mode: str | None = None, **kwargs):
        self.answers.append({"text": text, "parse_mode": parse_mode, "kwargs": kwargs})
        return SimpleNamespace()


class BotMenuRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_handler_restores_reply_keyboard_before_home_screen(self) -> None:
        message = FakeBotMessage()
        user = SimpleNamespace(
            id=7,
            telegram_id=42,
            is_blocked=False,
            preferred_protocol="vless",
            balance_rub=0,
            balance_reserved_rub=0,
            trial_used=False,
            trial_expires_at=None,
            subscription_status="inactive",
            subscription_expires_at=None,
            subscription_source=None,
        )

        with (
            patch.object(start_handlers, "get_user_by_telegram_id", new=AsyncMock(return_value=user)),
            patch.object(start_handlers, "count_user_vpn_clients", new=AsyncMock(return_value=2)),
        ):
            await start_handlers.menu_handler(message)

        self.assertEqual(len(message.answers), 2)
        self.assertEqual(message.answers[0]["text"], "⬇️ Главное меню снова закреплено снизу.")
        self.assertEqual(message.answers[0]["kwargs"]["reply_markup"], main_menu)
        self.assertEqual(message.answers[1]["kwargs"]["reply_markup"], home_keyboard)


class DeviceKeyDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_connection_uri_message_retries_without_copy_button_when_telegram_rejects_copy_text(self) -> None:
        class FlakyMessage(FakeBotMessage):
            def __init__(self) -> None:
                super().__init__()
                self._attempts = 0

            async def answer(self, text: str, parse_mode: str | None = None, **kwargs):
                self._attempts += 1
                if self._attempts == 1:
                    raise TelegramBadRequest(
                        method=SendMessage(chat_id=42, text="x"),
                        message="Telegram server says - Bad Request: BUTTON_COPY_TEXT_INVALID",
                    )
                return await super().answer(text, parse_mode=parse_mode, **kwargs)

        message = FlakyMessage()
        device = SimpleNamespace(id=42, email="Телефон", protocol="vless", user_id=7)
        metadata = {"device_name": "Телефон", "country_name": "Германия"}

        await device_handlers._send_connection_uri_message(
            message,
            device,
            metadata,
            "2026-04-06 12:00:00",
            f"vless://{'a' * 300}",
        )

        self.assertEqual(len(message.answers), 1)
        first_row = message.answers[0]["kwargs"]["reply_markup"].inline_keyboard[0]
        self.assertEqual(len(first_row), 1)
        self.assertEqual(first_row[0].text, "📷 Показать QR")


if __name__ == "__main__":
    unittest.main()
