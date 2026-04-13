import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.v2_data import _build_campaign_funnel, _build_campaign_stats_payload, get_v2_campaign_analytics_payload


class DashboardCampaignAnalyticsPayloadTests(unittest.TestCase):
    def test_campaign_stats_payload_uses_expected_stage_mapping(self) -> None:
        stats = _build_campaign_stats_payload(
            {
                "link_touched": 20,
                "bot_start": 11,
                "trial_started": 7,
                "config_issued": 5,
                "payment_success": 3,
                "subscription_renewed": 1,
            }
        )

        self.assertEqual(
            stats,
            {
                "transitions": 20,
                "bot_starts": 11,
                "trial_started": 7,
                "key_issued": 5,
                "paid": 3,
                "renewed": 1,
                "conversion_rate": 15.0,
            },
        )

    def test_campaign_funnel_uses_transitions_as_base_rate(self) -> None:
        funnel = _build_campaign_funnel(
            {
                "transitions": 10,
                "bot_starts": 6,
                "trial_started": 4,
                "key_issued": 3,
                "paid": 2,
                "renewed": 1,
            }
        )

        self.assertEqual(funnel[0], {"stage": "Переход по ссылке", "count": 10, "rate": 100.0})
        self.assertEqual(funnel[1]["stage"], "Нажали Start")
        self.assertEqual(funnel[1]["rate"], 60.0)
        self.assertEqual(funnel[4]["rate"], 20.0)
        self.assertEqual(funnel[5]["rate"], 10.0)

    def test_campaign_summary_accumulates_all_funnel_totals(self) -> None:
        serialized = [
            {
                "stats": {
                    "transitions": 10,
                    "bot_starts": 6,
                    "trial_started": 4,
                    "key_issued": 3,
                    "paid": 2,
                    "renewed": 1,
                }
            },
            {
                "stats": {
                    "transitions": 5,
                    "bot_starts": 2,
                    "trial_started": 1,
                    "key_issued": 1,
                    "paid": 1,
                    "renewed": 0,
                }
            },
        ]
        with (
            patch(
                "dashboard.v2_data._load_campaign_offer_items",
                AsyncMock(return_value=[SimpleNamespace(deep_link_token="item-1"), SimpleNamespace(deep_link_token="item-2")]),
            ),
            patch("dashboard.v2_data._load_campaign_stage_counts", AsyncMock(return_value={})),
            patch("dashboard.v2_data._serialize_campaign_row", side_effect=serialized),
        ):
            payload = asyncio.run(get_v2_campaign_analytics_payload())

        self.assertEqual(
            payload["summary"],
            {
                "total_campaigns": 2,
                "total_transitions": 15,
                "total_bot_starts": 8,
                "total_trial_started": 5,
                "total_key_issued": 4,
                "total_paid": 3,
                "total_renewed": 1,
                "overall_conversion_rate": 20.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
