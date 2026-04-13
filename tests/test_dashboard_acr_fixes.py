import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from dashboard.services import (
    _apply_env_runtime_changes,
    close_support_ticket,
    deep_repair_user_access,
    extend_subscription_for_user,
    send_manual_payment_reminder,
    send_support_reply,
    sync_user_clients_access,
    transfer_support_ticket_dashboard,
    update_env_value,
)
from dashboard.v2_data import _available_payment_status_actions
from dashboard.models import PaymentRecord


class DashboardAcrFixesTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_user_clients_access_reports_partial_failure(self) -> None:
        user = SimpleNamespace(id=41)
        devices = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=devices)),
            patch("dashboard.services.get_access_expires_at_from_user", return_value="expires"),
            patch(
                "dashboard.services._sync_single_device_access",
                new=AsyncMock(
                    side_effect=[
                        {"device_id": 1, "status": "success"},
                        {"device_id": 2, "status": "failed", "reason": "sync_error"},
                    ]
                ),
            ),
        ):
            result = await sync_user_clients_access(41)

        self.assertTrue(result["sync_failed"])
        self.assertEqual(result["processed_devices"], 2)
        self.assertEqual(result["successful_devices"], 1)
        self.assertEqual(result["failed_devices"], 1)

    async def test_deep_repair_user_access_marks_failure_if_post_sync_fails(self) -> None:
        admin = SimpleNamespace(id=7, display_name="Owner")

        with (
            patch(
                "dashboard.services._run_user_repair_operation",
                new=AsyncMock(
                    return_value={
                        "sync_failed": False,
                        "repair_needed": False,
                        "reason": None,
                        "failed_devices": 0,
                    }
                ),
            ),
            patch(
                "dashboard.services.sync_user_clients_access",
                new=AsyncMock(
                    return_value={
                        "sync_failed": True,
                        "processed_devices": 1,
                        "successful_devices": 0,
                        "failed_devices": 1,
                        "results": [{"device_id": 11, "status": "failed", "reason": "sync_error"}],
                    }
                ),
            ),
            patch("dashboard.services.mark_vpn_repair_needed", new=AsyncMock()) as mark_mock,
            patch("dashboard.services.create_vpn_repair_event", new=AsyncMock()) as event_mock,
        ):
            result = await deep_repair_user_access(41, admin, "127.0.0.1")

        self.assertTrue(result["sync_failed"])
        self.assertTrue(result["repair_needed"])
        self.assertEqual(result["reason"], "manual_repair_sync_failed")
        mark_mock.assert_awaited_once_with(41, "manual_repair_sync_failed")
        event_mock.assert_awaited_once_with(41, "failed", "manual_repair_sync_failed")

    async def test_transfer_support_ticket_dashboard_rejects_unknown_admin(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Manager")

        with patch("dashboard.services.get_support_admin_choices", new=AsyncMock(return_value=[])):
            with self.assertRaisesRegex(ValueError, "неактивному или неизвестному администратору"):
                await transfer_support_ticket_dashboard(77, 999999, admin, "127.0.0.1")

    async def test_extend_subscription_clears_repair_marker_without_extra_control_notice(self) -> None:
        admin = SimpleNamespace(id=55, display_name="Owner")
        user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="repair-user",
            subscription_expires_at=None,
            subscription_started_at=None,
            subscription_status="inactive",
            subscription_source=None,
        )

        fake_scalar = SimpleNamespace(scalar_one_or_none=lambda: user)
        fake_session = AsyncMock()
        fake_session.execute = AsyncMock(return_value=fake_scalar)
        fake_session.commit = AsyncMock()
        fake_session.__aenter__.return_value = fake_session
        fake_session.__aexit__.return_value = None

        with (
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.sync_user_clients_access", new=AsyncMock(return_value={"sync_failed": False})),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
            patch("dashboard.services.create_control_event", new=AsyncMock()) as control_event_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.send_user_message_and_refresh_home", new=AsyncMock()) as notify_mock,
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            await extend_subscription_for_user(41, 30, admin, "127.0.0.1")

        clear_mock.assert_awaited_once_with(41, emit_control_event=False)
        control_event_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()
        notify_mock.assert_awaited_once()

    async def test_close_support_ticket_returns_notification_state(self) -> None:
        admin = SimpleNamespace(id=12)

        with (
            patch("dashboard.services.get_ticket", new=AsyncMock(side_effect=[{"user_id": 88, "status": "in_progress"}, {"user_id": 88, "status": "closed"}])),
            patch("dashboard.services.close_ticket", new=AsyncMock()) as close_mock,
            patch("dashboard.services._notify_support_user_closed", new=AsyncMock(return_value=False)) as notify_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.invalidate_runtime_cache") as cache_mock,
        ):
            result = await close_support_ticket(88, admin, "127.0.0.1")

        self.assertEqual(result, {"closed": True, "user_notified": False})
        close_mock.assert_awaited_once_with(88)
        notify_mock.assert_awaited_once_with(88)
        audit_mock.assert_awaited_once()
        cache_mock.assert_called_once_with("overview_metrics")

    async def test_update_env_value_rejects_multiline_value(self) -> None:
        admin = SimpleNamespace(id=1)

        with self.assertRaisesRegex(ValueError, "не должно содержать перевод строки"):
            await update_env_value("DASHBOARD_TITLE", "line1\nline2", admin, "127.0.0.1")

    async def test_update_env_value_rejects_dangerous_secret_like_keys(self) -> None:
        admin = SimpleNamespace(id=1)

        with self.assertRaisesRegex(ValueError, "нельзя менять через панель"):
            await update_env_value("BOT_TOKEN", "secret", admin, "127.0.0.1")

    async def test_update_env_value_rejects_non_allowlisted_keys_even_if_they_look_safe(self) -> None:
        admin = SimpleNamespace(id=1)

        with self.assertRaisesRegex(ValueError, "нельзя менять через панель"):
            await update_env_value("SAFE_KEY", "value", admin, "127.0.0.1")

    async def test_apply_env_runtime_changes_reports_verified_and_failed_services(self) -> None:
        async def fake_system_command(*args):
            if args == ("systemctl", "restart", "svc-ok.service"):
                return 0, ""
            if args == ("systemctl", "is-active", "svc-ok.service"):
                return 0, "active\n"
            if args == ("systemctl", "restart", "svc-bad.service"):
                return 0, ""
            if args == ("systemctl", "is-active", "svc-bad.service"):
                return 3, "failed\n"
            raise AssertionError(f"unexpected system command: {args}")

        with patch("dashboard.services._system_command", new=AsyncMock(side_effect=fake_system_command)):
            result = await _apply_env_runtime_changes(["svc-ok.service", "svc-bad.service"])

        self.assertEqual(result["applied_services"], ["svc-ok.service", "svc-bad.service"])
        self.assertEqual(result["verified_services"], ["svc-ok.service"])
        self.assertEqual(result["failed_services"][0]["service_name"], "svc-bad.service")
        self.assertFalse(result["applied_ok"])

    async def test_update_env_value_can_apply_runtime_and_clear_restart_required(self) -> None:
        admin = SimpleNamespace(id=1)
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("DASHBOARD_TITLE=Old title\n", encoding="utf-8")
            with (
                patch("dashboard.services.ENV_PATH", env_path),
                patch(
                    "dashboard.services._apply_env_runtime_changes",
                    new=AsyncMock(
                        return_value={
                            "applied_services": ["amonora-dashboard.service"],
                            "verified_services": ["amonora-dashboard.service"],
                            "failed_services": [],
                            "applied_ok": True,
                        }
                    ),
                ) as apply_mock,
                patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            ):
                result = await update_env_value(
                    "DASHBOARD_TITLE",
                    "New title",
                    admin,
                    "127.0.0.1",
                    apply_runtime=False,
                )

        self.assertFalse(result["restart_required"])
        self.assertEqual(result["runtime_apply"]["verified_services"], ["amonora-dashboard.service"])
        self.assertEqual(result["runtime_apply"]["runtime_state"], "applied")
        apply_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()

    async def test_update_env_value_rolls_back_if_runtime_apply_fails(self) -> None:
        admin = SimpleNamespace(id=1)
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("DASHBOARD_TITLE=Old title\n", encoding="utf-8")
            with (
                patch("dashboard.services.ENV_PATH", env_path),
                patch(
                    "dashboard.services._apply_env_runtime_changes",
                    new=AsyncMock(
                        side_effect=[
                            {
                                "applied_services": ["amonora-dashboard.service"],
                                "verified_services": [],
                                "failed_services": [{"service_name": "amonora-dashboard.service", "error": "failed"}],
                                "applied_ok": False,
                            },
                            {
                                "applied_services": ["amonora-dashboard.service"],
                                "verified_services": ["amonora-dashboard.service"],
                                "failed_services": [],
                                "applied_ok": True,
                            },
                        ]
                    ),
                ) as apply_mock,
                patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            ):
                with self.assertRaisesRegex(ValueError, "изменения откатили"):
                    await update_env_value(
                        "DASHBOARD_TITLE",
                        "Broken title",
                        admin,
                        "127.0.0.1",
                    )
            self.assertEqual(env_path.read_text(encoding="utf-8"), "DASHBOARD_TITLE=Old title\n")

        self.assertEqual(apply_mock.await_count, 2)
        audit_mock.assert_awaited_once()

    async def test_send_support_reply_rejects_missing_ticket_before_telegram_delivery(self) -> None:
        admin = SimpleNamespace(id=17, display_name="Support Lead", telegram_id=7701)

        with (
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.Bot") as bot_cls,
        ):
            with self.assertRaisesRegex(ValueError, "Тикет не найден"):
                await send_support_reply(88, "Ответ", admin, "127.0.0.1")

        bot_cls.assert_not_called()

    async def test_send_support_reply_surfaces_blocked_support_bot_as_value_error(self) -> None:
        admin = SimpleNamespace(id=17, display_name="Support Lead", telegram_id=7701)
        fake_bot = SimpleNamespace(
            send_message=AsyncMock(
                side_effect=TelegramForbiddenError(
                    SendMessage(chat_id=88, text="Ответ"),
                    "bot was blocked by the user",
                )
            ),
            session=SimpleNamespace(close=AsyncMock()),
        )

        with (
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value={"user_id": 88})),
            patch("dashboard.services.Bot", return_value=fake_bot),
        ):
            with self.assertRaisesRegex(ValueError, "заблокировал support-бота"):
                await send_support_reply(88, "Ответ", admin, "127.0.0.1")

        fake_bot.send_message.assert_awaited_once()
        fake_bot.session.close.assert_awaited_once()

    async def test_send_manual_payment_reminder_delivers_to_open_sbp_manual_record(self) -> None:
        admin = SimpleNamespace(id=17, display_name="Support Lead", telegram_id=7701)
        record = SimpleNamespace(
            id=91,
            user_id=44,
            tariff_code="3m",
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            metadata_json='{"tariff_title":"3 месяца"}',
        )
        user = SimpleNamespace(id=44, telegram_id=100044)

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[record, record])),
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.send_user_message", new=AsyncMock(return_value=True)) as send_mock,
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            result = await send_manual_payment_reminder(91, admin, "127.0.0.1")

        self.assertEqual(result["record"], record)
        send_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()

    async def test_send_manual_payment_reminder_rejects_non_open_manual_sbp_record(self) -> None:
        admin = SimpleNamespace(id=17, display_name="Support Lead", telegram_id=7701)
        record = SimpleNamespace(
            id=92,
            user_id=44,
            tariff_code="3m",
            payment_method="sbp_manual",
            payment_status="confirmed",
            metadata_json="{}",
        )

        with patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(return_value=record)):
            with self.assertRaisesRegex(ValueError, "только для открытых заявок Ручная СБП"):
                await send_manual_payment_reminder(92, admin, "127.0.0.1")

    async def test_manual_waiting_payment_actions_do_not_offer_confirm_or_reject(self) -> None:
        record = PaymentRecord(
            id=1,
            user_id=44,
            tariff_code="1m",
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            amount=149,
            currency="RUB",
            duration_days=30,
        )

        actions = _available_payment_status_actions(record)

        self.assertNotIn("confirmed", actions)
        self.assertNotIn("rejected", actions)
        self.assertEqual(actions, ["expired", "disputed", "error"])


if __name__ == "__main__":
    unittest.main()
