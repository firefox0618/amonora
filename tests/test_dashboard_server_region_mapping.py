import unittest

from dashboard.services import _region_stats_key


class DashboardServerRegionMappingTests(unittest.TestCase):
    def test_region_stats_key_keeps_sweden_separate_from_germany(self) -> None:
        self.assertEqual(_region_stats_key("se"), "se")

    def test_region_stats_key_keeps_unknown_region_unmapped(self) -> None:
        self.assertIsNone(_region_stats_key("eu"))

    def test_region_stats_key_maps_legacy_netherlands_to_germany(self) -> None:
        self.assertEqual(_region_stats_key("nl"), "de")


if __name__ == "__main__":
    unittest.main()
