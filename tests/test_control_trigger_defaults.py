import asyncio
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("XUI_URL", "http://127.0.0.1:12053")
os.environ.setdefault("XUI_USERNAME", "test")
os.environ.setdefault("XUI_PASSWORD", "test")
os.environ.setdefault("CHANNEL_ID", "1")

import control_bot.storage as storage
from control_bot.storage import CTA_ACTIONS, TRIGGER_DEFAULTS


class _FakeExecuteResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.commits = 0

    async def execute(self, _query):
        return _FakeExecuteResult(self.rows)

    def add(self, row) -> None:
        self.rows.append(row)

    async def commit(self):
        self.commits += 1


class _FakeSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class ControlTriggerDefaultsTests(unittest.TestCase):
    def test_trial_funnel_defaults_include_open_devices_cta_and_new_rules(self) -> None:
        keys = {item["key"]: item for item in TRIGGER_DEFAULTS}

        self.assertEqual(CTA_ACTIONS["open_devices"], "📱 Открыть устройства")
        self.assertIn("trial_active_2h", keys)
        self.assertIn("trial_low_2h", keys)
        self.assertIn("trial_active_24h", keys)
        self.assertIn("trial_low_24h", keys)
        self.assertIn("trial_final_6h", keys)
        self.assertEqual(keys["trial_low_2h"]["buttons"][0]["action"], "open_devices")
        self.assertFalse(keys["trial_ends_1d"]["enabled"])
        self.assertFalse(keys["trial_ends_today"]["enabled"])
        self.assertNotIn("31 марта 2026", keys["trial_ends_1d"]["template_body"])
        self.assertIn("сохранить доступ", keys["trial_ends_1d"]["template_body"])
        self.assertNotIn("подарочные месяцы", keys["trial_ends_today"]["template_body"])
        self.assertIn("восстановить доступ", keys["trial_expired_3d"]["template_body"])

    def test_ensure_default_trigger_rules_rewrites_stale_builtin_promo_copy(self) -> None:
        stale_body = next(iter(storage._STALE_PROMO_TRIGGER_BODIES["trial_ends_1d"]))
        row = SimpleNamespace(
            key="trial_ends_1d",
            family="trial",
            title="trial",
            description="desc",
            enabled=False,
            config_json="{}",
            template_body=stale_body,
            buttons_json="[]",
            updated_at=None,
        )
        session = _FakeSession([row])
        now = datetime(2026, 4, 3, 10, 0, 0)

        with (
            patch.object(storage, "async_session", new=_FakeSessionFactory(session)),
            patch.object(storage, "utcnow", return_value=now),
        ):
            result = asyncio.run(storage.ensure_default_trigger_rules())

        self.assertEqual(session.commits, 1)
        self.assertEqual(result[0].template_body, storage._default_trigger_template_body("trial_ends_1d"))
        self.assertEqual(result[0].updated_at, now)


if __name__ == "__main__":
    unittest.main()
