# TASK 146 — Node alert stability tuning result

Дата: 31 марта 2026

## Что сделано

- `ops/control_error_triggers.py` больше не открывает node incident по обычной `warning`-деградации, если runtime не `critical` и общий health не `critical`.
- `ops/server_watchdog.py` теперь:
  - игнорирует legacy runtime-service noise для `EE`;
  - подтверждает `degraded` только после `3` подряд наблюдений;
  - оставляет `down` и `overloaded` на более быстром подтверждении;
  - не грузит БД лишним поиском affected users до фактического открытия incident.
- `ops/systemd/amonora-server-watchdog.timer` переведён с `1 мин` на `2 мин`.
- `dashboard/services.py` и `dashboard/main.py` получили более длинные read-cache TTL для server/overview путей.

## Ожидаемый эффект

- Уйдут короткие `warning`-алерты уровня `Нода деградирует`, если это был единичный transient spike.
- На core-host уменьшится постоянная служебная нагрузка от node polling.
- Реальные `down` и `critical` состояния останутся видимыми в control flow.

## Validation

- `./venv/bin/python -m py_compile ops/control_error_triggers.py ops/server_watchdog.py dashboard/services.py dashboard/main.py tests/test_control_error_triggers.py tests/test_server_watchdog.py`
- `./venv/bin/python -m unittest tests.test_control_error_triggers tests.test_server_watchdog`
