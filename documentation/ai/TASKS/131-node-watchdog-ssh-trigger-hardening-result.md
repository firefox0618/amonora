# TASK 131 — node watchdog SSH trigger hardening result

## What changed

- `ops/server_watchdog.py` now treats `SSH monitoring gap + healthy VPN runtime` as a non-paging blind spot instead of a full node outage;
- added regression coverage in `tests/test_server_watchdog.py`;
- documented the core-host SSH allowlist dependency in `documentation/RUNBOOK.md`.

## Production checks

- Germany node now allows `22/tcp` from core host `46.21.81.186`, and live snapshots again show `host_status=ok`, `ssh_status=active`, and real CPU/RAM/disk values;
- Estonia still returns `Connection refused` from the core host even after the same allowlist rule, so it remains a transport-level monitoring gap rather than a bot/runtime bug.

## Validation

- `venv/bin/python -m unittest tests.test_server_watchdog tests.test_control_error_triggers tests.test_access_reminders tests.test_access_reminders_triggers tests.test_control_queries`
- `venv/bin/python -m py_compile ops/server_watchdog.py tests/test_server_watchdog.py`
