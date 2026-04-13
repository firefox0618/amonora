# TASK 154 — Trial channel membership enforcement

## Status
Completed

## Goal
Make trial access depend on staying subscribed to the project channel for the full trial window, not only at initial activation.

## Why
The existing flow checked channel subscription only when trial was first activated. After that, users could unsubscribe and continue using the full trial. The required rule is stricter:
- to get trial, the user must subscribe;
- to keep trial active, the user must remain subscribed until trial ends;
- if the user unsubscribes mid-trial, access must be revoked immediately;
- if the user later returns before the original `trial_expires_at`, the same trial resumes only with the remaining time, without issuing a brand-new trial.

## Scope
- add persisted user-state for paused trial due to channel unsubscribe;
- update access helpers so paused trial is no longer treated as active access;
- update `/start` flow so paused-trial users see the right message and can resume the remaining trial after returning to the channel;
- extend `ops/access_reminders.py` to enforce channel membership for active trial users and run revoke/resume sync automatically;
- add regression tests for access guards, start flow, and worker behavior.

## Acceptance criteria
- unsubscribed active-trial users lose active trial access without resetting `trial_used`;
- resubscribed users do not receive a new trial, but can continue the original one if it is still within the original expiry window;
- background worker revokes VPN access on unsubscribe and restores it on resubscribe;
- automated tests cover the new behavior.
