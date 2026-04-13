# TASK 131 — node watchdog SSH trigger hardening

## Context

Production started sending repeated `node_offline` alerts even when Germany/Estonia still had a healthy VPN control plane (`3x-ui` responding). The alert source was `ops/server_watchdog.py`, which treated any `ssh_status=error` as a full outage.

Live inspection also showed that Germany and Estonia both keep `ufw limit 22/tcp`, so the core host `46.21.81.186` can lose SSH-based live metrics even while VPN runtime remains healthy.

## Scope

- make watchdog stop paging on pure SSH-monitoring gaps when runtime is healthy;
- keep real runtime failures and real host/SSH failures visible as incidents;
- add focused regression tests;
- restore node-side SSH monitoring access where safely possible without opening `22/tcp` broadly.

## Constraints

- do not break existing control bot / watchdog flow;
- do not hide real VPN runtime failures;
- do not open SSH publicly beyond the core host allowlist;
- keep changes small and reversible.

## Acceptance Criteria

- `ops/server_watchdog.py` does not classify `host/ssh error + healthy runtime` as `down`;
- Germany no longer produces a false `node_offline` because of SSH throttling;
- tests cover monitoring-gap and `xray_core` cases;
- docs mention the core-host SSH allowlist dependency for node monitoring.

## Validation

- `venv/bin/python -m unittest tests.test_server_watchdog tests.test_control_error_triggers tests.test_access_reminders tests.test_access_reminders_triggers tests.test_control_queries`
- production snapshots on the core host show Germany with live SSH metrics and without a monitoring-gap message
