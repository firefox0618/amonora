#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.device_limit_hardening import backfill_single_ip_limits


async def _run() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill single-IP x-ui limit for legacy VPN device keys.",
    )
    parser.add_argument("--user-id", type=int, default=None, help="Restrict rollout to a single internal user id.")
    parser.add_argument("--limit", type=int, default=None, help="Restrict rollout to the first N devices.")
    parser.add_argument("--full-json", action="store_true", help="Print the full per-device report.")
    parser.add_argument("--fail-on-errors", action="store_true", help="Exit with code 1 if any device fails.")
    args = parser.parse_args()

    payload = await backfill_single_ip_limits(user_id=args.user_id, limit=args.limit)
    print(json.dumps(payload if args.full_json else payload["summary"], ensure_ascii=False, indent=2))

    if args.fail_on_errors and payload["summary"]["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
