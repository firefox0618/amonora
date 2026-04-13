# TASK 054 — User issue summary in payments detail Result

## Result
Payment detail now exposes a compact access/repair issue summary for the linked user.

## Fields shown
- access status
- devices count
- repair-needed reason if present
- last repair attempt result/time if available

## UI behavior
- warning block appears only when an issue exists
- healthy users do not get an extra noisy warning block

## Still separate
- full user detail
- full support detail
- repair history drill-down
