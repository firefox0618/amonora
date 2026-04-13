# PAYMENT SUPPORT ACCESS TRIAGE MAP

Date: 2026-03-20
Status: current-state mapping
Scope: manual intervention hotspots across payment, support, and access flows

## Purpose

This document maps the current places where the live system still depends on manual triage, operator judgment, or support intervention around:

- payment confirmation
- support workload
- access activation after payment
- repair / recovery paths

The goal is not to redesign the whole payment/support architecture.
The goal is to answer one practical question:

> where does the system still consume manual operator time before money reliably turns into working access?

## How to read this map

Each triage hotspot is described through:

- `Case`
- `Primary source`
- `Why manual work appears`
- `Current visibility`
- `Current operator path`
- `Potential next hardening/automation value`

## Main triage hotspots

| Case | Primary source | Why manual work appears | Current visibility | Current operator path | Potential next hardening/automation value |
|---|---|---|---|---|---|
| Manual payment awaiting admin review | `PaymentRecord.payment_status = awaiting_admin_review`, `bot/db.py`, `support_bot`, `dashboard/services.py` | access must not activate until a human confirms the payment | visible in payments queue, overview system status, support/admin flow | support/admin confirms or rejects manually | high |
| Manual payment awaiting user payment | `PaymentRecord.payment_status = awaiting_user_payment` | requests remain open until user sends proof/payment details | visible in payments status, partly in support flow | operator waits, reminds, or later closes/rejects | medium |
| External payment confirmation guarded by idempotency seam | `confirm_external_payment_record`, `finalize_subscription_payment` | duplicate/late webhook or confirmation path can still require human understanding | mostly backend-safe, not really an operator queue item | usually resolved by code path, but debugging remains manual | medium |
| Payment confirmed, but VPN sync failed | `bot/payment_flow.py` -> `sync_failed`, `vpn_repair_needed` | entitlement becomes active but panel/device state may still drift | visible in user detail, overview attention, repair history | admin opens user detail and triggers `Repair VPN` | high |
| User has active access but no devices | entitlement state + empty `vpn_clients` | payment/trial succeeded, but actual provisioning was never completed | not strongly surfaced yet; only implicit or discovered during repair | support/admin explains or guides device creation manually | high |
| Manual repair fails repeatedly | `vpn_repair_events` | repeated sync attempts still fail and require deeper inspection | visible in user detail history and overview attention | admin retries, then manually investigates user/device/node state | high |
| Support backlog / unanswered tickets | `support_bot.storage`, support counts | queue pressure means more user issues stay unresolved longer | visible in support screen, overview alerts, overview system status | support/admin opens queue and processes manually | high |
| Access confusion after country/device expectations mismatch | `bot/handlers/devices.py`, user device metadata, real node state | user expectation and real provisioned state can diverge or be misunderstood | partly reduced by `032`, but still mostly handled in direct support/user messaging | user retries or support explains recreate flow | medium |
| Manual queue across payments + support overlap | support bot + dashboard payments queue | support team absorbs part of payment operations workload | split between payments screen and support queue | human context-switching between support and payment review | high |

## Current visibility by area

### 1. Payment queue visibility

Current visibility is already decent:

- payment statuses exist in `PaymentRecord`
- manual review items are visible in dashboard payments
- overview already surfaces manual payment queue pressure

What is still missing:

- a tighter operator map of which queue items most often convert into support load
- a clearer distinction between “waiting for user” and “waiting for admin” as operator effort categories

### 2. Support visibility

Current visibility is also real:

- support queue exists
- support counts are visible
- support history exists
- tickets/messages live in PostgreSQL

What is still missing:

- direct mapping between support backlog and payment/access failure categories
- quick visibility into which tickets are access-related versus payment-related versus generic support

### 3. Access/repair visibility

This area is now much stronger than before:

- `vpn_repair_needed` exists
- repair history exists
- `Repair VPN` action exists
- overview attention already surfaces repair-related user issues

What is still missing:

- an explicit surfaced case for “active entitlement but no devices”
- a clearer operator view of repeated repair failures as a queue-like work item

## Operator-knowledge hotspots

The following still depend too much on operator memory or cross-screen reasoning:

### 1. Which payment/support cases are really access cases

A support ticket may actually be:

- a payment confirmation wait
- a post-payment access sync problem
- a device provisioning problem

The system does not yet classify these into one triage-oriented operator view.

### 2. Which repair attempts are turning into repeated manual work

The raw history now exists, but repeated failure is still only a derived pattern.
There is no separate queue or summarized operator bucket for “these users are consuming repeated repair effort”.

### 3. Which paid users still need operator action before they really have working service

The most important hidden friction remains:

- revenue can become confirmed
- entitlement can become active
- but working VPN may still need manual attention

This is much better surfaced than before, but still not reduced into one compact triage list.

## Highest-value next automation / hardening candidates

### Candidate 1 — Surface `active access but no devices` as a first-class attention signal

Why it matters:

- this is a direct revenue-to-service friction point
- it is operationally important
- it likely generates avoidable support load

Why it is a good next task:

- narrow
- derivable from existing data
- useful both in user detail and overview attention

Expected value:

- reduce support guesswork
- help operators notice “paid but not actually provisioned” cases faster

### Candidate 2 — Add a triage-oriented support/payment/access category hint

Minimal form:

- not full NLP/classification
- just a small derived tag or summary bucket for:
  - payment queue
  - repair-needed access
  - support backlog overlap

Why it matters:

- the manual burden is not only volume, but context switching
- one operator currently has to infer category by reading across flows

Expected value:

- lower support/admin mental load
- better prioritization without building a full workflow engine

## Recommended next tasks

### 043 — Active access without devices attention signal

Goal:

- surface users who currently have active entitlement but zero provisioned devices

Why first:

- narrow
- high user value
- high revenue-to-service value
- already derivable from existing models

### 044 — Triage category hints for payment/support/access overlap

Goal:

- add a lightweight categorization layer for the most common manual cases

Why second:

- useful, but broader than `043`
- should come after the direct access-friction signal is surfaced

## Practical summary

The current system already handles many risky cases better than before:

- payment idempotency has a protected seam
- repair-needed state is persisted and visible
- repair history exists
- overview attention exists

But manual operator load still concentrates in one place:

- the boundary where payment, support, and real working access do not line up automatically

So the next best hardening step is not a giant workflow redesign.
It is to surface the next most expensive manual triage case with the smallest possible new signal.
