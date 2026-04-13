Date: 2026-03-23
Server: Core / backend (`46.21.81.186`)
Component: Dashboard / control-center UI / settings audit seams
Change:
- tightened the control-center layout: smaller radius, denser cards, ash-gray matte glass light/dark themes, compact auth screens, slimmer sticky topbar, and list-style sidebar without descriptive sublabels
- removed the global topbar search and reduced overview vertical stretch by collapsing the hero layer and compacting the command rail
- moved user and payment detail flows to overlay panels instead of persistent side rails
- added the traffic baseline reset action and owner-side admin role update API seam for control-center settings
- corrected audit isolation by caching audit payloads per admin instead of a shared cache key
Reason:
- the active operator shell was too airy and visually noisy for everyday production work
- users, payments, audit, roles, and traffic needed denser operator ergonomics without changing the existing product/runtime flows
Risk: medium
Checks:
- local TypeScript check via direct `tsc --noEmit`
- `./venv/bin/python -m compileall dashboard`
- `./venv/bin/python -m unittest tests.test_dashboard_api_v2_audit_contract tests.test_dashboard_api_v2_settings_contract tests.test_dashboard_api_v2_role_access -v`
- `./venv/bin/python -m unittest tests.test_dashboard_acr_second_pass -v`
- `git diff --check`
- production rollout:
  - pre-change backup:
    - `/opt/amonora_bot_backup/control-center-ui-density-20260323-013652`
  - synced deploy bundle into `/opt/amonora_bot`
  - `cd /opt/amonora_bot && venv/bin/python -m py_compile dashboard/main.py dashboard/services.py dashboard/v2_data.py`
  - `cd /opt/amonora_bot/dashboard/ui && npm run build`
  - `systemctl restart amonora-dashboard.service amonora-dashboard-ui.service`
  - `systemctl is-active amonora-dashboard.service amonora-dashboard-ui.service nginx` -> `active active active`
  - `http://127.0.0.1:3001/login` -> `200`
  - `http://127.0.0.1:8088/dashboard/api/v2/overview` without session -> `401`
  - `journalctl -u amonora-dashboard.service -n 20 --no-pager` -> clean restart, uvicorn startup visible
  - `journalctl -u amonora-dashboard-ui.service -n 20 --no-pager` -> clean restart, Next.js ready visible
Rollback:
- restore previous dashboard backend files and `dashboard/ui` sources from the pre-change backup on the core host
- rebuild `dashboard/ui` on the core host
- restart `amonora-dashboard.service` and `amonora-dashboard-ui.service`
- if rollout shows broader regressions, revert the pushed commit and resync the restored files to `/opt/amonora_bot`
Status: OK
