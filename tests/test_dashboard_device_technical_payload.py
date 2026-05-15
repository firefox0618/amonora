import json
import unittest

from datetime import datetime
from unittest.mock import AsyncMock, patch

from dashboard import services as dashboard_services
from dashboard.services import get_user_detail


class DashboardDeviceTechnicalPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_xui_live_device_ips_respects_explicit_provider_type(self) -> None:
        result = await dashboard_services._fetch_xui_live_device_ips("ee", "device_ee_1", provider_type="amneziawg")

        self.assertEqual(result["ip_source"], "metadata")
        self.assertEqual(result["ip_source_label"], "Из сохранённой метадаты")

    async def test_get_user_detail_exposes_device_technical_fields_when_available(self) -> None:
        user = type(
            "User",
            (),
            {
                "id": 333,
                "telegram_id": 777333,
                "username": "device-tech-user",
                "preferred_protocol": "vless",
                "is_blocked": False,
                "trial_used": False,
                "created_at": datetime(2026, 3, 26, 9, 0, 0),
                "vpn_repair_needed": False,
                "vpn_repair_reason": None,
                "vpn_repair_marked_at": None,
                "last_activity_at": datetime(2026, 3, 26, 9, 45, 0),
            },
        )()
        device = type(
            "VpnClient",
            (),
            {
                "id": 19,
                "protocol": "vless",
                "created_at": datetime(2026, 3, 26, 9, 5, 0),
                "email": "device_333_19",
                "client_data": json.dumps(
                    {
                        "country_code": "dk",
                        "country_name": "Дания",
                        "provider_type": "xray_core",
                        "device_name": "Рабочий ноутбук",
                        "device_type": "windows",
                        "device_model": "Surface Pro 9",
                        "os_version": "Windows 11",
                        "mac_address": "AA:BB:CC:DD:EE:FF",
                        "ip_address": "198.51.100.77",
                        "transport_label": "XHTTP",
                        "connection_profile": "reserve",
                    },
                    ensure_ascii=False,
                ),
            },
        )()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services.get_public_subscription_routes_for_user", new=AsyncMock(return_value=[])),
            patch(
                "dashboard.services.get_active_public_subscription_link_for_user",
                new=AsyncMock(
                    return_value=type(
                        "PublicSubscriptionLink",
                        (),
                        {
                            "token": "detail333token",
                            "last_viewed_at": None,
                            "last_feed_accessed_at": None,
                        },
                    )()
                ),
            ),
            patch("dashboard.services.list_vpn_repair_events", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_history", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_access_status_from_user", return_value="paid_active"),
            patch("dashboard.services.get_access_expires_at_from_user", return_value=datetime(2026, 4, 26, 9, 0, 0)),
        ):
            detail = await get_user_detail(333)

        assert detail is not None
        technical = detail["devices"][0]["technical"]
        self.assertEqual(technical["os_label"], "Windows")
        self.assertEqual(technical["device_model"], "Surface Pro 9")
        self.assertEqual(technical["os_version"], "Windows 11")
        self.assertEqual(technical["mac_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(technical["ip_address"], "198.51.100.77")
        self.assertEqual(technical["provider_label"], "Xray core")
        self.assertEqual(technical["transport_label"], "XHTTP")
        self.assertEqual(technical["connection_profile"], "reserve")
        self.assertEqual(technical["anti_sharing_scope_label"], "Xray access-log lease")
        self.assertIn("Lease-based anti-sharing", technical["anti_sharing_policy_summary"])

    async def test_get_user_detail_keeps_live_xui_ip_in_technical_payload(self) -> None:
        user = type(
            "User",
            (),
            {
                "id": 222,
                "telegram_id": 555000,
                "username": "live-ip-user",
                "preferred_protocol": "vless",
                "is_blocked": False,
                "trial_used": False,
                "created_at": datetime(2026, 3, 20, 10, 0, 0),
                "vpn_repair_needed": False,
                "vpn_repair_reason": None,
                "vpn_repair_marked_at": None,
                "last_activity_at": datetime(2026, 3, 20, 10, 40, 0),
            },
        )()
        device = type(
            "VpnClient",
            (),
            {
                "id": 10,
                "protocol": "vless",
                "created_at": datetime(2026, 3, 20, 10, 5, 0),
                "email": "device_222",
                "client_data": json.dumps(
                    {
                        "country_code": "de",
                        "country_name": "Германия",
                        "device_name": "iPhone",
                        "device_type": "ios",
                        "ip_address": "10.0.0.1",
                    },
                    ensure_ascii=False,
                ),
            },
        )()

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[device])),
            patch("dashboard.services.get_public_subscription_routes_for_user", new=AsyncMock(return_value=[])),
            patch(
                "dashboard.services.get_active_public_subscription_link_for_user",
                new=AsyncMock(
                    return_value=type(
                        "PublicSubscriptionLink",
                        (),
                        {
                            "token": "detail222token",
                            "last_viewed_at": None,
                            "last_feed_accessed_at": None,
                        },
                    )()
                ),
            ),
            patch("dashboard.services.list_vpn_repair_events", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_history", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_access_status_from_user", return_value="paid_active"),
            patch("dashboard.services.get_access_expires_at_from_user", return_value=datetime(2026, 4, 20, 10, 0, 0)),
            patch(
                "dashboard.services._fetch_xui_live_device_ips",
                new=AsyncMock(
                    return_value={
                        "real_ip": "203.0.113.10",
                        "ip_history": "203.0.113.10, 198.51.100.25",
                        "ip_source": "xui_client_ips",
                        "ip_source_label": "Живой IP из 3x-ui",
                        "ip_checked_at": "2026-03-20 12:40 UTC",
                    }
                ),
            ),
        ):
            detail = await get_user_detail(222)

        assert detail is not None
        technical = detail["devices"][0]["technical"]
        self.assertEqual(technical["ip_address"], "203.0.113.10")
        self.assertEqual(technical["fallback_ip_address"], "10.0.0.1")
        self.assertEqual(technical["ip_source_label"], "Живой IP из 3x-ui")
        self.assertEqual(technical["ip_history"], "203.0.113.10, 198.51.100.25")
        self.assertEqual(technical["anti_sharing_scope_label"], "3x-ui limitIp")
        self.assertIn("3x-ui", technical["anti_sharing_policy_summary"])

    async def test_build_device_technical_payload_normalizes_known_happ_os_build_codes(self) -> None:
        technical = dashboard_services._build_device_technical_payload(
            {
                "device_type": "windows",
                "device_model": "Windows PC",
                "os_version": "2603201341504",
                "country_code": "de",
                "provider_type": "xui",
            },
            display_ip="—",
            fallback_ip=None,
            live_ip_meta={},
            user_last_activity_at=None,
        )
        self.assertEqual(technical["os_version"], "11_10.0.26200")

        technical_android = dashboard_services._build_device_technical_payload(
            {
                "device_type": "android",
                "device_model": "Galaxy",
                "os_version": "1743595",
                "country_code": "dk",
                "provider_type": "xray_core",
            },
            display_ip="—",
            fallback_ip=None,
            live_ip_meta={},
            user_last_activity_at=None,
        )
        self.assertEqual(technical_android["os_version"], "15")

    async def test_get_user_detail_includes_bound_public_subscription_devices_and_link(self) -> None:
        user = type(
            "User",
            (),
            {
                "id": 444,
                "telegram_id": 444000,
                "username": "public-feed-user",
                "preferred_protocol": "vless",
                "is_blocked": False,
                "trial_used": False,
                "created_at": datetime(2026, 4, 1, 8, 0, 0),
                "vpn_repair_needed": False,
                "vpn_repair_reason": None,
                "vpn_repair_marked_at": None,
                "last_activity_at": datetime(2026, 4, 1, 8, 40, 0),
            },
        )()
        link = type(
            "PublicSubscriptionLink",
            (),
            {
                "token": "abcdefghijklmnop",
                "last_viewed_at": datetime(2026, 4, 1, 8, 35, 0),
                "last_feed_accessed_at": datetime(2026, 4, 1, 8, 36, 0),
            },
        )()
        routes = [
            type(
                "PublicSubscriptionRoute",
                (),
                {
                    "id": 901,
                    "slot_index": 1,
                    "country_code": "de",
                    "protocol": "vless",
                    "created_at": datetime(2026, 4, 1, 8, 5, 0),
                    "client_data": json.dumps(
                        {
                            "feed_device_fingerprint_hash": "abc123",
                            "device_name": "Home-PC_x86_64",
                            "device_model": "Home-PC_x86_64",
                            "device_type": "windows",
                            "os_name": "Windows",
                            "os_version": "2603201341504",
                            "source_ip": "203.0.113.55",
                            "feed_device_bound_at": "2026-04-01T08:10:00+00:00",
                            "feed_device_last_seen_at": "2026-04-01T08:38:00+00:00",
                        },
                        ensure_ascii=False,
                    ),
                },
            )(),
            type(
                "PublicSubscriptionRoute",
                (),
                {
                    "id": 902,
                    "slot_index": 1,
                    "country_code": "dk",
                    "protocol": "vless",
                    "created_at": datetime(2026, 4, 1, 8, 5, 0),
                    "client_data": json.dumps(
                        {
                            "feed_device_fingerprint_hash": "abc123",
                            "device_name": "Home-PC_x86_64",
                            "device_model": "Home-PC_x86_64",
                            "device_type": "windows",
                            "os_name": "Windows",
                            "os_version": "2603201341504",
                            "source_ip": "203.0.113.55",
                        },
                        ensure_ascii=False,
                    ),
                },
            )(),
        ]

        with (
            patch("dashboard.services.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("dashboard.services.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.services.get_user_vpn_clients", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_public_subscription_routes_for_user", new=AsyncMock(return_value=routes)),
            patch("dashboard.services.get_active_public_subscription_link_for_user", new=AsyncMock(return_value=link)),
            patch("dashboard.services.list_vpn_repair_events", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_payment_records", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_ticket", new=AsyncMock(return_value=None)),
            patch("dashboard.services.get_history", new=AsyncMock(return_value=[])),
            patch("dashboard.services.get_access_status_from_user", return_value="paid_active"),
            patch("dashboard.services.get_access_expires_at_from_user", return_value=datetime(2026, 5, 1, 8, 0, 0)),
        ):
            detail = await get_user_detail(444)

        assert detail is not None
        self.assertEqual(detail["subscription_link_url"], "https://client.amonora.ru/abcdefghijklmnop")
        self.assertEqual(detail["subscription_link_token"], "abcdefghijklmnop")
        self.assertEqual(len(detail["devices"]), 1)
        device = detail["devices"][0]
        self.assertTrue(device["metadata"]["subscription_route"])
        self.assertEqual(device["metadata"]["device_source_label"], "Единая ссылка")
        self.assertEqual(device["technical"]["os_version"], "11_10.0.26200")
        self.assertEqual(device["technical"]["ip_address"], "203.0.113.55")
        self.assertIn("Германия", device["metadata"]["country_name"])
        self.assertIn("Дания", device["metadata"]["country_name"])


if __name__ == "__main__":
    unittest.main()
