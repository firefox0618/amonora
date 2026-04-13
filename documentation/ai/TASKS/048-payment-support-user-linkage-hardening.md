# TASK 048 — Payment / support / user linkage hardening

## Status
Completed

## Goal
Reduce manual cross-screen/operator work by making payment issues, user repair state, and support context easier to connect in one coherent admin flow.

## Outcome

The payments detail surface now includes a minimal linked user context instead of forcing the operator to reconstruct the state across multiple tabs first.

## Scope kept intentionally narrow

Included:
- linkage added only in `selected_record` payment detail
- user access state
- repair-needed state
- support-ticket presence
- direct links to user and support screens

Not included:
- unified case management
- support workflow redesign
- broad payments CRM
