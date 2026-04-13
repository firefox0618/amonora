#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${AMONORA_BACKUP_ROOT:-/opt/amonora_bot/backups}"
SOURCE_KEY="${AMONORA_BACKUP_SOURCE_KEY:-core}"
BACKUP_DIR="${AMONORA_PG_BACKUP_DIR:-${BACKUP_ROOT}/core-pg}"
STATUS_DIR="${AMONORA_BACKUP_STATUS_DIR:-${BACKUP_ROOT}/status}"
RETENTION_DAYS="${AMONORA_BACKUP_RETENTION_DAYS:-7}"
DB_NAME="${AMONORA_PGDATABASE:-amonora}"
DB_USER="${AMONORA_PGUSER:-amonora}"
DB_HOST="${AMONORA_PGHOST:-127.0.0.1}"
DB_PORT="${AMONORA_PGPORT:-5432}"
PG_DUMP_CMD="${AMONORA_PG_DUMP_CMD:-pg_dump}"
RCLONE_CMD="${AMONORA_BACKUP_RCLONE_CMD:-rclone}"
RCLONE_REMOTE="${AMONORA_BACKUP_RCLONE_REMOTE:-}"

STAMP="$(date -u +%Y-%m-%d_%H-%M)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEST_DIR="${BACKUP_DIR}/${STAMP}"
ARTIFACT_SQL="${DEST_DIR}/amonora_db_${STAMP}.sql"
ARTIFACT_GZ="${ARTIFACT_SQL}.gz"
STATUS_FILE="${STATUS_DIR}/${SOURCE_KEY}.json"

mkdir -p "${DEST_DIR}" "${STATUS_DIR}"

"${PG_DUMP_CMD}" \
  --host "${DB_HOST}" \
  --port "${DB_PORT}" \
  --username "${DB_USER}" \
  --dbname "${DB_NAME}" \
  --format=p \
  --no-owner \
  --no-privileges > "${ARTIFACT_SQL}"

gzip -f "${ARTIFACT_SQL}"

if [[ ! -s "${ARTIFACT_GZ}" ]]; then
  echo "Backup artifact is empty: ${ARTIFACT_GZ}" >&2
  exit 1
fi

ARTIFACT_SHA256="$(sha256sum "${ARTIFACT_GZ}" | awk '{print $1}')"
OFFSITE_STATUS="not_configured"
OFFSITE_SYNCED_AT=""

if [[ -n "${RCLONE_REMOTE}" ]]; then
  "${RCLONE_CMD}" copy "${DEST_DIR}" "${RCLONE_REMOTE}/core-pg/${STAMP}" --transfers=2 --checkers=2
  OFFSITE_STATUS="synced"
  OFFSITE_SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +

export SOURCE_KEY NOW_ISO ARTIFACT_GZ ARTIFACT_SHA256 OFFSITE_STATUS OFFSITE_SYNCED_AT RCLONE_REMOTE
python3 - "${STATUS_FILE}" <<'PY'
import json
import os
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
payload = {
    "source_key": os.environ["SOURCE_KEY"],
    "runner": "server-side",
    "last_backup_at": os.environ["NOW_ISO"],
    "artifact_path": os.environ["ARTIFACT_GZ"],
    "artifact_sha256": os.environ["ARTIFACT_SHA256"],
    "offsite_status": os.environ["OFFSITE_STATUS"],
    "offsite_remote": os.environ.get("RCLONE_REMOTE", ""),
    "offsite_synced_at": os.environ.get("OFFSITE_SYNCED_AT", ""),
}
tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
tmp_path.replace(status_path)
PY

echo "Amonora core PG backup completed: ${ARTIFACT_GZ}"
