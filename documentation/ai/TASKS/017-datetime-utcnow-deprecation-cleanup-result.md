# TASK 017 — datetime.utcnow() deprecation cleanup result

## Status
Completed

## What changed
- `dashboard/security.py`
  - `utcnow()` now uses `datetime.now(timezone.utc).replace(tzinfo=None)` instead of deprecated `datetime.utcnow()`

## Why this shape was chosen
- the time source is now timezone-aware
- the returned value still preserves the current naive-UTC behavior expected by surrounding auth/session and SQLAlchemy code
- this keeps the patch narrowly scoped and avoids behavior drift

## Validation
- reran:
  - `./venv/bin/python -m unittest -q tests.test_dashboard_auth_session`
  - `./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_contract`
  - `./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_users_contract`
  - `./venv/bin/python -m unittest -q tests.test_dashboard_api_v2_support_contract`

## Result
- auth/API smoke tests still pass
- the previous deprecation warning no longer comes from `dashboard/security.py`
