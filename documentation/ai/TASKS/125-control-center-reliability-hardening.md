# TASK 125 — Control center reliability hardening

## Status
Completed

## Goal
Close the highest-risk reliability gaps found during the forensic audit of `Amonora Control`, while keeping the active production flows stable for real users.

## Why
- several operator actions still reported success even when sync or node-side state finished only partially;
- payment, support, repair, settings, and node-health surfaces still had false-green or unsafe edge paths;
- `amonora_control_tz_v5.md` expects the active control center to reflect real backend/bot/node state, not optimistic UI assumptions.

## Scope
- harden payment state transitions and delete guards against unsafe downgrade/delete paths;
- surface partial sync failure from user access mutations instead of pretending full success;
- reduce silent key/device drift for VLESS and Trojan clients when `inbound_id` is missing;
- make deep repair fail truthfully when post-repair sync still breaks;
- tighten support transfer and support close/reply truthfulness;
- make settings/service/env flows reflect what actually happened;
- expose missing `roles / notifications / integrations` settings slices in the active UI;
- relabel synthetic traffic activity so the panel stops presenting it as pure live traffic;
- add regression tests for the new guards.

## Out of scope
- production deploy;
- broad architecture rewrite;
- mass data migration;
- replacing the existing `dashboard` backend seam.

## Constraints
- no destructive refactor of active user/payment/support flows;
- keep changes small and reversible;
- keep audit visibility on sensitive actions;
- avoid UI claims that the backend cannot guarantee.

## Acceptance criteria
- user access mutations (`trial / extend / clear access / block`) can surface partial sync failure;
- deep repair does not end in false success if post-sync still fails;
- missing `inbound_id` no longer silently skips VLESS/Trojan cleanup or expiry sync;
- manual payment status/delete flows block unsafe confirmed-payment mutation and release held balance on terminal transitions;
- support transfer rejects unknown admins;
- support close/reply UI no longer implies guaranteed Telegram delivery when that cannot be proven;
- settings UI includes the read surfaces for `roles / notifications / integrations`;
- traffic UI clearly distinguishes operational activity from live node throughput;
- regression tests cover the new guards.

## Validation
- `./venv/bin/python -m compileall dashboard bot support_bot control_bot`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_fixes tests.test_dashboard_vpn_repair tests.test_payment_finalization tests.test_confirm_external_payment_record tests.test_dashboard_api_v2_settings_contract tests.test_dashboard_api_v2_role_access tests.test_dashboard_api_v2_support_contract`
- `dashboard/ui` TypeScript `tsc --noEmit`
- `git diff --check`
