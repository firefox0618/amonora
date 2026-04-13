# TASK 159 — Paid device-slot add-ons

## Context

`@amonora_bot` historically enforced a hard user-facing limit of `3` devices for ordinary users, while operator surfaces and trigger audiences also assumed a static `x/3` model.

The product now needs a safe v1 add-on path for selling extra device capacity without changing the semantics of the access subscription itself.

## Scope

- add a persistent entitlement model for paid extra device slots;
- calculate effective per-user device limit as `3 + active add-on slots` for normal users and `10` for complimentary admins/support-admins;
- add a user flow in `@amonora_bot` to buy `+1 устройство` for `49 ₽` until the end of the current paid period;
- reuse existing RUB payment seams (`Platega`, manual SBP/crypto, internal balance-only payment when possible) without routing the add-on through subscription finalization;
- expose dynamic max-device data and add-on-aware labels in `dashboard/ui` and `Amonora Control`;
- expire stale add-on entitlements in the shared 5-minute worker without auto-deleting existing VPN devices.

## Constraints

- add-ons are available only to active paid users;
- trial/inactive/blocked users cannot buy them;
- ordinary users may reach at most `8` effective devices (`3 + 5`);
- add-on lifetime is pinned to the paid subscription period that existed at purchase time and must not automatically extend on future renewals;
- existing devices must remain untouched if an add-on expires and the user is now above the downgraded limit.

## Acceptance criteria

- confirmed add-on payments create `DeviceSlotEntitlement` rows and do not modify `subscription_expires_at`;
- device creation and limit-reached UX use the real dynamic limit;
- `dashboard/ui` and `control_bot` stop showing stale `x/3` assumptions for relevant user/payment/support contexts;
- expired add-ons are marked `expired` by the existing worker and no longer count toward the effective limit;
- regression coverage exists for add-on payment finalization, dynamic device-limit calculation, payment label serialization, and control/dashboard display paths.
