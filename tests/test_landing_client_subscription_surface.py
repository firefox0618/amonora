import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.responses import PlainTextResponse

import landing.main as landing_main

PRIMARY_CLIENT_HOST = "client.amonora.ru"
LEGACY_CLIENT_HOST = "client.amonoraconnect.com"
PRIMARY_SITE_URL = "https://amonora.ru"


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
            headers={"host": LEGACY_CLIENT_HOST},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], PRIMARY_SITE_URL)

    def test_primary_client_host_root_redirects_back_to_primary_main_site(self) -> None:
        response = self.client.get(
            "/",
            headers={"host": PRIMARY_CLIENT_HOST},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], PRIMARY_SITE_URL)

    def test_client_host_token_page_serves_shell(self) -> None:
        response = self.client.get(
            "/abcdefghijklmnop",
            headers={"host": PRIMARY_CLIENT_HOST},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("window.__AMONORA_CLIENT_TOKEN__", response.text)
        self.assertIn("/client-static/assets/app.js", response.text)
        self.assertIn("/static/favicon.svg?v=20260515-client-domain-v6", response.text)

    def test_client_host_happ_wrapper_serves_auto_open_shell(self) -> None:
        response = self.client.get(
            "/happ/add?sub=https%3A%2F%2Fclient.amonora.ru%2Fabcdefghijklmnop",
            headers={"host": PRIMARY_CLIENT_HOST},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("happ://add/https://client.amonora.ru/sub/abcdefghijklmnop", response.text)
        self.assertIn("Скопировать ссылку", response.text)
        self.assertIn("Открыть страницу подписки", response.text)

    def test_legacy_client_host_happ_wrapper_accepts_legacy_subscription_url(self) -> None:
        response = self.client.get(
            "/happ/add?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop",
            headers={"host": LEGACY_CLIENT_HOST},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("happ://add/https://client.amonora.ru/sub/abcdefghijklmnop", response.text)

    def test_client_host_happ_wrapper_rejects_foreign_subscription_urls(self) -> None:
        response = self.client.get(
            "/happ/add?sub=https%3A%2F%2Fhapp.lavivas.org%2Fabc",
            headers={"host": PRIMARY_CLIENT_HOST},
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
                    "host": LEGACY_CLIENT_HOST,
                    "user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "vless://feed\n")
        feed_mock.assert_called_once_with("abcdefghijklmnop", slot_index=2, include_extra=False)

    def test_legacy_client_host_token_page_feed_query_is_accepted(self) -> None:
        with (
            patch.object(
                landing_main,
                "bind_public_subscription_request_slot",
                return_value={"status": "ok", "slot_index": 1},
            ),
            patch.object(
                landing_main,
                "get_public_subscription_feed_payload",
                return_value=("vless://feed\n", {"profile-title": "Amonora"}),
            ) as feed_mock,
        ):
            response = self.client.get(
                "/abcdefghijklmnop?feed=1",
                headers={"host": LEGACY_CLIENT_HOST},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://client.amonora.ru/sub/abcdefghijklmnop")
        feed_mock.assert_not_called()

    def test_primary_client_host_token_page_feed_query_supports_include_extra(self) -> None:
        with (
            patch.object(
                landing_main,
                "bind_public_subscription_request_slot",
                return_value={"status": "ok", "slot_index": 1},
            ),
            patch.object(
                landing_main,
                "get_public_subscription_feed_payload",
                return_value=("vless://feed\n", {"profile-title": "Amonora"}),
            ) as feed_mock,
        ):
            response = self.client.get(
                "/abcdefghijklmnop?feed=1&include_extra=1",
                headers={"host": PRIMARY_CLIENT_HOST},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://client.amonora.ru/sub/abcdefghijklmnop?include_extra=1")
        feed_mock.assert_not_called()

    def test_client_host_feed_passes_include_extra_flag(self) -> None:
        with patch.object(
            landing_main,
            "get_public_subscription_feed_payload",
            return_value=("vless://feed\n", {"profile-title": "Amonora"}),
        ) as feed_mock:
            response = self.client.get(
                "/sub/abcdefghijklmnop?include_extra=1",
                headers={"host": PRIMARY_CLIENT_HOST},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "vless://feed\n")
        feed_mock.assert_called_once_with("abcdefghijklmnop", slot_index=None, include_extra=True)

    def test_client_host_token_page_returns_clear_expired_message_for_happ_client(self) -> None:
        with (
            patch.object(landing_main, "bind_public_subscription_request_slot", return_value=None),
            patch.object(
                landing_main,
                "describe_public_subscription_feed_failure",
                return_value=(410, "Subscription expired"),
            ),
        ):
            response = self.client.get(
                "/abcdefghijklmnop",
                headers={
                    "host": PRIMARY_CLIENT_HOST,
                    "user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)",
                },
            )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.text, "Subscription expired")

    def test_client_host_token_page_returns_clear_limit_message_for_happ_client(self) -> None:
        with patch.object(
            landing_main,
            "bind_public_subscription_request_slot",
            return_value={"status": "limit_reached", "slot_index": 0},
        ):
            response = self.client.get(
                "/abcdefghijklmnop",
                headers={
                    "host": PRIMARY_CLIENT_HOST,
                    "user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.text, "Device limit reached")

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
            "feed_url": "https://client.amonora.ru/sub/abcdefghijklmnop",
            "page_url": "https://client.amonora.ru/abcdefghijklmnop",
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
                headers={"host": PRIMARY_CLIENT_HOST},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["subscription"]["status"], "active")
        self.assertNotEqual(
            response.json()["subscription"]["feed_url"],
            response.json()["subscription"]["page_url"],
        )

    def test_client_host_feed_returns_not_found_for_unknown_token(self) -> None:
        with (
            patch.object(landing_main, "get_public_subscription_feed_payload", return_value=None),
            patch.object(
                landing_main,
                "describe_public_subscription_feed_failure",
                return_value=(404, "Not Found"),
            ),
        ):
            response = self.client.get(
                "/sub/abcdefghijklmnop",
                headers={"host": LEGACY_CLIENT_HOST},
            )

        self.assertEqual(response.status_code, 404)

    def test_client_host_feed_returns_clear_route_error_when_payload_is_unavailable(self) -> None:
        with (
            patch.object(landing_main, "get_public_subscription_feed_payload", return_value=None),
            patch.object(
                landing_main,
                "describe_public_subscription_feed_failure",
                return_value=(503, "Subscription routes unavailable"),
            ),
        ):
            response = self.client.get(
                "/sub/abcdefghijklmnop",
                headers={"host": PRIMARY_CLIENT_HOST},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.text, "Subscription routes unavailable")

    def test_plaintext_response_helper_allows_utf8_announce_header(self) -> None:
        response = landing_main._plaintext_response_with_headers(
            "ok",
            headers={"announce": "Все самое лучшее для Вас 😊"},
        )

        self.assertIsInstance(response, PlainTextResponse)
        self.assertIn((b"announce", "Все самое лучшее для Вас 😊".encode("utf-8")), response.raw_headers)


if __name__ == "__main__":
    unittest.main()
