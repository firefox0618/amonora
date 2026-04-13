# TASK 153 — V2 payment reminder actionability parity

## Status
Completed

## Goal
Restore the `Напомнить об оплате` action in `dashboard/ui` payment detail for open manual SBP payments.

## Why
The feature was implemented in the backend action and in the UI button, but the `v2` payments payload used by the Next.js control center did not serialize `can_send_reminder`. As a result, the reminder button stayed hidden even for valid `sbp_manual` records like `#141`.

## Scope
- add `can_send_reminder` to the `dashboard/v2_data.py` payment serializer;
- cover the `v2` serializer with a regression test.

## Acceptance criteria
- open manual `СБП` payments in `dashboard/ui` show `Напомнить об оплате`;
- `GET /dashboard/api/v2/payments?record_id=<id>` returns `can_send_reminder: true` for eligible `sbp_manual` records;
- regression test covers the `v2` serializer.
