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

from test_bot.profiles import TEST_PROFILES, build_test_profile_link


class TestBotProfilesTests(unittest.TestCase):
    def test_only_active_region_profiles_remain(self) -> None:
        self.assertEqual(
            set(TEST_PROFILES),
            {
                "de_android",
                "de_iphone",
                "dk_android",
                "dk_iphone",
            },
        )

        de_android = TEST_PROFILES["de_android"]
        self.assertEqual(de_android.metadata["stream_network"], "tcp")
        self.assertEqual(de_android.metadata["reality_server_name"], "www.microsoft.com")
        self.assertEqual(de_android.metadata["fingerprint"], "chrome")

        de_iphone = TEST_PROFILES["de_iphone"]
        self.assertEqual(de_iphone.metadata["stream_network"], "tcp")
        self.assertEqual(de_iphone.metadata["reality_server_name"], "www.microsoft.com")
        self.assertEqual(de_iphone.metadata["fingerprint"], "safari")

        dk_android = TEST_PROFILES["dk_android"]
        self.assertEqual(dk_android.metadata["stream_network"], "xhttp")
        self.assertEqual(dk_android.metadata["stream_path"], "/api/v1/updates")
        self.assertEqual(dk_android.metadata["alpn"], ["h3", "h2", "http/1.1"])

        dk_iphone = TEST_PROFILES["dk_iphone"]
        self.assertEqual(dk_iphone.metadata["stream_network"], "xhttp")
        self.assertEqual(dk_iphone.metadata["stream_path"], "/graphql")
        self.assertEqual(dk_iphone.metadata["alpn"], ["h2", "http/1.1"])

    def test_active_profiles_still_build_links(self) -> None:
        payload = build_test_profile_link(TEST_PROFILES["dk_android"])
        self.assertIn("vless://", payload)
        self.assertIn("AMONORA-DK-ANDROID-TEST-V2", payload)


if __name__ == "__main__":
    unittest.main()
