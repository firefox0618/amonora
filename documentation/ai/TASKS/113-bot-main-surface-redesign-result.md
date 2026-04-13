# RESULT 113 — Bot Main Surface Redesign

## Done

- redesigned the main menu and home inline keyboard around `Личный кабинет`, `Устройства`, `Купить`, `Поддержка`, `Информация`, and `Реферальная система`
- removed `Канал` from the main menu while keeping legacy aliases working
- rebuilt `Личный кабинет` copy with dense status/type/balance/device fields
- rebuilt `Устройства` overview so the text block now shows compact per-device summaries above the buttons
- rebuilt `Купить` copy and tariff button labels in the new visual style
- rebuilt the support intro screen
- added a real in-bot `📚 Информация` hub with `Инструкции`, `FAQ`, and `Документы`
- updated docs and AI state tracking for the new bot shell

## Validation

- targeted tests:
  - `tests.test_bot_copy_updates`
  - `tests.test_referral_ui`
  - `tests.test_bot_devices_ui`
- syntax check:
  - `python3 -m compileall bot documentation`
- diff hygiene:
  - `git diff --check`

## Notes

- the redesign intentionally does not change payment orchestration, support routing, device provisioning, or DB schema
- per-device runtime health is still not modeled; the devices list keeps a presentation-level `🟢 Активно` state on the active access screen
