import json
import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.models import FinanceEntry, PaymentRecord
from dashboard.services import (
    _delete_device_remote_state,
    _is_retired_estonia_xui_admin_device,
    create_device_for_user,
    create_payment_record,
    delete_device_for_user,
    delete_payment_record,
    delete_user_with_access,
    send_manual_payment_reminder,
    send_support_reply,
    sync_payment_record_with_provider,
)


class _ScalarResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._scalar, list):
            return self._scalar
        return []


class _ExistsSession:
    def __init__(self, scalar) -> None:
        self.scalar = scalar

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarResult(self.scalar)


class _DeviceReadSession:
    def __init__(self, device) -> None:
        self.device = device
        self.deleted = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        return _ScalarResult(self.device)

    async def refresh(self, _obj):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True


class _DeletePaymentSession:
    def __init__(self, record, finance_rows) -> None:
        self.record = record
        self.finance_rows = finance_rows
        self.deleted = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "FROM payment_records" in text:
            return _ScalarResult(self.record)
        if "FROM finance_entries" in text:
            return _ScalarResult(self.finance_rows)
        raise AssertionError(f"Unexpected SQL in delete-payment test: {text}")

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True


class _DeleteUserAuditSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        if "SELECT payment_records.id " in text and "FROM payment_records" in text:
            return _ScalarResult([401, 402])
        if "SELECT support_tickets.id " in text and "FROM support_tickets" in text:
            return _ScalarResult([701])
        return _ScalarResult()

    async def commit(self):
        self.committed = True


