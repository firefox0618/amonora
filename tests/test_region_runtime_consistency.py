import unittest

from bot.utils.regions import (
    build_region_snapshot,
    get_country_runtime_service_name,
    get_country_runtime_type,
    get_region_anti_sharing_policy_summary,
    get_region_anti_sharing_scope_label,
)


class RegionRuntimeConsistencyTests(unittest.TestCase):
    def test_estonia_snapshot_is_retired(self) -> None:
        snapshot = build_region_snapshot("ee")

        self.assertEqual(snapshot["provider_type"], "retired")
        self.assertEqual(snapshot["runtime_type"], "retired")
        self.assertEqual(snapshot["runtime_service_name"], "retired")
        self.assertEqual(snapshot["anti_sharing_scope_label"], "Retired region")
        self.assertTrue(snapshot["retired"])

    def test_legacy_xui_device_can_still_resolve_xui_anti_sharing_labels(self) -> None:
        self.assertEqual(get_region_anti_sharing_scope_label("ee", provider_type="xui"), "3x-ui limitIp")
        self.assertIn("3x-ui", get_region_anti_sharing_policy_summary("ee", provider_type="xui"))

    def test_runtime_service_name_matches_region_runtime(self) -> None:
        self.assertEqual(get_country_runtime_type("de"), "xui")
        self.assertEqual(get_country_runtime_service_name("de"), "3x-ui")
        self.assertEqual(get_country_runtime_type("dk"), "xray_core")
        self.assertEqual(get_country_runtime_service_name("dk"), "xray")


if __name__ == "__main__":
    unittest.main()
