# System Surface Audit — 2026-03-25

## Scope

Audit target:

- `@amonora_bot`
- `@amonora_support_bot`
- `@amonora_control_bot`
- `landing`
- `dashboard` / `dashboard/ui`

Method:

- static code audit of handlers, routes, keyboards, and pages
- comparison with current known product/runtime caveats already fixed or documented in the repo

Status labels:

- `works` — there is a clear working seam in code
- `placeholder` — the surface exists intentionally, but does not complete the full scenario
- `questionable` — code seam exists, but runtime/external dependency can break the scenario
- `broken` — known current issue or dead-end scenario

## Known global caveats

1. `Platega` auto-`СБП` is still runtime-dependent on external webhook delivery through the public edge. The code seam exists, but the production incident with `Cloudflare` / webhook blocking is not fully eliminated in code alone.
2. `СБП` manual fallback is live and should be treated as the safe path when auto-`СБП` does not confirm.
3. Device IP surfaces in admin views depend on `3x-ui clientIps`; when the node returns `No IP Record`, UI falls back to metadata and cannot guarantee a fresh real IP.
4. Public `Мобильный` mode in the main bot is intentionally a placeholder for regular users. Admins keep an experimental live path.
5. Some admin/server actions are operationally real, but depend on backend host reachability and node runtime state.

## 1. `@amonora_bot`

| Surface / button / scenario | File / handler | Status | Why |
|---|---|---|---|
| `/start` new user onboarding | `bot/handlers/start.py` -> `start_handler`, `_handle_start_flow` | works | Creates/loads user, binds referral token, activates trial after channel check, or sends paywall/access state. |
| `✅ Подписался` after channel join | `bot/handlers/start.py` -> `trial_subscription_confirmed_callback` | works | Re-checks subscription and activates trial without forcing a second `/start`. |
| `👤 Личный кабинет` / `/menu` | `bot/handlers/start.py` -> `menu_handler`, `_restore_main_menu`, `_send_home` | works | Restores persistent reply keyboard and then renders the cabinet screen. |
| `📱 Устройства` from home | `bot/handlers/start.py` -> `home_devices_callback`; `bot/handlers/devices.py` -> `_show_devices_list` | works | Loads devices and create-device path behind active access checks. |
| Create device flow `name -> OS -> country -> mode` | `bot/handlers/devices.py` -> `add_device_callback`, `device_name_input`, `device_os_callback`, `device_create_country_callback`, `_create_device_from_selection` | works | Main create flow is complete and provisions through `x-ui` or `xray_core`. |
| Device mode button `🔌 Режим` | `bot/keyboards/devices.py`, `bot/handlers/devices.py` -> `device_location_callback`, `device_reprotocol_callback` | questionable | Works for viewing/reselecting mode, but changing to a different effective mode on an existing device is blocked and asks for recreation. |
| `📱 Мобильный` mode for regular users | `bot/utils/modes.py`, `bot/handlers/devices.py`, `bot/handlers/protocol.py` | placeholder | Deliberately shows an honest “in preparation” message instead of provisioning. |
| `📱 Мобильный` mode for admins | `bot/utils/modes.py`, `bot/vpn_provisioning.py` | works | Admins can use the experimental path; on Denmark it maps to reserve-profile. |
| `🛡 Стабильный` / `🧰 Резерв` modes | `bot/utils/modes.py` | works | Public mode layer is wired to real protocol/profile choices. |
| `🔑 Получить ключ` / `📷 QR` / `📘 Инструкция` | `bot/handlers/devices.py` -> `device_config_callback`, `device_qr_callback`, `device_guide_callback` | works | Clear delivery seam for keys, QR, and instructions. |
| `🧭 Маршруты РФ` | `bot/handlers/devices.py` -> `device_routing_callback` | works | Split-routing pack is generated and delivered from a dedicated handler. |
| `💳 Купить` / tariff list | `bot/handlers/tariffs.py` -> `tariffs_handler`, `buy_tariff_callback` | works | Tariff chooser and breakdown screen are wired. |
| `⭐ Telegram Stars` payment | `bot/handlers/tariffs.py` -> invoice flow | works | Native Telegram invoice path is fully wired. |
| Auto `💳 СБП` tariff payment | `bot/handlers/tariffs.py` -> `_show_platega_payment` | questionable | Code seam exists, but production confirmation depends on external webhook delivery that is known to be fragile until edge rules are fixed. |
| `💳 СБП (ручная)` | `bot/handlers/tariffs.py` -> `_show_manual_payment`, manual callbacks | works | Manual reserve flow is fully wired and is the safe fallback today. |
| `💎 Криптовалюта` | `bot/handlers/tariffs.py` -> `_show_platega_payment` / crypto path | works | External payment seam exists with status checks and finalize path. |
| `💰 Пополнить баланс` | `bot/handlers/start.py` -> `home_balance_callback`; `bot/handlers/tariffs.py` balance callbacks | works | Top-up amount and external balance payment flow are wired. |
| `СБП` for balance top-up | `bot/handlers/tariffs.py` -> `balance_method_callback` | placeholder | Explicitly disabled unless Platega top-up SBP is allowed; current UI shows the limitation instead of a broken flow. |
| Referral screen `🎁 Реферальная система` | `bot/handlers/referrals.py` | works | Live referral dashboard, copy/share link, refresh, balances, stats, and levels. |
| Support entry from main bot | `bot/keyboards/home.py`, `bot/handlers/support.py` | works | Opens the support intro and routes user to `@amonora_support_bot`. |
| Info hub `📚 Информация` | `bot/handlers/info.py` | works | Root, docs, and instruction surfaces are wired. |
| FAQ screen | `bot/handlers/info.py` -> `info_faq_callback` | questionable | Handler exists, but current public keyboard does not expose a FAQ button, so this is a hidden legacy seam rather than an active surface. |

