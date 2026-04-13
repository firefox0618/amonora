# TASK 113 — Bot Main Surface Redesign

## Summary

Apply the `Дизайн.txt` redesign to the main user-facing surfaces of `@amonora_bot` without refactoring payment, access, support-routing, or VPN provisioning logic.

## Scope

- redesign the main menu and home inline keyboard
- redesign `Личный кабинет`
- redesign `Устройства`
- redesign `Купить`
- redesign `Поддержка`
- introduce a fuller in-bot `📚 Информация` hub
- keep `Реферальная система` behavior, but align its entrypoints with the new shell

## Constraints

- no DB schema changes
- no payment-flow or provisioning semantics changes
- no support-bot routing changes
- keep old text aliases where needed for compatibility with already open chats/keyboards

## Acceptance criteria

- `@amonora_bot` main menu uses `Информация` instead of `Канал`
- home screen shows the denser cabinet layout from the approved design
- devices screen shows compact device summaries above inline buttons
- tariff screen uses the new compact style
- support screen uses the new short support intro
- info hub contains `Инструкции`, `FAQ`, and `Документы`
- targeted bot surface tests cover the new labels and texts
