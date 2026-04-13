# TASK 120 — Bot Country-Then-Mode UX

## Status
Completed

## Goal
Rebuild the main bot device-connection UX so the user chooses country first and then a Russian-language connection mode with an explicit `Автовыбор`.

## Why
The previous flow exposed the mode step before country selection, used English mode labels, and did not provide the requested recommended auto-selection UX.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/PUBLIC_SURFACES.md`
- `documentation/ai/STATE.md`
- `bot/handlers/devices.py`
- `bot/handlers/protocol.py`
- `bot/keyboards/devices.py`
- `bot/keyboards/protocols.py`
- `bot/utils/modes.py`
- `bot/utils/texts.py`
- `tests/test_bot_modes.py`
- `tests/test_bot_copy_updates.py`

## Current behavior
The bot exposed device-mode selection before country selection in the new-device flow, and the user-facing mode layer still used English labels `NOVA / CORE / ORIGIN`.

## Desired behavior
The user should first choose a country, then choose a Russian-language mode `Автовыбор / Нова / Ядро / Основа`, with mini-descriptions and `Автовыбор` as the only recommended default.

## Scope
Included:
- new-device country-then-mode flow
- existing-device `Страна и режим` flow updated to start from country
- user-facing mode labels/descriptions
- auto-mode resolution on top of current provisioning
- targeted tests and state/feature docs

## Out of scope
Not included:
- broad provisioning refactors
- removing legacy callback compatibility
- changing runtime paths or deployment assumptions

## Constraints
Important limitations:
- preserve current internal `vless` / `trojan` provisioning seams
- do not expose transport terminology to users
- keep stale inline callbacks backward-compatible where practical
- make the smallest reversible change

## Risks
Potential regressions or sensitive areas:
- stale inline keyboards in existing chats can still send old callback payloads
- existing-device mode change remains constrained by current reprovisioning limitations
- auto-mode must not silently reroute old devices to incompatible provisioning paths

## Acceptance criteria
Concrete conditions for completion:
- new device creation goes `ОС -> страна -> режим -> provisioning`
- the mode layer exposes `⭐️ Автовыбор`, `✨ Нова`, `🛡 Ядро`, `⚙️ Основа`
- mode descriptions are visible in the bot messages
- `Автовыбор` is the default/recommended mode and resolves to a vless-based internal path
- targeted tests pass

## Validation
Tests and manual checks required:
- `venv/bin/python -m unittest tests.test_bot_modes tests.test_bot_copy_updates`
- manual bot check:
  - create device: name -> OS -> country -> mode
  - existing device: `Страна и режим` opens country first
  - home/device cards show Russian mode labels

## Deliverables
- code changes
- docs updates
- short implementation summary
