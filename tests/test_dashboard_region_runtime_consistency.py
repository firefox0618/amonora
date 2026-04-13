import unittest

from types import SimpleNamespace

from dashboard import services as dashboard_services


class DashboardRegionRuntimeConsistencyTests(unittest.TestCase):
    def test_estonia_server_runtime_service_name_is_retired(self) -> None:
        server = SimpleNamespace(country_code="ee")

        self.assertEqual(dashboard_services._server_runtime_service_name(server), "retired")

    def test_estonia_service_pills_use_retired_runtime(self) -> None:
        server = SimpleNamespace(country_code="ee", is_local=False)
        base = {
            "awg_service_status": "active",
            "xui_status": "inactive",
            "xray_service_status": "inactive",
            "ssh_status": "active",
            "docker_status": "ok",
            "host_status": "ok",
        }

        pills = dashboard_services._service_pills_for_server(base, server)

        self.assertEqual(pills[0]["label"], "Retired")
        self.assertEqual(pills[0]["value"], "retired")
        self.assertEqual(pills[1]["value"], "n/a")

    def test_estonia_runtime_health_is_treated_as_retired(self) -> None:
        snapshot = {
            "country_code": "ee",
            "awg_service_status": "active",
            "xui_status": "inactive",
            "xui_service_status": "inactive",
        }

        self.assertEqual(dashboard_services._runtime_service_health_state(snapshot), "healthy")
        self.assertEqual(dashboard_services._provider_runtime_status_value(snapshot), "retired")

    def test_xui_runtime_health_prefers_runtime_service_over_panel_summary(self) -> None:
        snapshot = {
            "country_code": "de",
            "xui_status": "error",
            "xui_service_status": "active",
        }

        self.assertEqual(dashboard_services._runtime_service_health_state(snapshot), "healthy")
        self.assertEqual(dashboard_services._provider_runtime_status_value(snapshot), "active")

    def test_xui_service_pills_split_runtime_and_panel_health(self) -> None:
        server = SimpleNamespace(country_code="de", is_local=False)
        base = {
            "xui_status": "error",
            "xui_service_status": "active",
            "xui_clients": 18,
            "ssh_status": "active",
            "docker_status": "active",
            "host_status": "ok",
        }

        pills = dashboard_services._service_pills_for_server(base, server)

        self.assertEqual(pills[0], {"label": "3x-ui", "value": "active"})
        self.assertEqual(pills[1], {"label": "Panel", "value": "error"})

    def test_runtime_probe_ports_follow_public_vpn_listeners(self) -> None:
        self.assertEqual(dashboard_services._runtime_probe_ports("de"), (443,))
        self.assertEqual(dashboard_services._runtime_probe_ports("dk"), (443, 8443))
        self.assertEqual(dashboard_services._runtime_probe_ports("ee"), (22,))


if __name__ == "__main__":
    unittest.main()
