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


class DashboardInternalDailyNewsApiTests(unittest.TestCase):
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

    def test_history_endpoint_requires_internal_secret(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(dashboard_main, "list_daily_news_history", new=AsyncMock()) as history_mock,
        ):
            response = self.client.get("/dashboard/api/internal/daily-news/history")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])
        history_mock.assert_not_awaited()

    def test_history_endpoint_returns_rows(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "list_daily_news_history",
                new=AsyncMock(return_value=[{"id": "1", "status": "pending"}]),
            ) as history_mock,
        ):
            response = self.client.get(
                "/dashboard/api/internal/daily-news/history",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"]["rows"][0]["id"], "1")
        history_mock.assert_awaited_once_with()

    def test_upsert_endpoint_dispatches_payload(self) -> None:
        payload = {"id": "123", "title": "Hello", "status": "pending"}
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "upsert_daily_news_item",
                new=AsyncMock(return_value={"id": "123", "title": "Hello", "status": "pending"}),
            ) as upsert_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/daily-news/items/upsert",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"]["id"], "123")
        upsert_mock.assert_awaited_once_with(
            {
                "id": "123",
                "source_url": "",
                "source_title": "",
                "title": "Hello",
                "source_summary": "",
                "summary": "",
                "source_published_at": "",
                "published_at": "",
                "source_provider": "",
                "topic_key": "",
                "status": "pending",
                "post_text": "",
                "image_url": "",
                "review_requested_at": "",
            }
        )

    def test_review_message_endpoint_dispatches_update(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "update_daily_news_review_message",
                new=AsyncMock(return_value={"id": "123", "review_message_id": 99}),
            ) as update_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/daily-news/items/123/review-message",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
                json={"review_message_id": 99},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        update_mock.assert_awaited_once_with("123", 99)

    def test_status_endpoint_dispatches_update(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "update_daily_news_status",
                new=AsyncMock(return_value={"id": "123", "status": "posted"}),
            ) as update_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/daily-news/items/123/status",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
                json={"status": "posted", "approved_at": "2026-04-03T00:00:00", "posted_at": "2026-04-03T00:00:01"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        update_mock.assert_awaited_once_with(
            "123",
            {
                "status": "posted",
                "approved_at": "2026-04-03T00:00:00",
                "posted_at": "2026-04-03T00:00:01",
                "reject_reason": "",
            },
        )

    def test_publish_endpoint_dispatches_publish(self) -> None:
        with (
            patch.object(dashboard_main.config, "amonora_internal_channel_webhook_secret", "test-secret"),
            patch.object(
                dashboard_main,
                "publish_daily_news_item",
                new=AsyncMock(return_value={"id": "123", "status": "posted"}),
            ) as publish_mock,
        ):
            response = self.client.post(
                "/dashboard/api/internal/daily-news/items/123/publish",
                headers={dashboard_main.CHANNEL_INTERNAL_HEADER: "test-secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["data"]["status"], "posted")
        publish_mock.assert_awaited_once_with("123")


if __name__ == "__main__":
    unittest.main()
