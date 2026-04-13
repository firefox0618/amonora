# TASK 041 — Unify overview attention section

## Status
Completed

## Goal
Make the overview attention surface feel like one coherent section instead of two separate blocks for user issues and system status.

## Why
After `039` and `040`, overview already had both:

- user-level repair attention
- minimal system-level status

The next smallest useful step was not adding new signals, but making the presentation easier to scan and reason about.

## Scope
- keep the same existing signals
- keep the same existing backend payload
- unify presentation on overview into one section with two sub-groups:
  - `Users`
  - `System`

## Out of scope
- new signals
- backend refactor
- full alerts center
- new filters or workflows

## Acceptance criteria
- overview presents one coherent attention section
- user-level and system-level signals remain visually distinct
- no payload/API behavior changes are needed
- the page still typechecks/builds cleanly

## Validation
- frontend typecheck/build re-check in Windows Node environment
- manual visual sanity check through the updated layout

