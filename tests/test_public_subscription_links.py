import json
import os
import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import httpx


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_URL_EE", "http://127.0.0.1:12054")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("XUI_USERNAME_EE", "ee-test")
os.environ.setdefault("XUI_PASSWORD_EE", "ee-pass")
os.environ.setdefault("CHANNEL_ID", "1")

from bot import public_subscription as public_subscription_module
from bot import payment_flow


class PublicSubscriptionLinkTests(unittest.IsolatedAsyncioTestCase):
    def test_happ_user_agent_is_detected_as_subscription_client(self) -> None:
        detected = public_subscription_module.is_public_subscription_client_request(
            {"user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)"}
        )

        self.assertTrue(detected)

    def test_happ_windows_user_agent_extracts_os_version(self) -> None:
        payload = public_subscription_module.build_public_subscription_request_context(
            headers={"user-agent": "Happ/2.6.0/Windows/11"},
            source_ip="127.0.0.1",
        )

        self.assertEqual(payload["device_type"], "windows")
        self.assertEqual(payload["os_name"], "Windows")
        self.assertEqual(payload["os_version"], "11")

    def test_happ_windows_numeric_user_agent_normalizes_known_build_code(self) -> None:
        payload = public_subscription_module.build_public_subscription_request_context(
            headers={"user-agent": "Happ/2.6.0/Windows/2603201341504"},
            source_ip="127.0.0.1",
        )

        self.assertEqual(payload["device_type"], "windows")
        self.assertEqual(payload["os_version"], "11_10.0.26200")

    def test_happ_android_numeric_user_agent_normalizes_known_build_code(self) -> None:
        payload = public_subscription_module.build_public_subscription_request_context(
            headers={"user-agent": "Happ/3.16.1/Android/1743595"},
            source_ip="127.0.0.1",
        )

        self.assertEqual(payload["device_type"], "android")
        self.assertEqual(payload["os_version"], "15")

    def test_linux_platform_hint_does_not_override_android_user_agent(self) -> None:
        payload = public_subscription_module.build_public_subscription_request_context(
            headers={
                "user-agent": "Happ-Proxy/1.4.2 (Android 14; SM-S918B Build/UP1A)",
                "sec-ch-ua-platform": "Linux",
            },
            source_ip="127.0.0.1",
        )

        self.assertEqual(payload["device_type"], "android")
        self.assertEqual(payload["os_name"], "Android")

    def test_linux_platform_hint_does_not_override_ios_user_agent(self) -> None:
        payload = public_subscription_module.build_public_subscription_request_context(
            headers={
                "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) Happ/3.0",
                "sec-ch-ua-platform": "Linux",
            },
            source_ip="127.0.0.1",
        )

        self.assertEqual(payload["device_type"], "ios")
        self.assertEqual(payload["os_name"], "iOS")

    def test_public_server_entries_include_estonia_when_route_exists(self) -> None:
        routes = [
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "stream_network": "tcp",
                        "vless_link": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#de-old",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="fr",
                slot_index=1,
                xui_client_id="uuid-fr",
                client_uuid="uuid-fr",
                email="device_feed_42_fr_1",
                client_data=json.dumps(
                    {
                        "stream_network": "tcp",
                        "vless_link": "vless://uuid-fr@83.171.226.197:443?type=tcp&security=reality#fr-old",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="dk",
                slot_index=1,
                xui_client_id="uuid-dk",
                client_uuid="uuid-dk",
                email="device_feed_42_dk_1",
                client_data=json.dumps(
                    {
                        "stream_network": "xhttp",
                        "vless_link": "vless://uuid-dk@dk.amonoraconnect.com:443?type=xhttp&security=reality#dk-old",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="ee",
                slot_index=1,
                xui_client_id="uuid-ee",
                client_uuid="uuid-ee",
                email="device_feed_42_ee_1",
                client_data=json.dumps(
                    {
                        "stream_network": "tcp",
                        "vless_link": "vless://uuid-ee@est.amonoraconnect.com:443?type=tcp&security=reality&flow=xtls-rprx-vision#ee-old",
                    }
                ),
            ),
        ]

        entries = public_subscription_module._build_public_server_entries(routes)

        self.assertEqual(
            entries[:2],
            [
                {"label": "🇩🇪 #1 Германия", "uri": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#de-old"},
                {"label": "🇪🇪 #1 Эстония", "uri": "vless://uuid-ee@est.amonoraconnect.com:443?type=tcp&security=reality&flow=xtls-rprx-vision#ee-old"},
            ],
        )
        self.assertEqual(entries[2:], list(public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS))

    def test_public_server_entries_use_failover_and_keep_extra_server(self) -> None:
        routes = [
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#de-old",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="dk",
                slot_index=1,
                xui_client_id="uuid-dk",
                client_uuid="uuid-dk",
                email="device_feed_42_dk_1",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-dk@dk.amonoraconnect.com:443?type=xhttp&security=reality#dk-old",
                    }
                ),
            ),
        ]

        entries = public_subscription_module._build_public_server_entries(routes)

        self.assertEqual(
            [entry["label"] for entry in entries[:2]],
            [
                "🇩🇪 #1 Германия",
                "🇪🇪 #1 Эстония",
            ],
        )
        self.assertEqual(entries[2:], list(public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS))

    async def test_bind_request_slot_recovers_missing_public_slot_before_returning_limit_error(self) -> None:
        link = SimpleNamespace(user_id=42)
        user = SimpleNamespace(id=42, is_blocked=False)
        routes = [
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps({"feed_device_fingerprint_hash": "existing-slot"}),
            ),
        ]
        request_context = {
            "fingerprint_hash": "new-device-hash",
            "device_label": "iPhone 16",
            "device_model": "iPhone 16",
            "device_type": "ios",
            "os_name": "iOS",
        }

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(public_subscription_module, "has_active_access_from_user", return_value=True),
            patch.object(public_subscription_module, "get_device_limit_for_user", return_value=3),
            patch.object(
                public_subscription_module,
                "bind_public_subscription_device_slot",
                new=AsyncMock(
                    side_effect=[
                        {"status": "limit_reached", "created": False, "slot_index": 0, "active_devices": 1},
                        {"status": "ok", "created": True, "slot_index": 2, "active_devices": 2},
                    ]
                ),
            ) as bind_mock,
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_slot_access",
                new=AsyncMock(return_value=False),
            ) as slot_sync_mock,
        ):
            result = await public_subscription_module.bind_public_subscription_request_slot(
                "abcdefghijklmnop",
                request_context=request_context,
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["slot_index"], 2)
        self.assertEqual(bind_mock.await_count, 2)
        slot_sync_mock.assert_awaited_once_with(42, slot_index=2, create_missing=True)

    async def test_bind_request_slot_keeps_limit_error_when_all_slots_are_truly_occupied(self) -> None:
        link = SimpleNamespace(user_id=42)
        user = SimpleNamespace(id=42, is_blocked=False)
        routes = [
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps({"feed_device_fingerprint_hash": "existing-slot-1"}),
            ),
            SimpleNamespace(
                slot_index=2,
                client_data=json.dumps({"feed_device_fingerprint_hash": "existing-slot-2"}),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(public_subscription_module, "has_active_access_from_user", return_value=True),
            patch.object(public_subscription_module, "get_device_limit_for_user", return_value=2),
            patch.object(
                public_subscription_module,
                "bind_public_subscription_device_slot",
                new=AsyncMock(
                    return_value={
                        "status": "limit_reached",
                        "created": False,
                        "slot_index": 0,
                        "active_devices": 2,
                    }
                ),
            ) as bind_mock,
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_slot_access",
                new=AsyncMock(return_value=False),
            ) as slot_sync_mock,
        ):
            result = await public_subscription_module.bind_public_subscription_request_slot(
                "abcdefghijklmnop",
                request_context={"fingerprint_hash": "new-device-hash"},
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(bind_mock.await_count, 1)
        slot_sync_mock.assert_not_awaited()

    async def test_page_url_reuses_existing_active_token(self) -> None:
        existing = SimpleNamespace(token="existing_public_token")

        with (
            patch.object(
                public_subscription_module,
                "get_active_public_subscription_link_for_user",
                new=AsyncMock(return_value=existing),
            ),
            patch.object(
                public_subscription_module,
                "get_or_create_public_subscription_link",
                new=AsyncMock(),
            ) as create_mock,
        ):
            page_url = await public_subscription_module.get_or_create_public_subscription_page_url_for_user(42)

        self.assertEqual(page_url, "https://client.amonora.ru/existing_public_token")
        create_mock.assert_not_awaited()

    def test_happ_wrapper_url_is_built_from_public_page_url(self) -> None:
        wrapper_url = public_subscription_module.build_public_subscription_happ_wrapper_url(
            "https://client.amonora.ru/abcdefghijklmnop"
        )

        self.assertEqual(
            wrapper_url,
            "https://client.amonora.ru/happ/add?sub=https%3A%2F%2Fclient.amonora.ru%2Fabcdefghijklmnop",
        )

    def test_feed_url_builders_use_primary_client_domain(self) -> None:
        self.assertEqual(
            public_subscription_module.build_public_subscription_page_url("abcdefghijklmnop"),
            "https://client.amonora.ru/abcdefghijklmnop",
        )
        self.assertEqual(
            public_subscription_module.build_public_subscription_feed_url("abcdefghijklmnop"),
            "https://client.amonora.ru/sub/abcdefghijklmnop",
        )
        self.assertEqual(
            public_subscription_module.build_public_subscription_feed_url("abcdefghijklmnop", include_extra=True),
            "https://client.amonora.ru/sub/abcdefghijklmnop",
        )

    def test_happ_wrapper_url_normalizes_legacy_public_page_url_to_primary_client_domain(self) -> None:
        wrapper_url = public_subscription_module.build_public_subscription_happ_wrapper_url(
            "https://client.amonoraconnect.com/abcdefghijklmnop"
        )

        self.assertEqual(
            wrapper_url,
            "https://client.amonora.ru/happ/add?sub=https%3A%2F%2Fclient.amonora.ru%2Fabcdefghijklmnop",
        )

    def test_extract_public_subscription_token_accepts_primary_and_legacy_client_hosts(self) -> None:
        self.assertEqual(
            public_subscription_module.extract_public_subscription_token_from_url(
                "https://client.amonora.ru/abcdefghijklmnop?feed=1"
            ),
            "abcdefghijklmnop",
        )
        self.assertEqual(
            public_subscription_module.extract_public_subscription_token_from_url(
                "https://client.amonoraconnect.com/sub/abcdefghijklmnop"
            ),
            "abcdefghijklmnop",
        )

    def test_happ_wrapper_rejects_foreign_host_urls(self) -> None:
        with self.assertRaises(ValueError):
            public_subscription_module.build_public_subscription_happ_wrapper_url(
                "https://happ.lavivas.org/?sub=https%3A%2F%2Fclient.amonoraconnect.com%2Fabcdefghijklmnop"
            )

    async def test_summary_returns_active_payload(self) -> None:
        user = SimpleNamespace(
            id=42,
            username="amonora_user",
            telegram_id=145,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        link = SimpleNamespace(id=9, user_id=42, token="abcdefghijklmnop")
        routes = [
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "stream_network": "tcp",
                        "vless_link": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#de-old",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="dk",
                slot_index=1,
                xui_client_id="uuid-dk",
                client_uuid="uuid-dk",
                email="device_feed_42_dk_1",
                client_data=json.dumps(
                    {
                        "stream_network": "xhttp",
                        "vless_link": "vless://uuid-dk@dk.amonoraconnect.com:443?type=xhttp&security=reality#dk-old",
                        "reserve_vless_link": "vless://uuid-dk@dk.amonoraconnect.com:8443?type=xhttp&security=reality#dk-reserve-old",
                    }
                ),
            ),
            SimpleNamespace(status="disabled"),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ) as sync_mock,
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "get_user_vpn_clients",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                public_subscription_module,
                "get_device_limit_for_user",
                return_value=10,
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_summary_by_token("abcdefghijklmnop")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["display_name"], "@amonora_user")
        self.assertEqual(payload["telegram_id"], 145)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["status_label"], "Активна")
        self.assertEqual(payload["feed_url"], "https://client.amonora.ru/sub/abcdefghijklmnop")
        self.assertNotEqual(payload["feed_url"], payload["page_url"])
        self.assertEqual(payload["traffic_limit"], "∞")
        self.assertEqual(payload["traffic_used"], "0 МБ")
        self.assertEqual(payload["devices_limit"], 10)
        self.assertEqual(payload["bound_devices"], [])
        self.assertEqual(payload["bound_devices_count"], 0)
        self.assertEqual(payload["account_devices"], [])
        self.assertEqual(payload["account_devices_count"], 0)
        self.assertEqual(
            payload["servers"][:1],
            [
                {"label": "🇩🇪 #1 Германия"},
            ],
        )
        self.assertEqual(payload["servers"][1:2], [{"label": "🇪🇪 #1 Эстония"}])
        self.assertEqual(
            payload["servers"][2:],
            [{"label": entry["label"]} for entry in public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS],
        )
        self.assertEqual(len(payload["install_links"]), 7)
        self.assertEqual(payload["install_links"][0]["key"], "android")
        self.assertEqual(payload["install_links"][-1]["key"], "android_tv")
        self.assertGreaterEqual(len(payload["install_links"][0]["links"]), 2)
        sync_mock.assert_awaited_once_with(42, create_missing=True)

    async def test_summary_counts_bound_and_legacy_devices_together(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username="amonora_user",
            telegram_id=145,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        routes = [
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "stream_network": "tcp",
                        "vless_link": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#de-old",
                        "feed_device_fingerprint_hash": "slot-1",
                        "device_name": "iPhone 12",
                        "device_model": "iPhone 12",
                        "device_type": "ios",
                        "os_name": "iOS",
                        "os_version": "18.4",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                protocol="vless",
                country_code="dk",
                slot_index=1,
                xui_client_id="uuid-dk",
                client_uuid="uuid-dk",
                email="device_feed_42_dk_1",
                client_data=json.dumps(
                    {
                        "stream_network": "xhttp",
                        "vless_link": "vless://uuid-dk@dk.amonoraconnect.com:443?type=xhttp&security=reality#dk-old",
                        "reserve_vless_link": "vless://uuid-dk@dk.amonoraconnect.com:8443?type=xhttp&security=reality#dk-reserve-old",
                        "feed_device_fingerprint_hash": "slot-1",
                        "device_name": "iPhone 12",
                        "device_model": "iPhone 12",
                        "device_type": "ios",
                        "os_name": "iOS",
                        "os_version": "18.4",
                    }
                ),
            ),
        ]
        legacy_devices = [
            SimpleNamespace(
                id=71,
                email="legacy-device-1",
                created_at=datetime(2026, 4, 10, 12, 0, 0),
                client_data=json.dumps(
                    {
                        "device_name": "Office-PC_x86_64",
                        "device_type": "windows",
                        "os_name": "Windows",
                        "os_version": "11_10.0.26200",
                    }
                ),
            )
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "get_user_vpn_clients",
                new=AsyncMock(return_value=legacy_devices),
            ),
            patch.object(
                public_subscription_module,
                "get_device_limit_for_user",
                return_value=10,
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_summary_by_token(token)

        assert payload is not None
        self.assertEqual(payload["bound_devices_count"], 1)
        self.assertEqual(payload["account_devices_count"], 2)
        self.assertEqual(len(payload["account_devices"]), 2)
        self.assertEqual(payload["account_devices"][0]["kind"], "public_slot")
        self.assertEqual(payload["account_devices"][1]["kind"], "legacy_device")
        self.assertEqual(payload["account_devices"][1]["legacy_status"], "soft_migration_pending")
        self.assertEqual(payload["account_devices"][1]["legacy_status_label"], "Работает в legacy-режиме")
        self.assertIn("Legacy", payload["account_devices"][1]["source_label"])

    async def test_summary_and_feed_degrade_gracefully_when_route_provisioning_raises_read_error(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username="amonora_user",
            telegram_id=145,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        failing_provisioner = SimpleNamespace(
            health_check=AsyncMock(side_effect=httpx.ReadError("panel unavailable")),
            close=AsyncMock(),
        )

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                public_subscription_module,
                "get_user_vpn_clients",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                public_subscription_module,
                "get_device_limit_for_user",
                return_value=3,
            ),
            patch.object(
                public_subscription_module,
                "get_vless_provisioner",
                return_value=failing_provisioner,
            ),
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ),
        ):
            summary = await public_subscription_module.get_public_subscription_summary_by_token(token)
            feed_payload = await public_subscription_module.get_public_subscription_feed_payload(token)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["feed_url"], "https://client.amonora.ru/sub/abcdefghijklmnop")
        self.assertEqual(summary["page_url"], "https://client.amonora.ru/abcdefghijklmnop")
        self.assertGreater(len(summary["servers"]), 0)
        self.assertEqual(summary["bound_devices"], [])
        self.assertIsNotNone(feed_payload)
        assert feed_payload is not None
        content, headers = feed_payload
        self.assertIn("profile-title", headers)
        self.assertGreater(len([line for line in content.splitlines() if line.strip()]), 0)

    async def test_feed_payload_builds_headers_and_route_body(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        routes = [
            SimpleNamespace(
                id=1,
                user_id=42,
                country_code="de",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-1",
                xui_client_id="uuid-1",
                email="device_feed_42_de_2",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-1@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#old-name",
                    }
                ),
            ),
            SimpleNamespace(
                id=2,
                user_id=42,
                country_code="dk",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-2",
                xui_client_id="uuid-2",
                email="device_feed_42_dk_2",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-2@dk.amonoraconnect.com:443?type=xhttp&security=reality#old-dk",
                        "reserve_vless_link": "vless://uuid-2@dk.amonoraconnect.com:8443?type=xhttp&security=reality#old-dk-reserve",
                    }
                ),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ) as touch_mock,
        ):
            payload = await public_subscription_module.get_public_subscription_feed_payload(token)

        self.assertIsNotNone(payload)
        assert payload is not None
        content, headers = payload
        lines = [line for line in content.splitlines() if line.strip()]
        self.assertEqual(
            lines[0],
            f"#announce: {public_subscription_module._base64_prefixed_header_value(public_subscription_module.PUBLIC_SUBSCRIPTION_ANNOUNCE_TEXT)}",
        )
        self.assertEqual(lines[1], "#sub-expire: 1")
        self.assertEqual(lines[2], "#sub-expire-button-link: https://t.me/amonora_v_2_0_bot")
        uri_lines = lines[3:]
        self.assertEqual(
            len(uri_lines),
            len(public_subscription_module.PUBLIC_SUBSCRIPTION_VISIBLE_COUNTRY_CODES)
            + len(public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS),
        )
        self.assertTrue(uri_lines[0].startswith("vless://uuid-1@"))
        self.assertIn(f"#{quote(public_subscription_module._user_server_label('de', 2))}", uri_lines[0])
        self.assertTrue(uri_lines[0].startswith("vless://"))
        self.assertTrue(uri_lines[1].startswith("vless://"))
        self.assertNotIn("profile-title", content)
        self.assertNotIn("hide-settings", content)
        self.assertNotIn("profile-update-interval", content)
        self.assertNotIn("<html", content.lower())
        self.assertNotIn("{", content)
        self.assertEqual(
            uri_lines[2:],
            [
                public_subscription_module._rewrite_public_vless_uri(
                    str(entry["uri"]),
                    label=str(entry["label"]),
                )
                for entry in public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS
            ],
        )
        self.assertEqual(headers["profile-web-page-url"], f"https://client.amonora.ru/{token}")
        self.assertEqual(headers["profile-update-interval"], "3")
        self.assertEqual(headers["profile-title"], "Amonora")
        self.assertEqual(headers["support-url"], "https://t.me/amonora_v_2_0_bot")
        self.assertEqual(
            headers["announce"],
            public_subscription_module._base64_prefixed_header_value(
                public_subscription_module.PUBLIC_SUBSCRIPTION_ANNOUNCE_TEXT
            ),
        )
        self.assertNotIn("sub-info-color", headers)
        self.assertNotIn("sub-info-text", headers)
        self.assertEqual(headers["sub-expire"], "1")
        self.assertEqual(headers["sub-expire-button-link"], "https://t.me/amonora_v_2_0_bot")
        self.assertIn("expire=", headers["subscription-userinfo"])
        touch_mock.assert_awaited_once_with(token, feed_access=True)

    async def test_feed_payload_include_extra_keeps_legacy_query_compatible_with_unified_feed(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        routes = [
            SimpleNamespace(
                id=1,
                user_id=42,
                country_code="de",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-1",
                xui_client_id="uuid-1",
                email="device_feed_42_de_1",
                client_data=json.dumps({"vless_link": "vless://uuid-1@de.example:443?type=tcp#one"}),
            ),
            SimpleNamespace(
                id=2,
                user_id=42,
                country_code="dk",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-2",
                xui_client_id="uuid-2",
                email="device_feed_42_dk_1",
                client_data=json.dumps({"vless_link": "vless://uuid-2@dk.example:443?type=tcp#two"}),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ) as touch_mock,
        ):
            default_payload = await public_subscription_module.get_public_subscription_feed_payload(token)
            extra_payload = await public_subscription_module.get_public_subscription_feed_payload(
                token,
                include_extra=True,
            )

        self.assertIsNotNone(default_payload)
        self.assertIsNotNone(extra_payload)
        assert default_payload is not None
        assert extra_payload is not None
        self.assertEqual(default_payload[0], extra_payload[0])
        self.assertEqual(default_payload[1], extra_payload[1])
        self.assertEqual(touch_mock.await_count, 2)

    def test_build_public_server_entries_exposes_only_primary_routes(self) -> None:
        routes = [
            SimpleNamespace(
                status="active",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-de@ffconnect.amonoraconnect.com:443?type=tcp&security=reality#old-de",
                    }
                ),
            ),
            SimpleNamespace(
                status="active",
                country_code="dk",
                slot_index=1,
                xui_client_id="uuid-dk",
                client_uuid="uuid-dk",
                email="device_feed_42_dk_1",
                client_data=json.dumps(
                    {
                        "vless_link": "vless://uuid-dk@dk.amonoraconnect.com:443?type=xhttp&security=reality#old-dk",
                        "reserve_vless_link": "vless://uuid-dk@dk.amonoraconnect.com:8443?type=xhttp&security=reality#old-dk-reserve",
                    }
                ),
            ),
        ]

        entries = public_subscription_module._build_public_server_entries(routes)

        self.assertEqual(
            [entry["label"] for entry in entries[:2]],
            [
                "🇩🇪 #1 Германия",
                "🇪🇪 #1 Эстония",
            ],
        )
        self.assertEqual(entries[2:], list(public_subscription_module.PUBLIC_SUBSCRIPTION_EXTRA_SERVERS))
        self.assertTrue(entries[0]["uri"].startswith("vless://uuid-de@"))

    def test_build_public_server_entries_falls_back_when_route_port_is_malformed(self) -> None:
        routes = [
            SimpleNamespace(
                status="active",
                country_code="de",
                slot_index=1,
                xui_client_id="uuid-de",
                client_uuid="uuid-de",
                email="device_feed_42_de_1",
                client_data=json.dumps(
                    {
                        "port": "bad-port",
                        "stream_network": "tcp",
                        "reality_server_name": "www.microsoft.com",
                        "reality_short_id": "primary01",
                        "reality_public_key": "pubkey123",
                    }
                ),
            ),
        ]

        entries = public_subscription_module._build_public_server_entries(routes)

        self.assertGreaterEqual(len(entries), 1)
        self.assertEqual(entries[0]["label"], "🇩🇪 #1 Германия")
        self.assertIn("@ffconnect.amonoraconnect.com:443", entries[0]["uri"])

    async def test_feed_payload_skips_full_sync_when_slot_routes_are_ready(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        routes = [
            SimpleNamespace(
                id=1,
                user_id=42,
                country_code="de",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-1",
                xui_client_id="uuid-1",
                email="device_feed_42_de_1",
                client_data=json.dumps({"vless_link": "vless://uuid-1@de.example:443?type=tcp#one"}),
            ),
            SimpleNamespace(
                id=2,
                user_id=42,
                country_code="dk",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-2",
                xui_client_id="uuid-2",
                email="device_feed_42_dk_1",
                client_data=json.dumps({"vless_link": "vless://uuid-2@dk.example:443?type=tcp#two"}),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ) as sync_mock,
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_feed_payload(token, slot_index=1)

        self.assertIsNotNone(payload)
        sync_mock.assert_not_awaited()

    async def test_feed_payload_without_slot_index_exposes_all_active_slots(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        routes = [
            SimpleNamespace(
                id=1,
                user_id=42,
                country_code="de",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-1",
                xui_client_id="uuid-1",
                email="device_feed_42_de_1",
                client_data=json.dumps({"vless_link": "vless://uuid-1@de.example:443?type=tcp#one"}),
            ),
            SimpleNamespace(
                id=2,
                user_id=42,
                country_code="dk",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-2",
                xui_client_id="uuid-2",
                email="device_feed_42_dk_1",
                client_data=json.dumps({"vless_link": "vless://uuid-2@dk.example:443?type=tcp#two"}),
            ),
            SimpleNamespace(
                id=3,
                user_id=42,
                country_code="de",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-3",
                xui_client_id="uuid-3",
                email="device_feed_42_de_2",
                client_data=json.dumps({"vless_link": "vless://uuid-3@de2.example:443?type=tcp#three"}),
            ),
            SimpleNamespace(
                id=4,
                user_id=42,
                country_code="dk",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-4",
                xui_client_id="uuid-4",
                email="device_feed_42_dk_2",
                client_data=json.dumps({"vless_link": "vless://uuid-4@dk2.example:443?type=tcp#four"}),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(return_value=routes),
            ),
            patch.object(
                public_subscription_module,
                "get_device_limit_for_user",
                return_value=2,
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_feed_payload(token)

        self.assertIsNotNone(payload)
        body, _ = payload
        self.assertIn(f"#{quote(public_subscription_module._user_server_label('de', 1))}", body)
        self.assertIn(f"#{quote(public_subscription_module._user_server_label('de', 2))}", body)

    async def test_feed_payload_syncs_only_requested_slot_when_slot_routes_are_missing(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="active",
            subscription_expires_at=datetime(2026, 4, 25, 10, 0, 0),
            trial_expires_at=None,
        )
        initial_routes = [
            SimpleNamespace(
                id=1,
                user_id=42,
                country_code="de",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-1",
                xui_client_id="uuid-1",
                email="device_feed_42_de_2",
                client_data=json.dumps({"vless_link": "vless://uuid-1@de.example:443?type=tcp#one"}),
            ),
            SimpleNamespace(
                id=2,
                user_id=42,
                country_code="dk",
                slot_index=2,
                status="active",
                protocol="vless",
                client_uuid="uuid-2",
                xui_client_id="uuid-2",
                email="device_feed_42_dk_2",
                client_data=json.dumps({"vless_link": "vless://uuid-2@dk.example:443?type=tcp#two"}),
            ),
        ]
        synced_routes = [
            SimpleNamespace(
                id=3,
                user_id=42,
                country_code="de",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-3",
                xui_client_id="uuid-3",
                email="device_feed_42_de_1",
                client_data=json.dumps({"vless_link": "vless://uuid-3@de.example:443?type=tcp#three"}),
            ),
            SimpleNamespace(
                id=4,
                user_id=42,
                country_code="dk",
                slot_index=1,
                status="active",
                protocol="vless",
                client_uuid="uuid-4",
                xui_client_id="uuid-4",
                email="device_feed_42_dk_1",
                client_data=json.dumps({"vless_link": "vless://uuid-4@dk.example:443?type=tcp#four"}),
            ),
        ]

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                public_subscription_module,
                "get_public_subscription_routes_for_user",
                new=AsyncMock(side_effect=[initial_routes, synced_routes]),
            ),
            patch.object(
                public_subscription_module,
                "sync_public_subscription_slot_access",
                new=AsyncMock(return_value=False),
            ) as slot_sync_mock,
            patch.object(
                public_subscription_module,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ) as full_sync_mock,
            patch.object(
                public_subscription_module,
                "touch_public_subscription_surface",
                new=AsyncMock(return_value=True),
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_feed_payload(token, slot_index=1)

        self.assertIsNotNone(payload)
        slot_sync_mock.assert_awaited_once_with(42, slot_index=1, create_missing=True)
        full_sync_mock.assert_not_awaited()

    async def test_feed_payload_is_unavailable_for_inactive_user(self) -> None:
        token = "abcdefghijklmnop"
        link = SimpleNamespace(id=9, user_id=42, token=token)
        user = SimpleNamespace(
            id=42,
            username=None,
            telegram_id=987654321,
            is_blocked=False,
            subscription_status="inactive",
            subscription_expires_at=None,
            trial_expires_at=None,
        )

        with (
            patch.object(
                public_subscription_module,
                "get_public_subscription_link_by_token",
                new=AsyncMock(return_value=link),
            ),
            patch.object(
                public_subscription_module,
                "get_user_by_id",
                new=AsyncMock(return_value=user),
            ),
        ):
            payload = await public_subscription_module.get_public_subscription_feed_payload(token)

        self.assertIsNone(payload)

    async def test_bound_devices_for_user_groups_slot_metadata(self) -> None:
        routes = [
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps(
                    {
                        "feed_device_fingerprint_hash": "aaa",
                        "device_model": "SM-S918B",
                        "device_type": "android",
                        "os_name": "Android",
                        "os_version": "14",
                    }
                ),
            ),
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps({"feed_device_fingerprint_hash": "aaa"}),
            ),
            SimpleNamespace(
                slot_index=2,
                client_data=json.dumps({}),
            ),
        ]

        with patch.object(
            public_subscription_module,
            "get_public_subscription_routes_for_user",
            new=AsyncMock(return_value=routes),
        ):
            devices = await public_subscription_module.get_public_subscription_bound_devices_for_user(42)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["kind"], "public_slot")
        self.assertEqual(devices[0]["device_model"], "SM-S918B")
        self.assertEqual(devices[0]["os_version"], "14")

    async def test_bound_devices_normalize_existing_happ_os_versions(self) -> None:
        routes = [
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps(
                    {
                        "feed_device_fingerprint_hash": "aaa",
                        "device_model": "Home-PC_x86_64",
                        "device_type": "windows",
                        "os_name": "Windows",
                        "os_version": "2603201341504",
                        "user_agent": "Happ/2.6.0/Windows/2603201341504",
                    }
                ),
            ),
            SimpleNamespace(
                slot_index=2,
                client_data=json.dumps(
                    {
                        "feed_device_fingerprint_hash": "bbb",
                        "device_model": "23049PCD8G",
                        "device_type": "android",
                        "os_name": "Android",
                        "os_version": "1743595",
                        "user_agent": "Happ/3.16.1/Android/1743595",
                    }
                ),
            ),
        ]

        with patch.object(
            public_subscription_module,
            "get_public_subscription_routes_for_user",
            new=AsyncMock(return_value=routes),
        ):
            devices = await public_subscription_module.get_public_subscription_bound_devices_for_user(42)

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["os_version"], "11_10.0.26200")
        self.assertEqual(devices[1]["os_version"], "15")

    async def test_bound_devices_recover_android_type_from_saved_linux_hint(self) -> None:
        routes = [
            SimpleNamespace(
                slot_index=1,
                client_data=json.dumps(
                    {
                        "feed_device_fingerprint_hash": "aaa",
                        "device_model": "SM-S918B",
                        "device_type": "linux",
                        "os_name": "Android",
                        "os_version": "14",
                    }
                ),
            ),
        ]

        with patch.object(
            public_subscription_module,
            "get_public_subscription_routes_for_user",
            new=AsyncMock(return_value=routes),
        ):
            devices = await public_subscription_module.get_public_subscription_bound_devices_for_user(42)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["device_type"], "android")
        self.assertEqual(devices[0]["os_name"], "Android")

    async def test_sync_user_vpn_access_also_syncs_existing_public_surface(self) -> None:
        with (
            patch.object(payment_flow, "get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch.object(
                payment_flow,
                "sync_public_subscription_access",
                new=AsyncMock(return_value=False),
            ) as public_sync_mock,
        ):
            failed = await payment_flow.sync_user_vpn_access(42, None)

        self.assertFalse(failed)
        public_sync_mock.assert_awaited_once_with(42, create_missing=False)


if __name__ == "__main__":
    unittest.main()
