# LOCAL RESTORE RECIPE

Date: 2026-03-19
Status: verified locally
Scope: local machine only, no production changes

## Purpose

This document captures the shortest repeatable local restore drill for:
- PostgreSQL dump verification through a temporary Docker PostgreSQL instance
- `3x-ui` SQLite database verification through local SQLite access

It is intentionally a local validation recipe.
It is not a production restore playbook.

## Preconditions

Required on the local machine:
- Docker Desktop working
- backup artifacts already copied locally under:
  - `C:\Ops\Backups\amonora`

Optional but useful:
- WSL shell access
- Python available in the project virtualenv

## PostgreSQL local restore drill

### One-command option

Preferred local operator command:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\Skyfal\Scripts\amonora\restore_core_pg_local.ps1
```

What it does:
- PowerShell wrapper starts the canonical WSL restore script
- finds the newest valid core dump under `C:\Ops\Backups\amonora\core-pg`
- expands `.sql.gz` if needed
- starts a temporary local `postgres:16` container
- creates a temporary local role `amonora` inside the test container
- imports the dump into `test_restore`
- runs basic count checks
- removes the temporary container automatically

Verified result from the current drill path:
- `users_count = 10`
- `vpn_clients_count = 9`
- `payments_count = 2`

Use the manual step-by-step flow below only when debugging the restore path.

### Artifact used

Example source:
- `C:\Ops\Backups\amonora\core-pg\2026-03-19_20-29\amonora_db_20260316-195700.sql.gz`

### Step 1 — Unpack the dump

```bash
gunzip -kf /mnt/c/Ops/Backups/amonora/core-pg/2026-03-19_20-29/amonora_db_20260316-195700.sql.gz
```

### Step 2 — Start a temporary PostgreSQL container

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" run -d --name amonora-restore-drill -e POSTGRES_PASSWORD=amonora_restore -e POSTGRES_DB=test_restore postgres:16
```

### Step 3 — Wait until PostgreSQL is ready

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill pg_isready -U postgres -d test_restore
```

Expected result:
- `accepting connections`

### Step 4 — Copy the SQL into the container

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" cp "C:\Ops\Backups\amonora\core-pg\2026-03-19_20-29\amonora_db_20260316-195700.sql" amonora-restore-drill:/tmp/restore.sql
```

### Step 5 — Run the restore

First prepare the role expected by the dump:

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill psql -U postgres -d test_restore -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amonora') THEN CREATE ROLE amonora LOGIN; END IF; END \$\$;"
```

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill sh -lc 'psql -U postgres -d test_restore -f /tmp/restore.sql'
```

Important note:
- for the current local drill, creating a temporary role `amonora` first is the safest path
- this keeps the restore repeatable inside a blank temporary container

### Step 6 — Verify tables

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill sh -lc 'psql -U postgres -d test_restore -c "\dt"'
```

Expected tables include:
- `dashboard_admins`
- `dashboard_audit_logs`
- `dashboard_sessions`
- `managed_servers`
- `payment_records`
- `support_ticket_messages`
- `support_tickets`
- `users`
- `vpn_clients`

### Step 7 — Verify sample data counts

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill sh -lc 'psql -U postgres -d test_restore -c "select count(*) as users_count from public.users;"'
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill sh -lc 'psql -U postgres -d test_restore -c "select count(*) as vpn_clients_count from public.vpn_clients;"'
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" exec amonora-restore-drill sh -lc 'psql -U postgres -d test_restore -c "select count(*) as payments_count from public.payment_records;"'
```

Verified local result from the 2026-03-19 drill:
- `users_count = 10`
- `vpn_clients_count = 9`
- `payments_count = 2`

### Step 8 — Remove the temporary container

```bash
"/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" rm -f amonora-restore-drill
```

## `3x-ui` SQLite local verification drill

### Example artifacts

Germany:
- `C:\Ops\Backups\amonora\vpn-de\2026-03-19_20-29\x-ui.db`

Estonia:
- `C:\Ops\Backups\amonora\vpn-ee\2026-03-19_20-29\x-ui.db`

### Step 1 — Open through Python SQLite

Germany example:

```bash
./venv/bin/python - <<'PY'
import sqlite3
path = '/mnt/c/Ops/Backups/amonora/vpn-de/2026-03-19_20-29/x-ui.db'
con = sqlite3.connect(path)
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print(cur.fetchall())
con.close()
PY
```

Estonia example:

```bash
./venv/bin/python - <<'PY'
import sqlite3
path = '/mnt/c/Ops/Backups/amonora/vpn-ee/2026-03-19_20-29/x-ui.db'
con = sqlite3.connect(path)
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print(cur.fetchall())
con.close()
PY
```

### Expected tables

Verified on both node DBs:
- `client_traffics`
- `history_of_seeders`
- `inbound_client_ips`
- `inbounds`
- `outbound_traffics`
- `settings`
- `sqlite_sequence`
- `users`

## Interpretation rules

### PostgreSQL

Treat the drill as successful when:
- the SQL expands cleanly
- the temporary PostgreSQL instance imports the dump
- expected tables are present
- sample data queries return rows/counts

### `3x-ui`

Treat the drill as successful when:
- the DB file opens
- SQLite metadata is readable
- expected tables are present

## What this recipe proves

- current local backup artifacts are not just stored files
- PostgreSQL dump is restorable into a temporary local PostgreSQL runtime
- VPN node `x-ui.db` files are structurally valid SQLite databases

## What this recipe does not prove

- production restore sequencing
- production env/systemd/nginx reconstruction
- full `3x-ui` service-level restore
- disaster recovery under total infrastructure loss
