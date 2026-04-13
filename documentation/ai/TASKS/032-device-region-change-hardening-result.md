# TASK 032 — Device region change hardening result

## Status
Completed

## Output

Changed:
- `bot/handlers/devices.py`
- `bot/utils/regions.py`
- `bot/utils/texts.py`

Added:
- `tests/test_device_region_change_guard.py`

What changed:
- existing-device cross-region change is now blocked
- the callback no longer silently mutates device metadata into a fake “moved region” success state
- users now receive explicit recreate-device guidance instead

What remains intentionally unchanged:
- same-region selection remains safe
- no reprovision flow was added
- no production VPN architecture was changed
