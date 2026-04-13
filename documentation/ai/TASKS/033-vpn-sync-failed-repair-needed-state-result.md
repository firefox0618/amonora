# TASK 033 — VPN sync failed -> repair-needed state result

## Status
Completed

## Output

Changed:
- `backend/core/models.py`
- `backend/core/schema.py`
- `bot/db.py`
- `bot/payment_flow.py`
- `dashboard/services.py`
- `tests/test_payment_finalization.py`

What is now persisted:
- `users.vpn_repair_needed`
- `users.vpn_repair_reason`
- `users.vpn_repair_marked_at`

Current behavior:
- payment finalization with `sync_failed=True` now persists a repair-needed marker
- successful payment finalization sync clears the marker
- marker is visible in backend user detail payload through `vpn_repair_state`

What is intentionally not covered yet:
- admin-triggered mutations outside the payment path
- retry queue
- automatic repair flow
- dashboard UI redesign
