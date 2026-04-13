# TASK 059 — Lightweight issue prioritization layer

## Status
Completed

## Goal
Introduce a simple explicit priority layer so overview shows not only issues, but which ones matter most right now.

## Implementation
- added `priority` to:
  - repair-needed users
  - backup block
  - restore block
  - support block and support attention items
  - payments block and pending-payment items
- priority model:
  - `high`
  - `medium`
  - `low`

## First-pass rules
- payment-related repair -> `high`
- general repair-needed -> `medium`
- backup missing -> `high`
- backup stale / restore unknown / support backlog / payment queue -> `medium`
- healthy informational states -> `low`

## UI
- overview now shows a dedicated high-priority repair subsection
- system cards and actionable items show compact priority badges

