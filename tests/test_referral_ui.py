import unittest

from urllib.parse import parse_qs, urlparse

from bot.handlers import referrals as referral_handlers
from bot.utils.texts import referral_copy_message_text, referrals_text


class ReferralUiTests(unittest.IsolatedAsyncioTestCase):
    def test_share_url_uses_human_text_and_referral_link(self) -> None:
        url = referral_handlers._referral_share_url("https://t.me/amonora_bot?start=ref_548589949")
        parsed = parse_qs(urlparse(url).query)

        self.assertIn("https://t.me/share/url?", url)
        self.assertEqual(parsed["text"][0], "Лучший сервис для доступа\nПереходи и получай бонусные рубли 👇")
        self.assertEqual(parsed["url"][0], "https://t.me/amonora_bot?start=ref_548589949")

    def test_referral_screen_renders_link_balance_progress_and_bonus_rules(self) -> None:
        text = referrals_text(
            referral_link="https://t.me/amonora_bot?start=ref_demo123",
            balance_rub=70,
            earned_total_rub=140,
            invited_count=5,
            paid_count=2,
            current_level_name="Новичок",
            next_level_name="Продвинутый",
            left_to_next_level=2,
            progress_bar="[██████░░░░]",
        )

        self.assertIn("🎁 <b>Реферальная программа</b>", text)
        self.assertIn("https://t.me/amonora_bot?start=ref_demo123", text)
        self.assertIn("💰 Баланс: <b>70 ₽</b>", text)
        self.assertIn("📈 Заработано всего: <b>140 ₽</b>", text)
        self.assertIn("• Приглашено: <b>5</b>", text)
        self.assertIn("• Оплатили: <b>2</b>", text)
        self.assertIn("🏆 Уровень: <b>Новичок</b>", text)
        self.assertIn("50 ₽", text)
        self.assertIn("12 месяцев", text)
        self.assertIn("100 ₽", text)
        self.assertIn("на общий баланс", text)

    def test_referral_copy_message_uses_human_text_without_encoded_share_url(self) -> None:
        text = referral_copy_message_text(
            referral_link="https://t.me/amonora_bot?start=ref_demo123",
            share_text="Лучший сервис для доступа\nПереходи и получай бонусные рубли 👇",
        )

        self.assertIn("Лучший сервис для доступа", text)
        self.assertIn("Переходи и получай бонусные рубли", text)
        self.assertNotIn("Лучший+сервис+для+доступа", text)
        self.assertNotIn("https://t.me/share/url?", text)


if __name__ == "__main__":
    unittest.main()
