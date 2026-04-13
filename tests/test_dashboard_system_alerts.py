import tempfile
import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.services import _build_backup_status, _build_restore_validation_status


class DashboardSystemAlertsTests(unittest.TestCase):
    def test_build_backup_status_marks_recent_backup_as_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recent_dump = root / "amonora_db_2026-03-20.dump"
            recent_dump.write_text("backup", encoding="utf-8")

            now = datetime(2026, 3, 20, 12, 0, 0)
            recent_ts = (datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)).timestamp()
            recent_dump.touch()
            import os
            os.utime(recent_dump, (recent_ts, recent_ts))

            status = _build_backup_status(backup_root=root, now=now)

        self.assertFalse(status["backup_stale"])
        self.assertEqual(status["status"], "healthy")
        self.assertEqual(status["age_hours"], 2.0)
        self.assertEqual(status["stale_definition_hours"], 24)

    def test_build_backup_status_marks_old_backup_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pg_dir = root / "pg"
            pg_dir.mkdir(parents=True, exist_ok=True)
            stale_dump = pg_dir / "amonora_db_20260316-195700.sql.gz"
            stale_dump.write_text("backup", encoding="utf-8")

            now = datetime(2026, 3, 20, 12, 0, 0)
            stale_ts = (datetime(2026, 3, 19, 6, 0, 0, tzinfo=timezone.utc)).timestamp()
            stale_dump.touch()
            import os
            os.utime(stale_dump, (stale_ts, stale_ts))

            status = _build_backup_status(backup_root=root, now=now)

        self.assertTrue(status["backup_stale"])
        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["age_hours"], 30.0)

    def test_build_backup_status_includes_per_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for folder_name, stamp_hour in (("core-pg", 11), ("vpn-de", 10), ("vpn-ee", 9), ("vpn-dk", 8)):
                folder = root / folder_name / "2026-03-20_11-00"
                folder.mkdir(parents=True, exist_ok=True)
                backup_file = folder / "artifact.dump"
                backup_file.write_text("backup", encoding="utf-8")
                ts = (datetime(2026, 3, 20, stamp_hour, 0, 0, tzinfo=timezone.utc)).timestamp()
                import os
                os.utime(backup_file, (ts, ts))

            status = _build_backup_status(backup_root=root, now=datetime(2026, 3, 20, 12, 0, 0))

        self.assertEqual(len(status["sources"]), 4)
        self.assertEqual(status["sources"][0]["label"], "Core PG")
        self.assertEqual(status["sources"][0]["recent_files"], 1)
        self.assertFalse(status["sources"][0]["backup_stale"])

    def test_build_backup_status_uses_machine_signal_when_source_folder_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            status_dir = root / "status"
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / "core.json").write_text(
                """{
  "source_key": "core",
  "runner": "server-side",
  "last_backup_at": "2026-03-20T10:30:00Z",
  "offsite_status": "synced",
  "offsite_synced_at": "2026-03-20T10:35:00Z"
}""",
                encoding="utf-8",
            )

            status = _build_backup_status(backup_root=root, now=datetime(2026, 3, 20, 12, 0, 0))

        core_row = next(item for item in status["sources"] if item["key"] == "core")
        self.assertEqual(status["last_backup_at"], "2026-03-20 15:30 Екб")
        self.assertEqual(core_row["runner"], "server-side")
        self.assertEqual(core_row["offsite_status"], "synced")
        self.assertEqual(core_row["offsite_synced_at"], "2026-03-20 15:35 Екб")
        self.assertFalse(core_row["backup_stale"])

    def test_build_restore_validation_status_marks_recent_validation_as_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            signal = root / "restore-proof.json"
            signal.write_text(
                '{"status":"healthy","last_restore_validation_at":"2026-03-19T12:00:00Z","validated_public_tables":42,"proof_kind":"temporary_database_restore","proof_status":"verified","proof_scope":["core_pg"]}',
                encoding="utf-8",
            )

            from unittest.mock import patch

            with (
                patch("dashboard.services.RESTORE_PROOF_STATUS_PATH", signal),
                patch("dashboard.services.RESTORE_VALIDATION_STATUS_PATH", root / "restore-validation.json"),
            ):
                status = _build_restore_validation_status(now=datetime(2026, 3, 20, 12, 0, 0))

        self.assertEqual(status["status"], "healthy")
        self.assertFalse(status["restore_validation_stale"])
        self.assertEqual(status["age_days"], 1.0)
        self.assertEqual(status["signal_source"], "machine-readable restore proof status")
        self.assertTrue(status["real_restore_proof"])

    def test_build_restore_validation_status_does_not_trust_legacy_validation_without_proof_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            signal = root / "restore-validation.json"
            signal.write_text(
                '{"status":"healthy","last_restore_validation_at":"2026-03-19T12:00:00Z","validated_public_tables":42}',
                encoding="utf-8",
            )

            from unittest.mock import patch

            with (
                patch("dashboard.services.RESTORE_PROOF_STATUS_PATH", root / "restore-proof.json"),
                patch("dashboard.services.RESTORE_VALIDATION_STATUS_PATH", signal),
            ):
                status = _build_restore_validation_status(now=datetime(2026, 3, 20, 12, 0, 0))

        self.assertEqual(status["status"], "unknown")
        self.assertTrue(status["restore_validation_stale"])
        self.assertFalse(status["real_restore_proof"])

    def test_build_restore_validation_status_returns_unknown_without_signal(self) -> None:
        from unittest.mock import patch

        with (
            patch("dashboard.services.RESTORE_PROOF_STATUS_PATH", Path("/tmp/nonexistent-restore-proof.json")),
            patch("dashboard.services.RESTORE_VALIDATION_STATUS_PATH", Path("/tmp/nonexistent-restore-validation.json")),
        ):
            status = _build_restore_validation_status(now=datetime(2026, 3, 20, 12, 0, 0))

        self.assertEqual(status["status"], "unknown")
        self.assertTrue(status["restore_validation_stale"])
        self.assertEqual(status["last_restore_validation_at"], "—")
        self.assertEqual(status["signal_source"], "machine-readable restore proof status")


if __name__ == "__main__":
    unittest.main()
