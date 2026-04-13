# TASK 140 — control bot channel post buttons

## Status
Completed

## Goal
Allow the internal control bot to attach or replace inline URL buttons on an already published Telegram channel post.

## Why
The team needs a fast operational path for public channel posts without hand-editing messages or creating a separate posting console.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `control_bot/router.py`
- `control_bot/queries.py`
- `control_bot/channel_posts.py`

## Current behavior
Control bot supports operational screens, broadcasts, and trigger messages, but it does not have a flow for taking an existing forwarded channel post and adding buttons to it.

## Desired behavior
An owner/admin can forward a channel post into `@amonora_control_bot`, then send button definitions in a simple text format and have the bot update the original channel post keyboard in place.

## Scope
Included in this task:
- forwarded channel-post target detection
- parsing URL buttons from text
- owner/admin-gated control-bot flow for applying or clearing buttons
- focused unit tests
- feature/state documentation updates

## Out of scope
- editing post text/media
- multi-step callback buttons for channel readers
- a separate dashboard UI for channel-post editing

## Constraints
Important limitations:
- preserve current control-bot command and menu behavior
- do not change runtime env or deployment assumptions
- keep the new flow limited to internal owner/admin roles
- use only inline URL buttons in this pass

## Risks
- Telegram will reject edits if the bot is not a channel admin or lacks `can_edit_messages`
- forwarded messages without channel origin metadata cannot be mapped back to the original post
- malformed button input must not crash the control-bot FSM flow

## Acceptance criteria
- forwarding a channel post to control bot opens a button-edit flow
- button lines in the format `Text | URL` produce an inline keyboard on the original post
- `очистить` removes the existing keyboard from the selected post
- non-channel forwards and invalid button syntax return clear operator-facing errors
- focused tests cover origin extraction and button parsing

## Validation
- `./venv/bin/python -m unittest tests.test_control_channel_posts tests.test_control_router tests.test_control_queries`
- manual control-bot check:
  - forward a real channel post
  - apply one or more URL buttons
  - verify bot-side error when channel edit rights are missing

## Deliverables
- control-bot channel-post button workflow
- test coverage for helpers
- updated feature/state docs
