# Support Backlog and Repair Workload Map

## Overview

This document maps where support load currently comes from, especially around:
- access and VPN issues
- manual payment confirmation
- repair-needed states
- visibility gaps that still force operators to dig manually

The goal is not to redesign support, but to identify:
- the main support issue families
- what is already visible in the product/admin surfaces
- what still depends on operator memory
- which next small hardening steps would reduce workload fastest

## Main sources of support workload

## 1. Payment and confirmation issues

Typical cases:
- user has created a manual payment request but has not submitted proof yet
- user says they paid, but record is still `awaiting_admin_review`
- support/admin must manually confirm or reject
- user asks where access is after a payment was just confirmed

Primary sources:
- `dashboard.models.PaymentRecord`
- `bot/db.py`
- `bot/manual_payments.py`
- `support_bot/router.py`
- `dashboard/services.py`

Current visibility:
- manual payment queue in support bot
- manual payment queue pressure in overview system status
- payments surfaces in dashboard / `dashboard/ui`

Current support cost:
- queue review is still human-driven
- payment issue often turns into access triage after confirmation

## 2. Access active, but VPN state still needs repair

Typical cases:
- user entitlement is active
- VPN sync soft-failed
- user reports “paid but does not work”
- admin/support must inspect user detail and attempt repair

Primary sources:
- `bot/payment_flow.py`
- `bot/db.py` (`vpn_repair_needed`)
- `dashboard/services.py`
- `dashboard/ui` user detail and overview attention

Current visibility:
- user detail shows `vpn_repair_needed`
- manual repair history is shown
- overview attention rail surfaces repair-related users

Current support cost:
- support still needs to connect payment confirmation with access-repair state
- repeated repair failures still require manual investigation

## 3. Access/device mismatch after payment or repair

Typical cases:
- user has active access, but no devices
- user expects access to work immediately after payment
- admin repairs VPN state, but the real issue is missing/incorrect device state

Primary sources:
- access lifecycle around `PaymentRecord` and entitlement
- device/client state in bot/dashboard seams
- manual repair guard paths already added in `dashboard/services.py`

Current visibility:
- partly visible through repair guard behavior
- partly visible in user detail context
- not yet surfaced as a first-class attention signal everywhere

Current support cost:
- operators still need to inspect multiple surfaces to understand whether the problem is payment, entitlement, or device provisioning

## 4. Generic support ticket backlog

Typical cases:
- user asks for help without a clear technical category
- ticket may hide payment, access, device, or onboarding issue
- admin must classify manually by reading the thread

Primary sources:
- `support_bot/storage.py`
- support ticket/admin card flows in `support_bot/router.py`

Current visibility:
- ticket counts are visible
- support screen exists
- overview now surfaces support backlog count

Current support cost:
- ticket category is not explicit
- overlap with payment/access issues still requires human interpretation

## Current issue families

### A. Payment-origin issues

Examples:
- waiting for user payment proof
- waiting for admin confirmation
- rejected manual payment and follow-up questions

Current visibility:
- fairly visible in payment queue and support bot

Remaining gap:
- queue items do not clearly separate “waiting on customer” from “operator needs to act now” at a higher triage level

### B. Access/VPN-origin issues

Examples:
- `vpn_repair_needed`
- repeated failed repair attempts
- active entitlement but broken VPN state

Current visibility:
- good inside user detail
- partly visible on overview

Remaining gap:
- support workload still depends on someone connecting those signals back to the user’s ticket/payment story

### C. Visibility-gap issues

Examples:
- user complains “nothing works”, but the real issue is no devices
- ticket looks like payment issue, but access is already active and only repair is needed
- ticket looks like support issue, but really belongs in payment review queue

Current visibility:
- mostly not explicit as categories

Remaining gap:
- operator still acts as the correlation engine between payment, entitlement, device, and support state

## Where support load is already visible

Visible in product/admin surfaces:
- open support tickets
- manual payment queue pressure
- `vpn_repair_needed`
- repair history
- overview attention for repair-related users
- overview system status for support backlog and pending confirmations

Visible only after opening deeper context:
- exact repair failure history for a user
- whether a given ticket is really payment-side or access-side
- whether active access lacks working devices

Visible mostly through operator knowledge:
- which ticket categories consume the most time
- which “payment” issues are actually post-confirmation access issues
- which “support” issues are really waiting-for-user rather than waiting-for-admin

## Root-cause families

### Family 1: manual queue friction

The system still depends on:
- human review
- manual queue navigation
- cross-surface context switching

This produces:
- payment delays
- follow-up support messages
- duplicated operator attention

### Family 2: post-payment access drift

The system now exposes drift better than before, but the workload still exists:
- payment confirmed
- entitlement active
- VPN/device state still needs inspection or repair

This produces:
- “I paid but cannot use it” tickets
- repeated repair attempts
- extra operator hops between payments and user detail

### Family 3: missing explicit triage hints

Many support cases still require a person to infer:
- is this payment queue work?
- is this access repair work?
- is this onboarding/device setup work?

This produces:
- slower first response
- more context switching
- higher cognitive load on support/admin

## Highest-leverage next narrow tasks

### Candidate 1

`044a — active access without devices attention signal`

Why:
- this is a recurring hidden support cause between payment confirmation and actual working access
- it fits naturally into existing attention surfaces

Expected effect:
- reduce time spent debugging “paid but not working” cases

### Candidate 2

`044b — triage category hints across payment/support/access surfaces`

Why:
- support and payment work still overlap heavily
- even a minimal label/hint layer would reduce manual digging

Expected effect:
- faster classification of tickets and queues
- less operator-memory dependence

## What this map confirms

- support load does not come only from “support tickets”; it also comes from payment review and access repair seams
- the system now exposes several critical signals, but category-level triage is still partial
- the next highest-value improvements are narrow correlation/visibility steps, not a broad support-system rewrite
