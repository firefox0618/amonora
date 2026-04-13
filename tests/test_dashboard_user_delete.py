import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.services import delete_user_with_access


class _FakeAsyncResult:
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


class _DeleteUserSession:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        if "SELECT payment_records.id " in text and "FROM payment_records" in text:
            return _FakeAsyncResult([401, 402])
        if "SELECT support_tickets.id " in text and "FROM support_tickets" in text:
            return _FakeAsyncResult([701])
        if "UPDATE control_broadcast_deliveries SET user_id" in text:
            return _FakeAsyncResult()
        if "UPDATE control_trigger_delivery_logs SET user_id" in text:
            return _FakeAsyncResult()
        if "UPDATE users SET referred_by_user_id" in text:
            return _FakeAsyncResult()
        if "DELETE FROM referral_rewards" in text:
            return _FakeAsyncResult()
        if "DELETE FROM referrals" in text:
            return _FakeAsyncResult()
        if "DELETE FROM support_ticket_messages" in text:
            return _FakeAsyncResult()
        if "DELETE FROM support_tickets" in text:
            return _FakeAsyncResult()
        if "DELETE FROM user_balance_events" in text:
            return _FakeAsyncResult()
        if "DELETE FROM vpn_repair_events" in text:
            return _FakeAsyncResult()
        if "DELETE FROM channel_post_touches" in text:
            return _FakeAsyncResult()
        if "DELETE FROM device_slot_entitlements" in text:
            return _FakeAsyncResult()
        if "DELETE FROM vpn_client_activations" in text:
            return _FakeAsyncResult()
        if "DELETE FROM finance_entries" in text:
            return _FakeAsyncResult()
        if "DELETE FROM payment_records" in text:
            return _FakeAsyncResult()
        if "DELETE FROM vpn_clients" in text:
            return _FakeAsyncResult()
        if "DELETE FROM users" in text:
            return _FakeAsyncResult()
        raise AssertionError(f"Unexpected SQL statement: {text}")


class _FailingDeleteUserSession(_DeleteUserSession):
    def __init__(self, *, fail_on_commit: bool = True) -> None:
        super().__init__()
        if fail_on_commit:
            self.commit = AsyncMock(side_effect=RuntimeError("db commit failed"))


class DashboardUserDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_user_with_access_cleans_control_refs_before_user_delete(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(id=88, telegram_id=700088, username="user-88")
        device = SimpleNamespace(id=1)
        session = _DeleteUserSession()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services._device_metadata", return_value={}),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=901))) as create_job_mock,
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock()) as update_job_mock,
            patch("dashboard.services._delete_device_remote_state", new=AsyncMock()) as remote_delete_mock,
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.create_audit_log", new=AsyncMock()) as audit_mock,
            patch("dashboard.services.invalidate_runtime_cache") as cache_mock,
        ):
            deleted = await delete_user_with_access(88, admin, "127.0.0.1")

        self.assertTrue(deleted)
        create_job_mock.assert_awaited_once()
        self.assertGreaterEqual(update_job_mock.await_count, 3)
        remote_delete_mock.assert_awaited_once_with(device, {})
        session.commit.assert_awaited_once()
        audit_mock.assert_awaited_once()
        cache_mock.assert_called_once_with("overview_metrics", "xui_summary", "server_snapshots")

        joined = "\n".join(session.statements)
        self.assertIn("UPDATE control_broadcast_deliveries SET user_id", joined)
        self.assertIn("UPDATE control_trigger_delivery_logs SET user_id", joined)
        self.assertIn("DELETE FROM support_tickets", joined)
        self.assertIn("DELETE FROM support_ticket_messages", joined)
        self.assertIn("DELETE FROM finance_entries", joined)
        self.assertIn("DELETE FROM vpn_client_activations", joined)
        self.assertIn("DELETE FROM users", joined)
        self.assertLess(
            joined.index("UPDATE control_broadcast_deliveries SET user_id"),
            joined.index("DELETE FROM users"),
        )
        self.assertLess(
            joined.index("UPDATE control_trigger_delivery_logs SET user_id"),
            joined.index("DELETE FROM users"),
        )
        self.assertLess(
            joined.index("DELETE FROM finance_entries"),
            joined.index("DELETE FROM payment_records"),
        )

    async def test_delete_user_with_access_updates_deletion_job_before_user_delete(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(id=88, telegram_id=700088, username="user-88")
        device = SimpleNamespace(id=1)
        session = _DeleteUserSession()

        async def update_job_side_effect(*args, **kwargs):
            if kwargs.get("stage") == "local_delete_committing":
                joined_before_user_delete = "\n".join(session.statements)
                self.assertNotIn("DELETE FROM users", joined_before_user_delete)
            return None

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services._device_metadata", return_value={}),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=906))),
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock(side_effect=update_job_side_effect)) as update_job_mock,
            patch("dashboard.services._delete_device_remote_state", new=AsyncMock()),
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.create_audit_log", new=AsyncMock()),
            patch("dashboard.services.invalidate_runtime_cache"),
        ):
            deleted = await delete_user_with_access(88, admin, "127.0.0.1")

        self.assertTrue(deleted)
        joined = "\n".join(session.statements)
        self.assertIn("DELETE FROM users", joined)
        self.assertTrue(
            any(call.kwargs.get("stage") == "local_delete_committing" for call in update_job_mock.await_args_list)
        )

    async def test_delete_user_with_access_restores_remote_state_when_local_delete_fails(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(id=88, telegram_id=700088, username="user-88")
        device = SimpleNamespace(id=1)
        session = _FailingDeleteUserSession()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services._device_metadata", return_value={"country_code": "de"}),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=902))),
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock()) as update_job_mock,
            patch("dashboard.services._delete_device_remote_state", new=AsyncMock()) as remote_delete_mock,
            patch("dashboard.services._restore_device_remote_state", new=AsyncMock(return_value=True)) as remote_restore_mock,
            patch("dashboard.services.enqueue_restore_deleted_device_job", new=AsyncMock()) as enqueue_mock,
            patch("dashboard.services.async_session", return_value=session),
            patch("dashboard.services.get_access_expires_at_from_user", return_value=None),
        ):
            with self.assertRaisesRegex(ValueError, "remote state устройств восстановлен"):
                await delete_user_with_access(88, admin, "127.0.0.1")

        remote_delete_mock.assert_awaited_once_with(device, {"country_code": "de"})
        remote_restore_mock.assert_awaited_once_with(device, {"country_code": "de"}, None)
        enqueue_mock.assert_not_awaited()
        self.assertEqual(update_job_mock.await_args_list[-1].kwargs["status"], "failed")

    async def test_delete_user_with_access_restores_already_deleted_devices_when_second_remote_delete_fails(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(id=88, telegram_id=700088, username="user-88")
        first_device = SimpleNamespace(id=1)
        second_device = SimpleNamespace(id=2)

        remote_delete_mock = AsyncMock(side_effect=[None, RuntimeError("remote failure")])
        remote_restore_mock = AsyncMock(return_value=True)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[first_device, second_device])),
            patch(
                "dashboard.services._device_metadata",
                side_effect=[{"country_code": "de"}, {"country_code": "ee"}],
            ),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=903))),
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock()) as update_job_mock,
            patch("dashboard.services._delete_device_remote_state", new=remote_delete_mock),
            patch("dashboard.services._restore_device_remote_state", new=remote_restore_mock),
            patch("dashboard.services.enqueue_restore_deleted_device_job", new=AsyncMock()) as enqueue_mock,
            patch("dashboard.services.get_access_expires_at_from_user", return_value=None),
        ):
            with self.assertRaisesRegex(ValueError, "remote state устройств восстановлен"):
                await delete_user_with_access(88, admin, "127.0.0.1")

        self.assertEqual(remote_delete_mock.await_count, 2)
        remote_restore_mock.assert_awaited_once_with(first_device, {"country_code": "de"}, None)
        enqueue_mock.assert_not_awaited()
        self.assertEqual(update_job_mock.await_args_list[-1].kwargs["status"], "failed")

    async def test_delete_user_with_access_queues_restore_job_when_remote_restore_fails(self) -> None:
        admin = SimpleNamespace(id=5)
        user = SimpleNamespace(id=88, telegram_id=700088, username="user-88")
        first_device = SimpleNamespace(id=1)
        second_device = SimpleNamespace(id=2)

        remote_delete_mock = AsyncMock(side_effect=[None, RuntimeError("remote failure")])
        remote_restore_mock = AsyncMock(return_value=False)

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[first_device, second_device])),
            patch(
                "dashboard.services._device_metadata",
                side_effect=[{"country_code": "de"}, {"country_code": "ee"}],
            ),
            patch("dashboard.services._create_user_deletion_job", new=AsyncMock(return_value=SimpleNamespace(id=904))),
            patch("dashboard.services._update_user_deletion_job", new=AsyncMock()) as update_job_mock,
            patch("dashboard.services._delete_device_remote_state", new=remote_delete_mock),
            patch("dashboard.services._restore_device_remote_state", new=remote_restore_mock),
            patch("dashboard.services.enqueue_restore_deleted_device_job", new=AsyncMock()) as enqueue_mock,
            patch("dashboard.services.get_access_expires_at_from_user", return_value=None),
        ):
            with self.assertRaisesRegex(ValueError, "restore failed for devices: \\[1\\]"):
                await delete_user_with_access(88, admin, "127.0.0.1")

        enqueue_mock.assert_awaited_once()
        self.assertEqual(enqueue_mock.await_args.kwargs["device"], first_device)
        self.assertEqual(update_job_mock.await_args_list[-1].kwargs["status"], "failed")


if __name__ == "__main__":
    unittest.main()
