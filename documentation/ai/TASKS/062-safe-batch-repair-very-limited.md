# TASK 062 — Safe batch repair (very limited)

## Status
Complete

## Goal
Reduce repetitive manual repair work by allowing a very small safe batch of repair actions from overview.

## Implemented scope
- selection is limited to the visible repair-needed slice on overview
- batch execution reuses the existing single-user repair API
- execution is sequential, not parallel
- no backend queue or worker was added

## Safety limits
- only repair actions
- only already surfaced repair-needed users
- maximum effective batch size is the visible overview slice (`up to 5`)
- each user is processed independently

## Out of scope
- bulk destructive actions
- async jobs
- retry engine
- cross-screen batch tools

## Validation
- frontend typecheck/build
- manual verification of sequential batch flow and partial-failure summary
