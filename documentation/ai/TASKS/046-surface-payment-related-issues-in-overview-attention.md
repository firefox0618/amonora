# TASK 046 — Surface payment-related issues in overview attention

## Status
Completed

## Goal
Expose the most important payment-related operational issues in the overview attention surface so admins can spot payment/access problems early instead of discovering them through support or manual digging.

## Outcome

Overview attention now distinguishes payment-related repair cases from generic repair-needed users.

Added:
- `payment_related_users` in overview attention payload
- `payment_related_repairs` summary count
- `is_payment_related` marker on repair-needed items
- `stale_pending_confirmations` in overview `system_alerts.payments`

## Scope kept intentionally narrow

Included:
- payment-related repair visibility
- compact pending/stale manual-payment signal in overview

Not included:
- new payment screen
- broad analytics
- alert center
- notifications
