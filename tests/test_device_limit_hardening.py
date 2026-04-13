import unittest

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.db import activate_vpn_client_device, create_vpn_client


class _ScalarResult:
    def __init__(self, scalar=None) -> None:
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    def __init__(self, execute_results=None) -> None:
        self._execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.refreshes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query):
        if not self._execute_results:
            raise AssertionError("unexpected query")
        return self._execute_results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1
        if getattr(obj, "id", None) is None:
            obj.id = 501


class DeviceLimitHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_vpn_client_rechecks_limit_inside_save_callback(self) -> None:
        session = _FakeSession(
            execute_results=[
                _ScalarResult(SimpleNamespace(id=77, telegram_id=990077, active_device_slot_addons=0)),
                _ScalarResult(0),
                _ScalarResult(3),
            ]
        )

        with (
            patch("bot.db.ensure_schema", new=AsyncMock()),
            patch("bot.db.async_session", return_value=session),
        ):
            with self.assertRaisesRegex(ValueError, "current device limit"):
                await create_vpn_client(
                    user_id=77,
                    protocol="vless",
                    client_uuid="uuid-1",
                    email="device_77_1",
                    client_data={"country_code": "de"},
                )

        self.assertEqual(session.commits, 0)
        self.assertEqual(len(session.added), 0)

    async def test_create_vpn_client_succeeds_below_limit(self) -> None:
        session = _FakeSession(
            execute_results=[
                _ScalarResult(SimpleNamespace(id=78, telegram_id=990078, active_device_slot_addons=0)),
                _ScalarResult(0),
                _ScalarResult(2),
            ]
        )

        with (
            patch("bot.db.ensure_schema", new=AsyncMock()),
            patch("bot.db.async_session", return_value=session),
        ):
            result = await create_vpn_client(
                user_id=78,
                protocol="vless",
                client_uuid="uuid-2",
                email="device_78_1",
                client_data={"country_code": "de"},
            )

        self.assertEqual(result.id, 501)
        self.assertEqual(session.commits, 1)
        self.assertEqual(len(session.added), 1)

    async def test_activate_vpn_client_device_checks_limit_under_locked_client_row(self) -> None:
        session = _FakeSession(
            execute_results=[
                _ScalarResult(SimpleNamespace(id=14)),
                _ScalarResult(None),
                _ScalarResult(1),
            ]
        )

        with (
            patch("bot.db.ensure_schema", new=AsyncMock()),
            patch("bot.db.async_session", return_value=session),
        ):
            result = await activate_vpn_client_device(
                vpn_client_id=14,
                user_id=77,
                country_code="ee",
                fingerprint_hash="abc123",
                device_label="iPhone",
                platform="ios",
                app_version="1.0",
                source_ip="198.51.100.10",
                user_agent="AmonoraTest/1.0",
                max_devices=1,
            )

        self.assertEqual(result["status"], "limit_reached")
        self.assertEqual(result["active_devices"], 1)
        self.assertEqual(session.commits, 0)
        self.assertEqual(len(session.added), 0)


if __name__ == "__main__":
    unittest.main()
