import unittest

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from bot.utils.tariffs import promo_tariff_offer_block
from ops.access_reminders import _trigger_template_body


class PromoCopyConsistencyTests(unittest.TestCase):
    def test_shared_promo_offer_block_is_empty_after_promo_removal(self) -> None:
        with patch("bot.utils.tariffs.current_promo_now", return_value=datetime(2026, 3, 27, 12, 0, 0)):
            plain = promo_tariff_offer_block()
            plain_without_gift = promo_tariff_offer_block(include_gift_wording=False)
            html = promo_tariff_offer_block(bullets=True, html=True)

        self.assertEqual(plain, "")
        self.assertEqual(plain_without_gift, "")
        self.assertEqual(html, "")

    def test_access_reminder_templates_keep_default_copy_after_promo_removal(self) -> None:
        rule_1d = SimpleNamespace(key="trial_ends_1d", template_body="fallback")
        rule_today = SimpleNamespace(key="trial_ends_today", template_body="fallback")
        rule_expired = SimpleNamespace(key="trial_expired_3d", template_body="fallback")

        with patch("bot.utils.tariffs.current_promo_now", return_value=datetime(2026, 3, 27, 12, 0, 0)):
            body_1d = _trigger_template_body(rule_1d)
            body_today = _trigger_template_body(rule_today)
            body_expired = _trigger_template_body(rule_expired)

        self.assertEqual(body_1d, "fallback")
        self.assertEqual(body_today, "fallback")
        self.assertEqual(body_expired, "fallback")


if __name__ == "__main__":
    unittest.main()
