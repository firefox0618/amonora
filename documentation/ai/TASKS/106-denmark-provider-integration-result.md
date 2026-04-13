# TASK 106 — Denmark Provider Integration Result

## Result
Completed as a controlled product-integration pass.

Denmark is no longer just an ops/runtime node. The codebase now has a provider-aware VLESS provisioning seam that supports:

- `de` / `ee` through the existing `XUIClient` path;
- `dk` through a standalone `XrayCoreProvisioner`.

## What changed
- added `bot/vpn_provisioning.py` with:
  - `VPNProvisioner`
  - `XUIProvisioner`
  - `XrayCoreProvisioner`
  - provider factory helpers
- region metadata now distinguishes:
  - `provider_type`
  - `user_selectable`
  - `admin_visible`
  - `reserve_only`
- bot VLESS create/config/delete flows now resolve a provisioner instead of directly assuming `XUIClient`;
- post-payment VLESS sync now resolves a provisioner instead of directly assuming `XUIClient`;
- dashboard VLESS create/delete/sync flows now resolve a provisioner instead of directly assuming `XUIClient`;
- Denmark-specific runtime config was added to `.env.example`;
- dashboard server/watchdog surfaces now distinguish standalone Denmark `Xray` runtime from `3x-ui`-backed regions.

## Product behavior after this task
- Germany stays the default live user region;
- Estonia is hidden from normal user-facing selection and remains reserve/testing;
- Denmark stays hidden from broad user-facing selection;
- Denmark can be enabled for a narrow test cohort through:
  - `ENABLE_DK_TEST_FLOW`
  - `DK_TEST_TELEGRAM_IDS`
- dashboard/admin flows can work with Denmark explicitly;
- VLESS Denmark device metadata is now stored as a normalized `xray_core`-backed shape instead of panel-only fields.

## Important runtime assumptions
- core host must have SSH access to Denmark using the dashboard metrics key;
- Denmark runtime metadata lives on the Denmark host in:
  - `/usr/local/etc/xray/amonora_dk_meta.json`
- Denmark Xray config lives in:
  - `/usr/local/etc/xray/config.json`
- core host env must provide the `XRAY_CORE_DK_*` variables introduced in `.env.example`.

## Validation
- local Python regression set passed:
  - `tests.test_denmark_vpn_provisioning`
  - `tests.test_device_region_change_guard`
  - `tests.test_payment_finalization`
  - `tests.test_dashboard_vpn_repair`
  - `tests.test_dashboard_api_v2_contract`
- `python3 -m compileall bot dashboard ops tests` passed;
- `git diff --check` passed.

## Limitation
This task intentionally does not make Denmark a general-availability user region.

The rollout remains controlled:

- Germany is still primary;
- Estonia is still reserve/testing;
- Denmark is available through the new provider seam, but should be exposed to broader user traffic only after controlled cohort validation and backup/status discipline are fully confirmed.
