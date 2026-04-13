# TASK 050 RESULT — Backup visibility in dashboard (ops → UI bridge)

## What changed

Overview `System` -> `Backup` now shows:
- last known backup time
- stale threshold in hours
- per-source source rows where local backups exist:
  - `Core PG`
  - `VPN DE`
  - `VPN EE`

Each source row includes:
- last backup timestamp
- age in hours
- recent files count
- `ok / stale` status

## Signal source

This still uses local filesystem evidence under the configured dashboard backup root.

It does not yet prove:
- cloud replication
- restore success
- remote-storage health

## Validation

Updated:
- `tests/test_dashboard_system_alerts.py`
- `tests/test_dashboard_api_v2_contract.py`
