import argparse
import asyncio
import json

from ops.vpn_regions import reconcile_vpn_clients


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Full local↔remote VPN reconcile for Germany/Denmark plus retired Estonia cleanup inventory"
    )
    parser.add_argument("--apply", action="store_true", help="Apply metadata fixes and remote cleanup/repair actions")
    parser.add_argument(
        "--repair-missing-remote",
        action="store_true",
        help="Attempt to recreate missing active remote clients during apply",
    )
    parser.add_argument(
        "--retire-ee-cleanup",
        action="store_true",
        help="Allow destructive cleanup of retired Estonia local devices during apply",
    )
    args = parser.parse_args()

    report = await reconcile_vpn_clients(
        apply_changes=args.apply,
        repair_missing_remote=args.repair_missing_remote,
        retire_ee_cleanup=args.retire_ee_cleanup,
    )
    print("Total clients:", report["total"])
    print("Summary:", json.dumps(report["summary"], ensure_ascii=False))
    print("Missing remote:", len(report["missing"]))
    print("Remote recreated:", len(report.get("repaired", [])))
    print("Manual required:", len(report.get("manual_required", [])))
    print("Retired follow-up users:", len(report.get("retired_follow_up_users", [])))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
