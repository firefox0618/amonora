# TASK 044 — Support backlog and repair workload map

## Status
Completed

## Goal
Map where support load actually comes from, especially around access, payment confirmation, and VPN repair, so the next support-reducing improvements are chosen by evidence.

## Why
The project now exposes several important issue types:
- `vpn_repair_needed`
- repair attempts and failures
- support backlog
- manual payment confirmation queue
- system attention signals

But it is still unclear which support pain points consume the most operator time and which small fixes would reduce that load fastest.

## Scope
Read-only mapping only:
- no runtime changes
- no ticket workflow redesign
- no support bot rewrite

Mapped:
- main support issue categories
- which ones are caused by access/VPN problems
- which ones are caused by payment/manual confirmation
- which ones are caused by missing visibility
- which ones already have signals in dashboard
- which ones still require operator memory/manual digging

## Out of scope
- support UI redesign
- auto-reply systems
- ticket prioritization engine
- SLA logic
- support bot redesign

## Context
Relevant areas:
- `support_bot/storage.py`
- support-related payloads and UI surfaces
- repair-needed states
- manual payments
- payment/access drift paths
- overview attention sections

Relevant docs:
- `documentation/ALERTS_ATTENTION_MAP.md`
- `documentation/VPN_ACCESS_FLOW_MAP.md`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`

## Deliverables
- support backlog / repair workload map document
- task result note
- updated `STATE.md`
