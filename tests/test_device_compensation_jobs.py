import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot import device_compensation


class DeviceCompensationJobsTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_cleanup_created_device_job_deletes_local_row_after_remote_cleanup(self) -> None:
        payload = {
            "device": {
                "id": 51,
                "user_id": 77,
                "protocol": "vless",
                "client_uuid": "uuid-51",
                "email": "device_51",
                "xui_client_id": None,
            },
            "metadata": {"country_code": "de", "provider_type": "xui"},
        }

        with (
            patch.object(device_compensation, "_delete_remote_state_for_snapshot", new=AsyncMock(return_value=True)) as remote_mock,
            patch.object(device_compensation, "delete_vpn_client_and_return", new=AsyncMock(return_value=SimpleNamespace(id=51))) as delete_mock,
        ):
            cleaned = await device_compensation._execute_cleanup_created_device_job(payload)

        self.assertTrue(cleaned)
        remote_mock.assert_awaited_once()
        delete_mock.assert_awaited_once_with(51)

    async def test_execute_restore_deleted_device_job_restores_remote_state_from_payload(self) -> None:
        payload = {
            "device": {
                "id": 61,
                "user_id": 88,
                "protocol": "trojan",
                "client_uuid": "uuid-61",
                "email": "device_61",
                "xui_client_id": "uuid-61",
            },
            "metadata": {"country_code": "de", "inbound_id": 1},
            "access_expires_at": "2026-04-05T12:00:00",
        }

        with patch.object(device_compensation, "_restore_remote_state_for_snapshot", new=AsyncMock(return_value=True)) as restore_mock:
            restored = await device_compensation._execute_restore_deleted_device_job(payload)

        self.assertTrue(restored)
        restore_mock.assert_awaited_once()
        device_arg = restore_mock.await_args.args[0]
        self.assertEqual(device_arg.id, 61)
        self.assertEqual(device_arg.protocol, "trojan")

    async def test_execute_finalize_created_device_job_restores_existing_device_state(self) -> None:
        payload = {
            "device": {
                "id": 71,
                "user_id": 99,
                "protocol": "vless",
                "client_uuid": "uuid-71",
                "email": "device_71",
                "xui_client_id": None,
            },
            "metadata": {"country_code": "de", "provider_type": "xui", "device_name": "Office"},
            "access_expires_at": "2026-04-05T12:00:00",
        }
        existing = SimpleNamespace(
            id=71,
            user_id=99,
            protocol="vless",
            client_uuid="uuid-71",
            email="device_71",
            xui_client_id=None,
        )

        with (
            patch.object(device_compensation, "get_vpn_client_by_id", new=AsyncMock(return_value=existing)),
            patch.object(device_compensation, "update_vpn_client_metadata", new=AsyncMock()) as metadata_mock,
            patch.object(device_compensation, "_restore_remote_state_for_snapshot", new=AsyncMock(return_value=True)) as restore_mock,
        ):
            restored = await device_compensation._execute_finalize_created_device_job(payload)

        self.assertTrue(restored)
        metadata_mock.assert_awaited_once_with(71, payload["metadata"])
        restore_mock.assert_awaited_once()
        device_arg = restore_mock.await_args.args[0]
        self.assertEqual(device_arg.id, 71)
        self.assertEqual(device_arg.protocol, "vless")

    async def test_process_pending_device_compensation_jobs_tracks_completed_rescheduled_and_failed(self) -> None:
        jobs = [
            SimpleNamespace(id=1, action="cleanup_created_device"),
            SimpleNamespace(id=2, action="restore_deleted_device"),
            SimpleNamespace(id=3, action="restore_deleted_device"),
        ]

        with (
            patch.object(
                device_compensation,
                "_claim_pending_device_compensation_jobs",
                new=AsyncMock(return_value=jobs),
            ),
            patch.object(
                device_compensation,
                "_run_device_compensation_job",
                new=AsyncMock(side_effect=[True, False, RuntimeError("boom")]),
            ),
            patch.object(device_compensation, "_complete_device_compensation_job", new=AsyncMock()) as complete_mock,
            patch.object(
                device_compensation,
                "_release_device_compensation_job",
                new=AsyncMock(
                    side_effect=[
                        SimpleNamespace(status=device_compensation.DEVICE_COMP_STATUS_PENDING),
                        SimpleNamespace(status=device_compensation.DEVICE_COMP_STATUS_FAILED),
                    ]
                ),
            ) as release_mock,
        ):
            result = await device_compensation.process_pending_device_compensation_jobs(limit=10)

        self.assertEqual(
            result,
            {
                "checked": 3,
                "completed": 1,
                "rescheduled": 1,
                "failed": 1,
            },
        )
        complete_mock.assert_awaited_once_with(1)
        self.assertEqual(release_mock.await_count, 2)


if __name__ == "__main__":
    unittest.main()
