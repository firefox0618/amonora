import os
import unittest
from unittest.mock import AsyncMock, patch


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
os.environ.setdefault("VPN_HOST", "ffconnect.amonoraconnect.com")
os.environ.setdefault("VPN_HOST_EE", "est.amonoraconnect.com")
os.environ.setdefault("VPN_HOST_DK", "dk.amonoraconnect.com")
os.environ.setdefault("XRAY_CORE_DK_SSH_HOST", "81.17.159.58")
os.environ.setdefault("XRAY_CORE_DK_SSH_KEY_PATH", "/tmp/dashboard_metrics")
os.environ.setdefault("XRAY_CORE_DK_SSH_KNOWN_HOSTS", "/tmp/known_hosts")

from bot.config import config
from bot.utils.regions import get_country_panel_url, get_country_provider_type, get_country_vpn_host, get_user_selectable_region_codes
from bot.utils.vless import build_vless_link_from_metadata
from bot.vpn_provisioning import XUIProvisioner, XrayCoreProvisioner, region_supports_protocol


class DenmarkVpnProvisioningTests(unittest.TestCase):
    def test_denmark_region_is_provider_backed_without_xui_panel(self) -> None:
        self.assertEqual(get_country_provider_type("dk"), "xray_core")
        self.assertIsNone(get_country_panel_url("dk"))

    def test_estonia_hidden_and_denmark_is_publicly_selectable(self) -> None:
        self.assertEqual(get_user_selectable_region_codes(), ["de", "dk"])
        self.assertEqual(get_user_selectable_region_codes(telegram_id=42), ["de", "dk"])

    def test_estonia_region_is_hidden_but_xui_backed_for_subscription_feed(self) -> None:
        self.assertEqual(get_country_provider_type("ee"), "xui")
        self.assertEqual(get_country_panel_url("ee"), "http://127.0.0.1:12054")
        self.assertEqual(get_country_vpn_host("ee"), "est.amonoraconnect.com")

    def test_estonia_region_uses_explicit_configured_panel_url_without_legacy_remap(self) -> None:
        with patch.object(config, "xui_url_ee", "http://est.amonoraconnect.com:2053/dashboard"):
            self.assertEqual(get_country_panel_url("ee"), "http://est.amonoraconnect.com:2053/dashboard")

    def test_denmark_supports_vless_only(self) -> None:
        self.assertTrue(region_supports_protocol("dk", "vless"))
        self.assertFalse(region_supports_protocol("dk", "trojan"))

    def test_build_vless_link_from_xray_core_metadata(self) -> None:
        link = build_vless_link_from_metadata(
            metadata={
                "stream_network": "xhttp",
                "reality_server_name": "www.asus.com",
                "reality_short_id": "abcd1234",
                "reality_password": "secret-password",
                "xhttp_path": "/dk-test",
                "stream_mode": "auto",
                "alpn": ["h3", "h2", "http/1.1"],
                "port": 443,
            },
            client_uuid="11111111-1111-1111-1111-111111111111",
            email="device@test",
            connection_name="AMONORA-DK",
            country_code="dk",
        )
        self.assertIn("vless://11111111-1111-1111-1111-111111111111@dk.amonoraconnect.com:443", link)
        self.assertIn("type=xhttp", link)
        self.assertIn("security=reality", link)
        self.assertIn("sni=www.asus.com", link)
        self.assertIn("sid=abcd1234", link)
        self.assertIn("path=%2Fdk-test", link)
        self.assertIn("alpn=h3%2Ch2%2Chttp%2F1.1", link)

    def test_denmark_host_falls_back_to_dedicated_public_host_not_global_vpn_host(self) -> None:
        with patch.object(config, "vpn_host_dk", None), patch.object(config, "xray_core_dk_ssh_host", "81.17.159.58"):
            self.assertEqual(get_country_vpn_host("dk"), "dk.amonoraconnect.com")

    def test_xray_core_metadata_supports_primary_and_reserve_profiles(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        provisioner._load_state = AsyncMock(
            return_value={
                "config": {},
                "meta": {
                    "active_profile": "primary",
                    "mtu_default": 1400,
                    "mtu_fallback": 1420,
                    "compatibility_fallback_region": "de",
                    "dns_servers": [
                        "https+local://cloudflare-dns.com/dns-query",
                        "https+local://dns.sb/dns-query",
                        "localhost",
                    ],
                    "profiles": {
                        "primary": {
                            "port": 443,
                            "reality_server_name": "www.apple.com",
                            "reality_short_id": "primary01",
                            "reality_password": "primary-pbk",
                            "xhttp_path": "/api/v1/updates",
                            "stream_mode": "packet-up",
                            "fingerprint": "chrome",
                            "alpn": ["h3", "h2", "http/1.1"],
                            "h3_preferred": True,
                        },
                        "reserve": {
                            "port": 8443,
                            "reality_server_name": "www.apple.com",
                            "reality_short_id": "reserve01",
                            "reality_password": "reserve-pbk",
                            "xhttp_path": "/graphql",
                            "stream_mode": "packet-up",
                            "fingerprint": "chrome",
                            "alpn": ["h2", "http/1.1"],
                            "h2_fallback": True,
                        },
                    },
                },
            }
        )

        import asyncio

        metadata = asyncio.run(
            provisioner.build_vless_metadata(
                client_uuid="11111111-1111-1111-1111-111111111111",
                email="device@test",
                country_code="dk",
                base_metadata={"server_record_id": "device@test"},
            )
        )
        self.assertEqual(metadata["active_profile"], "primary")
        self.assertEqual(metadata["stream_mode"], "packet-up")
        self.assertEqual(metadata["mtu_default"], 1400)
        self.assertEqual(metadata["mtu_fallback"], 1420)
        self.assertEqual(metadata["compatibility_fallback_region"], "de")
        self.assertIn("primary", metadata["connection_profiles"])
        self.assertIn("reserve", metadata["connection_profiles"])
        self.assertEqual(metadata["connection_profiles"]["reserve"]["port"], 8443)
        self.assertEqual(metadata["connection_profiles"]["reserve"]["stream_mode"], "packet-up")
        self.assertIn("path=%2Fgraphql", metadata["reserve_vless_link"])
        self.assertIn("mode=packet-up", metadata["reserve_vless_link"])
        self.assertIn("mode=packet-up", metadata["vless_link"])

    def test_white_mode_prefers_reserve_profile_on_denmark(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        provisioner._load_state = AsyncMock(
            return_value={
                "config": {},
                "meta": {
                    "active_profile": "primary",
                    "profiles": {
                        "primary": {
                            "port": 443,
                            "reality_server_name": "www.apple.com",
                            "reality_short_id": "primary01",
                            "reality_password": "primary-pbk",
                            "xhttp_path": "/api/v1/updates",
                            "stream_mode": "packet-up",
                        },
                        "reserve": {
                            "port": 8443,
                            "reality_server_name": "www.apple.com",
                            "reality_short_id": "reserve01",
                            "reality_password": "reserve-pbk",
                            "xhttp_path": "/graphql",
                            "stream_mode": "packet-up",
                        },
                    },
                },
            }
        )

        import asyncio

        metadata = asyncio.run(
            provisioner.build_vless_metadata(
                client_uuid="11111111-1111-1111-1111-111111111111",
                email="device@test",
                country_code="dk",
                base_metadata={"mode": "white"},
            )
        )

        self.assertEqual(metadata["active_profile"], "reserve")
        self.assertEqual(metadata["connection_profile"], "reserve")
        self.assertIn(":8443", metadata["vless_link"])
        self.assertIn("path=%2Fgraphql", metadata["vless_link"])

    def test_xray_core_ssh_python_quotes_remote_python_command(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        provisioner.host = "81.17.159.58"
        provisioner.key_path = "/tmp/dashboard_metrics"
        provisioner.known_hosts = "/tmp/known_hosts"
        fake_process = AsyncMock()
        fake_process.communicate = AsyncMock(return_value=(b"ok", b""))
        fake_process.returncode = 0

        async def run_check() -> None:
            with patch("asyncio.create_subprocess_exec", return_value=fake_process) as mocked_exec:
                code, output = await provisioner._ssh_python("print('ok')")
                self.assertEqual(code, 0)
                self.assertEqual(output, "ok")
                remote_command = mocked_exec.call_args.args[-1]
                self.assertIn("python3 -c", remote_command)
                self.assertIn("exec(sys.stdin.read())", remote_command)

        import asyncio

        asyncio.run(run_check())

    def test_xray_core_save_state_resets_failed_unit_before_restart(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        captured: dict[str, object] = {}

        async def fake_ssh(script: str) -> tuple[int, str]:
            captured["script"] = script
            return 0, "ok"

        provisioner._ssh_python = fake_ssh  # type: ignore[assignment]

        import asyncio

        asyncio.run(provisioner._save_state({"inbounds": [], "outbounds": []}))

        script = str(captured.get("script") or "")
        self.assertIn('systemctl", "reset-failed", "xray"', script)
        self.assertIn('systemctl", "restart", "xray"', script)

    def test_xray_core_upsert_client_is_idempotent_for_existing_enabled_client(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        config_payload = {
            "inbounds": [
                {
                    "protocol": "vless",
                    "listen": "@xhttp-dk",
                    "settings": {
                        "clients": [
                            {"id": "uuid-1", "email": "device@test"},
                            {"id": "uuid-2", "email": "other@test"},
                        ]
                    },
                }
            ]
        }

        changed = provisioner._upsert_client(
            config_payload,
            client_uuid="uuid-1",
            email="device@test",
            enabled=True,
        )

        self.assertFalse(changed)
        clients = config_payload["inbounds"][0]["settings"]["clients"]
        self.assertEqual(
            clients,
            [
                {"id": "uuid-1", "email": "device@test"},
                {"id": "uuid-2", "email": "other@test"},
            ],
        )

    def test_xray_core_sync_vless_client_skips_save_on_noop_update(self) -> None:
        provisioner = XrayCoreProvisioner("dk")
        provisioner._load_state = AsyncMock(
            return_value={
                "config": {
                    "inbounds": [
                        {
                            "protocol": "vless",
                            "listen": "@xhttp-dk",
                            "settings": {"clients": [{"id": "uuid-1", "email": "device@test"}]},
                        }
                    ]
                }
            }
        )
        provisioner._save_state = AsyncMock()

        import asyncio
        from datetime import datetime

        asyncio.run(
            provisioner.sync_vless_client(
                client_uuid="uuid-1",
                email="device@test",
                metadata={},
                access_expires_at=datetime.utcnow(),
            )
        )

        provisioner._save_state.assert_not_awaited()

    def test_xui_provisioner_delete_logs_in_before_panel_operation(self) -> None:
        fake_client = AsyncMock()
        fake_client.login = AsyncMock(return_value=True)
        fake_client.delete_vless_client = AsyncMock(return_value={"success": True})

        async def run_check() -> None:
            with patch("bot.vpn_provisioning.XUIClient", return_value=fake_client):
                provisioner = XUIProvisioner("de")
                result = await provisioner.delete_vless_client(
                    client_uuid="uuid-1",
                    email="device@test",
                    metadata={"inbound_id": 1},
                )
                self.assertEqual(result["success"], True)
                fake_client.login.assert_awaited_once()
                fake_client.delete_vless_client.assert_awaited_once_with(
                    inbound_id=1,
                    client_uuid="uuid-1",
                    email="device@test",
                )

        import asyncio

        asyncio.run(run_check())


if __name__ == "__main__":
    unittest.main()