## 2. `@amonora_support_bot`

| Surface / button / scenario | File / handler | Status | Why |
|---|---|---|---|
| `/start` support entry | `support_bot/router.py` -> `start_handler` | works | Distinguishes admin panel vs user support entry. |
| User sends a new support message | `support_bot/router.py` -> private message handler | works | Registers ticket, stores message preview, and notifies admins. |
| User sends text / photo / video / audio | `support_bot/router.py` -> `_is_supported_user_message`, `_extract_attachment` | works | These media types are accepted and stored. |
| User sends voice / sticker / GIF / document / video note | `support_bot/router.py` -> `USER_MEDIA_RESTRICTION_TEXT` | placeholder | The bot handles this intentionally by refusing unsupported content types. |
| Admin panel filters `Все / Новые / В работе / Мои / Закрытые` | `support_bot/router.py` -> `support:panel:*` callbacks | works | Filters are fully wired and backed by storage queries. |
| `✅ Взять диалог` | `support_bot/router.py` -> `support:take:*` | works | Assigns ticket and refreshes admin cards. |
| `✉ Ответить` | `support_bot/router.py` -> `support:reply:*`, `ReplyStates.waiting_reply` | works | Admin reply state is implemented and sends a user-facing message. |
| `📜 История` | `support_bot/router.py` -> `support:history:*` | works | Renders message history including attachment markers. |
| `🔁 Передать` | `support_bot/router.py` -> `support:transfer:*`, `support:transferto:*` | works | Transfer flow exists and notifies the target admin. |
| `🔒 Закрыть` | `support_bot/router.py` -> `support:close:*` | works | Closes ticket and tries to notify the user. |
| User notification after close | `support_bot/router.py` -> `_notify_user_closed` | questionable | Implemented, but like any Telegram send it depends on whether the user can still receive the bot message. |

## 3. `@amonora_control_bot`

