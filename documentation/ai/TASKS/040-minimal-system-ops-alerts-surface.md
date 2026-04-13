# TASK 040 — Minimal system ops alerts surface

## Status
Completed

## Goal
Surface the most critical system-level operational risks in a minimal form so admin can quickly understand whether the system itself needs attention.

## Why
After `039`, overview already shows user-level repair issues.

The next small step is to surface a compact system-level block for already known signals:

- backup freshness
- support backlog
- manual payment confirmation queue

## Scope
- extend overview payload with a compact `system_alerts` block
- add a small `System status` UI section on overview
- reuse existing support/payment counters
- use a simple filesystem heuristic for backup freshness

## Out of scope
- full monitoring
- node health monitoring
- external alert integrations
- full ops alerts center
- notifications

## Acceptance criteria
- overview shows a visible system-level block
- at least backup/support/payments are surfaced
- values are compact and actionable
- normal overview behavior remains intact

## Validation
- helper test for backup freshness heuristic
- overview API contract updated for `system_alerts`
- targeted backend tests
- frontend typecheck/build re-check in Windows Node environment

