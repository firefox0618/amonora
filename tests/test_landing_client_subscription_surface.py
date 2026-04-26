import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.responses import PlainTextResponse

import landing.main as landing_main


class LandingClientSubscriptionSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_cm = TestClient(landing_main.app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_cm.__exit__(None, None, None)

    def test_main_host_cannot_open_client_summary_api(self) -> None:
        response = self.client.get("/api/public/subscriptions/abcdefghijklmnop/summary")

        self.assertEqual(response.status_code, 404)

    def test_client_host_root_redirects_back_to_main_site(self) -> None:
        response = self.client.get(
            "/",
            headers={"host": "client.amonoraconnect.com"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://www.amonoraconnect.com")

    def test_client_host_token_page_serves_shell(self) -> None:
        response = self.client.get(
            "/abcdefghijklmnop",
            headers={"host": "client.amonoraconnect.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("window.__AMONORA_CLIENT_TOKEN__", response.text)
        self.assertIn("/client-static/assets/app.js", response.text)
        self.assertIn("/static/favicon.svg?v=20260410-client-sakura-v5", response.text)

    def test_client_host_happ_wrapper_serves_auto_open_shell(self) -> None:
        response = self.client.get(
            "/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
            headers={"host": "client.amonoraconnect.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("happ://add/https://client.amonoraconnect.com/abcdefghijklmnop?feed=1", response.text)
        self.assertIn("Скопировать ссылку", response.text)
        self.assertIn("Открыть страницу подписки", response.text)

    def test_client_host_happ_wrapper_rejects_foreign_subscription_urls(self) -> None:
        response = self.client.get(
            "/happ/add?sub=https%3A%2F%2Fhapp.lavivas.org%2Fabc",
            headers={"host": "client.amonoraconnect.com"},
        )

        self.assertEqual(response.status_code, 404)

    def test_client_host_token_page_returns_feed_for_happ_client(self) -> None:
        with (
            patch.object(
                landing_main,
                "bind_public_subscription_request_slot",
                return_value={"status": "ok", "slot_index": 2},
            ),
            patch.object(
                landing_main,
                "get_public_subscription_feed_payload",
                return_value=("vless://feed\n", {"profile-title": "Amonora"}),
            ) as feed_mock,
        ):
            response = self.client.get(
                "/abcdefghijklmnop",
                headers={
                    "host": "client.amonoraconnect.com",
                    "user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "vless://feed\n")
        feed_mock.assert_called_once_with("abcdefghijklmnop", slot_index=2)

    def test_client_host_summary_returns_payload(self) -> None:
        summary = {
            "display_name": "@amonora",
            "telegram_id": 1456398235,
            "status": "active",
            "status_label": "Активна",
            "expires_at": "2026-04-25T10:00:00",
            "days_left": 10,
            "traffic_used": "0 МБ",
            "traffic_limit": "∞",
            "feed_url": "https://client.amonoraconnect.com/abcdefghijklmnop?feed=1",
            "page_url": "https://client.amonoraconnect.com/abcdefghijklmnop",
            "bot_url": "https://t.me/amonora_v_2_0_bot",
            "is_active": True,
            "channel_url": "https://t.me/amonora_new",
            "support_url": "https://t.me/amonora_support_bot",
            "install_links": [],
            "devices_limit": 3,
            "servers": [{"label": "#1 Германия"}, {"label": "#1 Дания"}, {"label": "#2 Дания"}],
            "bound_devices": [],
            "bound_devices_count": 0,
        }

        with patch.object(landing_main, "get_public_subscription_summary_by_token", return_value=summary):
            response = self.client.get(
                "/api/public/subscriptions/abcdefghijklmnop/summary",
                headers={"host": "client.amonoraconnect.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["subscription"]["status"], "active")

    def test_client_host_feed_returns_not_found_for_unknown_token(self) -> None:
        with patch.object(landing_main, "get_public_subscription_feed_payload", return_value=None):
            response = self.client.get(
                "/sub/abcdefghijklmnop",
                headers={"host": "client.amonoraconnect.com"},
            )

        self.assertEqual(response.status_code, 404)

    def test_plaintext_response_helper_allows_utf8_announce_header(self) -> None:
        response = landing_main._plaintext_response_with_headers(
            "ok",
            headers={"announce": "Все самое лучшее для Вас 😊"},
        )

        self.assertIsInstance(response, PlainTextResponse)
        self.assertIn((b"announce", "Все самое лучшее для Вас 😊".encode("utf-8")), response.raw_headers)


if __name__ == "__main__":
    unittest.main()
