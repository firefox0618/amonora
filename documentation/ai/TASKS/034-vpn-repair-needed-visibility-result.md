# TASK 034 — VPN repair-needed visibility in dashboard_v2 result

## Status
Completed

## Output

Changed:
- `dashboard_v2/src/lib/types.ts`
- `dashboard_v2/src/app/(dashboard)/users/page.tsx`

What is now visible:
- when `vpn_repair_state.repair_needed = true`, the user detail panel shows:
  - visible warning block
  - `repair-needed` badge
  - reason, if present
  - marked timestamp, if present

What remains intentionally uncovered:
- no retry buttons
- no list-wide filter
- no bulk repair tools
- no repair workflow redesign
