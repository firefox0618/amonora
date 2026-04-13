import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import control_bot.queries as control_queries


def _keyboard_texts(markup) -> list[str]:
    texts: list[str] = []
    for row in markup.inline_keyboard:
        for button in row:
            texts.append(button.text)
    return texts


class ControlQueriesTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_payments_screen_shows_telegram_review_entries_without_panel_links(self) -> None:
        record = SimpleNamespace(
            id=41,
            user_id=7,
            telegram_id=70123456,
            payment_status="awaiting_admin_review",
            payment_method="sbp_manual",
            amount=299,
            currency="RUB",
            created_at=control_queries.utcnow(),
        )

        with (
            patch("control_bot.queries.list_payment_records", new=AsyncMock(return_value=[record])),
        ):
            _, keyboard = await control_queries.build_payments_screen_for(5487345316)

        self.assertIsNotNone(keyboard)
        texts = _keyboard_texts(keyboard)
        self.assertIn("🔄 Обновить", texts)
        self.assertIn("💳 Заявка #41", texts)
        self.assertNotIn("👤 Открыть пользователя", texts)
        self.assertNotIn("💳 Открыть платёж", texts)

    async def test_build_payment_focus_shows_review_actions_for_operator(self) -> None:
        payment_focus = {
            "id": 73,
            "user_id": 88,
            "telegram_id": 123456,
            "username": "focus_user",
            "payment_status": "awaiting_admin_review",
            "payment_method": "sbp_manual",
            "amount": 299,
            "currency": "RUB",
            "duration_days": 30,
            "tariff_code": "1m",
            "list_price_amount": 299,
            "balance_reserved_amount": 0,
            "balance_applied_amount": 0,
            "reference": "ABC",
            "note": "Комментарий",
        }

        with (
            patch("control_bot.queries.get_payment_focus", new=AsyncMock(return_value=payment_focus)),
            patch("control_bot.queries.control_role_for_telegram_id", return_value="operator"),
        ):
            _, keyboard = await control_queries.build_payment_focus(73, 5487345316)

        texts = _keyboard_texts(keyboard)
        self.assertIn("✅ Подтвердить", texts)
        self.assertIn("❌ Отклонить", texts)
        self.assertIn("🔄 Обновить", texts)
        self.assertIn("👤 Открыть пользователя", texts)
        self.assertNotIn("💳 Открыть платёж", texts)

    async def test_build_login_codes_screen_returns_no_buttons_for_non_owner(self) -> None:
        with (
            patch("control_bot.queries.list_active_dashboard_sessions", new=AsyncMock(return_value=[])),
            patch("control_bot.queries.control_role_for_telegram_id", return_value="admin"),
        ):
            _, keyboard = await control_queries.build_login_codes_screen(548589949)

        self.assertIsNotNone(keyboard)
        self.assertEqual(_keyboard_texts(keyboard), ["🔄 Обновить"])

    async def test_build_login_codes_screen_keeps_only_terminate_for_owner(self) -> None:
        session = {
            "username": "rudolf",
            "telegram_id": 895068,
            "ttl_minutes": 180,
            "created_at": control_queries.utcnow(),
        }
        with (
            patch("control_bot.queries.list_active_dashboard_sessions", new=AsyncMock(return_value=[session])),
            patch("control_bot.queries.control_role_for_telegram_id", return_value="owner"),
        ):
            text, keyboard = await control_queries.build_login_codes_screen(7650618403)

        self.assertIn("rudolf", text)
        self.assertIn("89••68", text)
        texts = _keyboard_texts(keyboard)
        self.assertEqual(texts, ["🔒 Завершить все", "🔄 Обновить"])

    async def test_build_last_events_screen_filters_by_severity(self) -> None:
        critical = SimpleNamespace(category="nodes", severity="CRITICAL", title="Critical node", created_at=control_queries.utcnow())
        info = SimpleNamespace(category="users", severity="INFO", title="Info user", created_at=control_queries.utcnow())
        with patch("control_bot.queries.list_control_events", new=AsyncMock(return_value=[critical, info])):
            text, _ = await control_queries.build_last_events_screen(severity_filter="CRITICAL")

        self.assertIn("Critical node", text)
        self.assertNotIn("Info user", text)

    async def test_build_last_events_screen_includes_short_request_id_when_present(self) -> None:
        event = SimpleNamespace(
            id=1,
            category="system",
            severity="INFO",
            title="User updated",
            created_at=control_queries.utcnow(),
            payload_json="{}",
            request_id="req-1234567890",
        )

        with patch("control_bot.queries.list_control_events", new=AsyncMock(return_value=[event])):
            text, _ = await control_queries.build_last_events_screen()

        self.assertIn("req <code>req-1234</code>", text)

    async def test_build_problems_screen_includes_core_sections(self) -> None:
        overview_payload = {
            "system_alerts": {
                "payments": {
                    "pending_confirmations": 2,
                    "stale_pending_confirmations": 1,
                    "oldest_pending_manual_payments": [{"payment_id": 55}],
                },
                "support": {
                    "open_tickets": 3,
                    "new_tickets": 1,
                    "oldest_open_tickets": [{"ticket_user_id": 7001, "label": "@user"}],
                },
                "nodes": {
                    "issues": 1,
                    "down": 1,
                    "degraded": 0,
                    "items": [{"server_id": 9, "name": "Germany"}],
                },
            },
            "attention": {
                "repair_needed_users": [{"user_id": 88, "username": "damaged"}],
                "summary": {
                    "repair_needed": 1,
                    "sync_errors": 1,
                    "high_priority_repairs": 1,
                },
            },
        }
        with patch("control_bot.queries.get_v2_overview_payload", new=AsyncMock(return_value=overview_payload)):
            text, keyboard = await control_queries.build_problems_screen()

        self.assertIn("ПЛАТЕЖИ", text)
        self.assertIn("ДОСТУП / REPAIR", text)
        self.assertIn("ПОДДЕРЖКА", text)
        self.assertIn("НОДЫ", text)
        self.assertIn("💳 Платёж #55", _keyboard_texts(keyboard))

    async def test_build_support_screen_lists_ticket_buttons(self) -> None:
        support_payload = {
            "tickets": [
                {
                    "user_id": 7001,
                    "username": "focus_user",
                    "full_name": "Focus User",
                    "status": "new",
                    "last_user_message_preview": "Не работает VPN",
                }
            ],
            "counts": {"all": 1, "new": 1, "in_progress": 0, "mine": 0, "closed": 0},
        }
        with patch("control_bot.queries.get_v2_support_payload", new=AsyncMock(return_value=support_payload)):
            text, keyboard = await control_queries.build_support_screen()

        self.assertIn("ПОДДЕРЖКА", text)
        self.assertIn("focus_user", text)
        self.assertIn("💬 focus_user", _keyboard_texts(keyboard))

    async def test_build_node_focus_uses_refresh_label_instead_of_resync(self) -> None:
        payload = {
            "selected_node": {
                "id": 4,
                "name": "Germany",
                "country_name": "Германия",
                "status_label": "Активна",
                "host": "1.2.3.4",
                "cpu_percent": 11,
                "memory_used_percent": 22,
                "disk_used_percent": 33,
                "total_network_mbps": 44,
                "active_devices": 5,
                "uptime": "1d",
                "service_pills": [],
            }
        }

        with patch("control_bot.queries.get_v2_servers_payload", new=AsyncMock(return_value=payload)):
            _, keyboard = await control_queries.build_node_focus(4)

        texts = _keyboard_texts(keyboard)
        self.assertIn("🔄 Обновить статус", texts)
        self.assertNotIn("🔄 Resync", texts)

    async def test_build_settings_screen_marks_mandatory_categories_as_locked(self) -> None:
        profiles = [
            {
                "telegram_id": 5487345316,
                "role": "operator",
                "display_name": "Менеджер",
                "username": "manager",
                "enabled_count": 4,
                "total_count": 6,
                "preferences": {
                    "payments": True,
                    "users": True,
                    "support": True,
                    "nodes": False,
                    "security": True,
                    "system": False,
                },
            }
        ]

        with (
            patch("control_bot.queries.list_notification_preference_rows", new=AsyncMock(return_value=profiles)),
            patch("control_bot.queries.control_role_for_telegram_id", return_value="operator"),
        ):
            text, keyboard = await control_queries.build_settings_screen(5487345316)

        self.assertIn("Платежи 🔒", text)
        self.assertIn("Безопасность 🔒", text)
        texts = _keyboard_texts(keyboard)
        self.assertIn("🔒 Платежи", texts)
        self.assertIn("🔒 Безопасность", texts)
        self.assertIn("❌ Ноды и инфраструктура", texts)

    async def test_build_help_screen_keeps_channel_commands_in_command_block_and_mentions_channel_post_flow(self) -> None:
        with patch("control_bot.queries.control_role_for_telegram_id", return_value="owner"):
            text, _ = await control_queries.build_help_screen(7650618403)

        self.assertIn("📢 /broadcast  — owner-only рассылки и триггеры", text)
        self.assertIn("📣 /channel   — owner/admin контент-план канала", text)
        self.assertIn("Перешлите сюда пост из канала", text)
        self.assertLess(
            text.index("📢 /broadcast  — owner-only рассылки и триггеры"),
            text.index("📣 /channel   — owner/admin контент-план канала"),
        )
        self.assertLess(
            text.index("📣 /channel   — owner/admin контент-план канала"),
            text.index("Перешлите сюда пост из канала"),
        )

    async def test_build_user_focus_uses_dynamic_device_limit_from_payload(self) -> None:
        payload = {
            "user": {
                "id": 11,
                "username": "alice",
                "telegram_id": 7111,
                "status_label": "Активен",
                "status": "paid_active",
                "plan_label": "3 месяца",
                "access_expires_at": "2026-06-01 12:00:00",
                "max_devices": 5,
                "preferred_protocol": "vless",
                "trial_used": True,
                "is_blocked": False,
                "balance_rub": 0,
            },
            "devices": [{}, {}, {}, {}],
            "support_ticket": None,
            "payments": [],
            "vpn_repair_state": {"repair_needed": False},
        }

        with patch("control_bot.queries.get_v2_user_detail_payload", new=AsyncMock(return_value=payload)):
            text, _ = await control_queries.build_user_focus(11)

        self.assertIn("Устройства: <b>4/5</b>", text)


if __name__ == "__main__":
    unittest.main()
