# TASK 152 — Support UI multiline formatting result

## Status
Completed

## What changed
- support history in `dashboard/ui` now preserves line breaks via multiline rendering instead of collapsing message text into one paragraph;
- the operator reply composer on the support screen now uses a multiline textarea, so `Enter` inserts a new line while drafting;
- UI kit gained a shared `Textarea` component for this control-center flow.

## Files changed
- `dashboard/ui/src/app/(dashboard)/support/page.tsx`
- `dashboard/ui/src/components/ui.tsx`
- `documentation/FEATURES.md`
- `documentation/ai/STATE.md`
- `documentation/ai/TASKS/152-support-ui-multiline-formatting.md`

## Validation
- `npm run build` in `dashboard/ui` on the production host
- smoke check against `http://127.0.0.1:3001/support`
- manual support-screen verification after deploy

## Notes
- this is a frontend-only change; support API contracts and reply delivery semantics are unchanged.
