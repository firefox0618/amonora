import unittest

from sqlalchemy.dialects import postgresql

from ops import server_watchdog


class ServerWatchdogTests(unittest.TestCase):
    def test_estonia_runtime_noise_is_ignored_by_watchdog(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "ee",
            "host_status": "ok",
            "ssh_status": "active",
            "xui_status": "inactive",
            "xui_service_status": "inactive",
            "xray_service_status": "inactive",
            "overall_state": "healthy",
        }

        self.assertFalse(server_watchdog._is_server_down(snapshot))
        self.assertFalse(server_watchdog._is_server_degraded(snapshot))

    def test_monitoring_gap_does_not_open_down_or_degraded_incident_when_runtime_is_healthy(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "de",
            "host_status": "error",
            "ssh_status": "error",
            "xui_status": "ok",
            "xui_service_status": "unknown",
            "overall_state": "healthy",
        }

        self.assertFalse(server_watchdog._is_server_down(snapshot))
        self.assertFalse(server_watchdog._is_server_degraded(snapshot))

    def test_xui_runtime_service_failure_still_counts_as_real_down(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "de",
            "host_status": "ok",
            "ssh_status": "active",
            "xui_status": "error",
            "xui_service_status": "failed",
            "overall_state": "critical",
        }

        self.assertTrue(server_watchdog._is_server_down(snapshot))

    def test_xui_panel_noise_is_not_treated_as_runtime_down(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "de",
            "host_status": "ok",
            "ssh_status": "active",
            "xui_status": "error",
            "xui_service_status": "active",
            "overall_state": "healthy",
        }

        self.assertFalse(server_watchdog._is_server_down(snapshot))
        self.assertFalse(server_watchdog._is_server_degraded(snapshot))

    def test_xray_core_ignores_inactive_xui_service_status(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "dk",
            "host_status": "ok",
            "ssh_status": "active",
            "xray_service_status": "active",
            "xui_service_status": "inactive",
            "overall_state": "healthy",
        }

        self.assertFalse(server_watchdog._is_server_down(snapshot))
        self.assertFalse(server_watchdog._is_server_degraded(snapshot))

    def test_estonia_runtime_is_retired(self) -> None:
        snapshot = {
            "status": "active",
            "country_code": "ee",
            "host_status": "ok",
            "ssh_status": "active",
            "awg_service_status": "active",
            "xui_status": "inactive",
            "xui_service_status": "inactive",
            "overall_state": "healthy",
        }

        self.assertEqual(server_watchdog._vpn_runtime_label(snapshot), "Retired")
        self.assertEqual(server_watchdog._vpn_runtime_status(snapshot), "n/a")
        self.assertEqual(server_watchdog._vpn_runtime_service_status(snapshot), "n/a")
        self.assertFalse(server_watchdog._is_server_down(snapshot))
        self.assertFalse(server_watchdog._is_server_degraded(snapshot))

    def test_estonia_notifications_allow_only_real_down(self) -> None:
        self.assertTrue(server_watchdog._node_notifications_allowed({"country_code": "ee"}, "down"))
        self.assertFalse(server_watchdog._node_notifications_allowed({"country_code": "ee"}, "degraded"))
        self.assertFalse(server_watchdog._node_notifications_allowed({"country_code": "ee"}, "overloaded"))
        self.assertTrue(server_watchdog._node_notifications_allowed({"country_code": "de"}, "degraded"))

    def test_watchdog_confirmation_thresholds_require_more_for_degraded(self) -> None:
        pending: dict[str, dict] = {}

        should_open, count = server_watchdog._advance_pending(pending, "4", "degraded", "CPU 72.0%")
        self.assertFalse(should_open)
        self.assertEqual(count, 1)

        should_open, count = server_watchdog._advance_pending(pending, "4", "degraded", "CPU 72.0%")
        self.assertFalse(should_open)
        self.assertEqual(count, 2)

        should_open, count = server_watchdog._advance_pending(pending, "4", "degraded", "CPU 72.0%")
        self.assertTrue(should_open)
        self.assertEqual(count, 3)

    def test_watchdog_confirmation_thresholds_keep_down_faster(self) -> None:
        pending: dict[str, dict] = {}

        should_open, count = server_watchdog._advance_pending(pending, "4", "down", "ssh=error")
        self.assertFalse(should_open)
        self.assertEqual(count, 1)

        should_open, count = server_watchdog._advance_pending(pending, "4", "down", "ssh=error")
        self.assertTrue(should_open)
        self.assertEqual(count, 2)

    def test_affected_users_query_joins_real_users_only(self) -> None:
        statement = (
            server_watchdog.select(server_watchdog.VpnClient.user_id, server_watchdog.VpnClient.client_data, server_watchdog.User)
            .join(server_watchdog.User, server_watchdog.User.id == server_watchdog.VpnClient.user_id)
            .where(server_watchdog.shared_real_user_sql_clause(server_watchdog.User))
        )
        compiled = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()

        self.assertIn("join users on users.id = vpn_clients.user_id", compiled)
        self.assertIn("is_synthetic", compiled)
        self.assertIn("bridge_", compiled)


if __name__ == "__main__":
    unittest.main()
