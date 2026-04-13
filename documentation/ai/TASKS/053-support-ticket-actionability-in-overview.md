# TASK 053 — Support ticket actionability in overview

## Status
Completed

## Goal
Make support backlog actionable from overview by surfacing a short list of the oldest open tickets instead of showing only a raw count.

## Implementation
- extended overview system support payload with `oldest_open_tickets`
- actionability rule:
  - oldest 3 tickets with `new` or `in_progress` status
- each item carries:
  - `user_id`
  - `username`
  - `status`
  - `created_at`
  - `updated_at`
  - `preview`
  - `href`

## Scope kept
- no support workflow redesign
- no ticket assignment logic
- no SLA engine

