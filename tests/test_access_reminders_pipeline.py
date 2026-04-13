import unittest

from datetime import datetime
from unittest.mock import AsyncMock, patch

from ops import access_reminders


class AccessReminderPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_continues_after_stage_failure_and_persists_stateful_stages(self) -> None:
        now = datetime(2026, 4, 5, 12, 0, 0)
        state = {"events": {}}

        with (
            patch("ops.access_reminders._enforce_trial_channel_membership", new=AsyncMock(return_value={"checked": 1})) as trial_mock,
            patch("ops.access_reminders._revoke_expired_vpn_access", new=AsyncMock(side_effect=RuntimeError("boom"))) as revoke_mock,
            patch("ops.access_reminders._purge_expired_trial_vpn_access", new=AsyncMock(return_value={"purged": 2})),
            patch("ops.access_reminders._purge_expired_bridge_access", new=AsyncMock(return_value={"deleted_users": 1})),
            patch("ops.access_reminders.expire_device_slot_entitlements", new=AsyncMock(return_value={"expired": 1})) as slot_mock,
            patch("ops.access_reminders._recover_vpn_repair_needed_users", new=AsyncMock(return_value={"recovered": 1})) as repair_mock,
            patch("ops.access_reminders.process_pending_campaigns", new=AsyncMock(return_value={"processed": 3})) as campaign_mock,
            patch("ops.access_reminders._process_trigger_rules", new=AsyncMock(return_value={"sent": 2})) as trigger_mock,
            patch("ops.access_reminders.emit_control_error_triggers", new=AsyncMock(return_value={"incidents": 1})) as incident_mock,
            patch("ops.access_reminders.reconcile_confirmed_payment_records", new=AsyncMock(return_value={"reconciled": 4})) as payment_mock,
            patch("ops.access_reminders.process_pending_device_compensation_jobs", new=AsyncMock(return_value={"completed": 1})) as compensation_mock,
            patch("ops.access_reminders._save_state") as save_state_mock,
            patch.object(access_reminders.logger, "exception"),
        ):
            results = await access_reminders._run_worker_pipeline(state, now)

        trial_mock.assert_awaited_once_with(state, now)
        revoke_mock.assert_awaited_once_with(state, now)
        slot_mock.assert_awaited_once_with(now_utc=now)
        repair_mock.assert_awaited_once_with(state, now, limit=10)
        campaign_mock.assert_awaited_once()
        trigger_mock.assert_awaited_once_with(now)
        incident_mock.assert_awaited_once_with(now_utc=now)
        payment_mock.assert_awaited_once_with(limit=25)
        compensation_mock.assert_awaited_once_with(limit=10)
        self.assertEqual(save_state_mock.call_count, len(access_reminders.STATEFUL_STAGE_NAMES))
        self.assertEqual(results["trial_channel"]["status"], "ok")
        self.assertEqual(results["revocations"]["status"], "failed")
        self.assertEqual(results["scheduled"]["processed"], 3)
        self.assertEqual(results["device_compensation"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
