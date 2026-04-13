import unittest

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from bot.payment_flow import sync_user_vpn_access
import ops.access_reminders as access_reminders_module
from ops.access_reminders import (
    _enforce_trial_channel_membership,
    _recover_vpn_repair_needed_users,
    _purge_expired_bridge_access,
    _purge_expired_trial_vpn_access,
    _revoke_expired_vpn_access,
)


class SyncUserVpnAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_user_vpn_access_disables_vless_when_access_is_missing(self) -> None:
        client = type(
            "VpnClient",
            (),
            {
                "protocol": "vless",
                "client_uuid": "uuid-1",
                "xui_client_id": None,
                "email": "device@example",
                "client_data": '{"country_code":"de","provider_type":"xui","inbound_id":1}',
            },
        )()
        provisioner = type(
            "Provisioner",
            (),
            {
                "health_check": AsyncMock(return_value=True),
                "sync_vless_client": AsyncMock(),
                "close": AsyncMock(),
            },
        )()

        with (
            patch("bot.payment_flow.get_user_vpn_clients", new=AsyncMock(return_value=[client])),
            patch("bot.payment_flow.get_vless_provisioner", return_value=provisioner),
        ):
            failed = await sync_user_vpn_access(77, None)

        self.assertFalse(failed)
        provisioner.sync_vless_client.assert_awaited_once_with(
            client_uuid="uuid-1",
            email="device@example",
            metadata={"country_code": "de", "provider_type": "xui", "inbound_id": 1},
            access_expires_at=None,
        )
        provisioner.close.assert_awaited_once()

    async def test_sync_user_vpn_access_persists_reconciled_vless_metadata(self) -> None:
        client = type(
            "VpnClient",
            (),
            {
                "id": 55,
                "protocol": "vless",
                "client_uuid": "uuid-2",
                "xui_client_id": None,
                "email": "device2@example",
                "client_data": '{"country_code":"de","provider_type":"xui","inbound_id":1}',
            },
        )()

        async def _mutate_metadata(*, metadata, **_kwargs):
            metadata["inbound_id"] = 44

        provisioner = type(
            "Provisioner",
            (),
            {
                "health_check": AsyncMock(return_value=True),
                "sync_vless_client": AsyncMock(side_effect=_mutate_metadata),
                "close": AsyncMock(),
            },
        )()

        with (
            patch("bot.payment_flow.get_user_vpn_clients", new=AsyncMock(return_value=[client])),
            patch("bot.payment_flow.get_vless_provisioner", return_value=provisioner),
            patch("bot.payment_flow.update_vpn_client_metadata", new=AsyncMock()) as update_metadata_mock,
        ):
            failed = await sync_user_vpn_access(77, datetime(2026, 4, 5, 12, 0, 0))

        self.assertFalse(failed)
        update_metadata_mock.assert_awaited_once_with(55, {"country_code": "de", "provider_type": "xui", "inbound_id": 44})


class ExpiredAccessRevocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_recover_vpn_repair_needed_users_clears_marker_after_successful_sync(self) -> None:
        now = datetime(2026, 4, 5, 12, 0, 0)
        user = type(
            "User",
            (),
            {
                "id": 71,
                "telegram_id": 1234567,
                "username": "paid_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_expires_at": None,
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now + timedelta(days=10),
                "subscription_status": "active",
                "subscription_source": "telegram_stars",
                "vpn_repair_needed": True,
                "vpn_repair_marked_at": now - timedelta(hours=2),
                "created_at": now - timedelta(days=5),
            },
        )()
        state: dict = {}

        with (
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[user])),
            patch("ops.access_reminders.get_user_vpn_clients", new=AsyncMock(return_value=[object()])),
            patch(
                "ops.access_reminders.sync_user_vpn_access_with_single_retry",
                new=AsyncMock(return_value={"sync_failed": False, "auto_retry_attempted": True, "auto_retry_succeeded": True}),
            ) as sync_mock,
            patch("ops.access_reminders.clear_vpn_repair_needed", new=AsyncMock()) as clear_mock,
        ):
            result = await _recover_vpn_repair_needed_users(state, now, limit=10)

        self.assertEqual(result, {"checked": 1, "recovered": 1, "failed": 0, "skipped": 0})
        sync_mock.assert_awaited_once_with(71, user.subscription_expires_at)
        clear_mock.assert_awaited_once_with(71)
        self.assertEqual(state["events"]["71"]["vpn_repair_recovery"]["last_result"], "success")

    async def test_enforce_trial_channel_membership_pauses_access_for_unsubscribed_trial(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, 0)
        trial_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_started_at": now - timedelta(days=1),
                "trial_expires_at": now + timedelta(days=2),
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=1),
            },
        )()
        paused_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_started_at": now - timedelta(days=1),
                "trial_expires_at": now + timedelta(days=2),
                "trial_channel_unsubscribed_at": now,
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=1),
            },
        )()
        state: dict = {}

        with (
            patch.object(access_reminders_module.config, "channel_id", "@amonora_vpn"),
            patch.object(access_reminders_module.config, "bot_token", "test-token"),
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[trial_user])),
            patch("ops.access_reminders.is_user_subscribed", new=AsyncMock(return_value=False)),
            patch("ops.access_reminders.pause_trial_for_channel_unsubscribe", new=AsyncMock(return_value=paused_user)) as pause_mock,
            patch("ops.access_reminders.sync_user_vpn_access", new=AsyncMock(return_value=False)) as sync_mock,
            patch("ops.access_reminders._send_trial_channel_pause_notice", new=AsyncMock(return_value="sent")) as notify_mock,
            patch("ops.access_reminders.Bot") as bot_cls,
        ):
            bot_cls.return_value.session.close = AsyncMock()
            result = await _enforce_trial_channel_membership(state, now)

        self.assertEqual(result, {"checked": 1, "paused": 1, "resumed": 0, "notified": 1, "suppressed": 0, "failed": 0})
        pause_mock.assert_awaited_once_with(98, paused_at=now)
        sync_mock.assert_awaited_once_with(98, None)
        self.assertEqual(notify_mock.await_count, 1)
        self.assertIs(notify_mock.await_args.args[1], paused_user)

    async def test_enforce_trial_channel_membership_resumes_access_for_resubscribed_trial(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, 0)
        paused_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_started_at": now - timedelta(days=1),
                "trial_expires_at": now + timedelta(days=2),
                "trial_channel_unsubscribed_at": now - timedelta(hours=3),
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=1),
            },
        )()
        resumed_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_started_at": now - timedelta(days=1),
                "trial_expires_at": now + timedelta(days=2),
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=1),
            },
        )()
        state: dict = {}

        with (
            patch.object(access_reminders_module.config, "channel_id", "@amonora_vpn"),
            patch.object(access_reminders_module.config, "bot_token", "test-token"),
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[paused_user])),
            patch("ops.access_reminders.is_user_subscribed", new=AsyncMock(return_value=True)),
            patch("ops.access_reminders.resume_trial_after_channel_resubscribe", new=AsyncMock(return_value=resumed_user)) as resume_mock,
            patch(
                "ops.access_reminders.sync_user_vpn_access_with_single_retry",
                new=AsyncMock(return_value={"sync_failed": False}),
            ) as sync_mock,
            patch("ops.access_reminders._send_trial_channel_resume_notice", new=AsyncMock(return_value="sent")) as notify_mock,
            patch("ops.access_reminders.Bot") as bot_cls,
        ):
            bot_cls.return_value.session.close = AsyncMock()
            result = await _enforce_trial_channel_membership(state, now)

        self.assertEqual(result, {"checked": 1, "paused": 0, "resumed": 1, "notified": 1, "suppressed": 0, "failed": 0})
        resume_mock.assert_awaited_once_with(98)
        sync_mock.assert_awaited_once_with(98, resumed_user.trial_expires_at)
        self.assertEqual(notify_mock.await_count, 1)
        self.assertIs(notify_mock.await_args.args[1], resumed_user)

    async def test_enforce_trial_channel_membership_backfills_notice_for_already_paused_trial(self) -> None:
        now = datetime(2026, 4, 2, 12, 0, 0)
        paused_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_started_at": now - timedelta(days=1),
                "trial_expires_at": now + timedelta(days=2),
                "trial_channel_unsubscribed_at": now - timedelta(hours=3),
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=1),
            },
        )()
        marker = f"paused:{paused_user.trial_channel_unsubscribed_at.isoformat()}:{paused_user.trial_expires_at.isoformat()}"
        state = {
            "events": {
                "98": {
                    "trial_channel_membership": {
                        "marker": marker,
                        "last_result": "success",
                    }
                }
            }
        }

        with (
            patch.object(access_reminders_module.config, "channel_id", "@amonora_vpn"),
            patch.object(access_reminders_module.config, "bot_token", "test-token"),
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[paused_user])),
            patch("ops.access_reminders.is_user_subscribed", new=AsyncMock(return_value=False)),
            patch("ops.access_reminders.pause_trial_for_channel_unsubscribe", new=AsyncMock()) as pause_mock,
            patch("ops.access_reminders.sync_user_vpn_access", new=AsyncMock()) as sync_mock,
            patch("ops.access_reminders._send_trial_channel_pause_notice", new=AsyncMock(return_value="sent")) as notify_mock,
            patch("ops.access_reminders.Bot") as bot_cls,
        ):
            bot_cls.return_value.session.close = AsyncMock()
            result = await _enforce_trial_channel_membership(state, now)

        self.assertEqual(result, {"checked": 1, "paused": 0, "resumed": 0, "notified": 1, "suppressed": 0, "failed": 0})
        pause_mock.assert_not_awaited()
        sync_mock.assert_not_awaited()
        self.assertEqual(notify_mock.await_count, 1)
        self.assertIs(notify_mock.await_args.args[1], paused_user)

    async def test_revoke_expired_vpn_access_runs_once_per_marker(self) -> None:
        now = datetime(2026, 3, 31, 12, 0, 0)
        expired_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "expired_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_expires_at": now - timedelta(days=6),
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=7),
            },
        )()
        active_user = type(
            "User",
            (),
            {
                "id": 77,
                "telegram_id": 123,
                "username": "active_user",
                "is_blocked": False,
                "trial_used": False,
                "trial_expires_at": None,
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now + timedelta(days=1),
                "subscription_status": "active",
                "subscription_source": "telegram_stars",
                "created_at": now - timedelta(days=1),
            },
        )()
        state: dict = {}

        with (
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[expired_user, active_user])),
            patch("ops.access_reminders.sync_user_vpn_access", new=AsyncMock(return_value=False)) as sync_mock,
        ):
            first = await _revoke_expired_vpn_access(state, now)
            second = await _revoke_expired_vpn_access(state, now)

        self.assertEqual(first, {"processed": 1, "revoked": 1, "failed": 0})
        self.assertEqual(second, {"processed": 0, "revoked": 0, "failed": 0})
        sync_mock.assert_awaited_once_with(98, None)

    async def test_purge_expired_trial_vpn_access_removes_trial_only_devices(self) -> None:
        now = datetime(2026, 3, 31, 12, 0, 0)
        expired_trial_user = type(
            "User",
            (),
            {
                "id": 98,
                "telegram_id": 232096694,
                "username": "expired_trial_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_expires_at": now - timedelta(days=6),
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": None,
                "subscription_status": "inactive",
                "subscription_source": None,
                "created_at": now - timedelta(days=7),
            },
        )()
        expired_paid_user = type(
            "User",
            (),
            {
                "id": 77,
                "telegram_id": 123,
                "username": "expired_paid_user",
                "is_blocked": False,
                "trial_used": True,
                "trial_expires_at": now - timedelta(days=10),
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now - timedelta(days=1),
                "subscription_status": "inactive",
                "subscription_source": "telegram_stars",
                "created_at": now - timedelta(days=30),
            },
        )()
        device = type(
            "VpnClient",
            (),
            {
                "id": 501,
                "user_id": 98,
                "protocol": "vless",
                "client_uuid": "uuid-501",
                "xui_client_id": None,
                "email": "device_98@example",
                "client_data": '{"country_code":"de","provider_type":"xui","inbound_id":1}',
            },
        )()
        provisioner = type(
            "Provisioner",
            (),
            {
                "delete_vless_client": AsyncMock(return_value={"success": True}),
                "close": AsyncMock(),
            },
        )()
        state: dict = {}

        with (
            patch("ops.access_reminders._load_users", new=AsyncMock(return_value=[expired_trial_user, expired_paid_user])),
            patch("ops.access_reminders.get_user_vpn_clients", new=AsyncMock(side_effect=[[device], []])) as get_clients_mock,
            patch("ops.access_reminders.get_vless_provisioner", return_value=provisioner),
            patch("ops.access_reminders.delete_vpn_client", new=AsyncMock(return_value=True)) as delete_mock,
        ):
            first = await _purge_expired_trial_vpn_access(state, now)
            second = await _purge_expired_trial_vpn_access(state, now)

        self.assertEqual(first, {"processed": 1, "purged": 1, "failed": 0})
        self.assertEqual(second, {"processed": 0, "purged": 0, "failed": 0})
        self.assertEqual(get_clients_mock.await_count, 2)
        provisioner.delete_vless_client.assert_awaited_once_with(
            client_uuid="uuid-501",
            email="device_98@example",
            metadata={"country_code": "de", "provider_type": "xui", "inbound_id": 1},
        )
        provisioner.close.assert_awaited_once()
        delete_mock.assert_awaited_once_with(501)

    async def test_purge_expired_bridge_access_removes_devices_and_deletes_user(self) -> None:
        now = datetime(2026, 4, 3, 12, 0, 0)
        bridge_user = type(
            "User",
            (),
            {
                "id": 111,
                "telegram_id": 900000000000111,
                "username": "bridge_cleanup_user",
                "is_blocked": False,
                "trial_used": False,
                "trial_expires_at": None,
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now - timedelta(hours=2),
                "subscription_status": "inactive",
                "subscription_source": "landing_bridge",
                "created_at": now - timedelta(days=1),
            },
        )()
        normal_user = type(
            "User",
            (),
            {
                "id": 112,
                "telegram_id": 123456,
                "username": "regular_user",
                "is_blocked": False,
                "trial_used": False,
                "trial_expires_at": None,
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now + timedelta(days=1),
                "subscription_status": "active",
                "subscription_source": "telegram_stars",
                "created_at": now - timedelta(days=7),
            },
        )()
        device = type("VpnClient", (), {"id": 601, "user_id": 111})()
        state: dict = {}

        with (
            patch("ops.access_reminders._load_expired_bridge_users", new=AsyncMock(side_effect=[[bridge_user], []])),
            patch("ops.access_reminders.get_user_vpn_clients", new=AsyncMock(return_value=[device])) as get_clients_mock,
            patch("ops.access_reminders._purge_expired_trial_device", new=AsyncMock(return_value=True)) as purge_device_mock,
            patch("ops.access_reminders.delete_landing_bridge_user_if_unused", new=AsyncMock(return_value=True)) as delete_user_mock,
        ):
            first = await _purge_expired_bridge_access(state, now)
            second = await _purge_expired_bridge_access(state, now)

        self.assertEqual(first, {"processed": 1, "purged": 1, "deleted_users": 1, "failed": 0})
        self.assertEqual(second, {"processed": 0, "purged": 0, "deleted_users": 0, "failed": 0})
        purge_device_mock.assert_awaited_once_with(device)
        delete_user_mock.assert_awaited_once_with(111)
        self.assertEqual(get_clients_mock.await_count, 1)

    async def test_purge_expired_bridge_access_deletes_unused_user_without_devices(self) -> None:
        now = datetime(2026, 4, 3, 12, 0, 0)
        bridge_user = type(
            "User",
            (),
            {
                "id": 211,
                "telegram_id": 900000000000211,
                "username": "bridge_no_devices",
                "is_blocked": False,
                "trial_used": False,
                "trial_expires_at": None,
                "trial_channel_unsubscribed_at": None,
                "subscription_expires_at": now - timedelta(hours=5),
                "subscription_status": "inactive",
                "subscription_source": "landing_bridge",
                "created_at": now - timedelta(days=1),
            },
        )()
        state: dict = {}

        with (
            patch("ops.access_reminders._load_expired_bridge_users", new=AsyncMock(return_value=[bridge_user])),
            patch("ops.access_reminders.get_user_vpn_clients", new=AsyncMock(side_effect=[[], []])) as get_clients_mock,
            patch("ops.access_reminders.delete_landing_bridge_user_if_unused", new=AsyncMock(return_value=True)) as delete_user_mock,
        ):
            result = await _purge_expired_bridge_access(state, now)

        self.assertEqual(result, {"processed": 0, "purged": 0, "deleted_users": 1, "failed": 0})
        delete_user_mock.assert_awaited_once_with(211)
        self.assertEqual(get_clients_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()
