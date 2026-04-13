# TASK 119 — Bot Referral Surface Placeholder

## Status
Completed

## Goal
Temporarily disable the user-facing referral screen in the main bot and replace it with a placeholder message.

## Why
The current request is to remove the active referral-system UI from the bot without touching the underlying referral/balance mechanics in payments and backend logic.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/PUBLIC_SURFACES.md`
- `documentation/ai/STATE.md`
- `bot/handlers/referrals.py`
- `bot/handlers/start.py`
- `bot/utils/texts.py`
- `tests/test_referral_ui.py`
- `tests/test_bot_copy_updates.py`

## Current behavior
The main bot opened a full referral screen with invite link, stats, and share button from both the main menu and the home inline shell.

## Desired behavior
When the user opens `Реферальная система`, the bot should show a short `пока в разработке` placeholder instead of the active referral UI.

## Scope
Included:
- main-menu referral entrypoint
- home inline referral entrypoint
- user-facing text
- regression tests
- feature/public-surface/state docs

## Out of scope
Not included:
- removing referral bonus logic from payments
- removing referral data from backend or database
- changing balance behavior in `Личном кабинете`

## Constraints
Important limitations:
- keep the button label in the bot shell unchanged
- keep backend referral balance and payment behavior intact
- make the smallest reversible change

## Risks
Potential regressions or sensitive areas:
- user-facing copy/tests can drift if one entrypoint is updated and the other is not
- disabling the screen must not affect payment-side referral bonuses

## Acceptance criteria
Concrete conditions for completion:
- opening `🎁 Реферальная система` shows a placeholder text
- `home:referrals` callback shows the same placeholder text
- referral stats/share UI is no longer exposed from the main bot shell
- targeted tests pass

## Validation
Tests and manual checks required:
- `./venv/bin/python -m unittest -q tests.test_referral_ui tests.test_bot_copy_updates`
- manual bot check after deploy: open `🎁 Реферальная система` from menu and home shell

## Deliverables
- code changes
- docs updates
- short implementation summary
