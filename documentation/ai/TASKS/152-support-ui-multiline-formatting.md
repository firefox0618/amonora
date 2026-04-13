# TASK 152 — Support UI multiline formatting

## Status
Completed

## Goal
Make support messages in `dashboard/ui` preserve user-entered line breaks and let operators compose multiline replies naturally.

## Why
Support replies look correctly formatted in Telegram but collapsed into a single paragraph in the panel, which makes moderation text and long instructions hard to read. The operator reply field also needs multiline drafting.

## Context
Relevant docs and code areas:
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `dashboard/ui/src/app/(dashboard)/support/page.tsx`
- `dashboard/ui/src/components/ui.tsx`

## Current behavior
- support history bubbles collapse `\n` into a single visual paragraph on the website;
- the reply control is a one-line `Input`, so `Enter` cannot be used to move to the next line while composing a reply.

## Desired behavior
- support history in the panel should render with visible line breaks;
- the reply field should be a multiline textarea;
- `Enter` in the reply field should insert a new line.

## Scope
- add a shared textarea component to the UI kit;
- switch support reply from single-line input to multiline textarea;
- preserve line breaks in support history rendering;
- update docs/state.

## Out of scope
- keyboard shortcuts like `Ctrl+Enter` to send;
- broader redesign of the support screen layout.

## Constraints
- keep the current support API contract unchanged;
- preserve existing support send/assign/close actions;
- avoid unrelated UI refactors.

## Risks
- minimal front-end only change; main risk is layout drift in the support composer row on smaller screens.

## Acceptance criteria
- multiline support messages in history render as multiline in `dashboard/ui`;
- operator reply field supports multiline input with `Enter`;
- `dashboard/ui` builds successfully after the change.

## Validation
- `npm run build` in `dashboard/ui`
- manual check of the support screen after deploy

## Deliverables
- updated support message rendering
- new multiline reply composer
- docs/state update
