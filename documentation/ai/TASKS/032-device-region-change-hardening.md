# TASK 032 — Device region change hardening

## Status
Completed

## Goal
Eliminate the confirmed metadata-only region drift path in the device flow by preventing silent country changes that do not reprovision the real VPN client.

## Why
The VPN access flow map identified a concrete high-confidence inconsistency path:
- `bot/handlers/devices.py` currently allows device country change through metadata mutation
- this updates PostgreSQL-side device metadata
- but does not reprovision the real client on another VPN node

That means UI/database state can diverge from actual `3x-ui` panel state.

This is a narrow and high-value hardening target because it:
- removes a real drift source
- reduces support confusion
- does not require redesigning the full VPN architecture

## Context
Relevant docs:
- `documentation/VPN_ACCESS_FLOW_MAP.md`
- `documentation/DOMAIN.md`
- `documentation/FEATURES.md`
- `documentation/RUNBOOK.md`
- `documentation/ai/STATE.md`

Relevant code areas:
- `bot/handlers/devices.py`
- device location / country change callbacks
- any related device settings text helpers or keyboards if messaging must change

## Current behavior
Current device country change flow:
- opens the region picker for an existing device
- writes a new region snapshot into `VpnClient.client_data`
- returns success text

Current behavior does not:
- delete the old panel client
- reprovision a new client on the target node
- prove that the actual VPN device moved

## Desired behavior
The product should no longer silently present a device as moved to another region when only metadata changed.

For the first hardening pass, the safest acceptable behavior is:
- block actual cross-region change for existing devices
- tell the user to recreate the device instead

## Scope
- identify the existing region-change callback for already created devices
- block region change when selected country differs from the device’s current region
- keep same-region selection safe
- return explicit user-facing guidance:
  - recreate the device for region move
- add/update focused tests if a stable seam is practical

## Out of scope
- full reprovision/migrate-device flow
- automatic deletion/recreation on another node
- changing provisioning architecture
- broad device UX redesign
- changing trial/payment logic

## Constraints
- prefer the smallest behavior-safe change
- do not silently mutate region metadata into a fake “successful move”
- do not widen into a large VPN refactor
- preserve existing same-region behavior where practical

## Risks
- existing UX may imply that region change should work
- message text may need to be clear enough to avoid user confusion
- a too-broad fix could break adjacent device settings flows

## Acceptance criteria
- metadata-only cross-region device change is no longer allowed
- user receives explicit “recreate device” guidance
- same-region behavior remains safe
- no production-infrastructure assumptions are changed

## Validation
Manual checks:
- verify the callback no longer writes misleading region metadata for cross-region moves
- verify user-facing message is explicit
- verify device settings flow still works for adjacent actions

## Deliverables
- narrow code change for region-change guard
- short task result note
- updated state if completed
