# TASK 054 — User issue summary in payments detail

## Status
Completed

## Goal
Show a compact user issue summary in payment detail so admins can immediately see repair/access problems without jumping away.

## Implementation
- extended `selected_record.linked_user_context` with `user_issue_summary`
- included:
  - `has_issue`
  - `access_status`
  - `devices_count`
  - `vpn_repair_needed`
  - `vpn_repair_reason`
  - `last_repair_result`
  - `last_repair_at`
- payment detail UI now renders the block only when an issue exists

## Scope kept
- no payment page redesign
- no support workflow changes
- no extra route

