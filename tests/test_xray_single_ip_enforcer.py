import unittest

from datetime import UTC, datetime, timedelta

from ops.xray_single_ip_enforcer import (
    AccessEvent,
    apply_routing_rules,
    build_managed_routing_rules,
    ensure_access_log_config,
    ensure_proxy_protocol_config,
    is_enforceable_ip,
    parse_access_log_line,
    update_leases,
)


class XraySingleIpEnforcerTests(unittest.TestCase):
    def test_parse_access_log_line_extracts_timestamp_ip_and_email(self) -> None:
        event = parse_access_log_line(
            "2026/03/26 01:02:03.123456 from 203.0.113.4:54123 accepted tcp:www.apple.com:443 [@xhttp-dk-primary >> proxy] email: device_17_123"
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.ip, "203.0.113.4")
        self.assertEqual(event.email, "device_17_123")
        self.assertEqual(event.occurred_at, datetime(2026, 3, 26, 1, 2, 3, tzinfo=UTC))

    def test_update_leases_keeps_first_ip_while_lease_is_active(self) -> None:
        now = datetime(2026, 3, 26, 2, 0, 0, tzinfo=UTC)
        events = [
            AccessEvent(now - timedelta(seconds=90), "203.0.113.4", "device_17_123"),
            AccessEvent(now - timedelta(seconds=30), "198.51.100.9", "device_17_123"),
        ]

        leases = update_leases(
            {},
            events,
            now=now,
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
            ignored_prefixes=("test_",),
            ignored_emails=("dk-main",),
            lease_seconds=180,
        )

        self.assertEqual(leases["device_17_123"]["active_ip"], "203.0.113.4")
        self.assertEqual(leases["device_17_123"]["last_overflow_ip"], "198.51.100.9")

    def test_update_leases_switches_ip_after_lease_expires(self) -> None:
        now = datetime(2026, 3, 26, 2, 0, 0, tzinfo=UTC)
        events = [
            AccessEvent(now - timedelta(seconds=400), "203.0.113.4", "device_17_123"),
            AccessEvent(now - timedelta(seconds=30), "198.51.100.9", "device_17_123"),
        ]

        leases = update_leases(
            {},
            events,
            now=now,
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
            ignored_prefixes=("test_",),
            ignored_emails=("dk-main",),
            lease_seconds=180,
        )

        self.assertEqual(leases["device_17_123"]["active_ip"], "198.51.100.9")
        self.assertEqual(leases["device_17_123"]["active_ip_count"], 1)

    def test_update_leases_allows_multiple_ips_when_max_devices_is_two(self) -> None:
        now = datetime(2026, 3, 26, 2, 0, 0, tzinfo=UTC)
        events = [
            AccessEvent(now - timedelta(seconds=120), "203.0.113.4", "device_17_123"),
            AccessEvent(now - timedelta(seconds=90), "198.51.100.9", "device_17_123"),
        ]

        leases = update_leases(
            {},
            events,
            now=now,
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
            ignored_prefixes=("test_",),
            ignored_emails=("dk-main",),
            lease_seconds=180,
            max_devices=2,
        )

        lease = leases["device_17_123"]
        self.assertEqual(lease["active_ip_count"], 2)
        self.assertEqual([item["ip"] for item in lease["active_ips"]], ["203.0.113.4", "198.51.100.9"])

    def test_update_leases_allows_whitelisted_ip_without_using_device_slot(self) -> None:
        now = datetime(2026, 3, 26, 2, 0, 0, tzinfo=UTC)
        events = [
            AccessEvent(now - timedelta(seconds=120), "203.0.113.4", "device_17_123"),
            AccessEvent(now - timedelta(seconds=90), "198.51.100.9", "device_17_123"),
            AccessEvent(now - timedelta(seconds=30), "192.0.2.44", "device_17_123"),
        ]

        leases = update_leases(
            {},
            events,
            now=now,
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
            ignored_prefixes=("test_",),
            ignored_emails=("dk-main",),
            lease_seconds=180,
            max_devices=1,
            whitelist_by_email={"device_17_123": ("198.51.100.9",)},
        )

        lease = leases["device_17_123"]
        self.assertEqual(lease["active_ip_count"], 1)
        self.assertEqual(lease["allowed_ip_count"], 2)
        self.assertEqual(lease["whitelisted_ips"], ["198.51.100.9"])
        self.assertEqual(lease["last_overflow_ip"], "192.0.2.44")
        self.assertEqual([item["ip"] for item in lease["active_ips"]], ["203.0.113.4", "198.51.100.9"])

    def test_build_routing_rules_creates_allow_then_block_pair(self) -> None:
        rules = build_managed_routing_rules(
            {"device_17_123": {"active_ip": "203.0.113.4", "last_seen_at": "2026-03-26T02:00:00+00:00"}}
        )

        self.assertEqual(rules[0]["user"], ["device_17_123"])
        self.assertEqual(rules[0]["sourceIP"], ["203.0.113.4"])
        self.assertEqual(rules[0]["outboundTag"], "direct")
        self.assertEqual(rules[1]["outboundTag"], "block")

    def test_build_routing_rules_support_multiple_allowed_ips(self) -> None:
        rules = build_managed_routing_rules(
            {
                "device_17_123": {
                    "active_ips": [
                        {
                            "ip": "203.0.113.4",
                            "first_seen_at": "2026-03-26T01:58:00+00:00",
                            "last_seen_at": "2026-03-26T01:59:00+00:00",
                            "whitelisted": False,
                        },
                        {
                            "ip": "198.51.100.9",
                            "first_seen_at": "2026-03-26T01:59:10+00:00",
                            "last_seen_at": "2026-03-26T02:00:00+00:00",
                            "whitelisted": True,
                        },
                    ]
                }
            }
        )

        self.assertEqual(rules[0]["sourceIP"], ["203.0.113.4", "198.51.100.9"])
        self.assertEqual(rules[1]["outboundTag"], "block")

    def test_build_routing_rules_skips_unspecified_ip(self) -> None:
        rules = build_managed_routing_rules(
            {"device_17_123": {"active_ip": "0.0.0.0", "last_seen_at": "2026-03-26T02:00:00+00:00"}}
        )

        self.assertEqual(rules, [])

    def test_apply_routing_rules_keeps_base_rules_after_generated_rules(self) -> None:
        config = {
            "routing": {
                "rules": [
                    {"type": "field", "outboundTag": "block", "ip": ["geoip:private"]},
                ]
            }
        }

        updated, changed = apply_routing_rules(
            config,
            {"device_17_123": {"active_ip": "203.0.113.4", "last_seen_at": "2026-03-26T02:00:00+00:00"}},
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
        )

        self.assertTrue(changed)
        self.assertEqual(updated["routing"]["rules"][0]["user"], ["device_17_123"])
        self.assertEqual(updated["routing"]["rules"][-1]["ip"], ["geoip:private"])

    def test_ensure_access_log_config_sets_warning_access_and_error_paths(self) -> None:
        updated, changed = ensure_access_log_config({}, access_log_path="/var/log/xray/access.log", error_log_path="/var/log/xray/error.log")

        self.assertTrue(changed)
        self.assertEqual(updated["log"]["access"], "/var/log/xray/access.log")
        self.assertEqual(updated["log"]["error"], "/var/log/xray/error.log")
        self.assertEqual(updated["log"]["loglevel"], "warning")

    def test_ensure_proxy_protocol_config_enables_fallback_xver_and_xhttp_accept_proxy(self) -> None:
        config = {
            "inbounds": [
                {
                    "settings": {
                        "fallbacks": [
                            {"dest": "@xhttp-dk-primary", "xver": 0},
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                    },
                },
                {
                    "streamSettings": {
                        "network": "xhttp",
                        "xhttpSettings": {
                            "path": "/api/v1/updates",
                        },
                    }
                },
            ]
        }

        updated, changed = ensure_proxy_protocol_config(config)

        self.assertTrue(changed)
        self.assertEqual(updated["inbounds"][0]["settings"]["fallbacks"][0]["xver"], 1)
        self.assertTrue(updated["inbounds"][1]["streamSettings"]["xhttpSettings"]["acceptProxyProtocol"])

    def test_is_enforceable_ip_rejects_unspecified_addresses(self) -> None:
        self.assertFalse(is_enforceable_ip("0.0.0.0"))
        self.assertFalse(is_enforceable_ip("::"))
        self.assertTrue(is_enforceable_ip("203.0.113.4"))

    def test_update_leases_drops_existing_unspecified_ip_lease(self) -> None:
        now = datetime(2026, 3, 26, 2, 0, 0, tzinfo=UTC)

        leases = update_leases(
            {"device_17_123": {"active_ip": "0.0.0.0", "last_seen_at": now.isoformat()}},
            [],
            now=now,
            managed_prefixes=("device_", "dashboard_", "landing_bridge_"),
            ignored_prefixes=("test_",),
            ignored_emails=("dk-main",),
            lease_seconds=180,
        )

        self.assertEqual(leases, {})


if __name__ == "__main__":
    unittest.main()
