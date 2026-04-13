# TASK 124 — Control center spec refresh

## Status
Completed

## Goal
Refresh the `Amonora Control` technical specification in Russian so the team has one current source of truth that reflects the real Telegram-first product flows, multi-admin roles, manual SBP review, sync/repair expectations, and the premium SaaS UI direction.

## Why

- the earlier `amonora_control_tz_v4.md` covered the core control-center shape but no longer captured the full set of clarified business rules and UX expectations gathered later;
- the updated panel already has a strong implementation base, so the next iteration needs a cleaner spec that separates must-have production behavior from UX+ polish items;
- the repository needs an explicit written artifact that future changes can follow without re-collecting the same requirements from chat history.

## Scope

- create a new Russian markdown specification that supersedes the older brief;
- capture clarified roles, statuses, payment flow, support model, node model, sync/deep-repair expectations, and visual direction;
- separate mandatory production scope from polish/phase-2 UX features;
- leave runtime code unchanged.

## Out of scope

- new backend implementation;
- deployment;
- changing ports, services, or production secrets;
- rewriting architecture docs beyond minimal AI task/state trace.

## Acceptance criteria

- a new spec file exists in the repository root;
- the file is Russian-first and usable by both engineers and AI UI generators;
- the spec clearly distinguishes core production scope from UX+ extras;
- the AI state/task trail reflects that the current control-center specification has been refreshed.
