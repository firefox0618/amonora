from __future__ import annotations

import argparse
import asyncio
import json
import logging

from backend.core.analytics import run_analytics_maintenance
from backend.core.schema import ensure_schema
from bot.utils.logging_setup import configure_logging


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh lightweight Amonora analytics rollups for dashboard analytics.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill stable historical attribution/events before refreshing rollups.",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Rebuild rollup buckets from the full analytics_events ledger.",
    )
    return parser


async def run(*, backfill: bool = False, full_refresh: bool = False) -> dict[str, object]:
    await ensure_schema()
    result = await run_analytics_maintenance(backfill=backfill, full_refresh=full_refresh)
    logger.info("Amonora analytics maintenance finished: %s", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    asyncio.run(run(backfill=bool(args.backfill), full_refresh=bool(args.full_refresh)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
