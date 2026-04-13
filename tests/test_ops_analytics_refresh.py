import unittest

from unittest.mock import AsyncMock, patch

import ops.analytics_refresh as analytics_refresh


class AnalyticsRefreshRunnerTests(unittest.TestCase):
    def test_main_runs_backfill_and_full_refresh_flags(self) -> None:
        with (
            patch.object(analytics_refresh, "configure_logging"),
            patch.object(analytics_refresh, "ensure_schema", new=AsyncMock()) as ensure_mock,
            patch.object(
                analytics_refresh,
                "run_analytics_maintenance",
                new=AsyncMock(return_value={"ok": True}),
            ) as maintenance_mock,
        ):
            exit_code = analytics_refresh.main(["--backfill", "--full-refresh"])

        self.assertEqual(exit_code, 0)
        ensure_mock.assert_awaited_once()
        maintenance_mock.assert_awaited_once_with(backfill=True, full_refresh=True)


if __name__ == "__main__":
    unittest.main()
