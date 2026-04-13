# VPN ACCESS FLOW MAP

Date: 2026-03-19
Status: current-state flow map
Scope: confirmed code-path map with explicit drift points

## Purpose

This document maps the real VPN access lifecycle across:
- payment state
- entitlement/subscription state
- VPN client / `3x-ui` state

The goal is not to describe the ideal architecture.
The goal is to describe the working system as it exists now, identify where state can diverge, and highlight the smallest high-value hardening steps.

## State layers

The current access system is split across three distinct state layers.

### 1. Payment state

Primary source:
- `dashboard.models.PaymentRecord`

Main transitions:
- `pending`
- `awaiting_user_payment`
- `awaiting_admin_review`
- `confirmed`
- `rejected`
- `expired`
- `cancelled`

Main code paths:
- `bot/db.py`:
  - `create_external_payment_record`
  - `create_manual_payment_record`
  - `confirm_external_payment_record`
  - `review_manual_payment_record`

Important rule:
- payment confirmation is not the same thing as access
- payment state is the guard that prevents duplicate finalization for external payments

### 2. Entitlement / subscription state

Primary source:
- `backend.core.models.User`

Main fields:
- `trial_used`
- `trial_started_at`
- `trial_expires_at`
- `subscription_started_at`
- `subscription_expires_at`
- `subscription_status`
- `subscription_source`
- `is_blocked`

Main code paths:
- `bot/db.py`:
  - `activate_trial`
  - `activate_paid_subscription`
  - `get_access_expires_at`
- `dashboard/services.py`:
  - `grant_trial_to_user`
  - `extend_subscription_for_user`
  - `set_user_block_state`
  - `remove_user_tariff`

Access interpretation helpers:
- `bot/utils/access.py`

Important rule:
- entitlement is not the same thing as VPN panel state
- a user may have valid entitlement even if panel sync is stale or partially failed

### 3. VPN / device / node state

Primary sources:
- PostgreSQL `vpn_clients`
- actual remote `3x-ui` panel state on VPN nodes

Main local representation:
- `backend.core.models.VpnClient`
- `VpnClient.client_data` metadata:
  - `country_code`
  - `country_name`
  - `inbound_id`
  - protocol-specific delivery/config fields

Main code paths:
- `bot/handlers/devices.py`
- `bot/vpn_api.py`
- `dashboard/services.py`

Important rule:
- `vpn_clients` metadata is not the same thing as confirmed panel reality
- panel state can drift away from DB metadata and entitlement

## Canonical transition points

### 1. User enters the product

Confirmed path:
- `bot/handlers/start.py`
  - `get_or_create_user`
  - if user has active access -> show active state
  - if user has no trial and passes channel check -> `activate_trial`
  - otherwise user is routed toward tariffs/payment

Confirmed behavior:
- trial is granted directly in bot flow
- admin/support users may receive complimentary access through `get_or_create_user` sync logic in `bot/db.py`

Current implication:
- entitlement can exist before any VPN device exists
- access is not equal to “VPN provisioned”

### 2. Device provisioning turns entitlement into VPN state

Confirmed path:
- `bot/handlers/devices.py`
  - user selects protocol + region
  - handler checks `get_access_expires_at`
  - if no access -> provisioning blocked
  - if access exists -> `XUIClient.provision_*`
  - on panel success -> `create_vpn_client`
  - then metadata is enriched through `update_vpn_client_metadata`

Protocols covered:
- `vless`
- `trojan`

Important detail:
- provisioning is the moment where entitlement becomes actual node/client state
- before provisioning, a paid/trial user may still have zero working devices

### 3. Paid activation extends entitlement

Canonical orchestration seam:
- `bot/payment_flow.py`
  - `finalize_subscription_payment`

Confirmed sequence:
1. tariff lookup
2. `activate_paid_subscription`
3. `get_access_expires_at`
4. `sync_user_vpn_access`

Confirmed entry points:
- `landing/main.py` crypto webhook path
- `bot/handlers/tariffs.py` Telegram Stars path
- `bot/manual_payments.py` manual payment confirmation path

Important detail:
- `finalize_subscription_payment` itself is not idempotent
- duplicate protection lives one layer above it in payment confirmation logic

### 4. Payment confirmation gates repeated finalization

External payments:
- `bot/db.py` -> `confirm_external_payment_record`

Manual payments:
- `bot/db.py` -> `review_manual_payment_record`

Confirmed behavior:
- first confirm marks record confirmed
- duplicate external confirm returns `just_confirmed = False`
- manual confirm does not reconfirm an already confirmed record

Current implication:
- payment layer is the guard against duplicate entitlement extension
- the entitlement/finalization layer assumes that guard already worked

### 5. Entitlement changes try to sync existing VPN clients

Payment-driven sync path:
- `bot/payment_flow.py` -> `sync_user_vpn_access`

Admin-driven sync path:
- `dashboard/services.py` -> `sync_user_clients_access`

Both paths:
- load current entitlement expiry
- load user devices from PostgreSQL
- try to login to the appropriate `3x-ui` panel
- update protocol-specific expiry/enable state

Important detail:
- this is duplicated logic in two different modules
- behavior is similar, but not clearly centralized as one contract

### 6. Expiry and “no access” messaging are entitlement-driven

Confirmed path:
- `ops/access_reminders.py`

