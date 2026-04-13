#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${AMONORA_BACKUP_ROOT:-/opt/amonora_bot/backups}"
BACKUP_DIR="${AMONORA_PG_BACKUP_DIR:-${BACKUP_ROOT}/core-pg}"
STATUS_DIR="${AMONORA_BACKUP_STATUS_DIR:-${BACKUP_ROOT}/status}"
SOURCE_KEY="${AMONORA_RESTORE_VALIDATION_SOURCE_KEY:-restore-validation}"
DB_USER="${AMONORA_PGUSER:-amonora}"
DB_HOST="${AMONORA_PGHOST:-127.0.0.1}"
DB_PORT="${AMONORA_PGPORT:-5432}"
CREATEDB_CMD="${AMONORA_CREATEDB_CMD:-createdb}"
DROPDB_CMD="${AMONORA_DROPDB_CMD:-dropdb}"
PSQL_CMD="${AMONORA_PSQL_CMD:-psql}"
RESTORE_TIMEOUT_SECONDS="${AMONORA_RESTORE_VALIDATION_TIMEOUT_SECONDS:-300}"

STATUS_FILE="${STATUS_DIR}/${SOURCE_KEY}.json"
PROOF_FILE="${STATUS_DIR}/restore-proof.json"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TMP_DB="amonora_restore_probe_$(date -u +%Y%m%d%H%M%S)"

mkdir -p "${STATUS_DIR}"

LATEST_DUMP="$(find "${BACKUP_DIR}" -type f -name '*.sql.gz' | sort | tail -n 1 || true)"
if [[ -z "${LATEST_DUMP}" ]]; then
  echo "No PostgreSQL backup artifact found under ${BACKUP_DIR}" >&2
  exit 1
fi

cleanup() {
  "${DROPDB_CMD}" --if-exists --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" "${TMP_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${CREATEDB_CMD}" --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" "${TMP_DB}"
timeout "${RESTORE_TIMEOUT_SECONDS}" bash -lc "gunzip -c '${LATEST_DUMP}' | '${PSQL_CMD}' --host '${DB_HOST}' --port '${DB_PORT}' --username '${DB_USER}' --dbname '${TMP_DB}' --set ON_ERROR_STOP=1 >/dev/null"
TABLE_COUNT="$("${PSQL_CMD}" --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" --dbname "${TMP_DB}" --tuples-only --no-align --command "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d '[:space:]')"

if [[ -z "${TABLE_COUNT}" || "${TABLE_COUNT}" == "0" ]]; then
  echo "Restore validation produced no public tables" >&2
  exit 1
fi

export NOW_ISO LATEST_DUMP STATUS_FILE PROOF_FILE TABLE_COUNT
python3 - <<'PY'
import json
import os
from pathlib import Path

status_path = Path(os.environ["STATUS_FILE"])
proof_path = Path(os.environ["PROOF_FILE"])
payload = {
    "source_key": "restore-validation",
    "status": "healthy",
    "runner": "server-side",
    "last_restore_validation_at": os.environ["NOW_ISO"],
    "artifact_path": os.environ["LATEST_DUMP"],
    "validated_public_tables": int(os.environ["TABLE_COUNT"]),
    "proof_kind": "temporary_database_restore",
    "proof_status": "verified",
    "proof_scope": ["core_pg"],
    "drill_target": "temporary_database_probe",
}
tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
tmp_path.replace(status_path)

proof_payload = {
    **payload,
    "source_key": "restore-proof",
}
proof_tmp = proof_path.with_suffix(proof_path.suffix + ".tmp")
proof_tmp.write_text(json.dumps(proof_payload, ensure_ascii=False, indent=2), encoding="utf-8")
proof_tmp.replace(proof_path)
PY

echo "Amonora restore validation completed: ${LATEST_DUMP}"
