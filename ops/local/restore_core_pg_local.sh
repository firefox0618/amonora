#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="/mnt/c/Ops/Backups/amonora/core-pg"
CONTAINER_NAME="amonora-restore-drill"
POSTGRES_IMAGE="postgres:16"
DATABASE_NAME="test_restore"
POSTGRES_PASSWORD="amonora_restore"
DOCKER="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
KEEP_CONTAINER=0

if [[ "${1:-}" == "--keep-container" ]]; then
  KEEP_CONTAINER=1
fi

if [[ ! -x "$DOCKER" ]]; then
  echo "docker.exe not found at $DOCKER" >&2
  exit 1
fi

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "Backup root not found: $BACKUP_ROOT" >&2
  exit 1
fi

LATEST_SQL="$(find "$BACKUP_ROOT" -type f -regextype posix-extended -regex '.*/amonora_db_[0-9].*\.sql$' | sort | tail -n 1 || true)"

if [[ -z "$LATEST_SQL" ]]; then
  LATEST_GZ="$(find "$BACKUP_ROOT" -type f -regextype posix-extended -regex '.*/amonora_db_[0-9].*\.sql\.gz$' | sort | tail -n 1 || true)"
  if [[ -z "$LATEST_GZ" ]]; then
    echo "No PostgreSQL dump artifact found under $BACKUP_ROOT" >&2
    exit 1
  fi
  echo "Expanding gzip dump:"
  echo "  Source: $LATEST_GZ"
  gunzip -kf "$LATEST_GZ"
  LATEST_SQL="${LATEST_GZ%.gz}"
fi

if [[ ! -f "$LATEST_SQL" ]]; then
  echo "Prepared SQL file not found: $LATEST_SQL" >&2
  exit 1
fi

SQL_WINDOWS="$(wslpath -w "$LATEST_SQL")"
SQL_SIZE="$(stat -c %s "$LATEST_SQL")"

echo "Using PostgreSQL dump:"
echo "  $SQL_WINDOWS"
echo "  Size: $SQL_SIZE bytes"

"$DOCKER" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "Starting temporary PostgreSQL container..."
"$DOCKER" run -d --name "$CONTAINER_NAME" \
  -e "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
  -e "POSTGRES_DB=$DATABASE_NAME" \
  "$POSTGRES_IMAGE" >/dev/null

cleanup() {
  if [[ "$KEEP_CONTAINER" -eq 0 ]]; then
    echo "Removing temporary container..."
    "$DOCKER" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

for _ in $(seq 1 30); do
  if "$DOCKER" exec "$CONTAINER_NAME" pg_isready -U postgres -d "$DATABASE_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! "$DOCKER" exec "$CONTAINER_NAME" pg_isready -U postgres -d "$DATABASE_NAME" >/dev/null 2>&1; then
  echo "Temporary PostgreSQL container did not become ready in time" >&2
  exit 1
fi

echo "Copying SQL into container..."
"$DOCKER" cp "$SQL_WINDOWS" "${CONTAINER_NAME}:/tmp/restore.sql"

echo "Preparing temporary restore role..."
"$DOCKER" exec "$CONTAINER_NAME" psql -U postgres -d "$DATABASE_NAME" -c \
  "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amonora') THEN CREATE ROLE amonora LOGIN; END IF; END \$\$;" >/dev/null

echo "Running restore..."
"$DOCKER" exec "$CONTAINER_NAME" sh -lc "psql -U postgres -d $DATABASE_NAME -f /tmp/restore.sql" >/dev/null

echo "Running post-restore checks..."
USERS_COUNT="$("$DOCKER" exec "$CONTAINER_NAME" psql -U postgres -d "$DATABASE_NAME" -tAc "select count(*) from public.users;" | tr -d '\r' | xargs)"
VPN_CLIENTS_COUNT="$("$DOCKER" exec "$CONTAINER_NAME" psql -U postgres -d "$DATABASE_NAME" -tAc "select count(*) from public.vpn_clients;" | tr -d '\r' | xargs)"
PAYMENTS_COUNT="$("$DOCKER" exec "$CONTAINER_NAME" psql -U postgres -d "$DATABASE_NAME" -tAc "select count(*) from public.payment_records;" | tr -d '\r' | xargs)"

if [[ -z "$USERS_COUNT" || -z "$VPN_CLIENTS_COUNT" || -z "$PAYMENTS_COUNT" ]]; then
  echo "One or more restore verification queries returned empty output" >&2
  exit 1
fi

echo
echo "Restore drill completed successfully."
echo "Container: $CONTAINER_NAME"
echo "Database: $DATABASE_NAME"
echo "users_count=$USERS_COUNT"
echo "vpn_clients_count=$VPN_CLIENTS_COUNT"
echo "payments_count=$PAYMENTS_COUNT"

if [[ "$KEEP_CONTAINER" -eq 1 ]]; then
  trap - EXIT
  echo "Keeping container running because --keep-container was provided."
fi