| Surface / button / scenario | File / handler | Status | Why |
|---|---|---|---|
| `/start` internal shell | `control_bot/router.py` -> `start_handler` | works | Role-aware start screen and persistent keyboard. |
| `Дашборд` / `Статус` | `control_bot/router.py` -> `_handle_named_screen("dashboard")` | works | Uses `build_status_screen`. |
| `Ноды` and node filters | `control_bot/router.py` -> `nodes_handler`, `nodes_callback`, `nodes_filtered_callback` | works | Read-side screen and filter callbacks are wired. |
| Node actions `health check / restart / maintenance / refresh` | `control_bot/router.py` -> `control:node:action:*` | questionable | Code seam exists and calls real server actions, but execution depends on runtime/host reachability. |
| `Платежи` list and payment focus | `control_bot/router.py` -> payments handlers; `control_bot/queries.py` | works | Review list and detail screens are wired. |
| Manual payment `✅ Подтвердить` / `❌ Отклонить` | `control_bot/router.py` -> payment confirm/reject callbacks | works | Calls payment review logic directly. |
| `Пользователи` and `/user` lookup | `control_bot/router.py` -> users/user handlers | works | Search and focus screen are implemented. |
| User actions `Sync / Deep repair / Продлить / Trial / Блок / Разблок / Снять доступ` | `control_bot/router.py` -> `control:user:*` | works | These actions call shared dashboard/backend services. |
| `🎁 Trial недоступен` button | `control_bot/queries.py` -> `control:user:noop:*`; `control_bot/router.py` -> `user_noop_callback` | placeholder | Visible by design for ineligible users and intentionally returns “action unavailable”. |
| `Поддержка` screen and ticket actions | `control_bot/router.py` -> support callbacks | works | Open, assign, reply, transfer, close are wired. |
| `Коды входа` | `control_bot/router.py` -> `login_codes_handler`, `login_codes_callback` | works | Sessions and codes screens are wired. |
| `🔒 Завершить все` | `control_bot/router.py` -> `login_codes_terminate_callback` | works | Owner-only action is implemented. |
| `Уведомления` / `Настройки` | `control_bot/router.py` -> `settings_handler`, settings callbacks | works | Preference toggles are real and backed by storage. |
| `Рассылка / Триггеры` | `control_bot/router.py` -> broadcast/compose flow | works | Owner-only compose, templates, priority, CTA, schedule, and dispatch are implemented. |
| Test send in compose flow | `control_bot/router.py` -> `control:compose:test` | works | Explicit test dispatch exists. |

## 4. `landing`

| Surface / button / route | File / handler | Status | Why |
|---|---|---|---|
| `/` landing page | `landing/main.py` -> `landing_index`; `landing/templates/index.html` | works | Main public page renders with product sections, bot/channel CTAs, and bridge panel. |
| Apex -> `www` redirect | `landing/main.py` -> `canonical_public_host_middleware` | works | Public GET/HEAD requests for `/`, `/manual`, `/legal/*` redirect to canonical host. |
| `/manual` | `landing/main.py` -> `manual_page`; `landing/templates/legal.html`; `landing/static/landing.js` | works | Manual page renders from markdown and uses reveal fallback so text is visible on mobile. |
| `/legal/*` pages | `landing/main.py` -> `legal_page` | works | Legal documents render from markdown. |
| Cookie banner / modal | `landing/static/landing.js` | works | Pure client-side localStorage consent UI. |
| Hero/topbar CTA buttons to bot/channel | `landing/templates/index.html` | works | Simple external links. |
| `Ключ на день` bridge request | `landing/main.py` -> `bridge_access`; `landing/static/landing.js` | questionable | Full seam exists, but success depends on bridge node health and current rate limits. |
| Bridge copy button | `landing/static/landing.js` | works | Clipboard copy with fallback. |
| Bridge result buttons `Открыть инструкцию` / `Открыть бота` | `landing/templates/index.html` | works | Direct links after successful bridge issuance. |
| `/health` | `landing/main.py` -> `healthcheck` | works | Live health endpoint exists. |
| `Platega` webhook | `landing/main.py` -> `platega_webhook` | questionable | App seam exists and is correct, but production confirmation is known to fail when blocked by public edge/WAF. |
| Legacy `Crypto Pay` webhook | `landing/main.py` -> `crypto_pay_webhook` | placeholder | Intentionally disabled by default and returns `410` unless explicitly re-enabled. |

## 5. `dashboard` / `dashboard/ui`

