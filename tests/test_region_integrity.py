import asyncio
import json

from ops.vpn_regions import check_region_integrity


async def main() -> None:
    report = await check_region_integrity(run_cross_check=True)
    print("DE login ok:", report["active_regions"]["de"]["login_ok"])
    print("DK health ok:", report["active_regions"]["dk"]["health_check_ok"])
    print("EE retired:", report["retired_regions"]["ee"]["retired"])
    print("Cross-check ok:", report.get("cross_check_ok", True))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
