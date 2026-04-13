#!/usr/bin/env bash
set -euo pipefail

exec sudo -u postgres -- /usr/bin/pg_dump "$@"
