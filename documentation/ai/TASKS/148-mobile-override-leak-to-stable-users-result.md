# TASK 148 — Mobile override leak to stable users result

Дата: 31 марта 2026

## Что сделано

- в `bot/handlers/devices.py` env mobile override ограничен только веткой `mode = mobile`;
- обычные `mobile_happ` устройства в `stable / reserve` теперь снова получают live per-device payload через provisioner;
- добавлен regression test в `tests/test_mobile_mode_override.py`;
- продовый cleanup должен пересобрать metadata у уже созданных Germany/DK `mobile_happ` устройств, если у них `mode != mobile`, чтобы убрать shared override-link.

## Ожидаемый результат

- admin-only experimental `Мобильный` режим сохраняет свой shared override-link;
- обычные Germany/DK mobile users не зависят от fixed env link и используют свой реальный ключ ноды.
