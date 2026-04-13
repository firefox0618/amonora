import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from dashboard.v2_data import _collect_region_and_plan_metrics, get_v2_users_payload


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


class _UsersPayloadSession:
    def __init__(
        self,
        *,
        user=None,
        users=None,
        device_stats,
        country_rows,
        payment_counts,
        latest_status_rows,
        latest_tariff_rows,
        public_route_rows=None,
    ) -> None:
        self._users = list(users or ([] if user is None else [user]))
        self._device_stats = device_stats
        self._country_rows = country_rows
        self._payment_counts = payment_counts
        self._latest_status_rows = latest_status_rows
        self._latest_tariff_rows = latest_tariff_rows
        self._public_route_rows = public_route_rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        text = str(statement).lower()
        if "from users" in text:
            return _FakeScalarResult(self._users)
        if "count(vpn_clients.id)" in text:
            return _FakeRowResult(self._device_stats)
        if "from vpn_clients" in text:
            return _FakeRowResult(self._country_rows)
        if "count(payment_records.id)" in text:
            return _FakeRowResult(self._payment_counts)
        if "row_number()" in text and "tariff_code" in text:
            return _FakeRowResult(self._latest_tariff_rows)
        if "row_number()" in text and "payment_status" in text:
            return _FakeRowResult(self._latest_status_rows)
        if "from public_subscription_routes" in text:
            return _FakeRowResult(self._public_route_rows)
        raise AssertionError(f"unexpected query: {statement}")