| Surface / route / button | File / handler | Status | Why |
|---|---|---|---|
| `/login` | `dashboard/ui/src/app/login/page.tsx`; `dashboard/ui/src/app/auth/request-code/route.ts` | works | Login form is wired to backend auth request-code API. |
| `/verify` | `dashboard/ui/src/app/verify/page.tsx`; `dashboard/ui/src/app/auth/verify/route.ts` | works | Code verification and session cookie pass-through are implemented. |
| Auth notice fallback text | `dashboard/ui/src/app/auth/request-code/route.ts` | questionable | Fallback copy still mentions `@amonora_support_bot`, but backend currently returns a real notice for `@amonora_control_bot`, so this is stale fallback copy rather than an active broken flow. |
| Root `/` -> `/overview` | `dashboard/ui/src/app/page.tsx` | works | Immediate redirect. |
| Main navigation shell | `dashboard/ui/src/components/app-shell.tsx` | works | Nav renders from session payload; pages exist for overview/users/servers/traffic/payments/support/knowledge/audit/settings. |
| Overview cards and quick links | `dashboard/ui/src/app/(dashboard)/overview/page.tsx` | works | KPIs, recent payments, attention rail, and audit snippets are wired to API. |
| `Срез тарифа` | `dashboard/ui/src/app/(dashboard)/overview/page.tsx`; `dashboard/v2_data.py` | works | Slice data is now explicit for `1 / 3 / 6 / 12`. |
| Users page | `dashboard/ui/src/app/(dashboard)/users/page.tsx` | works | Search, tariff filter, user detail, device and access actions are wired. |
| User actions `trial / extend / block / clear-access / sync / deep repair` | `dashboard/main.py` API v2 + users page | works | Backend/API and UI actions exist. |
| Device IPs in user detail | `dashboard/services.py`, `dashboard/v2_data.py`, users page | questionable | Live IP seam exists, but can degrade to fallback metadata when `3x-ui` has no current IP record. |
| Payments page | `dashboard/ui/src/app/(dashboard)/payments/page.tsx`; `dashboard/main.py` payment routes | works | Payment list, create, confirm, reject, sync, finance views are wired. |
| Finance view | same as above | works | Earlier payload error was fixed; current code path is live. |
| Auto payment sync from provider | `dashboard/main.py` + `dashboard/services.py` | works | Open records auto-refresh through backend sync seams. |
| `СБП` status in payments | payment pages + Platega sync | questionable | UI is wired, but provider truth still depends on webhook/provider reachability. |
| Support page | `dashboard/ui/src/app/(dashboard)/support/page.tsx`; `dashboard/main.py` support routes | works | Queue, detail, reply, assign, transfer, close are wired. |
| Attachment preview / open attachment | `dashboard/main.py` attachment route; support page | works | Attachment seam exists via Telegram file fetch path. |
| Servers page | `dashboard/ui/src/app/(dashboard)/servers/page.tsx`; `dashboard/main.py` server routes | questionable | Read surface is real; write actions depend on ops/runtime reachability. |
| Traffic page | `dashboard/ui/src/app/(dashboard)/traffic/page.tsx`; `/dashboard/api/v2/traffic` | works | Traffic/audit curve and reset endpoint exist. |
| Monthly reset action | `dashboard/main.py` -> `/dashboard/api/v2/traffic/reset` | works | Endpoint exists and monthly reset logic has already been added. |
| Knowledge page | `dashboard/ui/src/app/(dashboard)/knowledge/page.tsx`; `/dashboard/api/v2/knowledge` | works | Read-only docs surface with search is wired. |
| Audit page | `dashboard/ui/src/app/(dashboard)/audit/page.tsx`; `/dashboard/api/v2/audit` | works | Searchable audit surface is wired. |
| Settings page | `dashboard/ui/src/app/(dashboard)/settings/page.tsx`; settings APIs | works | Notifications, roles/permissions, env, docs report, service actions are wired. |
| Env/service write actions | `dashboard/main.py` settings endpoints | questionable | The UI seam exists, but effectiveness depends on runtime and may require restart/redeploy. |

## Buttons or scenarios that are intentionally non-final

1. Public `📱 Мобильный` mode in `@amonora_bot`
2. `🎁 Trial недоступен` in `@amonora_control_bot`
3. Legacy `Crypto Pay` webhook on `landing`
4. `СБП` top-up for balance when Platega balance-SBP is disabled
5. Existing-device mode changes that would require a real reprovision/recreation

## Buttons or scenarios with known incomplete end-to-end behavior

1. Auto `СБП` confirmation through `Platega` when webhook delivery is blocked at the public edge
2. Live device IP display in admin surfaces when `3x-ui` does not currently populate `clientIps`
3. Node/server actions when backend host reachability or node runtime is degraded
4. User notification certainty after support close/reply, because Telegram delivery can still fail externally

## Practical release gate

Before a release, manually verify at minimum:

1. `@amonora_bot`: `/start`, trial, create device, stable key delivery, manual SBP, referral screen
2. `@amonora_support_bot`: new user message, admin take/reply/close
3. `@amonora_control_bot`: dashboard, payments review, `/user`, login codes, notifications
4. `landing`: `/`, `/manual`, `/legal/terms`, `/bridge/access`
5. `dashboard/ui`: `/login`, `/verify`, `/overview`, `/users`, `/payments`, `/support`, `/servers`, `/settings`
