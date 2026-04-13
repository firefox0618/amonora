# 133 — bot mode layer simplification

## Context

The main `@amonora_bot` had already moved to a country-first connection flow, but the user-facing mode layer still exposed older labels `Автовыбор / Нова / Ядро / Основа`, while the team decided to simplify the product language to:

- `Стабильный`
- `Мобильный`
- `Резерв`

At the same time, the dedicated mobile-route is not yet ready for normal users, so the product needs a safe placeholder for public UX while preserving an admin-only experimental path for live testing.

## Scope

- replace the public mode labels in the bot UX
- keep backward compatibility for older mode values already stored in user/device metadata
- preserve country-first creation flow
- keep `Мобильный` visible but non-provisioning for regular users
- keep `Мобильный` as a real admin-only experimental route
- update documentation and regression tests

## Constraints

- do not break existing devices that still carry old mode values in metadata
- do not expose transport/protocol jargon in public bot copy
- do not remove Denmark `Xray core` reserve-profile seam; reuse it for experimental/fallback behavior where appropriate
- keep device-country migration rules unchanged

## Acceptance criteria

- device creation shows `Германия / Дания` first, then `Стабильный / Мобильный / Резерв`
- regular users who tap `Мобильный` get an honest placeholder instead of a broken device create attempt
- admins can still create/test `Мобильный`
- old `auto / nova / core / origin / white` metadata still render as valid modern labels
- device card emphasizes mode instead of showing the country as a primary card field
- tests cover label rendering, legacy normalization, admin-vs-user mobile behavior, and Denmark profile mapping

## Validation

- `py_compile` on changed Python files
- bot unit tests around modes/copy/devices
- manual smoke:
  - create device in Germany with `Стабильный`
  - tap `Мобильный` as regular user and confirm placeholder
  - create/test `Мобильный` as admin
  - reopen an existing old device and confirm its mode still renders cleanly
