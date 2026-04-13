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


class DashboardInternalChannelApiTests(unittest.TestCase):
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

    def test_generate_endpoint_rejects_invalid_secret(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(dashboard_main, "generate_due_channel_content_items", new=AsyncMock()) as generate_mock,
        ):
            response = self.client.post("/dashboard/api/internal/channel/generate", json={})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])
        generate_mock.assert_not_awaited()

    def test_generate_endpoint_dispatches_due_generation_with_valid_secret(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "generate_due_channel_content_items",
                new=AsyncMock(return_value={"processed_count": 1}),
            ) as generate_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/channel/generate",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
                json={"notify_missing_content": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"]["processed_count"], 1)
        generate_mock.assert_awaited_once_with(notify_missing_content=True)

    def test_publish_endpoint_dispatches_single_item_with_valid_secret(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "publish_channel_content_item",
                new=AsyncMock(return_value={"id": 41, "status": "published"}),
            ) as publish_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/channel/publish",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
                json={"item_id": 41, "allow_failed_retry": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"]["id"], 41)
        publish_mock.assert_awaited_once_with(41, allow_failed_retry=True)


if __name__ == "__main__":
    unittest.main()
