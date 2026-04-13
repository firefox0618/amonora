# REPAIR_REASON_MAP

## Purpose

This document defines the canonical set of payment/access/VPN repair reasons used by the system.

Goal:
- keep repair markers understandable
- keep overview grouping stable
- avoid uncontrolled growth of overlapping strings

## Canonical reasons

### Payment-related

- `post_payment_sync_failed`
- `post_payment_access_incomplete`

### Manual-repair-related

- `manual_repair_sync_failed`
- `manual_repair_no_access`
- `manual_repair_no_devices`

## Event-only reasons

These are used for repair event history, not for the persistent `vpn_repair_needed` marker:

- `manual_repair`
- `auto_repair_success`
- `auto_repair_failed`

`manual_repair` is an event-source marker, not a failure reason. It may appear in stored rows, but dashboard payloads normalize it into:
- `source = manual`
- `outcome = success`
- `reason = null`

## Legacy aliases still recognized

The UI and grouping layer still normalize old stored values:

- `manual_repair_failed` -> `manual_repair_sync_failed`
- `manual_repair_failed_no_access` -> `manual_repair_no_access`
- `manual_repair_failed_no_devices` -> `manual_repair_no_devices`

## Category model

- `post_payment_*` -> payment-related
- `manual_repair_*` -> manual-repair-related
- `auto_repair_*` -> repair event history only

## Event semantics

Repair history now separates three concepts:

- `source`
  - `post_payment`
  - `manual`
  - `auto`
- `outcome`
  - `success`
  - `failed`
  - `skipped`
- `reason`
  - only present when there is a meaningful failure/skip reason

Examples:
- successful manual repair:
  - `source = manual`
  - `outcome = success`
  - `reason = null`
- manual repair with no devices:
  - `source = manual`
  - `outcome = skipped`
  - `reason = manual_repair_no_devices`
- post-payment sync failure:
  - `source = post_payment`
  - `outcome = failed`
  - `reason = post_payment_sync_failed`

## Human-readable labels

Dashboard payloads now expose both:
- canonical reason code
- human-readable label

Current labels:
- `post_payment_sync_failed` -> `Post-payment VPN sync failed`
- `post_payment_access_incomplete` -> `Post-payment access incomplete`
- `manual_repair_sync_failed` -> `Manual repair sync failed`
- `manual_repair_no_access` -> `Manual repair skipped: no active access`
- `manual_repair_no_devices` -> `Manual repair skipped: no devices`
- `auto_repair_success` -> `Auto-retry recovered the VPN sync`
- `auto_repair_failed` -> `Auto-retry failed to recover the VPN sync`

## Notes

- this is a naming normalization layer, not a behavior redesign
- historical rows do not require a DB migration for first pass
- new writes should prefer canonical names only
