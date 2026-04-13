#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${AMONORA_BACKUP_ROOT:-/opt/amonora_bot/backups}"
STATUS_DIR="${AMONORA_BACKUP_STATUS_DIR:-${BACKUP_ROOT}/status}"
RETENTION_DAYS="${AMONORA_BACKUP_RETENTION_DAYS:-7}"
SOURCE_KEY="${AMONORA_REMOTE_SOURCE_KEY:?AMONORA_REMOTE_SOURCE_KEY is required}"
REMOTE_HOST="${AMONORA_REMOTE_HOST:?AMONORA_REMOTE_HOST is required}"
REMOTE_PATH="${AMONORA_REMOTE_PATH:?AMONORA_REMOTE_PATH is required}"
REMOTE_USER="${AMONORA_REMOTE_SSH_USER:-root}"
REMOTE_PORT="${AMONORA_REMOTE_SSH_PORT:-22}"
REMOTE_KEY="${AMONORA_REMOTE_SSH_KEY:-}"
REMOTE_KNOWN_HOSTS="${AMONORA_REMOTE_KNOWN_HOSTS:-}"
ARTIFACT_NAME="${AMONORA_REMOTE_ARTIFACT_NAME:-${SOURCE_KEY}_$(date -u +%Y-%m-%d_%H-%M).tar.gz}"
RCLONE_CMD="${AMONORA_BACKUP_RCLONE_CMD:-rclone}"
RCLONE_REMOTE="${AMONORA_BACKUP_RCLONE_REMOTE:-}"

STAMP="$(date -u +%Y-%m-%d_%H-%M)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DEST_DIR="${BACKUP_ROOT}/${SOURCE_KEY}/${STAMP}"
STATUS_FILE="${STATUS_DIR}/${SOURCE_KEY}.json"
ARTIFACT_PATH="${DEST_DIR}/${ARTIFACT_NAME}"

mkdir -p "${DEST_DIR}" "${STATUS_DIR}"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -p "${REMOTE_PORT}")
if [[ -n "${REMOTE_KEY}" ]]; then
  SSH_OPTS+=(-i "${REMOTE_KEY}")
fi
if [[ -n "${REMOTE_KNOWN_HOSTS}" ]]; then
  SSH_OPTS+=(-o "UserKnownHostsFile=${REMOTE_KNOWN_HOSTS}" -o StrictHostKeyChecking=yes)
else
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
fi

REMOTE_PARENT="$(dirname "${REMOTE_PATH}")"
REMOTE_NAME="$(basename "${REMOTE_PATH}")"
REMOTE_PARENT_Q="$(printf '%q' "${REMOTE_PARENT}")"
REMOTE_NAME_Q="$(printf '%q' "${REMOTE_NAME}")"

ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" \
  "set -euo pipefail; cd ${REMOTE_PARENT_Q}; tar -czf - ${REMOTE_NAME_Q}" > "${ARTIFACT_PATH}"

if [[ ! -s "${ARTIFACT_PATH}" ]]; then
  echo "Remote artifact archive is empty: ${ARTIFACT_PATH}" >&2
  exit 1
fi

ARTIFACT_SHA256="$(sha256sum "${ARTIFACT_PATH}" | awk '{print $1}')"
OFFSITE_STATUS="not_configured"
OFFSITE_SYNCED_AT=""

if [[ -n "${RCLONE_REMOTE}" ]]; then
  "${RCLONE_CMD}" copy "${DEST_DIR}" "${RCLONE_REMOTE}/${SOURCE_KEY}/${STAMP}" --transfers=2 --checkers=2
  OFFSITE_STATUS="synced"
  OFFSITE_SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

find "${BACKUP_ROOT}/${SOURCE_KEY}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +

export SOURCE_KEY NOW_ISO ARTIFACT_PATH ARTIFACT_SHA256 REMOTE_HOST REMOTE_PATH OFFSITE_STATUS OFFSITE_SYNCED_AT RCLONE_REMOTE
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
    "artifact_path": os.environ["ARTIFACT_PATH"],
    "artifact_sha256": os.environ["ARTIFACT_SHA256"],
    "remote_host": os.environ["REMOTE_HOST"],
    "remote_path": os.environ["REMOTE_PATH"],
    "offsite_status": os.environ["OFFSITE_STATUS"],
    "offsite_remote": os.environ.get("RCLONE_REMOTE", ""),
    "offsite_synced_at": os.environ.get("OFFSITE_SYNCED_AT", ""),
}
tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
tmp_path.replace(status_path)
PY

echo "Amonora remote artifact backup completed: ${ARTIFACT_PATH}"
