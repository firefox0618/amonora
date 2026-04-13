# TASK 051 — Backup restore status visibility in dashboard Result

## Result
Added a minimal restore-readiness signal to dashboard overview.

## What is shown
- `last_restore_validation_at`
- `restore_validation_stale`
- `status`
- `stale_definition_days`
- `signal_source`

## Signal source
The first pass uses existing local documentation artifacts from completed restore tasks, not runtime monitoring.

## Freshness rule
- fresh: latest validation artifact is within 30 days
- stale: latest validation artifact is older than 30 days
- unknown: no validation artifact found

## Not covered
- automatic restore execution
- restore scheduling
- production restore
- external monitoring
