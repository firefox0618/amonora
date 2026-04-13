# Manual Payments Flow Map

## Overview

This document maps the real manual payment lifecycle as it exists today across the bot, support bot, dashboard, and payment/access activation seams.

It focuses on:
- how manual payments are created
- how they move through review states
- where operator review happens
- where payment confirmation turns into access activation
- where ambiguity, delays, and repeated operator work still happen

This is a current-state map, not a future redesign.

## Primary entities and states

Primary entity:
- `dashboard.models.PaymentRecord`

Primary manual statuses:
- `awaiting_user_payment`
- `awaiting_admin_review`
- `confirmed`
- `rejected`
- `cancelled`
- `expired`

Primary actors:
- user in Telegram bot
- support/admin reviewer in `support_bot`
- admin reviewer in `dashboard` / `dashboard/ui`
- payment/access orchestration in `bot.manual_payments` and `bot.payment_flow`

## Canonical lifecycle

### 1. Manual payment request is created

Creation paths:
- `bot/handlers/tariffs.py`
- `dashboard/services.py` (`create_payment_record`)

Creation persistence:
- `bot/db.py` -> `create_manual_payment_record(...)`

Initial state:
- `payment_status = awaiting_user_payment`

What is stored immediately:
- `user_id`
- `tariff_code`
- `payment_method`
- `amount`
- `currency`
- `duration_days`
- `external_payment_id` in synthetic `manual_*` format
- optional metadata like tariff title / telegram id / source

Important detail:
- `create_manual_payment_record(...)` reuses an existing open manual record for the same `user + tariff + payment_method` instead of creating duplicates.

### 2. User submits proof / marks payment as sent

Bot user flow:
- `bot/handlers/tariffs.py` -> `manual_payment_submitted_callback`

State transition:
- `bot/db.py` -> `mark_manual_payment_record_submitted(...)`
- `awaiting_user_payment` -> `awaiting_admin_review`

Side effect:
- `bot.manual_payments.notify_support_admins_about_manual_payment(...)`

What changes here:
- optional `reference`
- optional `note`
- merged metadata
- queue becomes visible to support/admin reviewers

### 3. Manual payment enters operator review queue

Current review surfaces:
- `support_bot/router.py` payment panel
- `dashboard` / `dashboard/ui` payment-related admin flows via `dashboard/services.py`

Current visibility:
- support bot shows:
  - count waiting for admin review
  - count still waiting for user payment
- overview system status already shows manual payment queue pressure
- payments surfaces can inspect specific records

### 4. Reviewer confirms or rejects

Shared review boundary:
- `bot/db.py` -> `review_manual_payment_record(...)`

Support-bot confirm/reject:
- `bot/manual_payments.py`
  - `confirm_manual_payment(...)`
  - `reject_manual_payment(...)`
- triggered from `support_bot/router.py`

Dashboard confirm/reject:
- `dashboard/services.py`
  - `confirm_payment_record(...)`
  - `reject_payment_record(...)`

Review side effects captured:
- `reviewed_by_actor_id`
- `reviewed_by_actor_name`
- `reviewed_at`
- `confirmed_at` or `rejection_reason`

Important safety seam:
- repeated confirm/reject of already-processed records is guarded by status checks in `review_manual_payment_record(...)`

### 5. Confirmation becomes access activation

When a manual payment is confirmed, the manual record itself is not the end of the flow.

Activation path:
- `bot/manual_payments.py` -> `confirm_manual_payment(...)`
- then `bot/payment_flow.py` -> `finalize_subscription_payment(...)`

What this does:
- activates or extends entitlement
- computes/returns new access expiry
- attempts VPN sync
- may set `vpn_repair_needed` if sync soft-fails

So the real chain is:
- `manual review` -> `PaymentRecord confirmed` -> `finalize_subscription_payment(...)` -> `entitlement active` -> `VPN sync attempted`

### 6. Post-confirmation follow-up

After successful manual confirmation path:
- user is notified
- referral bonus notification may run
- finance sync may run for confirmed payment
- overview/payments metrics update through existing cache invalidation paths

If VPN sync fails:
- access may already be active
- `vpn_repair_needed` becomes the visible repair seam
- admin later resolves through user detail / `Repair VPN`

## Operator touchpoints

### User-side operator-adjacent touchpoints

User can:
- create manual payment request
- submit it for review
- re-open status screen
- cancel still-open request

These happen in:
- `bot/handlers/tariffs.py`

### Support reviewer touchpoints

Support/admin can:
- open manual payments queue
- inspect individual record
- confirm payment
- reject payment

These happen in:
- `support_bot/router.py`
- `bot/manual_payments.py`

### Dashboard/admin touchpoints

Admin can:
- create payment record from dashboard
- mark it as waiting for review
- confirm it
- reject it

These happen in:
- `dashboard/services.py`
- dashboard payment surfaces / APIs

## Real friction and ambiguity points

### 1. One flow spans three surfaces

The same manual payment can cross:
- Telegram bot
- support bot
- dashboard

This is workable, but it increases context switching and operator-memory dependence.

### 2. `awaiting_user_payment` and `awaiting_admin_review` both stay open

These are both counted as open manual payments.

That means the queue mixes:
- cases where user still has not really submitted payment proof
- cases where operator must review and decide now

This creates triage noise.

### 3. Confirmation and access activation are separate steps

A reviewer may think “payment is done”, but the real service path still continues into:
- entitlement activation
- expiry computation
- VPN sync

So manual payment friction is not only payment-review friction.

### 4. Payment confirmed does not guarantee working access immediately

After confirmation, the system can still land in:
- `vpn_repair_needed`
- repeated failed repair attempts

This means some “payment” work actually becomes “access repair” work.

### 5. Support queue and payment queue overlap operationally

A user who asks support about access may in fact be waiting on:
- manual payment confirmation
- access activation after confirmation
- VPN repair after activation

This overlap still requires manual digging across multiple surfaces.

### 6. Dashboard-created manual records can bypass the user-origin context

`dashboard/services.py` can create manual payments directly by raw `user_id`.

This is useful operationally, but it keeps a human-error seam:
- wrong user selection
- unclear provenance
- record exists without the same user-side context as Telegram-origin requests

## Current visibility

Clearly visible already:
- manual queue pressure on overview
- reviewable payments in payments surfaces
- support-bot payment panel
- confirmed/rejected status on record level
- downstream access-repair signals through `vpn_repair_needed`

Still not well unified:
- why an item is still open
- whether the bottleneck is user-side, reviewer-side, or post-confirmation access-side
- which manual payments are likely to become support load next

## Best next narrow hardening tasks

### Candidate 1

`043a — split manual payment attention between waiting-for-user and waiting-for-review`

Why:
- the current open queue mixes two different types of work
- this is a small visibility improvement, not a billing redesign

Minimal outcome:
- clearer queue labels and counts
- less operator triage friction

### Candidate 2

`043b — active access without devices attention signal`

Why:
- manual payment pain often continues after confirmation
- the next expensive operator step is frequently access/device mismatch, not payment review itself

Minimal outcome:
- clearer bridge between payment confirmation and support/access follow-up

## What this map confirms

- manual payments are not a single isolated queue; they are a cross-surface workflow
- the hard boundary is `PaymentRecord`, but the operator experience extends beyond it
- confirmation safety is better than before, but triage clarity is still only partial
- the most useful next steps are narrow visibility and triage improvements, not a large rewrite
