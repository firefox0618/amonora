# TASK 160 — Smart trial funnel on existing bot/backend contour

## Status
Completed

## Goal
Add a smarter conversion funnel for trial users without introducing a second onboarding system or moving logic into `n8n`.

## Why
The product already had:
- one-trial protection;
- channel-membership-gated trial activation;
- pause/resume of active trial on unsubscribe/resubscribe;
- a shared `amonora-access-reminders` worker and DB-driven trigger engine.

What was missing was the conversion layer on top:
- persisted trial segmentation;
- a reliable definition of “technical engagement”;
- timed segment-aware follow-ups during the active trial window;
- a CTA that can send the user straight into `📱 Устройства` instead of only tariffs/support.

## Scope
- add persisted `users.trial_activity_level` and `users.trial_engaged_at`;
- keep `/start`-based trial activation unchanged;
- add a `bot/db` helper that upgrades a live trial from `low` to `active` on the first technical step;
- mark technical engagement from successful device creation and successful key/QR/routing delivery flows;
- extend trigger matching with `trial_hours_since_start` and `trial_hours_before_expiry`;
- add new built-in trial funnel trigger rules (`2h`, `24h`, `final 6h`);
- disable the older `trial_ends_1d` and `trial_ends_today` default rules to avoid duplicate trial chains;
- add `open_devices` as a campaign CTA handled by `@amonora_bot`;
- update docs and tests.

## Acceptance criteria
- a newly activated trial starts as `low` with no `trial_engaged_at`;
- first technical engagement upgrades the trial to `active` and stores the first engagement timestamp once;
- ordinary menu activity still only updates `last_activity_at`;
- paused trial users do not receive smart-funnel trigger messages while unsubscribed;
- after resubscribe, the same trial continues from the original `trial_started_at / trial_expires_at` without restarting the funnel from scratch;
- funnel messages can lead the user directly to `📱 Устройства`;
- targeted tests cover helper logic, trigger matching, CTA routing, and legacy-rule disable defaults.
