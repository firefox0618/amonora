import json
import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.models import PaymentRecord
from dashboard.services import (
    assign_support_ticket_dashboard,
    close_support_ticket,
    confirm_payment_record,
    extend_subscription_for_user,
    grant_trial_to_user,
    reject_payment_record,
    remove_user_tariff,
    set_payment_record_status,
    set_user_block_state,
    set_user_preferred_protocol,
    transfer_support_ticket_dashboard,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DummySession:
    def __init__(self, result_value):
        self._result_value = result_value
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarResult(self._result_value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


class DashboardAuditEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    def _audit_payload(self, audit_mock: AsyncMock) -> dict:
        self.assertTrue(audit_mock.await_args_list)
        details = audit_mock.await_args_list[-1].args[4]
        self.assertIsInstance(details, str)
        return json.loads(details)

    async def test_grant_trial_audit_contains_before_after_and_sync_result(self) -> None:
        admin = SimpleNamespace(id=7, display_name="Owner")
        before_user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="trial-user",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="inactive",
            subscription_source=None,
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=False,
        )
        after_payload = dict(before_user.__dict__)
        after_payload.update(
            {
                "trial_expires_at": datetime(2026, 4, 6, 10, 0, 0),
                "trial_used": True,
            }
        )
        after_user = SimpleNamespace(**after_payload)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=before_user)),
            patch("dashboard.services.activate_trial", new=AsyncMock(return_value=after_user)),
            patch("dashboard.services.sync_user_clients_access", new=AsyncMock(return_value={"sync_failed": False, "processed_devices": 2, "failed_devices": 0})),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await grant_trial_to_user(41, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["trial_expires_at"], None)
        self.assertEqual(payload["after"]["trial_used"], True)
        self.assertEqual(payload["sync_result"]["processed_devices"], 2)

    async def test_extend_subscription_audit_contains_before_after_and_sync_result(self) -> None:
        admin = SimpleNamespace(id=9, display_name="Owner")
        user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="paid-user",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="inactive",
            subscription_source=None,
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=True,
        )
        fake_session = _DummySession(user)

        with (
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.sync_user_clients_access", new=AsyncMock(return_value={"sync_failed": False, "processed_devices": 1, "failed_devices": 0})),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.send_user_message_and_refresh_home", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await extend_subscription_for_user(41, 30, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["subscription_status"], "inactive")
        self.assertEqual(payload["after"]["subscription_status"], "active")
        self.assertEqual(payload["days"], 30)

    async def test_block_user_audit_contains_before_after_and_sync_result(self) -> None:
        admin = SimpleNamespace(id=3, display_name="Owner")
        user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="block-user",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=True,
        )
        fake_session = _DummySession(user)

        with (
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.sync_user_clients_access", new=AsyncMock(return_value={"sync_failed": False, "processed_devices": 1, "failed_devices": 0})),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.send_user_message_and_refresh_home", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await set_user_block_state(41, True, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertFalse(payload["before"]["is_blocked"])
        self.assertTrue(payload["after"]["is_blocked"])

    async def test_remove_user_tariff_audit_contains_before_after_and_sync_result(self) -> None:
        admin = SimpleNamespace(id=3, display_name="Owner")
        user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="paid-user",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=datetime(2026, 4, 1, 10, 0, 0),
            subscription_expires_at=datetime(2026, 5, 1, 10, 0, 0),
            trial_expires_at=None,
            trial_used=True,
        )
        fake_session = _DummySession(user)

        with (
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.sync_user_clients_access", new=AsyncMock(return_value={"sync_failed": False, "processed_devices": 1, "failed_devices": 0})),
            patch("dashboard.services.clear_vpn_repair_needed", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await remove_user_tariff(41, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["subscription_status"], "active")
        self.assertEqual(payload["after"]["subscription_status"], "inactive")

    async def test_set_user_preferred_protocol_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=3, display_name="Owner")
        user = SimpleNamespace(
            id=41,
            telegram_id=9041,
            username="proto-user",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=None,
            subscription_expires_at=None,
            trial_expires_at=None,
            trial_used=True,
        )
        fake_session = _DummySession(user)

        with (
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await set_user_preferred_protocol(41, "trojan", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["preferred_protocol"], "vless")
        self.assertEqual(payload["after"]["preferred_protocol"], "trojan")

    async def test_confirm_payment_record_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        before_record = PaymentRecord(
            id=73,
            user_id=51,
            payment_method="telegram_stars",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        after_record = PaymentRecord(
            id=73,
            user_id=51,
            payment_method="telegram_stars",
            payment_status="confirmed",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
            confirmed_at=datetime(2026, 4, 3, 12, 0, 0),
        )
        fake_session = _DummySession(before_record)

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[before_record, after_record, after_record])),
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services._finalize_confirmed_payment_access", new=AsyncMock(return_value={"sync_failed": False})),
            patch("dashboard.services.sync_income_entry_for_payment_record", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await confirm_payment_record(73, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["payment_status"], "awaiting_user_payment")
        self.assertEqual(payload["after"]["payment_status"], "confirmed")

    async def test_reject_payment_record_audit_contains_before_after_and_reason(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        before_record = PaymentRecord(
            id=91,
            user_id=51,
            payment_method="sbp_manual",
            payment_status="awaiting_admin_review",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        after_record = PaymentRecord(
            id=91,
            user_id=51,
            payment_method="sbp_manual",
            payment_status="rejected",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
            rejection_reason="bad proof",
        )

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[before_record, after_record])),
            patch("dashboard.services.reject_manual_payment", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await reject_payment_record(91, admin, "127.0.0.1", reason="bad proof")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["reason"], "bad proof")
        self.assertEqual(payload["before"]["payment_status"], "awaiting_admin_review")
        self.assertEqual(payload["after"]["payment_status"], "rejected")

    async def test_set_payment_record_status_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        record = PaymentRecord(
            id=77,
            user_id=51,
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        fake_session = _DummySession(record)

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch("dashboard.services.async_session", return_value=fake_session),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await set_payment_record_status(77, "expired", admin, "127.0.0.1", reason="timeout")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["payment_status"], "awaiting_user_payment")
        self.assertEqual(payload["after"]["payment_status"], "expired")
        self.assertEqual(payload["reason"], "timeout")

    async def test_assign_support_ticket_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=12, display_name="Support", telegram_id=7001)
        before_ticket = {"user_id": 88, "status": "new", "assigned_admin_id": None, "assigned_admin_name": None, "updated_at": None, "closed_at": None}
        after_ticket = {"user_id": 88, "status": "in_progress", "assigned_admin_id": 7001, "assigned_admin_name": "Support", "updated_at": "2026-04-03T12:00:00", "closed_at": None}

        with (
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=before_ticket)),
            patch("dashboard.services.assign_ticket", new=AsyncMock(return_value=after_ticket)),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await assign_support_ticket_dashboard(88, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["assigned_admin_id"], None)
        self.assertEqual(payload["after"]["assigned_admin_id"], 7001)

    async def test_transfer_support_ticket_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=12, display_name="Support", telegram_id=7001)
        before_ticket = {"user_id": 88, "status": "in_progress", "assigned_admin_id": 7001, "assigned_admin_name": "Support", "updated_at": None, "closed_at": None}
        after_ticket = {"user_id": 88, "status": "in_progress", "assigned_admin_id": 7002, "assigned_admin_name": "New Admin", "updated_at": "2026-04-03T12:00:00", "closed_at": None}

        with (
            patch("dashboard.services.get_support_admin_choices", new=AsyncMock(return_value=[{"telegram_id": 7002, "display_name": "New Admin"}])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=before_ticket)),
            patch("dashboard.services.transfer_ticket", new=AsyncMock(return_value=after_ticket)),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await transfer_support_ticket_dashboard(88, 7002, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["assigned_admin_id"], 7001)
        self.assertEqual(payload["after"]["assigned_admin_id"], 7002)

    async def test_close_support_ticket_audit_contains_before_after_and_notification_flag(self) -> None:
        admin = SimpleNamespace(id=12, display_name="Support")
        before_ticket = {"user_id": 88, "status": "in_progress", "assigned_admin_id": 7001, "assigned_admin_name": "Support", "updated_at": None, "closed_at": None}
        after_ticket = {"user_id": 88, "status": "closed", "assigned_admin_id": None, "assigned_admin_name": None, "updated_at": "2026-04-03T12:01:00", "closed_at": "2026-04-03T12:01:00"}

        with (
            patch("dashboard.services.get_ticket", new=AsyncMock(side_effect=[before_ticket, after_ticket])),
            patch("dashboard.services.close_ticket", new=AsyncMock()),
            patch("dashboard.services._notify_support_user_closed", new=AsyncMock(return_value=True)),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await close_support_ticket(88, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertTrue(payload["user_notified"])
        self.assertEqual(payload["before"]["status"], "in_progress")
        self.assertEqual(payload["after"]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