class DashboardOperatorAuditFollowupTests(unittest.IsolatedAsyncioTestCase):
    def _audit_payload(self, audit_mock: AsyncMock) -> dict:
        self.assertTrue(audit_mock.await_args_list)
        details = audit_mock.await_args_list[-1].args[4]
        self.assertIsInstance(details, str)
        return json.loads(details)

    async def test_create_payment_record_audit_contains_after_snapshot(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        tariff = SimpleNamespace(code="1m", rub_price=149, duration_days=30, title="1 month")
        record = PaymentRecord(
            id=55,
            user_id=77,
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )

        with (
            patch("dashboard.services._get_runtime_tariff", return_value=tariff),
            patch("dashboard.services.async_session", return_value=_ExistsSession(77)),
            patch("dashboard.services.get_open_payment_intent_for_user", new=AsyncMock(return_value=None)),
            patch("dashboard.services.create_manual_payment_record", new=AsyncMock(return_value=record)),
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(return_value=record)),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await create_payment_record(77, "sbp_manual", "1m", "awaiting_user_payment", "", "", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertIsNone(payload["before"])
        self.assertEqual(payload["after"]["payment_method"], "sbp_manual")
        self.assertEqual(payload["after"]["payment_status"], "awaiting_user_payment")

    async def test_sync_payment_record_provider_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=1)
        before_record = PaymentRecord(
            id=91,
            user_id=77,
            payment_method="sbp_platega",
            payment_status="pending",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
        )
        after_record = PaymentRecord(
            id=91,
            user_id=77,
            payment_method="sbp_platega",
            payment_status="confirmed",
            tariff_code="1m",
            amount=149,
            currency="RUB",
            duration_days=30,
            confirmed_at=datetime(2026, 4, 3, 12, 0, 0),
        )

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[before_record, after_record])),
            patch(
                "dashboard.services.sync_platega_record_by_id",
                new=AsyncMock(return_value={"provider_status": "PAID", "just_confirmed": True, "provider_sync_problem": None}),
            ),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await sync_payment_record_with_provider(91, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["payment_status"], "pending")
        self.assertEqual(payload["after"]["payment_status"], "confirmed")
        self.assertEqual(payload["provider_status"], "PAID")

    async def test_send_manual_payment_reminder_audit_contains_before_after(self) -> None:
        admin = SimpleNamespace(id=1)
        record = PaymentRecord(
            id=92,
            user_id=77,
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=99,
            list_price_amount=149,
            currency="RUB",
            duration_days=30,
        )
        user = SimpleNamespace(id=77, telegram_id=900077)

        with (
            patch("dashboard.services.get_payment_record_by_id", new=AsyncMock(side_effect=[record, record])),
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_tariff", return_value=SimpleNamespace(title="1 month")),
            patch("dashboard.services.send_user_message", new=AsyncMock(return_value=True)),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await send_manual_payment_reminder(92, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["payment_status"], "awaiting_user_payment")
        self.assertEqual(payload["after"]["payment_method"], "sbp_manual")
        self.assertTrue(payload["delivered"])

    async def test_delete_payment_record_audit_contains_before_and_null_after(self) -> None:
        admin = SimpleNamespace(id=1)
        record = PaymentRecord(
            id=93,
            user_id=77,
            payment_method="sbp_manual",
            payment_status="awaiting_user_payment",
            tariff_code="1m",
            amount=99,
            currency="RUB",
            duration_days=30,
        )
        finance_rows = [FinanceEntry(id=301), FinanceEntry(id=302)]
        session = _DeletePaymentSession(record, finance_rows)

        with (
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services._release_reserved_balance_for_record", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            deleted = await delete_payment_record(93, admin, "127.0.0.1")

        self.assertTrue(deleted)
        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["payment_method"], "sbp_manual")
        self.assertIsNone(payload["after"])
        self.assertEqual(payload["finance_entries_removed"], [301, 302])

    async def test_create_device_for_user_audit_contains_created_device_snapshot(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        user = SimpleNamespace(id=77, telegram_id=700077, username="user-77", subscription_status="active")
        provisioner = SimpleNamespace(
            provision_vless_client=AsyncMock(
                return_value=SimpleNamespace(
                    vpn_client_id=501,
                    client_uuid="uuid-501",
                    email="dashboard_77_device",
                    metadata={},
                )
            ),
            close=AsyncMock(),
        )

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 5, 1, 12, 0, 0))),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={77: 0})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_device_limit_for_user", return_value=3),
            patch("dashboard.services.region_supports_protocol", return_value=True),
            patch("dashboard.services.get_vless_provisioner", return_value=provisioner),
            patch("dashboard.services.update_vpn_client_metadata", new=AsyncMock()),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await create_device_for_user(77, "Pixel 9", "phone", "vless", "de", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertIsNone(payload["before"])
        self.assertEqual(payload["after"]["id"], 501)
        self.assertEqual(payload["after"]["device_name"], "Pixel 9")
        self.assertEqual(payload["after"]["country_code"], "de")

    async def test_delete_device_for_user_audit_contains_before_and_null_after(self) -> None:
        admin = SimpleNamespace(id=5, display_name="Owner")
        device = SimpleNamespace(
            id=602,
            user_id=77,
            email="device-602",
            protocol="vless",
            client_uuid="uuid-602",
            xui_client_id=None,
            client_data=json.dumps({"country_code": "de", "device_name": "MacBook", "device_type": "desktop", "protocol": "vless"}),
            created_at=datetime(2026, 4, 3, 12, 0, 0),
        )
        read_session = _DeviceReadSession(device)
        delete_session = _DeviceReadSession(device)

        with (
            patch("dashboard.services.async_session", side_effect=[read_session, delete_session]),
            patch("dashboard.services._delete_device_remote_state", new=AsyncMock()),
            patch("dashboard.services.get_access_expires_at", new=AsyncMock(return_value=datetime(2026, 5, 1, 12, 0, 0))),
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=SimpleNamespace(id=77, telegram_id=700077, username="user-77"))),
            patch("dashboard.services.create_control_event", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await delete_device_for_user(602, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["id"], 602)
        self.assertEqual(payload["before"]["device_name"], "MacBook")
        self.assertIsNone(payload["after"])

    async def test_delete_device_remote_state_skips_retired_estonia_xui_admin_device(self) -> None:
        device = SimpleNamespace(
            id=239,
            protocol="vless",
            client_uuid="uuid-239",
            xui_client_id=None,
            email="dashboard_17_ec1d2e6780a6",
        )
        metadata = {
            "country_code": "ee",
            "provider_type": "xui",
            "admin_visible": True,
            "reserve_only": True,
            "user_selectable": False,
        }

        with patch("dashboard.services.get_vless_provisioner") as provisioner_mock:
            await _delete_device_remote_state(device, metadata)

        provisioner_mock.assert_not_called()

    def test_retired_estonia_xui_admin_device_detection_requires_dashboard_metadata(self) -> None:
        self.assertTrue(
            _is_retired_estonia_xui_admin_device(
                {
                    "country_code": "ee",
                    "provider_type": "xui",
                    "admin_visible": True,
                    "reserve_only": True,
                    "user_selectable": False,
                },
                email="dashboard_18_a1287644f157",
            )
        )
        self.assertFalse(
            _is_retired_estonia_xui_admin_device(
                {
                    "country_code": "ee",
                    "provider_type": "xui",
                    "admin_visible": True,
                    "reserve_only": True,
                    "user_selectable": False,
                },
                email="device_18_regular",
            )
        )

    async def test_delete_user_with_access_audit_contains_before_and_null_after(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(
            id=88,
            telegram_id=700088,
            username="user-88",
            is_blocked=False,
            preferred_protocol="vless",
            subscription_status="active",
            subscription_source="manual",
            subscription_started_at=None,
            subscription_expires_at=datetime(2026, 5, 1, 12, 0, 0),
            trial_expires_at=None,
            trial_used=True,
        )
        device = SimpleNamespace(id=1, client_data=json.dumps({"country_code": "de"}))
        session = _DeleteUserAuditSession()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services._device_metadata", return_value={"country_code": "de"}),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=905))),
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock()),
            patch("dashboard.services._delete_device_remote_state", new=AsyncMock()),
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            await delete_user_with_access(88, admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["username"], "user-88")
        self.assertIsNone(payload["after"])
        self.assertEqual(payload["devices_deleted"], 1)
        self.assertEqual(payload["deletion_job_id"], 905)

    async def test_send_support_reply_audit_contains_before_after_and_message_info(self) -> None:
        admin = SimpleNamespace(id=7, display_name="Owner", telegram_id=7007)
        before_ticket = {"user_id": 88, "status": "open", "assigned_to": None, "messages_count": 2}
        after_ticket = {"user_id": 88, "status": "open", "assigned_to": None, "messages_count": 3}
        fake_bot = SimpleNamespace(send_message=AsyncMock(), session=SimpleNamespace(close=AsyncMock()))

        with (
            patch("dashboard.services.config.support_bot_token", "token"),
            patch("dashboard.services.get_ticket", new=AsyncMock(side_effect=[before_ticket, after_ticket])),
            patch("dashboard.services.Bot", return_value=fake_bot),
            patch("dashboard.services.register_admin_reply", new=AsyncMock(return_value={"id": 1})),
            patch("dashboard.services.invalidate_runtime_cache"),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
        ):
            await send_support_reply(88, "Ответ пользователю", admin, "127.0.0.1")

        payload = self._audit_payload(audit_mock)
        self.assertEqual(payload["before"]["messages_count"], 2)
        self.assertEqual(payload["after"]["messages_count"], 3)
        self.assertEqual(payload["message_length"], len("Ответ пользователю"))
        self.assertTrue(payload["delivered"])


if __name__ == "__main__":
    unittest.main()
