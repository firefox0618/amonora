import unittest

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from ops import control_error_triggers


def _service_status_map(**overrides):
    payload = {
        key: {"label": unit_name, "service_label": label, "status": "active"}
        for key, (unit_name, label) in control_error_triggers.MONITORED_SERVICE_UNITS.items()
    }
    for key, status in overrides.items():
        payload[key]["status"] = status
    return payload


class ControlErrorTriggerTests(unittest.IsolatedAsyncioTestCase):
    def test_monitored_services_include_nginx_and_timers(self) -> None:
        self.assertIn("nginx", control_error_triggers.MONITORED_SERVICE_UNITS)
        self.assertIn("access_reminders_timer", control_error_triggers.MONITORED_SERVICE_UNITS)
        self.assertIn("server_watchdog_timer", control_error_triggers.MONITORED_SERVICE_UNITS)

    def test_build_service_incident_specs_marks_failed_units(self) -> None:
        incidents, recoveries = control_error_triggers.build_service_incident_specs(
            _service_status_map(main_bot="failed", dashboard_ui="activating")
        )

        by_key = {item.dedupe_key: item for item in incidents}
        self.assertEqual(
            by_key["control-health:service:main_bot"].severity,
            "CRITICAL",
        )
        self.assertEqual(
            by_key["control-health:service:dashboard_ui"].severity,
            "WARNING",
        )
        self.assertIn("control-health:service:landing", recoveries)
        self.assertNotIn("control-health:service:support_bot", by_key)

    def test_build_node_incident_specs_marks_down_and_only_critical_degraded_nodes(self) -> None:
        incidents, recoveries = control_error_triggers.build_node_incident_specs(
            [
                {
                    "id": 1,
                    "name": "Germany",
                    "country_name": "Germany",
                    "status": "active",
                    "overall_state": "warning",
                    "runtime_state": "healthy",
                    "host_status": "ok",
                    "ssh_status": "active",
                    "xui_status": "active",
                    "xui_service_status": "active",
                    "status_message": "transient pressure",
                    "ping_label": "180 ms",
                },
                {
                    "id": 2,
                    "name": "Denmark",
                    "country_name": "Denmark",
                    "status": "down",
                    "overall_state": "critical",
                    "host_status": "error",
                    "ssh_status": "error",
                    "xray_service_status": "failed",
                    "status_message": "host unreachable",
                    "ping_label": "—",
                },
                {
                    "id": 6,
                    "name": "Germany Critical",
                    "country_name": "Germany",
                    "status": "active",
                    "overall_state": "critical",
                    "runtime_state": "healthy",
                    "host_status": "ok",
                    "ssh_status": "active",
                    "xui_status": "error",
                    "xui_service_status": "active",
                    "status_message": "latency spike",
                    "ping_label": "1079 ms",
                },
                {
                    "id": 3,
                    "name": "Estonia",
                    "country_name": "Estonia",
                    "status": "maintenance",
                    "overall_state": "healthy",
                    "status_message": "ok",
                    "ping_label": "40 ms",
                },
            ]
        )

        by_key = {item.dedupe_key: item for item in incidents}
        self.assertEqual(by_key["control-health:node:2"].severity, "CRITICAL")
        self.assertEqual(by_key["control-health:node:6"].severity, "WARNING")
        self.assertEqual(by_key["control-health:node:6"].payload["runtime_status"], "active")
        self.assertIn("Runtime: <code>active</code>", by_key["control-health:node:6"].message)
        self.assertNotIn("control-health:node:1", by_key)
        self.assertNotIn("control-health:node:3", by_key)
        self.assertIn("control-health:node:3", recoveries)

    def test_build_node_incident_specs_skips_non_down_estonia_noise(self) -> None:
        incidents, recoveries = control_error_triggers.build_node_incident_specs(
            [
                {
                    "id": 4,
                    "name": "Amonora Estonia Node",
                    "country_code": "ee",
                    "country_name": "Estonia",
                    "status": "active",
                    "overall_state": "warning",
                    "host_status": "ok",
                    "ssh_status": "active",
                    "xui_status": "active",
                    "xui_service_status": "active",
                    "status_message": "noisy monitoring drift",
                    "ping_label": "180 ms",
                }
            ]
        )

        self.assertEqual(incidents, [])
        self.assertIn("control-health:node:4", recoveries)

    def test_build_node_incident_specs_keeps_real_estonia_down(self) -> None:
        incidents, _ = control_error_triggers.build_node_incident_specs(
            [
                {
                    "id": 5,
                    "name": "Amonora Estonia Node",
                    "country_code": "ee",
                    "country_name": "Estonia",
                    "status": "down",
                    "overall_state": "critical",
                    "host_status": "error",
                    "ssh_status": "error",
                    "xui_status": "error",
                    "xui_service_status": "failed",
                    "status_message": "host unreachable",
                    "ping_label": "—",
                }
            ]
        )

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].severity, "CRITICAL")

    def test_build_node_incident_specs_skips_local_core_degradation_noise(self) -> None:
        incidents, recoveries = control_error_triggers.build_node_incident_specs(
            [
                {
                    "id": 2,
                    "name": "Amonora Core",
                    "country_code": "eu",
                    "country_name": "Europe",
                    "is_local": True,
                    "status": "active",
                    "overall_state": "warning",
                    "host_status": None,
                    "ssh_status": None,
                    "xui_status": "n/a",
                    "xui_service_status": "n/a",
                    "status_message": "transient local pressure",
                    "ping_label": "0.2 ms",
                }
            ]
        )

        self.assertEqual(incidents, [])
        self.assertIn("control-health:node:2", recoveries)

    def test_build_user_incident_specs_aggregates_repair_needed_users(self) -> None:
        now = datetime(2026, 3, 23, 12, 0, 0)
        users = [
            SimpleNamespace(
                id=11,
                telegram_id=10011,
                username="paid_user",
                vpn_repair_needed=True,
                vpn_repair_reason="post_payment_sync_failed",
                vpn_repair_marked_at=now - timedelta(hours=1),
                is_blocked=False,
                trial_used=True,
                trial_expires_at=None,
                subscription_status="active",
                subscription_source="telegram_stars",
                subscription_expires_at=now + timedelta(days=20),
            ),
            SimpleNamespace(
                id=12,
                telegram_id=10012,
                username="damaged_user",
                vpn_repair_needed=True,
                vpn_repair_reason="manual_repair_sync_failed",
                vpn_repair_marked_at=now - timedelta(hours=8),
                is_blocked=False,
                trial_used=True,
                trial_expires_at=None,
                subscription_status="inactive",
                subscription_source=None,
                subscription_expires_at=now - timedelta(days=1),
            ),
        ]

        incidents, recoveries = control_error_triggers.build_user_incident_specs(
            users,
            {11: 1, 12: 0},
            now_utc=now,
        )

        self.assertEqual(len(incidents), 1)
        incident = incidents[0]
        self.assertEqual(incident.severity, "CRITICAL")
        self.assertEqual(incident.payload["total"], 2)
        self.assertEqual(incident.payload["payment_related"], 1)
        self.assertEqual(incident.payload["stale"], 1)
        self.assertEqual(incident.payload["without_devices"], 1)
        self.assertIn(control_error_triggers.USER_ACCESS_DEDUPE_KEY, recoveries)

    async def test_emit_control_error_triggers_emits_only_critical_node_incidents_and_recoveries(self) -> None:
        statuses = _service_status_map(main_bot="active")
        snapshots = [
            {
                "id": 21,
                "name": "Germany",
                "country_name": "Germany",
                "status": "active",
                "overall_state": "warning",
                "runtime_state": "healthy",
                "host_status": "ok",
                "ssh_status": "active",
                "xui_status": "active",
                "xui_service_status": "active",
                "status_message": "transient pressure",
                "ping_label": "160 ms",
            }
        ]
        users = [
            SimpleNamespace(
                id=31,
                telegram_id=1031,
                username="healthy_user",
                vpn_repair_needed=False,
                vpn_repair_reason=None,
                vpn_repair_marked_at=None,
                is_blocked=False,
                trial_used=False,
                trial_expires_at=None,
                subscription_status="inactive",
                subscription_source=None,
                subscription_expires_at=None,
            )
        ]

        create_event = AsyncMock(side_effect=[SimpleNamespace(id=701), SimpleNamespace(id=702)])

        with (
            patch.object(control_error_triggers, "load_monitored_service_statuses", new=AsyncMock(return_value=statuses)),
            patch.object(control_error_triggers, "get_server_snapshots", new=AsyncMock(return_value=snapshots)),
            patch.object(control_error_triggers, "_load_user_repair_inputs", new=AsyncMock(return_value=(users, {}))),
            patch.object(
                control_error_triggers,
                "_list_unresolved_incident_keys",
                new=AsyncMock(
                    return_value={
                        "control-health:service:main_bot",
                        control_error_triggers.USER_ACCESS_DEDUPE_KEY,
                    }
                ),
            ),
            patch.object(control_error_triggers, "create_control_event", create_event),
            patch.object(control_error_triggers, "_mark_event_resolved", new=AsyncMock()) as resolve_mock,
        ):
            result = await control_error_triggers.emit_control_error_triggers(now_utc=datetime(2026, 3, 23, 12, 0, 0))

        self.assertEqual(result["node_incidents"], 0)
        self.assertEqual(result["recoveries"], 2)
        calls = create_event.await_args_list
        self.assertEqual(calls[0].kwargs["event_type"], "service_recovered")
        self.assertEqual(calls[1].kwargs["event_type"], "user_access_recovered")
        self.assertEqual(resolve_mock.await_count, 2)


if __name__ == "__main__":
    unittest.main()
