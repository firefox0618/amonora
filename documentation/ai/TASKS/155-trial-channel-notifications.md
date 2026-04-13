# TASK 155 — Trial channel pause/resume notifications

## Status
Completed

## Goal
Make trial channel-enforcement user-visible by sending a clear Telegram explanation whenever a trial is paused or resumed because of channel membership.

## Why
Task `154` enforced the rule correctly, but users whose trial was paused after unsubscribing could lose access without an explicit explanation unless they re-opened `/start`. The system now needs proactive messaging so:
- users understand why access disappeared;
- operators do not get avoidable support noise from “VPN stopped working” reports;
- already-paused users can receive a one-time backfill notice without resetting or reissuing trial.

## Scope
- add dedicated pause/resume notification text for channel-enforced trial;
- extend `ops/access_reminders.py` so it sends a one-time pause notice when trial is paused and a one-time resume notice when trial is restored;
- add a notice-specific dedupe state so already-paused users can receive a backfilled explanation without repeating the revoke action;
- cover the new behavior with regression tests and update state/docs.

## Acceptance criteria
- newly paused trial users receive one explanation message with subscribe/open-bot actions;
- newly resumed trial users receive one explanation message that the remaining trial is restored;
- already-paused users with no prior notice receive one backfill message on the next worker run;
- the worker does not spam repeat notices for the same pause/resume marker.
