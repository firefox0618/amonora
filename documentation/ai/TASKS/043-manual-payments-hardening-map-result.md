# TASK 043 RESULT — Manual payments hardening map

## Outcome

A canonical current-state manual payments map now exists:
- `documentation/MANUAL_PAYMENTS_FLOW_MAP.md`

## What it captures

- creation of manual payment requests from bot and dashboard paths
- transition from `awaiting_user_payment` to `awaiting_admin_review`
- support-bot and dashboard review touchpoints
- confirm/reject boundary through `review_manual_payment_record(...)`
- access activation handoff through `confirm_manual_payment(...)` -> `finalize_subscription_payment(...)`
- post-confirmation drift into `vpn_repair_needed`

## Main friction points identified

1. One manual-payment lifecycle spans bot, support bot, and dashboard.
2. Open queue mixes `awaiting_user_payment` with `awaiting_admin_review`.
3. Payment confirmation and working access are still separate seams.
4. Some payment load becomes access-repair load after confirmation.
5. Dashboard-created manual records keep a small human-error/provenance seam.

## Highest-value next narrow tasks

- split manual-payment attention between “waiting for user” and “waiting for review”
- surface `active access without devices` as an explicit attention signal

## Runtime impact

None. This was a read-only mapping pass.
