import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import dashboard.services as dashboard_services


class _FakeBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self.session = SimpleNamespace(close=AsyncMock())


class DashboardChannelSubscriptionStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        dashboard_services.invalidate_runtime_cache("channel_subscription_statuses")

    async def test_channel_subscription_statuses_are_cached(self) -> None:
        with (
            patch.object(dashboard_services.config, "bot_token", "test-token"),
            patch.object(dashboard_services.config, "channel_id", "@amonora_vpn"),
            patch.object(dashboard_services, "Bot", _FakeBot),
            patch.object(dashboard_services, "is_user_subscribed", new=AsyncMock(return_value=True)) as subscribed_mock,
        ):
            first = await dashboard_services.get_channel_subscription_statuses([111])
            second = await dashboard_services.get_channel_subscription_statuses([111])

        self.assertEqual(first[111]["status"], "subscribed")
        self.assertEqual(second[111]["status"], "subscribed")
        subscribed_mock.assert_awaited_once()

    async def test_channel_subscription_statuses_return_unknown_when_config_missing(self) -> None:
        with (
            patch.object(dashboard_services.config, "bot_token", ""),
            patch.object(dashboard_services.config, "channel_id", ""),
        ):
            result = await dashboard_services.get_channel_subscription_statuses([111])

        self.assertEqual(result[111]["status"], "unknown")
        self.assertEqual(result[111]["label"], "Не проверено")


if __name__ == "__main__":
    unittest.main()
