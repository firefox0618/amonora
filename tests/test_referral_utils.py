import unittest

from bot.utils.referrals import build_referral_link, calc_level, referral_bonus_for_tariff, render_progress_bar


class ReferralUtilsTests(unittest.TestCase):
    def test_bonus_map_matches_tariff_matrix(self) -> None:
        self.assertEqual(referral_bonus_for_tariff("1m"), 50)
        self.assertEqual(referral_bonus_for_tariff("3m"), 50)
        self.assertEqual(referral_bonus_for_tariff("6m"), 50)
        self.assertEqual(referral_bonus_for_tariff("12m"), 100)
        self.assertEqual(referral_bonus_for_tariff("unknown"), 0)

    def test_level_progress_covers_zero_middle_and_top_ranges(self) -> None:
        self.assertEqual(calc_level(0), ("Без уровня", "Новичок", 1, 0))
        self.assertEqual(calc_level(3), ("Новичок", "Продвинутый", 1, 100))
        self.assertEqual(calc_level(7), ("Продвинутый", "Партнер", 4, 50))
        self.assertEqual(calc_level(12), ("Партнер", None, 0, 100))

    def test_link_and_progress_bar_render_expected_shapes(self) -> None:
        self.assertEqual(build_referral_link("demo123"), "https://t.me/amonora_bot?start=ref_demo123")
        self.assertEqual(render_progress_bar(60), "[██████░░░░]")


if __name__ == "__main__":
    unittest.main()
