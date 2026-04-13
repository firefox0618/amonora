# TASK 048 RESULT — Payment / support / user linkage hardening

## What changed

`selected_record` in payments payload now carries `linked_user_context` when the payment belongs to a real user.

The payments detail UI now shows:
- access status
- access expiry
- device count
- `vpn_repair_needed`
- repair reason if present
- support-ticket presence/status
- direct `Open user` and `Open support` links

## Why this helps

Operators no longer need to jump blindly from:
- payments
- to users
- to support

just to understand the first-level context of a problematic payment.

## What remains manual

- deep support conversation handling
- full cross-surface triage
- richer case management