class DashboardV2UsersPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_v2_users_payload_searches_by_tariff_code_and_exposes_plan_fields(self) -> None:
        user = SimpleNamespace(
            id=7,
            telegram_id=7007,
            username="alice",
            preferred_protocol="vless",
            is_blocked=False,
            balance_rub=0,
            created_at=datetime(2026, 3, 24, 12, 0, 0),
            trial_used=False,
            subscription_expires_at=datetime(2026, 6, 24, 12, 0, 0),
            trial_expires_at=None,
        )

        def session_factory():
            return _UsersPayloadSession(
                user=user,
                device_stats=[(7, 2, datetime(2026, 3, 24, 13, 0, 0))],
                country_rows=[(7, '{"country_code":"de"}'), (7, '{"country_code":"dk"}')],
                payment_counts=[(7, 5)],
                latest_status_rows=[(7, "confirmed")],
                latest_tariff_rows=[(7, "3m")],
                public_route_rows=[],
            )

        with (
            patch("dashboard.v2_data.async_session", session_factory),
            patch("dashboard.v2_data.get_channel_subscription_statuses", new=AsyncMock(return_value={7007: {"status": "ok", "label": "OK", "checked_at": None}})),
            patch("dashboard.v2_data.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={7: 0})),
            patch("dashboard.v2_data.get_access_status_from_user", return_value="paid_active"),
            patch("dashboard.v2_data.get_access_expires_at_from_user", return_value=datetime(2026, 6, 24, 12, 0, 0)),
            patch("dashboard.v2_data.dashboard_user_status", return_value={"code": "active", "label": "Активен"}),
        ):
            payload = await get_v2_users_payload("3m")

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["plan_code"], "3m")
        self.assertEqual(payload["items"][0]["plan_bucket"], "paid")
        self.assertEqual(payload["items"][0]["plan"], "3 месяца")
        self.assertEqual(payload["items"][0]["max_devices"], 3)

    async def test_get_v2_users_payload_defaults_missing_aggregate_rows_to_zero(self) -> None:
        user = SimpleNamespace(
            id=11,
            telegram_id=1011,
            username="sparse-user",
            preferred_protocol="vless",
            is_blocked=False,
            balance_rub=150,
            created_at=datetime(2026, 4, 1, 9, 30, 0),
            trial_used=False,
            subscription_expires_at=None,
            trial_expires_at=None,
        )

        def session_factory():
            return _UsersPayloadSession(
                user=user,
                device_stats=[],
                country_rows=[],
                payment_counts=[],
                latest_status_rows=[],
                latest_tariff_rows=[],
                public_route_rows=[],
            )

        with (
            patch("dashboard.v2_data.async_session", session_factory),
            patch("dashboard.v2_data.get_channel_subscription_statuses", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_access_status_from_user", return_value="inactive"),
            patch("dashboard.v2_data.get_access_expires_at_from_user", return_value=None),
            patch("dashboard.v2_data.dashboard_user_status", return_value={"code": "inactive", "label": "Не активен"}),
        ):
            payload = await get_v2_users_payload("")

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["devices"], 0)
        self.assertEqual(payload["items"][0]["payments"], 0)
        self.assertFalse(payload["items"][0]["device_limit_reached"])

    async def test_get_v2_users_payload_counts_bound_public_subscription_slots(self) -> None:
        user = SimpleNamespace(
            id=15,
            telegram_id=1015,
            username="public-link-user",
            preferred_protocol="vless",
            is_blocked=False,
            balance_rub=0,
            created_at=datetime(2026, 4, 2, 9, 30, 0),
            trial_used=False,
            subscription_expires_at=None,
            trial_expires_at=None,
        )

        def session_factory():
            return _UsersPayloadSession(
                user=user,
                device_stats=[],
                country_rows=[],
                payment_counts=[],
                latest_status_rows=[],
                latest_tariff_rows=[],
                public_route_rows=[
                    (15, "de", 1, '{"feed_device_fingerprint_hash":"slot-one","country_code":"de"}'),
                    (15, "dk", 1, '{"feed_device_fingerprint_hash":"slot-one","country_code":"dk"}'),
                    (15, "ee", 2, '{"feed_device_fingerprint_hash":"slot-two","country_code":"ee"}'),
                ],
            )

        with (
            patch("dashboard.v2_data.async_session", session_factory),
            patch("dashboard.v2_data.get_channel_subscription_statuses", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_access_status_from_user", return_value="inactive"),
            patch("dashboard.v2_data.get_access_expires_at_from_user", return_value=None),
            patch("dashboard.v2_data.dashboard_user_status", return_value={"code": "inactive", "label": "Не активен"}),
        ):
            payload = await get_v2_users_payload("")

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["devices"], 2)
        self.assertEqual(payload["items"][0]["countries_label"], "Германия, Дания")
        self.assertEqual(payload["summary"]["with_devices"], 1)

    async def test_get_v2_users_payload_applies_filters_and_paginates(self) -> None:
        paid_user = SimpleNamespace(
            id=21,
            telegram_id=1021,
            username="paid-user",
            preferred_protocol="vless",
            is_blocked=False,
            balance_rub=0,
            created_at=datetime(2026, 4, 3, 9, 30, 0),
            trial_used=False,
            subscription_expires_at=datetime(2026, 5, 3, 9, 30, 0),
            trial_expires_at=None,
        )
        trial_user = SimpleNamespace(
            id=22,
            telegram_id=1022,
            username="trial-user",
            preferred_protocol="vless",
            is_blocked=False,
            balance_rub=0,
            created_at=datetime(2026, 4, 4, 9, 30, 0),
            trial_used=True,
            subscription_expires_at=None,
            trial_expires_at=datetime(2026, 4, 7, 9, 30, 0),
        )

        def session_factory():
            return _UsersPayloadSession(
                users=[paid_user, trial_user],
                device_stats=[],
                country_rows=[],
                payment_counts=[],
                latest_status_rows=[],
                latest_tariff_rows=[(21, "1m")],
                public_route_rows=[],
            )

        with (
            patch("dashboard.v2_data.async_session", session_factory),
            patch("dashboard.v2_data.get_channel_subscription_statuses", new=AsyncMock(return_value={})),
            patch("dashboard.v2_data.get_active_device_slot_counts_for_users", new=AsyncMock(return_value={})),
            patch(
                "dashboard.v2_data.get_access_status_from_user",
                side_effect=lambda user: "trial_active" if user.id == 22 else "paid_active",
            ),
            patch(
                "dashboard.v2_data.get_access_expires_at_from_user",
                side_effect=lambda user: user.trial_expires_at if user.id == 22 else user.subscription_expires_at,
            ),
            patch(
                "dashboard.v2_data.dashboard_user_status",
                side_effect=lambda user, latest_payment_status=None: {"code": "trial", "label": "Пробный"}
                if user.id == 22
                else {"code": "active", "label": "Активен"},
            ),
        ):
            payload = await get_v2_users_payload("", status_filter="trial", page=1, page_size=1)

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], 22)
        self.assertEqual(payload["pagination"]["page"], 1)
        self.assertEqual(payload["pagination"]["page_size"], 20)
        self.assertEqual(payload["pagination"]["total_items"], 1)
        self.assertEqual(payload["filters"]["status"], "trial")

    async def test_collect_region_and_plan_metrics_preseeds_extended_tariffs(self) -> None:
        with patch("dashboard.v2_data._load_users_clients_payments", new=AsyncMock(return_value=([], [], []))):
            metrics = await _collect_region_and_plan_metrics()

        labels = set(metrics["plan_counts"].keys())
        self.assertIn("3 месяца", labels)
        self.assertIn("6 месяцев", labels)
        self.assertIn("12 месяцев", labels)
