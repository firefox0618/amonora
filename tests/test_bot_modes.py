import os
import unittest


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
os.environ.setdefault("VPN_HOST", "ffconnect.amonoraconnect.com")
os.environ.setdefault("VPN_HOST_DK", "dk.amonoraconnect.com")

from bot.config import config
from bot.utils.modes import (
    DEFAULT_MODE,
    format_mode,
    get_auto_mode,
    get_mode_connection_profile,
    get_mode_keys,
    get_mode_protocol,
    get_mode_region_codes,
    infer_mode_from_protocol,
    mode_available_for_user,
    mode_supported_in_region,
    normalize_mode,
    resolve_auto_mode,
    resolve_effective_mode,
)

config.admin_ids = [1]
config.support_admin_ids = [1]


class BotModesTests(unittest.TestCase):
    def test_legacy_mode_aliases_normalize_to_current_public_modes(self) -> None:
        self.assertEqual(normalize_mode("auto"), "stable")
        self.assertEqual(normalize_mode("автовыбор"), "stable")
        self.assertEqual(normalize_mode("nova"), "stable")
        self.assertEqual(normalize_mode("нова"), "stable")
        self.assertEqual(normalize_mode("core"), "stable")
        self.assertEqual(normalize_mode("ядро"), "stable")
        self.assertEqual(normalize_mode("origin"), "stable")
        self.assertEqual(normalize_mode("base"), "stable")
        self.assertEqual(normalize_mode("основа"), "stable")
        self.assertEqual(normalize_mode("white"), "mobile")
        self.assertEqual(normalize_mode("стабильный"), "stable")
        self.assertEqual(normalize_mode("мобильный"), "mobile")
        self.assertEqual(normalize_mode("резерв"), "reserve")

    def test_existing_protocols_fallback_to_new_public_modes(self) -> None:
        self.assertEqual(infer_mode_from_protocol("trojan"), "reserve")
        self.assertEqual(infer_mode_from_protocol("vless"), "stable")
        self.assertEqual(
            infer_mode_from_protocol("vless", {"stream_network": "xhttp", "country_code": "dk"}),
            "stable",
        )
        self.assertEqual(
            infer_mode_from_protocol(
                "vless",
                {"connection_profile": "reserve", "country_code": "dk"},
            ),
            "reserve",
        )

    def test_mode_to_protocol_mapping_matches_new_runtime_policy(self) -> None:
        self.assertEqual(get_mode_protocol("stable"), "vless")
        self.assertEqual(get_mode_protocol("mobile"), "vless")
        self.assertEqual(get_mode_protocol("reserve"), "trojan")
        self.assertEqual(get_mode_protocol("stable", "de"), "vless")
        self.assertEqual(get_mode_protocol("mobile", "de"), "vless")
        self.assertEqual(get_mode_protocol("reserve", "de"), "trojan")
        self.assertEqual(get_mode_protocol("stable", "dk"), "vless")
        self.assertEqual(get_mode_protocol("mobile", "dk"), "vless")
        self.assertEqual(get_mode_protocol("reserve", "dk"), "vless")

    def test_mode_connection_profiles_match_denmark_xray_layout(self) -> None:
        self.assertEqual(get_mode_connection_profile("stable", "dk"), "primary")
        self.assertEqual(get_mode_connection_profile("mobile", "dk"), "reserve")
        self.assertEqual(get_mode_connection_profile("reserve", "dk"), "reserve")
        self.assertIsNone(get_mode_connection_profile("stable", "de"))

    def test_mode_region_support_keeps_public_regions(self) -> None:
        self.assertTrue(mode_supported_in_region("stable", "de"))
        self.assertTrue(mode_supported_in_region("stable", "dk"))
        self.assertTrue(mode_supported_in_region("mobile", "de"))
        self.assertTrue(mode_supported_in_region("mobile", "dk"))
        self.assertTrue(mode_supported_in_region("reserve", "de"))
        self.assertTrue(mode_supported_in_region("reserve", "dk"))

    def test_region_lists_keep_public_regions_for_each_mode(self) -> None:
        self.assertEqual(get_mode_region_codes(mode="stable"), ["de", "dk"])
        self.assertEqual(get_mode_region_codes(mode="mobile"), ["de", "dk"])
        self.assertEqual(get_mode_region_codes(mode="reserve"), ["de", "dk"])

    def test_mode_keys_and_labels_use_new_public_copy(self) -> None:
        self.assertEqual(get_mode_keys(), ("stable", "mobile", "reserve"))
        self.assertEqual(get_mode_keys(telegram_id=1), ("stable", "mobile", "reserve"))
        self.assertEqual(format_mode("stable"), "🛡 Стабильный")
        self.assertEqual(format_mode("mobile"), "☁ Мобильный")
        self.assertEqual(format_mode("mobile", country_code="de"), "☁ Мобильный")
        self.assertEqual(format_mode("mobile", country_code="dk"), "☁ Мобильный")
        self.assertEqual(format_mode("reserve", with_recommended=True), "🧰 Резерв")
        self.assertEqual(format_mode("reserve"), "🧰 Резерв")

    def test_mobile_mode_is_available_for_regular_users(self) -> None:
        self.assertTrue(mode_available_for_user("mobile", telegram_id=1))
        self.assertTrue(mode_available_for_user("mobile", telegram_id=42))
        self.assertTrue(mode_available_for_user("stable", telegram_id=42))

    def test_default_mode_now_points_to_stable(self) -> None:
        self.assertEqual(DEFAULT_MODE, "stable")
        self.assertEqual(get_auto_mode(), "stable")
        self.assertEqual(get_mode_protocol(get_auto_mode()), "vless")
        self.assertEqual(resolve_auto_mode("de"), "stable")
        self.assertEqual(resolve_auto_mode("dk"), "stable")
        self.assertEqual(resolve_effective_mode("stable", "de"), "stable")
        self.assertEqual(resolve_effective_mode("reserve", "dk"), "reserve")


if __name__ == "__main__":
    unittest.main()
