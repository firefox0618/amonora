import json
import os
import unittest
from pathlib import Path


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

from bot.utils.routing import (
    BLOCKED_PROTOCOLS,
    CLIENT_ROUTING_PACKS,
    SPLIT_DIRECT_DOMAINS,
    SPLIT_DIRECT_IPS,
    build_full_tunnel_pack,
    build_split_routing_pack,
    build_split_routing_pack_for_device,
    build_split_routing_rules,
)


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PACKS_DIR = ROOT / "documentation" / "vpn" / "client-packs"


class ClientRoutingPackTests(unittest.TestCase):
    def test_split_routing_rules_send_ru_direct_and_global_proxy(self) -> None:
        routing = build_split_routing_rules()

        self.assertEqual(routing["domainStrategy"], "IPIfNonMatch")
        self.assertEqual(routing["rules"][0]["domain"], list(SPLIT_DIRECT_DOMAINS))
        self.assertEqual(routing["rules"][1]["ip"], list(SPLIT_DIRECT_IPS))
        self.assertEqual(routing["rules"][2]["protocol"], list(BLOCKED_PROTOCOLS))
        self.assertEqual(routing["rules"][3]["outboundTag"], "proxy")
        self.assertEqual(routing["rules"][3]["network"], "tcp,udp")

    def test_device_os_maps_to_expected_client_pack(self) -> None:
        android_spec, _ = build_split_routing_pack_for_device("android")
        ios_spec, _ = build_split_routing_pack_for_device("ios")
        desktop_spec, _ = build_split_routing_pack_for_device("windows")

        self.assertEqual(android_spec.target_client, "v2rayNG")
        self.assertEqual(ios_spec.target_client, "Streisand")
        self.assertEqual(desktop_spec.target_client, "Nekoray")

    def test_documented_split_packs_match_runtime_builder(self) -> None:
        expected = {
            "v2rayng-split-tunnel.json": build_split_routing_pack(CLIENT_ROUTING_PACKS["v2rayng"]),
            "nekoray-split-tunnel.json": build_split_routing_pack(CLIENT_ROUTING_PACKS["nekoray"]),
            "streisand-split-tunnel.json": build_split_routing_pack(CLIENT_ROUTING_PACKS["streisand"]),
        }

        for filename, payload in expected.items():
            with self.subTest(filename=filename):
                documented = json.loads((CLIENT_PACKS_DIR / filename).read_text(encoding="utf-8"))
                self.assertEqual(documented, payload)

    def test_documented_full_tunnel_packs_match_runtime_builder(self) -> None:
        expected = {
            "v2rayng-full-tunnel.json": build_full_tunnel_pack(CLIENT_ROUTING_PACKS["v2rayng"]),
            "nekoray-full-tunnel.json": build_full_tunnel_pack(CLIENT_ROUTING_PACKS["nekoray"]),
            "streisand-full-tunnel.json": build_full_tunnel_pack(CLIENT_ROUTING_PACKS["streisand"]),
        }

        for filename, payload in expected.items():
            with self.subTest(filename=filename):
                documented = json.loads((CLIENT_PACKS_DIR / filename).read_text(encoding="utf-8"))
                self.assertEqual(documented, payload)


if __name__ == "__main__":
    unittest.main()
