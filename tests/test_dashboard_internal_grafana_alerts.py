import os
import unittest

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

import dashboard.main as dashboard_main


class DashboardInternalGrafanaAlertsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.startup_handlers = list(dashboard_main.app.router.on_startup)
        dashboard_main.app.router.on_startup.clear()
        cls.client_cm = TestClient(dashboard_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)
        dashboard_main.app.router.on_startup[:] = cls.startup_handlers

    def test_webhook_rejects_wrong_secret(self) -> None:
        with patch.object(dashboard_main.config, "amonora_grafana_alerts_webhook_secret", "grafana-secret"):
            response = self.client.post(
                "/dashboard/api/internal/grafana/alerts/wrong",
                headers={"content-type": "application/json"},
                json={},
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_webhook_normalizes_firing_payload_into_control_event(self) -> None:
        payload = {
            "status": "firing",
            "groupKey": "{alertname=\"payment_drop\"}",
            "commonLabels": {
                "alertname": "payment_success_drop",
                "alert_class": "revenue",
                "severity": "critical",
            },
            "commonAnnotations": {
                "summary": "Платежи просели",
                "description": "Проверить revenue funnel",
                "dashboard_url": "https://grafana.amonoraconnect.com/d/amonora-revenue-monetization",
            },
            "alerts": [{"status": "firing"}],
        }
        with (
            patch.object(dashboard_main.config, "amonora_grafana_alerts_webhook_secret", "grafana-secret"),
            patch.object(dashboard_main, "create_control_event", new=AsyncMock(return_value=type("Event", (), {"id": 77})())) as event_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/grafana/alerts/grafana-secret",
                headers={"content-type": "application/json"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        event_mock.assert_awaited_once()
        kwargs = event_mock.await_args.kwargs
        self.assertEqual(kwargs["category"], "payments")
        self.assertEqual(kwargs["severity"], "CRITICAL")
        self.assertEqual(kwargs["entity_type"], "grafana_alert")
        self.assertIsNotNone(kwargs["dedupe_key"])
        self.assertEqual(kwargs["payload"]["alert_class"], "revenue")

    def test_webhook_resolved_payload_uses_resolve_dedupe_key(self) -> None:
        payload = {
            "status": "resolved",
            "groupKey": "{alertname=\"repair_pressure\"}",
            "commonLabels": {
                "alertname": "repair_pressure",
                "alert_class": "ops",
                "severity": "warning",
            },
            "commonAnnotations": {"summary": "Repair pressure normalized"},
            "alerts": [{"status": "resolved"}],
        }
        with (
            patch.object(dashboard_main.config, "amonora_grafana_alerts_webhook_secret", "grafana-secret"),
            patch.object(dashboard_main, "create_control_event", new=AsyncMock(return_value=None)) as event_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/grafana/alerts/grafana-secret",
                headers={"content-type": "application/json"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        kwargs = event_mock.await_args.kwargs
        self.assertIsNone(kwargs["dedupe_key"])
        self.assertIsNotNone(kwargs["resolve_dedupe_key"])


if __name__ == "__main__":
    unittest.main()
