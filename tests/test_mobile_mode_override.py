import unittest

from bot.handlers import devices


class MobileModeOverrideTests(unittest.TestCase):
    def test_with_connection_name_replaces_fragment(self) -> None:
        link = "vless://uuid@example.com:443?type=tcp#Old%20Name"
        result = devices._with_connection_name(link, devices.MOBILE_MODE_OVERRIDE_NAME)
        self.assertTrue(result.endswith("%E2%98%81%EF%B8%8F%20AMONORA-LTE"))

    def test_override_is_disabled_for_regular_stable_mobile_delivery(self) -> None:
        self.assertFalse(
            devices._should_use_mobile_mode_override(
                {
                    "delivery_mode": "mobile_happ",
                    "mode": "stable",
                    "resolved_mode": "stable",
                    "country_code": "de",
                }
            )
        )

    def test_override_is_kept_for_experimental_mobile_mode(self) -> None:
        self.assertTrue(
            devices._should_use_mobile_mode_override(
                {
                    "delivery_mode": "mobile_happ",
                    "mode": "mobile",
                    "resolved_mode": "mobile",
                    "country_code": "de",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
