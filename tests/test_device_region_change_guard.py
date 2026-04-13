import unittest

from bot.utils.regions import is_cross_region_change


class DeviceRegionChangeGuardTests(unittest.TestCase):
    def test_same_region_is_not_cross_region_change(self) -> None:
        self.assertFalse(is_cross_region_change("de", "de"))

    def test_legacy_alias_normalizes_to_same_region(self) -> None:
        self.assertFalse(is_cross_region_change("de", "nl"))

    def test_different_regions_are_detected(self) -> None:
        self.assertTrue(is_cross_region_change("de", "ee"))


if __name__ == "__main__":
    unittest.main()