It classifies:
- `trial_active`
- `paid_active`
- `vip_active`
- `expired`
- `inactive`
- `blocked`

Important detail:
- reminders are based on entitlement state in PostgreSQL
- they do not verify whether VPN panel/device state is actually in sync

### 7. Manual repair and operator intervention paths exist

Confirmed manual/admin touchpoints:
- `dashboard/services.py`
  - `grant_trial_to_user`
  - `extend_subscription_for_user`
  - `set_user_block_state`
  - `remove_user_tariff`
  - `create_device_for_user`
  - `delete_device_for_user`
  - `delete_user_with_access`
- `bot/manual_payments.py`
  - `confirm_manual_payment`
  - `reject_manual_payment`
- `ops/vpn_regions.py`
  - `reconcile_vpn_clients`

Current implication:
- support/admin team already functions as part of the consistency system
- some drift is recoverable, but not all repair steps are surfaced as one canonical operational flow

## Drift and failure points

Below are the main confirmed drift points, ordered by practical risk/value.

### 1. Metadata-only device country change

Confirmed path:
- `bot/handlers/devices.py` -> `device_country_change_callback`

Current behavior:
- updates `VpnClient` metadata with new `country_code`
- does not reprovision the client on the target node
- does not remove and recreate the panel client

Why this matters:
- UI/DB may say the device moved regions
- real panel-side client may still live on the old node
- support may see confusing “wrong country / wrong panel / wrong inbound” symptoms

Confidence:
- high

### 2. Payment success can leave entitlement active while VPN sync soft-fails

Confirmed path:
- `bot/payment_flow.py`

Current behavior:
- `activate_paid_subscription` succeeds first
- `sync_user_vpn_access` may fail softly
- result still returns success with `sync_failed = True`

Why this matters:
- money can become entitlement without becoming working VPN state immediately
- support load shifts to manual repair
- users may receive success messaging plus a warning instead of fully working access

Confidence:
- high

### 3. Admin access mutations use a second sync implementation

Confirmed paths:
- payment flow sync in `bot/payment_flow.py`
- admin sync in `dashboard/services.py`

Why this matters:
- two similar access-sync paths can drift in behavior over time
- fixes may be applied in one place and missed in the other

Confidence:
- high

### 4. `activate_paid_subscription` ignores `tariff_code` and `payment_id`

Confirmed path:
- `bot/db.py` -> `activate_paid_subscription`

Current behavior:
- `tariff_code` and `payment_id` are accepted
- then explicitly discarded

Why this matters:
- entitlement extension is not tightly bound to a durable payment-to-subscription trace at this layer
- later investigation of access drift relies more heavily on `PaymentRecord` than on entitlement mutation history

Confidence:
- high

### 5. Reminder/visibility layer can look healthy while VPN state is stale

Confirmed path:
- `ops/access_reminders.py`

Current behavior:
- reminders rely on entitlement state only
- they do not cross-check live `vpn_clients` usability or recent sync status

Why this matters:
- user messaging and admin visibility can lag behind real device-level brokenness

Confidence:
- medium

## Support and manual recovery touchpoints

Confirmed operator surfaces:
- manual payment confirmation/rejection
- dashboard trial grant / extension / block / tariff removal
- dashboard device create/delete
- region metadata reconciliation through `ops/vpn_regions.py`

Likely operator pain zones inferred from code shape:
- “payment succeeded but access not working yet”
- “device says one region, but panel/client reality differs”
- “expired/blocked/unblocked state did not fully propagate to all devices”

Inference note:
- the exact support workload split is not fully instrumented in code
- but the presence of multiple manual repair hooks strongly suggests that operator intervention already absorbs part of drift cost

## Highest-value small hardening tasks

### Candidate 1 — Block or redesign metadata-only region change

Why it is high-value:
- very narrow surface
- directly removes a confirmed drift path
- likely reduces confusing support cases fast

Minimal safe version:
- disable `device_country_change_callback` when the selected country differs from the current actual device region
- replace it with explicit messaging:
  - “region move requires device recreation”

Better later version:
- implement explicit reprovision flow instead of metadata mutation

Recommended task shape:
- small UI/backend guard only
- no broad VPN refactor

### Candidate 2 — Persist VPN sync failures as repair-needed state

Why it is high-value:
- closes the gap between entitlement success and actual access propagation
- helps support/admin see drift instead of relying on logs and warning texts

Minimal safe version:
- on payment/admin sync failure, write a durable flag/event for the affected user/device
- expose this state in dashboard or a narrow admin query path

Better later version:
- add a retry/repair queue

Recommended task shape:
- first only record and surface the failure
- do not automate retries in the same task

## Recommended next step

Best next implementation step:
- Candidate 1 — block metadata-only device region change

Why this should go first:
- it fixes a confirmed hard drift path
- it is narrower than sync-failure persistence
- it has lower operational ambiguity

Second best next step:
- Candidate 2 — persist and surface VPN sync failures after payment/admin access changes

## Summary

The current VPN access system works through a layered model:
- payment confirmation
- entitlement mutation
- VPN device provisioning / sync

The system is functional, but not fully closed against drift.

The two most important confirmed realities are:
- payment-to-entitlement success does not guarantee immediate VPN sync success
- device region change currently allows metadata drift without real reprovisioning

This means the right hardening strategy is not a broad rewrite.
It is a sequence of small tasks that remove specific drift paths one by one.
