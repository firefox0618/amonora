# TASK 030 — One-click restore script result

## Status
Completed

## Output

Created:
- `ops/local/restore_core_pg_local.ps1`
- `ops/local/restore_core_pg_local.sh`

Stable local runnable copy:
- `C:\Users\Skyfal\Scripts\amonora\restore_core_pg_local.ps1`

What the script now does in one command:
- PowerShell wrapper starts the canonical WSL restore script
- finds the newest valid core PostgreSQL dump under `C:\Ops\Backups\amonora\core-pg`
- expands the dump if only `.sql.gz` is present
- starts a temporary `postgres:16` Docker container
- creates a temporary local role `amonora` inside the test container
- imports the dump into `test_restore`
- runs post-restore checks:
  - `users`
  - `vpn_clients`
  - `payment_records`
- removes the temporary container unless `-KeepContainer` is provided

Verified local run:
- artifact used:
  - `C:\Ops\Backups\amonora\core-pg\2026-03-19_20-29\amonora_db_20260316-195700.sql`
- Docker image:
  - `postgres:16`
- database:
  - `test_restore`
- result:
  - `users_count = 10`
  - `vpn_clients_count = 9`
  - `payments_count = 2`

Observed note:
- the one-click drill now avoids the previous missing-role failure mode by creating a temporary local role `amonora` before import
