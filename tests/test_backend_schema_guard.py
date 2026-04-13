import unittest

from types import SimpleNamespace
from unittest.mock import call
from unittest.mock import AsyncMock, patch

import backend.core.schema as core_schema
import dashboard.schema as dashboard_schema


class _FakeAsyncContextManager:
    def __init__(self, connection) -> None:
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.run_sync_calls = 0

    async def execute(self, statement, params=None):
        self.executed.append(str(statement))
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: []),
            scalar=lambda: True,
        )

    async def run_sync(self, fn):
        self.run_sync_calls += 1
        return None


class BackendSchemaGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        core_schema._schema_ready = False

    async def asyncTearDown(self) -> None:
        core_schema._schema_ready = False

    async def test_ensure_schema_validates_existing_schema_when_auto_apply_disabled(self) -> None:
        existing_tables = set(core_schema.REQUIRED_SCHEMA_COLUMNS)
        existing_columns = {
            table_name: set(required_columns)
            for table_name, required_columns in core_schema.REQUIRED_SCHEMA_COLUMNS.items()
        }

        with (
            patch("backend.core.schema.os.getenv", return_value="0"),
            patch("backend.core.schema._detect_missing_required_schema", new=AsyncMock(return_value=[])) as detect_mock,
        ):
            await core_schema.ensure_schema()

        self.assertTrue(core_schema._schema_ready)
        detect_mock.assert_awaited_once()
        self.assertEqual(existing_tables, set(core_schema.REQUIRED_SCHEMA_COLUMNS))
        self.assertEqual(set(existing_columns), set(core_schema.REQUIRED_SCHEMA_COLUMNS))

    async def test_ensure_schema_fails_fast_when_required_columns_are_missing(self) -> None:
        with (
            patch("backend.core.schema.os.getenv", return_value="0"),
            patch(
                "backend.core.schema._detect_missing_required_schema",
                new=AsyncMock(return_value=["users.trial_activity_level", "payment_records.metadata_json"]),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "users.trial_activity_level"):
                await core_schema.ensure_schema()

        self.assertFalse(core_schema._schema_ready)

    async def test_apply_schema_migrations_executes_only_unapplied_steps(self) -> None:
        connection = _FakeConnection()
        migrations = (
            core_schema.SchemaMigrationStep("step_applied", "SELECT 'already'"),
            core_schema.SchemaMigrationStep("step_new", "SELECT 'new'"),
        )

        with (
            patch("backend.core.schema._ensure_schema_migration_registry", new=AsyncMock()),
            patch(
                "backend.core.schema._load_applied_schema_migration_keys",
                new=AsyncMock(return_value={"step_applied"}),
            ),
            patch("backend.core.schema._migration_effect_present", new=AsyncMock(return_value=True)),
            patch("backend.core.schema._record_applied_schema_migration", new=AsyncMock()) as record_mock,
        ):
            await core_schema.apply_schema_migrations(connection, migrations)

        self.assertEqual(connection.executed, ["SELECT 'new'"])
        record_mock.assert_awaited_once_with(connection, "step_new")

    async def test_apply_schema_migrations_does_not_record_step_when_effect_is_missing(self) -> None:
        connection = _FakeConnection()
        migrations = (
            core_schema.SchemaMigrationStep(
                "step_verify",
                "SELECT 'verify'",
                "SELECT FALSE",
            ),
        )

        with (
            patch("backend.core.schema._ensure_schema_migration_registry", new=AsyncMock()),
            patch(
                "backend.core.schema._load_applied_schema_migration_keys",
                new=AsyncMock(return_value=set()),
            ),
            patch("backend.core.schema._migration_effect_present", new=AsyncMock(return_value=False)),
            patch("backend.core.schema._record_applied_schema_migration", new=AsyncMock()) as record_mock,
        ):
            await core_schema.apply_schema_migrations(connection, migrations)

        self.assertEqual(connection.executed, ["SELECT 'verify'"])
        record_mock.assert_not_awaited()

    async def test_ensure_schema_auto_apply_uses_versioned_core_migrations(self) -> None:
        connection = _FakeConnection()

        with (
            patch("backend.core.schema.os.getenv", return_value="1"),
            patch(
                "backend.core.schema.engine",
                new=SimpleNamespace(begin=lambda: _FakeAsyncContextManager(connection)),
            ),
            patch("backend.core.schema.apply_schema_migrations", new=AsyncMock()) as apply_mock,
            patch("backend.core.schema._detect_missing_required_schema", new=AsyncMock(return_value=[])),
        ):
            await core_schema.ensure_schema()

        self.assertTrue(core_schema._schema_ready)
        self.assertEqual(connection.run_sync_calls, 1)
        apply_mock.assert_awaited_once_with(connection, core_schema.CORE_SCHEMA_MIGRATIONS)

    async def test_ensure_dashboard_schema_applies_core_and_dashboard_migrations(self) -> None:
        connection = _FakeConnection()

        with (
            patch(
                "dashboard.schema.engine",
                new=SimpleNamespace(begin=lambda: _FakeAsyncContextManager(connection)),
            ),
            patch("dashboard.schema.apply_schema_migrations", new=AsyncMock()) as apply_mock,
        ):
            await dashboard_schema.ensure_dashboard_schema()

        self.assertEqual(connection.run_sync_calls, 1)
        self.assertEqual(
            apply_mock.await_args_list,
            [
                call(connection, core_schema.CORE_SCHEMA_MIGRATIONS),
                call(connection, dashboard_schema.DASHBOARD_SCHEMA_MIGRATIONS),
            ],
        )


if __name__ == "__main__":
    unittest.main()
