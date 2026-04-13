# ALERTS ATTENTION MAP

Date: 2026-03-20
Status: current-state mapping
Scope: existing attention signals, current visibility, and minimal UI placement model

## Purpose

This document collects the main states that currently require attention across the product and operations layers.

It exists to answer one practical question:

> what can already be broken, degraded, or drifted in the system, and where is that visible right now?

This is a mapping artifact only.
It does not add new runtime behavior and does not redesign the alerting model yet.

## How to read this map

Each signal is described through:

- `Signal`
- `Source`
- `Current visibility`
- `Severity`
- `Suggested UI placement`

Two levels are separated on purpose:

- `User-level` signals
- `System-level` signals

This is important because a broken user access flow and a degraded infrastructure state should not be mixed into one flat list without context.

## User-level signals

| Signal | Source | Current visibility | Severity | Suggested UI placement |
|---|---|---|---|---|
| VPN repair needed | `backend.core.models.User.vpn_repair_needed`, `bot/payment_flow.py`, `dashboard/services.py` | Visible in `panel UI` user detail | High | User detail + future overview attention rail |
| Failed manual VPN repair | `vpn_repair_events`, `dashboard/services.py` | Visible in `panel UI` user detail history | Medium | User detail + future overview attention rail when repeated |
| Repeated failed repair attempts | `vpn_repair_events` aggregated per user | Not aggregated yet; only visible by reading user history manually | High | Future overview attention rail + user risk badge |
| Active entitlement but VPN sync failed | `bot/payment_flow.py` -> repair-needed marker | Indirectly visible through `vpn_repair_needed` | High | User detail + future overview attention block |
| Manual repair cannot start because user has no devices | `dashboard/services.py` guard path `manual_repair_no_devices` | Visible only after a failed manual repair attempt | Medium | User detail |
| Manual repair cannot start because user has no active access | `dashboard/services.py` guard path `manual_repair_no_access` | Visible only after a failed manual repair attempt | Medium | User detail |
| Region change requires recreate | `bot/handlers/devices.py`, `032` hardening path | Visible only in bot-side user flow and message | Medium | Future user detail/access note |
| User has active access but zero provisioned devices | entitlement layer + `vpn_clients` absence | Not explicitly surfaced as an alert yet | Medium | User detail + future user-level attention bucket |

## System-level signals

| Signal | Source | Current visibility | Severity | Suggested UI placement |
|---|---|---|---|---|
| Service not active | `dashboard/services.py` -> `overview_metrics()` from `get_service_statuses()` | Visible in overview alerts and services screen | High | Overview alerts rail + services page |
| Server in maintenance | `dashboard/services.py` -> server snapshot status | Visible in overview alerts and servers screen | Medium | Overview alerts rail + servers page |
| Disk usage >= 85% on managed node | `dashboard/services.py` -> server snapshots | Visible in overview alerts and servers screen | High | Overview alerts rail + servers page |
| CPU usage >= 85% on managed node | `dashboard/services.py` -> server snapshots | Visible in overview alerts and servers screen | High | Overview alerts rail + servers page |
| New support tickets | support counts from `support_bot.storage` / dashboard support payload | Visible in overview alerts and support screen | Medium | Overview alerts rail + support summary |
| Open manual payment queue | payment review breakdown in `dashboard/services.py` | Visible in overview alerts and payments screen | Medium | Overview alerts rail + payments summary |
| Off-host backup not confirmed for production hosts | ops verification docs | Visible only in documentation | High | Future ops/admin alerts surface |
| Provider snapshots absent or inactive | ops verification docs | Visible only in documentation | High | Future ops/admin alerts surface |
| Backup posture still local-first | backup plan + verification docs | Visible only in documentation and operator memory | High | Future ops/admin alerts surface |
| Restore readiness only partially proven | restore-readiness docs + local drill docs | Visible only in documentation | Medium | Future ops/admin alerts surface |
| VPN node / panel drift outside explicit repair flow | split control-plane/data-plane model, `3x-ui` reality, `vpn_clients` metadata drift risk | Partially visible through user repair paths, not collected into one UI layer | High | Future overview + servers/alerts surface |

## Current visibility gaps

The current system already has useful attention signals, but they are split across several places:

### 1. Some signals are visible only in one narrow screen

Examples:

- `vpn_repair_needed`
- repair history
- support queue details

This means the admin often has to open the exact user or exact section first.

### 2. Some signals exist only as derived operator knowledge

Examples:

- repeated repair failures
- active entitlement with no devices
- backup still being local-first

These are real conditions, but they are not yet summarized into a shared attention layer.

### 3. Some signals live only in documentation

Examples:

- off-host backup gap
- provider snapshot gap
- partial restore-readiness

These are important operational truths, but they are not currently visible inside `panel UI`.

### 4. The overview alerts rail is real, but still incomplete

The current overview already surfaces:

- service inactivity
- server overload / maintenance
- new support tickets
- manual payment queue

But it does not yet include:

- user-level VPN repair risk
- repeated repair failures
- backup/restore attention signals

## Proposed first UI buckets

If a future unified attention surface is built, the smallest sensible first buckets are:

- `needs repair`
- `payments issues`
- `support backlog`
- `infrastructure`
- `backup / restore`

## Minimal UI placement model

This is not a UI implementation plan yet.
It is only the first placement model.

### 1. User detail

Best for:

- repair-needed
- repair history
- user-specific access drift

Already partially implemented.

### 2. Overview attention rail

Best for:

- small count of high-value current problems
- items that should be noticed without opening user detail first

Best first candidates for extension:

- users with `vpn_repair_needed`
- users with repeated failed repair attempts
- manual payment queue
- support backlog

### 3. Infrastructure / ops surface

Best for:

- backup posture gaps
- restore-readiness gaps
- server/node degradation
- provider snapshot absence

This likely belongs either in:

- the overview operational rail
- or a later dedicated ops/alerts surface

## Recommended next implementation candidates

### 039 — Overview attention rail for user-level repair issues

Goal:

- surface a small count/list of users that currently need repair attention

Best first signals:

- `vpn_repair_needed`
- repeated failed repair attempts

### 040 — Minimal system ops alerts surface

Goal:

- surface already confirmed system-level operational gaps without building a full monitoring stack

Best first signals:

- local-only backup posture
- missing provider snapshot protection
- restore drill not yet fully production-proven

## Practical summary

The system already has a real but fragmented attention layer.

Right now:

- user-level repair signals are the most mature and actionable
- overview alerts already exist for support/payments/services/servers
- ops safety gaps are well documented but not yet surfaced in admin UI

So the next correct move is not to invent more signals.
The next correct move is to decide which existing signals deserve first-class placement in `panel UI`.
