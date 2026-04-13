import unittest

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

import dashboard.services as dashboard_services
import dashboard.v2_data as dashboard_v2_data


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


class _FakeScalarResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeRowResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _VpnOverviewSession:
    def __init__(self, *, users, devices, executed) -> None:
        self._users = users
        self._devices = devices
        self._executed = executed

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement)
        self._executed.append(text)
        if "from vpn_clients" in text.lower():
            return _FakeScalarResult(self._devices)
        if "from users" in text.lower():
            return _FakeScalarResult(self._users)
        raise AssertionError(f"unexpected query: {text}")


class DashboardUsersQueryHardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        dashboard_services.invalidate_runtime_cache(
            "vpn_overview_default",
            "managed_region_device_stats",
            "overview_metrics",
            "server_snapshots",
            "xui_summary",
        )

    def test_build_v2_users_base_query_searches_real_users_and_confirmed_tariffs(self) -> None:
        compiled = _compile(dashboard_v2_data._build_v2_users_base_query("3m"))

        self.assertIn("from users", compiled)
        self.assertIn("users.is_synthetic", compiled)
        self.assertIn("exists (select payment_records.id", compiled)
        self.assertIn("payment_records.payment_status = 'confirmed'", compiled)
        self.assertIn("payment_records.tariff_code", compiled)

    def test_build_v2_user_device_stats_query_groups_by_user(self) -> None:
        compiled = _compile(dashboard_v2_data._build_v2_user_device_stats_query([7, 8]))

        self.assertIn("from vpn_clients", compiled)
        self.assertIn("count(vpn_clients.id)", compiled)
        self.assertIn("max(vpn_clients.created_at)", compiled)
        self.assertIn("group by vpn_clients.user_id", compiled)
        self.assertIn("vpn_clients.user_id in (7, 8)", compiled)

    def test_build_v2_user_latest_payment_status_query_uses_window(self) -> None:
        compiled = _compile(dashboard_v2_data._build_v2_user_latest_payment_status_query([7, 8]))

        self.assertIn("row_number() over", compiled)
        self.assertIn("partition by payment_records.user_id", compiled)
        self.assertIn("order by payment_records.created_at desc, payment_records.id desc", compiled)
        self.assertIn("where anon_1.row_number = 1", compiled)

    def test_build_v2_user_latest_confirmed_tariff_query_filters_confirmed_only(self) -> None:
        compiled = _compile(dashboard_v2_data._build_v2_user_latest_confirmed_tariff_query([7, 8]))

        self.assertIn("payment_records.payment_status = 'confirmed'", compiled)
        self.assertIn("payment_records.tariff_code is not null", compiled)
        self.assertIn("row_number() over", compiled)

    async def test_get_vpn_overview_uses_default_cache_on_repeat_calls(self) -> None:
        now = datetime(2026, 4, 5, 10, 0, 0)
        user = SimpleNamespace(
            id=1,
            telegram_id=1001,
            username="alice",
            is_synthetic=False,
            subscription_expires_at=now + timedelta(days=10),
            trial_expires_at=None,
            trial_used=False,
            trial_started_at=None,
            subscription_status="active",
            is_blocked=False,
        )
        device = SimpleNamespace(
            id=11,
            user_id=1,
            protocol="vless",
            email="device_11",
            client_data='{"country_code":"de","country_name":"Germany","device_name":"Phone"}',
            created_at=now - timedelta(hours=2),
        )
        executed: list[str] = []

        def session_factory():
            return _VpnOverviewSession(users=[user], devices=[device], executed=executed)

        with (
            patch.object(dashboard_services, "async_session", session_factory),
            patch.object(dashboard_services, "utcnow", return_value=now),
        ):
            first = await dashboard_services.get_vpn_overview()
            second = await dashboard_services.get_vpn_overview()

        self.assertEqual(first["summary"]["total_devices"], 1)
        self.assertEqual(second["summary"]["total_devices"], 1)
        self.assertEqual(len(executed), 2)


if __name__ == "__main__":
    unittest.main()
