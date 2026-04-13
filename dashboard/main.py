import asyncio
import hmac
import json
import time
from datetime import datetime, timedelta
from html import escape
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from bot.config import config
from backend.core.promo_codes import create_promo_code
from bot.manual_payments import PAYMENT_STATUS_LABELS
from bot.utils.texts import manual_payment_method_label
from bot.utils.logging_setup import configure_logging
from control_bot.channel_content import (
    CHANNEL_CONTENT_TYPE_OFFER,
    CHANNEL_INTERNAL_HEADER,
    create_channel_content_item,
    generate_channel_content_item,
    generate_due_channel_content_items,
    publish_channel_content_item,
    publish_due_channel_content_items,
)
from control_bot.dispatcher import delete_control_message, send_panel_auth_code
from control_bot.storage import get_notification_preferences, set_notification_preference
from dashboard.schema import ensure_dashboard_schema, seed_dashboard_defaults
from dashboard.security import generate_code, generate_session_token, hash_token, utcnow
from dashboard.finance import sync_income_entries_for_confirmed_payments
from dashboard.daily_news import (
    list_daily_news_history,
    publish_daily_news_item,
    update_daily_news_review_message,
    update_daily_news_status,
    upsert_daily_news_item,
)
from dashboard.services import (
    assign_support_ticket_dashboard,
    approve_finance_entry,
    cancel_finance_entry,
    close_support_ticket,
    confirm_payment_record,
    create_control_event,
    create_audit_log,
    create_device_for_user,
    create_finance_entry,
    create_managed_server,
    create_payment_record,
    create_session,
    clear_dashboard_auth_failures,
    delete_dashboard_login_code,
    dashboard_settings,
    delete_finance_entry,
    delete_device_for_user,
    delete_payment_record,
    delete_user_with_access,
    delete_session,
    extend_subscription_for_user,
    generate_finance_report,
    generate_operations_report,
    get_admin_by_session,
    get_dashboard_auth_lockout_state,
    get_finance_dashboard,
    get_finance_entries,
    get_finance_summary,
    get_pending_dashboard_login_code,
    get_managed_servers,
    get_payment_records,
    get_payment_focus,
    get_runtime_tariffs,
    get_runtime_tariffs_list,
    get_server_snapshots,
    get_server_snapshot_by_id,
    get_service_statuses,
    get_support_admin_choices,
    get_support_dashboard_counts,
    get_support_ticket_detail,
    get_support_attachment_content,
    get_support_tickets,
    get_documentation_page,
    get_user_detail,
    get_user_device_status_payload,
    get_users,
    get_vpn_overview,
    grant_trial_to_user,
    deep_repair_user_access,
    nav_items,
    overview_metrics,
    read_masked_env,
    recent_audit_logs,
    record_dashboard_auth_failure,
    repair_user_vpn_access,
    reset_traffic_baseline,
    reject_payment_record,
    remove_user_tariff,
    role_has_any_permission,
    role_has_permission,
    run_server_action,
    send_manual_payment_reminder,
    send_support_reply,
    set_current_audit_request_id,
    set_payment_record_status,
    service_action as run_service_action,
    service_logs,
    set_user_block_state,
    set_user_preferred_protocol,
    sync_payment_record_with_provider,
    sync_user_access_state,
    update_server_status,
    update_tariffs,
    update_role_permission_override,
    update_env_value,
    update_admin_avatar,
    verify_admin_credentials,
    upsert_dashboard_login_code,
    increment_dashboard_login_code_attempts,
    purge_expired_dashboard_login_codes,
    LOGIN_CODE_REQUEST_COOLDOWN_SECONDS,
    ROLE_NAMES,
    refresh_role_permission_overrides_cache,
    summarize_server_snapshots,
    transfer_support_ticket_dashboard,
    update_dashboard_admin_access,
    reset_current_audit_request_id,
)
from dashboard.v2_data import (
    get_v2_audit_payload,
    get_v2_campaign_analytics_detail_payload,
    get_v2_campaign_analytics_payload,
    get_v2_knowledge_payload,
    get_v2_notifications_payload,
    get_v2_overview_payload,
    get_v2_payments_payload,
    get_v2_promocodes_payload,
    get_v2_search_payload,
    get_v2_servers_payload,
    get_v2_session_payload,
    get_v2_settings_payload,
    get_v2_support_payload,
    get_v2_traffic_payload,
    get_v2_user_detail_payload,
    get_v2_users_payload,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Amonora Dashboard")
app.mount("/dashboard/static", StaticFiles(directory=str(BASE_DIR / "static")), name="dashboard-static")

_PENDING_CODES: dict[str, dict] = {}
_AUTH_RATE_LIMITS: dict[str, list[datetime]] = {}
_AUTH_RATE_LIMIT_LOCK = asyncio.Lock()
MAX_LOGIN_CODE_ATTEMPTS = 5
LOGIN_CODE_TTL_MINUTES = 5
AUTH_REQUEST_LIMIT = 5
AUTH_REQUEST_WINDOW_SECONDS = 300
AUTH_VERIFY_LIMIT = 8
AUTH_VERIFY_WINDOW_SECONDS = 300
_V2_READ_CACHE: dict[str, tuple[float, object]] = {}
_V2_READ_CACHE_LOCK = asyncio.Lock()
EKB_TZ = ZoneInfo("Asia/Yekaterinburg")


@app.middleware("http")
async def dashboard_request_id_middleware(request: Request, call_next):
    raw_request_id = str(request.headers.get("x-request-id") or "").strip()
    request_id = (raw_request_id[:64] if raw_request_id else uuid4().hex)
    request.state.request_id = request_id
    token = set_current_audit_request_id(request_id)
    response = None
    try:
        if request.url.path.startswith("/dashboard") or request.url.path in {"/login", "/verify"}:
            _assert_same_origin_for_cookie_request(request)
        response = await call_next(request)
    except HTTPException as exc:
        response = await http_exception_handler(request, exc)
    finally:
        reset_current_audit_request_id(token)
    response.headers.setdefault("X-Request-ID", request_id)
    return response


class V2LoginRequest(BaseModel):
    username: str
    password: str


class V2VerifyRequest(BaseModel):
    username: str
    code: str


class V2ExtendRequest(BaseModel):
    days: int


class V2BlockRequest(BaseModel):
    blocked: bool


class V2ProtocolRequest(BaseModel):
    protocol: str


class V2ClearAccessRequest(BaseModel):
    remove_devices: bool = False


class V2CreateDeviceRequest(BaseModel):
    device_name: str
    device_type: str
    protocol: str
    country_code: str


class V2CreatePaymentRequest(BaseModel):
    user_id: int | None = None
    payment_method: str
    tariff_code: str
    payment_status: str
    reference: str = ""
    note: str = ""


class V2RejectPaymentRequest(BaseModel):
    reason: str = ""


class V2CreatePromoCodeRequest(BaseModel):
    code: str = ""
    kind: str
    title: str = ""
    description: str = ""
    discount_percent: int | None = None
    grant_days: int | None = None
    max_redemptions: int = 1
    expires_at: datetime | None = None


class V2CreateCampaignRequest(BaseModel):
    topic_brief: str
    cta_label: str = "Попробовать бесплатно"


class V2CreateFinanceRequest(BaseModel):
    entry_type: str
    category: str
    amount: int
    note: str = ""
    related_server: str = ""
    status: str = "draft"
    counterparty_admin_id: int | None = None
    occurred_at: str = ""


class V2CreateServerRequest(BaseModel):
    name: str
    host: str
    public_ip: str
    country_code: str
    country_name: str
    provider: str = ""
    status: str = "active"


class V2ServerStatusRequest(BaseModel):
    status: str


class V2ServerActionRequest(BaseModel):
    action: str
    target_server_id: int | None = None


class V2SupportTransferRequest(BaseModel):
    target_admin_id: int


class V2SupportReplyRequest(BaseModel):
    message: str


class V2PaymentStatusRequest(BaseModel):
    payment_status: str
    reason: str = ""


class V2ServiceActionRequest(BaseModel):
    service_name: str
    action: str


class V2TariffsRequest(BaseModel):
    tariff_1m_rub: int
    tariff_3m_rub: int
    tariff_6m_rub: int
    tariff_12m_rub: int


class V2EnvRequest(BaseModel):
    key: str
    value: str
    apply_runtime: bool = False


class V2UpdateAdminAccessRequest(BaseModel):
    role: str
    is_active: bool


class V2NotificationPreferenceRequest(BaseModel):
    telegram_id: int
    category: str
    enabled: bool


class V2RolePermissionOverrideRequest(BaseModel):
    role: str
    permission: str
    enabled: bool


class InternalChannelGenerateRequest(BaseModel):
    item_id: int | None = None
    notify_missing_content: bool = False


class InternalChannelPublishRequest(BaseModel):
    item_id: int | None = None
    allow_failed_retry: bool = False


class InternalDailyNewsUpsertRequest(BaseModel):
    id: str
    source_url: str = ""
    source_title: str = ""
    title: str = ""
    source_summary: str = ""
    summary: str = ""
    source_published_at: str = ""
    published_at: str = ""
    source_provider: str = ""
    topic_key: str = ""
    status: str = "pending"
    post_text: str = ""
    image_url: str = ""
    review_requested_at: str = ""


class InternalDailyNewsReviewMessageRequest(BaseModel):
    review_message_id: int | None = None


class InternalDailyNewsStatusRequest(BaseModel):
    status: str
    approved_at: str = ""
    posted_at: str = ""
    reject_reason: str = ""


def _api_ok(data=None, notice: str | None = None, status_code: int = 200):
    payload = {"ok": True}
    if notice:
        payload["notice"] = notice
    if data is not None:
        payload["data"] = data
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


def _api_error(message: str, status_code: int = 400):
    return JSONResponse(jsonable_encoder({"ok": False, "error": message}), status_code=status_code)


def _cache_key(name: str, *parts: object) -> str:
    safe_parts = [name]
    for part in parts:
        safe_parts.append(str(part or ""))
    return "::".join(safe_parts)


def _require_any_permission(admin, *permissions: str):
    if permissions and not role_has_any_permission(admin.role, *permissions):
        return _api_error("Недостаточно прав", 403)
    return None


def _is_owner(admin) -> bool:
    return str(getattr(admin, "role", "") or "").strip() == "owner"


async def _invalidate_v2_cache(*prefixes: str | None) -> None:
    async with _V2_READ_CACHE_LOCK:
        active_prefixes = tuple(prefix for prefix in prefixes if prefix)
        if not prefixes or not active_prefixes:
            _V2_READ_CACHE.clear()
            return
        stale_keys = [key for key in _V2_READ_CACHE if any(key.startswith(prefix) for prefix in active_prefixes)]
        for key in stale_keys:
            _V2_READ_CACHE.pop(key, None)


async def _get_v2_cached_payload(
    cache_key: str,
    ttl_seconds: int,
    factory,
    *,
    bypass: bool = False,
):
    now = time.monotonic()
    if not bypass and ttl_seconds > 0:
        async with _V2_READ_CACHE_LOCK:
            cached = _V2_READ_CACHE.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]

    payload = await factory()

    if ttl_seconds > 0:
        async with _V2_READ_CACHE_LOCK:
            _V2_READ_CACHE[cache_key] = (time.monotonic() + ttl_seconds, payload)

    return payload


def _notice(request: Request) -> tuple[str | None, str | None]:
    return request.query_params.get("notice"), request.query_params.get("error")


def _redirect(path: str, notice: str | None = None, error: str | None = None) -> RedirectResponse:
    parts = urlsplit(path)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    if notice:
        params["notice"] = notice
    if error:
        params["error"] = error
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params, doseq=True), parts.fragment))
    return RedirectResponse(url=url, status_code=303)


def _redirect_to_new_ui(path: str, request: Request | None = None, **extra_params: object) -> RedirectResponse:
    parts = urlsplit(path)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    if request is not None:
        params.update({key: value for key, value in request.query_params.items()})
    for key, value in extra_params.items():
        if value is None:
            params.pop(key, None)
            continue
        params[key] = str(value)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params, doseq=True), parts.fragment))
    return RedirectResponse(url=url, status_code=303)


def _hash_login_code(code: str) -> str:
    return hash_token(f"dashboard-login-code::{code}")


def _code_matches(raw_code: str, hashed_code: str) -> bool:
    return hmac.compare_digest(_hash_login_code(raw_code.strip()), hashed_code)


async def _hit_dashboard_auth_rate_limit(scope: str, request: Request, username: str, *, limit: int, window_seconds: int) -> bool:
    normalized_username = str(username or "").strip().lower() or "-"
    ip_address = _client_ip(request) or "unknown"
    now = utcnow()
    cutoff = now - timedelta(seconds=max(int(window_seconds), 1))
    rate_keys = (
        f"{scope}:{normalized_username}:{ip_address}",
        f"{scope}:{normalized_username}:__global__",
    )
    async with _AUTH_RATE_LIMIT_LOCK:
        limit_value = max(int(limit), 1)
        refreshed: dict[str, list[datetime]] = {}
        for rate_key in rate_keys:
            recent = [seen_at for seen_at in _AUTH_RATE_LIMITS.get(rate_key, []) if seen_at > cutoff]
            refreshed[rate_key] = recent
            if len(recent) >= limit_value:
                _AUTH_RATE_LIMITS[rate_key] = recent
                return True
        for rate_key, recent in refreshed.items():
            recent.append(now)
            _AUTH_RATE_LIMITS[rate_key] = recent
        stale_before = now - timedelta(seconds=max(int(window_seconds), 1) * 2)
        for stale_key in [key for key, values in _AUTH_RATE_LIMITS.items() if not values or values[-1] < stale_before]:
            _AUTH_RATE_LIMITS.pop(stale_key, None)
    return False


async def _delete_login_code_message(telegram_id: int | None, message_id: int | None, bot_key: str | None = None) -> None:
    if not telegram_id or not message_id:
        return
    if bot_key == "control":
        await delete_control_message(telegram_id, message_id)
        return
    token = config.support_bot_token if bot_key == "support" else config.bot_token if bot_key == "main" else config.support_bot_token
    if not token:
        return
    bot = Bot(token)
    try:
        await bot.delete_message(telegram_id, message_id)
    except Exception:
        pass
    finally:
        await bot.session.close()


async def _clear_pending_code(username: str, pending: dict | None = None, *, delete_message: bool = False) -> None:
    payload = pending or _PENDING_CODES.pop(username, None)
    if payload is None:
        db_payload = await delete_dashboard_login_code(username)
        if db_payload is not None:
            payload = {
                "code_hash": db_payload.code_hash,
                "admin_id": db_payload.admin_id,
                "telegram_id": db_payload.telegram_id,
                "message_id": db_payload.message_id,
                "bot_key": db_payload.bot_key,
                "attempts": int(db_payload.attempts or 0),
                "expires_at": db_payload.expires_at,
                "created_at": db_payload.created_at,
            }
    else:
        await delete_dashboard_login_code(username)
    if payload is None:
        return
    _PENDING_CODES.pop(username, None)
    if delete_message:
        await _delete_login_code_message(payload.get("telegram_id"), payload.get("message_id"), payload.get("bot_key"))


async def _purge_expired_pending_codes() -> None:
    expired_rows = await purge_expired_dashboard_login_codes()
    for row in expired_rows:
        _PENDING_CODES.pop(row.username, None)
    expired = [
        username
        for username, pending in _PENDING_CODES.items()
        if pending.get("expires_at") is None or pending["expires_at"] <= utcnow()
    ]
    for username in expired:
        await _clear_pending_code(username, _PENDING_CODES.get(username))


async def _request_dashboard_login_code(admin, audit_action: str, ip_address: str | None) -> None:
    await _purge_expired_pending_codes()
    existing = _PENDING_CODES.get(admin.username)
    if existing is None:
        existing_row = await get_pending_dashboard_login_code(admin.username)
        if existing_row is not None:
            existing = {
                "code_hash": existing_row.code_hash,
                "admin_id": existing_row.admin_id,
                "telegram_id": existing_row.telegram_id,
                "message_id": existing_row.message_id,
                "bot_key": existing_row.bot_key,
                "attempts": int(existing_row.attempts or 0),
                "expires_at": existing_row.expires_at,
                "created_at": existing_row.created_at,
            }
            _PENDING_CODES[admin.username] = existing
    if existing:
        created_at = existing.get("created_at")
        if isinstance(created_at, datetime):
            age_seconds = (utcnow() - created_at).total_seconds()
            if age_seconds < LOGIN_CODE_REQUEST_COOLDOWN_SECONDS:
                raise ValueError("Код уже отправлен недавно. Подожди немного и попробуй снова.")
        await _clear_pending_code(admin.username, existing, delete_message=True)

    code = generate_code()
    message_id, bot_key = await send_panel_auth_code(
        admin_username=admin.username,
        telegram_id=admin.telegram_id,
        code=code,
        ttl_minutes=LOGIN_CODE_TTL_MINUTES,
    )
    _PENDING_CODES[admin.username] = {
        "code_hash": _hash_login_code(code),
        "admin_id": admin.id,
        "telegram_id": admin.telegram_id,
        "message_id": message_id,
        "bot_key": bot_key,
        "attempts": 0,
        "created_at": utcnow(),
        "expires_at": utcnow() + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
    }
    await upsert_dashboard_login_code(
        username=admin.username,
        admin_id=admin.id,
        code_hash=_PENDING_CODES[admin.username]["code_hash"],
        telegram_id=admin.telegram_id,
        message_id=message_id,
        bot_key=bot_key,
        expires_at=_PENDING_CODES[admin.username]["expires_at"],
        now_utc=_PENDING_CODES[admin.username]["created_at"],
    )
    await create_audit_log(
        admin.id,
        audit_action,
        "dashboard_admin",
        str(admin.id),
        json.dumps(
            {
                "admin": _dashboard_admin_audit_snapshot(admin),
                "delivery": {
                    "bot_key": bot_key,
                    "message_id": message_id,
                    "expires_at": _PENDING_CODES[admin.username]["expires_at"].isoformat(),
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )


def _dashboard_admin_audit_snapshot(admin) -> dict[str, object]:
    return {
        "id": int(getattr(admin, "id", 0) or 0),
        "username": str(getattr(admin, "username", "") or "").strip(),
        "role": str(getattr(admin, "role", "") or "").strip(),
        "telegram_id": int(getattr(admin, "telegram_id", 0) or 0) if getattr(admin, "telegram_id", None) is not None else None,
        "is_active": bool(getattr(admin, "is_active", True)),
    }


def _session_fingerprint(request: Request) -> str | None:
    token = request.cookies.get(dashboard_settings()["cookie_name"])
    normalized = str(token or "").strip()
    if not normalized:
        return None
    return hash_token(normalized)[:16]


async def _audit_dashboard_auth_event(
    request: Request,
    action: str,
    *,
    username: str | None = None,
    admin_id: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {}
    normalized_username = str(username or "").strip()
    if normalized_username:
        payload["username"] = normalized_username
    if details:
        payload.update(details)
    details_text = json.dumps(payload, ensure_ascii=False) if payload else None
    await create_audit_log(
        admin_id,
        action,
        "dashboard_auth",
        normalized_username or (str(admin_id) if admin_id is not None else None),
        details_text,
        _client_ip(request),
    )


async def get_current_admin(request: Request):
    _assert_same_origin_for_cookie_request(request)
    token = request.cookies.get(dashboard_settings()["cookie_name"])
    admin = await get_admin_by_session(token)
    if admin is None:
        raise HTTPException(status_code=401)
    return admin


def _client_ip(request: Request) -> str | None:
    trusted_proxy_networks = (
        ip_network("127.0.0.0/8"),
        ip_network("::1/128"),
    )

    def _normalize_ip(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            return str(ip_address(normalized))
        except ValueError:
            return None

    def _trusted_proxy_peer(value: str | None) -> bool:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return False
        if normalized in {"localhost"}:
            return True
        parsed = _normalize_ip(normalized)
        if parsed is None:
            return False
        candidate = ip_address(parsed)
        return any(candidate in network for network in trusted_proxy_networks)

    direct_ip = str(request.client.host).strip() if request.client and request.client.host else ""
    if _trusted_proxy_peer(direct_ip):
        for header_name in ("x-amonora-client-ip", "cf-connecting-ip", "x-real-ip"):
            forwarded = _normalize_ip(request.headers.get(header_name))
            if forwarded:
                return forwarded[:64]
        forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            for raw_part in forwarded_for.split(","):
                candidate = _normalize_ip(raw_part)
                if candidate:
                    return candidate[:64]
    direct = _normalize_ip(direct_ip)
    return direct[:64] if direct else None


def _request_origin_host(request: Request) -> str | None:
    origin = str(request.headers.get("origin") or "").strip()
    if origin:
        parsed = urlsplit(origin)
        return str(parsed.netloc or "").strip().lower() or None
    referer = str(request.headers.get("referer") or "").strip()
    if referer:
        parsed = urlsplit(referer)
        return str(parsed.netloc or "").strip().lower() or None
    return None


def _current_request_host(request: Request) -> str | None:
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").strip().lower()
    if forwarded_host:
        current_host = forwarded_host.split(",", 1)[0].strip()
        if current_host:
            return current_host
    current_host = str(request.headers.get("host") or request.url.netloc or "").strip().lower()
    return current_host or None


def _assert_same_origin_for_cookie_request(request: Request) -> None:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    request_origin = _request_origin_host(request)
    if not request_origin:
        return
    current_host = _current_request_host(request)
    if not current_host:
        return
    if request_origin != current_host:
        raise HTTPException(status_code=403, detail="Cross-site request is not allowed")


def _require_internal_channel_secret(request: Request):
    expected = str(getattr(config, "amonora_internal_channel_webhook_secret", "") or "").strip()
    if not expected:
        return _api_error("Internal channel webhook secret is not configured", 503)
    provided = str(request.headers.get(CHANNEL_INTERNAL_HEADER, "") or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return _api_error("Недостаточно прав", 403)
    return None


def _require_internal_grafana_secret(secret: str):
    expected = str(getattr(config, "amonora_grafana_alerts_webhook_secret", "") or "").strip()
    if not expected:
        return _api_error("Grafana alert webhook secret is not configured", 503)
    if not secret or not hmac.compare_digest(str(secret).strip(), expected):
        return _api_error("Недостаточно прав", 403)
    return None


def _grafana_alert_category(alert_class: str, alert_name: str) -> str:
    normalized_class = str(alert_class or "").strip().lower()
    normalized_name = str(alert_name or "").strip().lower()
    if normalized_class == "revenue":
        return "payments"
    if normalized_name.startswith("node_"):
        return "nodes"
    if normalized_name.startswith("service_"):
        return "errors"
    if normalized_class == "ops":
        return "access"
    return "system"


def _grafana_alert_text(payload: dict) -> tuple[str, str, str, str, str, dict]:
    status = str(payload.get("status") or "firing").strip().lower() or "firing"
    common_labels = payload.get("commonLabels") if isinstance(payload.get("commonLabels"), dict) else {}
    common_annotations = payload.get("commonAnnotations") if isinstance(payload.get("commonAnnotations"), dict) else {}
    alert_name = str(common_labels.get("alertname") or "grafana_alert").strip() or "grafana_alert"
    alert_class = str(common_labels.get("alert_class") or "ops").strip().lower() or "ops"
    severity = str(common_labels.get("severity") or "warning").strip().upper() or "WARNING"
    summary = str(common_annotations.get("summary") or common_annotations.get("description") or alert_name).strip() or alert_name
    description = str(common_annotations.get("description") or "").strip()
    dashboard_url = str(common_annotations.get("dashboard_url") or "").strip()
    panel_url = str(common_annotations.get("panel_url") or "").strip()
    alerts = payload.get("alerts")
    alerts_count = len(alerts) if isinstance(alerts, list) else 0
    group_key = str(payload.get("groupKey") or common_labels.get("scope_key") or alert_name).strip() or alert_name
    dedupe_key = f"grafana:{alert_class}:{alert_name}:{group_key}"[:255]

    state_label = "Алерт сработал" if status == "firing" else "Алерт восстановился"
    title = f"Grafana · {summary}"[:255]
    lines = [
        f"Класс: <b>{escape(alert_class)}</b>",
        f"Severity: <b>{escape(severity)}</b>",
        f"Правило: <code>{escape(alert_name)}</code>",
        f"Состояние: <b>{escape(state_label)}</b>",
    ]
    if alerts_count:
        lines.append(f"Алертов в группе: <b>{alerts_count}</b>")
    if description and description != summary:
        lines.append(f"Описание: {escape(description)}")
    if dashboard_url:
        lines.append(f"Dashboard: {escape(dashboard_url)}")
    if panel_url:
        lines.append(f"Panel: {escape(panel_url)}")

    normalized = {
        "status": status,
        "alert_name": alert_name,
        "alert_class": alert_class,
        "severity": severity,
        "summary": summary,
        "description": description,
        "alerts_count": alerts_count,
        "group_key": group_key,
        "dashboard_url": dashboard_url,
        "panel_url": panel_url,
        "common_labels": common_labels,
        "common_annotations": common_annotations,
    }
    return (
        _grafana_alert_category(alert_class, alert_name),
        severity,
        title,
        "\n".join(lines),
        dedupe_key,
        normalized,
    )


async def _warm_dashboard_cache() -> None:
    try:
        await get_server_snapshots(force_refresh=True)
        await overview_metrics(force_refresh=True)
    except Exception:
        pass


@app.on_event("startup")
async def startup_event() -> None:
    configure_logging()
    await ensure_dashboard_schema()
    await seed_dashboard_defaults()
    await refresh_role_permission_overrides_cache()
    await sync_income_entries_for_confirmed_payments()
    asyncio.create_task(_warm_dashboard_cache())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        if request.url.path.startswith("/dashboard/api/v2/"):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await default_http_exception_handler(request, exc)


@app.post("/dashboard/api/internal/channel/generate")
async def internal_channel_generate(
    request: Request,
    payload: InternalChannelGenerateRequest | None = Body(default=None),
):
    if denial := _require_internal_channel_secret(request):
        return denial
    request_payload = payload or InternalChannelGenerateRequest()
    try:
        if request_payload.item_id is not None:
            result = await generate_channel_content_item(int(request_payload.item_id))
        else:
            result = await generate_due_channel_content_items(
                notify_missing_content=bool(request_payload.notify_missing_content),
            )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(result)


@app.post("/dashboard/api/internal/channel/publish")
async def internal_channel_publish(
    request: Request,
    payload: InternalChannelPublishRequest | None = Body(default=None),
):
    if denial := _require_internal_channel_secret(request):
        return denial
    request_payload = payload or InternalChannelPublishRequest()
    try:
        if request_payload.item_id is not None:
            result = await publish_channel_content_item(
                int(request_payload.item_id),
                allow_failed_retry=bool(request_payload.allow_failed_retry),
            )
        else:
            result = await publish_due_channel_content_items()
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(result)


@app.get("/dashboard/api/internal/daily-news/history")
async def internal_daily_news_history(request: Request):
    if denial := _require_internal_channel_secret(request):
        return denial
    try:
        rows = await list_daily_news_history()
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok({"rows": rows})


@app.post("/dashboard/api/internal/daily-news/items/upsert")
async def internal_daily_news_upsert(
    request: Request,
    payload: InternalDailyNewsUpsertRequest,
):
    if denial := _require_internal_channel_secret(request):
        return denial
    try:
        row = await upsert_daily_news_item(payload.model_dump())
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(row)


@app.post("/dashboard/api/internal/daily-news/items/{item_id}/review-message")
async def internal_daily_news_review_message(
    item_id: str,
    request: Request,
    payload: InternalDailyNewsReviewMessageRequest,
):
    if denial := _require_internal_channel_secret(request):
        return denial
    try:
        row = await update_daily_news_review_message(item_id, payload.review_message_id)
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(row)


@app.post("/dashboard/api/internal/daily-news/items/{item_id}/status")
async def internal_daily_news_status(
    item_id: str,
    request: Request,
    payload: InternalDailyNewsStatusRequest,
):
    if denial := _require_internal_channel_secret(request):
        return denial
    try:
        row = await update_daily_news_status(item_id, payload.model_dump())
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(row)


@app.post("/dashboard/api/internal/daily-news/items/{item_id}/publish")
async def internal_daily_news_publish(
    item_id: str,
    request: Request,
):
    if denial := _require_internal_channel_secret(request):
        return denial
    try:
        row = await publish_daily_news_item(item_id)
    except ValueError as exc:
        return _api_error(str(exc), 400)
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok(row)


@app.post("/dashboard/api/internal/grafana/alerts/{secret}")
async def internal_grafana_alerts(secret: str, request: Request):
    if denial := _require_internal_grafana_secret(secret):
        return denial
    content_type = str(request.headers.get("content-type") or "").strip().lower()
    if "application/json" not in content_type:
        return _api_error("Grafana alert payload must be JSON", 415)
    try:
        payload = await request.json()
    except Exception:
        return _api_error("Grafana alert payload is invalid JSON", 400)
    if not isinstance(payload, dict):
        return _api_error("Grafana alert payload must be an object", 400)

    category, severity, title, message, dedupe_key, normalized_payload = _grafana_alert_text(payload)
    status = str(normalized_payload.get("status") or "firing").strip().lower()
    try:
        event = await create_control_event(
            category=category,
            severity=severity,
            event_type=f"grafana_{str(normalized_payload.get('alert_name') or 'alert').strip().lower()}"[:100],
            title=title,
            message=message,
            entity_type="grafana_alert",
            entity_id=str(normalized_payload.get("alert_name") or "grafana_alert")[:255],
            payload=normalized_payload,
            dedupe_key=dedupe_key if status == "firing" else None,
            resolve_dedupe_key=dedupe_key if status != "firing" else None,
        )
    except Exception as exc:
        return _api_error(str(exc), 500)
    return _api_ok({"status": status, "dedupe_key": dedupe_key, "event_id": getattr(event, "id", None)})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    token = request.cookies.get(dashboard_settings()["cookie_name"])
    admin = await get_admin_by_session(token)
    if admin is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/dashboard/overview", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "settings": dashboard_settings(), **dict(zip(["notice", "error"], _notice(request)))})


@app.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    _assert_same_origin_for_cookie_request(request)
    normalized_username = username.strip()
    if await _hit_dashboard_auth_rate_limit(
        "request_code",
        request,
        normalized_username,
        limit=AUTH_REQUEST_LIMIT,
        window_seconds=AUTH_REQUEST_WINDOW_SECONDS,
    ):
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_rate_limited",
            username=normalized_username,
        )
        return _redirect("/login", error="Слишком много попыток. Подожди немного и попробуй снова.")
    lockout = await get_dashboard_auth_lockout_state(
        "request_code",
        normalized_username,
        ip_address=_client_ip(request),
    )
    if lockout["locked"]:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_lockout",
            username=normalized_username,
            details={"retry_after_seconds": int(lockout["retry_after_seconds"])},
        )
        return _redirect("/login", error="Вход временно заблокирован из-за серии неудачных попыток. Подожди и попробуй снова.")
    admin = await verify_admin_credentials(normalized_username, password)
    if admin is None:
        await record_dashboard_auth_failure(
            "request_code",
            normalized_username,
            ip_address=_client_ip(request),
        )
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_invalid_credentials",
            username=normalized_username,
        )
        return _redirect("/login", error="Неверный логин или пароль")
    await clear_dashboard_auth_failures(
        "request_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    if not admin.telegram_id:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_missing_telegram",
            username=admin.username,
            admin_id=admin.id,
        )
        return _redirect("/login", error="У администратора не указан Telegram ID")

    try:
        await _request_dashboard_login_code(admin, "request_login_code", _client_ip(request))
    except ValueError as exc:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_cooldown",
            username=admin.username,
            admin_id=admin.id,
            details={"reason": str(exc)},
        )
        return _redirect("/login", error=str(exc))
    except Exception:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_delivery_failed",
            username=admin.username,
            admin_id=admin.id,
        )
        return _redirect("/login", error="Не удалось отправить код в Telegram. Убедись, что бот открыт у администратора.")

    await clear_dashboard_auth_failures(
        "request_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    await clear_dashboard_auth_failures(
        "verify_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    return _redirect(f"/verify?username={quote_plus(admin.username)}", notice="Код отправлен в Telegram")


@app.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request, username: str = ""):
    return templates.TemplateResponse(
        "verify.html",
        {
            "request": request,
            "username": username,
            "settings": dashboard_settings(),
            **dict(zip(["notice", "error"], _notice(request))),
        },
    )


@app.post("/verify")
async def verify_action(request: Request, username: str = Form(...), code: str = Form(...)):
    _assert_same_origin_for_cookie_request(request)
    normalized_username = username.strip()
    if await _hit_dashboard_auth_rate_limit(
        "verify_code",
        request,
        normalized_username,
        limit=AUTH_VERIFY_LIMIT,
        window_seconds=AUTH_VERIFY_WINDOW_SECONDS,
    ):
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_rate_limited",
            username=normalized_username,
        )
        return _redirect(f"/verify?username={quote_plus(normalized_username)}", error="Слишком много попыток. Запроси новый код позже.")
    lockout = await get_dashboard_auth_lockout_state(
        "verify_code",
        normalized_username,
        ip_address=_client_ip(request),
    )
    if lockout["locked"]:
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_lockout",
            username=normalized_username,
            details={"retry_after_seconds": int(lockout["retry_after_seconds"])},
        )
        return _redirect(f"/verify?username={quote_plus(normalized_username)}", error="Проверка кода временно заблокирована из-за серии неудачных попыток.")
    await _purge_expired_pending_codes()
    pending = _PENDING_CODES.get(normalized_username)
    if pending is None:
        db_pending = await get_pending_dashboard_login_code(normalized_username)
        if db_pending is not None:
            pending = {
                "code_hash": db_pending.code_hash,
                "admin_id": db_pending.admin_id,
                "telegram_id": db_pending.telegram_id,
                "message_id": db_pending.message_id,
                "bot_key": db_pending.bot_key,
                "attempts": int(db_pending.attempts or 0),
                "expires_at": db_pending.expires_at,
                "created_at": db_pending.created_at,
            }
            _PENDING_CODES[normalized_username] = pending
    if pending is None:
        await record_dashboard_auth_failure(
            "verify_code",
            normalized_username,
            ip_address=_client_ip(request),
        )
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_code_missing",
            username=normalized_username,
        )
        return _redirect(f"/verify?username={quote_plus(normalized_username)}", error="Код истёк. Войди снова.")
    if not _code_matches(code, pending["code_hash"]):
        updated_pending = await increment_dashboard_login_code_attempts(normalized_username)
        pending["attempts"] = int(updated_pending.attempts if updated_pending is not None else int(pending.get("attempts") or 0) + 1)
        await record_dashboard_auth_failure(
            "verify_code",
            normalized_username,
            ip_address=_client_ip(request),
        )
        if pending["attempts"] >= MAX_LOGIN_CODE_ATTEMPTS:
            await _audit_dashboard_auth_event(
                request,
                "auth_verify_attempts_exceeded",
                username=normalized_username,
                admin_id=pending.get("admin_id"),
                details={"attempts": pending["attempts"]},
            )
            await _clear_pending_code(normalized_username, pending)
            return _redirect(f"/login?username={quote_plus(normalized_username)}", error="Превышено число попыток. Запроси новый код.")
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_invalid_code",
            username=normalized_username,
            admin_id=pending.get("admin_id"),
            details={"attempts": pending["attempts"]},
        )
        return _redirect(f"/verify?username={quote_plus(normalized_username)}", error="Неверный код")

    token = generate_session_token()
    await create_session(pending["admin_id"], token)
    await _clear_pending_code(normalized_username, pending)
    await clear_dashboard_auth_failures(
        "verify_code",
        normalized_username,
        ip_address=_client_ip(request),
    )
    await clear_dashboard_auth_failures(
        "request_code",
        normalized_username,
        ip_address=_client_ip(request),
    )
    await _audit_dashboard_auth_event(
        request,
        "auth_verify_success",
        username=normalized_username,
        admin_id=pending.get("admin_id"),
    )

    response = _redirect("/dashboard/overview", notice="Вход выполнен")
    response.set_cookie(
        dashboard_settings()["cookie_name"],
        token,
        httponly=True,
        samesite="lax",
        secure=dashboard_settings()["cookie_secure"],
        max_age=dashboard_settings()["session_hours"] * 3600,
    )
    return response


@app.post("/logout")
async def logout(request: Request, admin=Depends(get_current_admin)):
    token = request.cookies.get(dashboard_settings()["cookie_name"])
    await delete_session(token)
    await create_audit_log(
        admin.id,
        "logout",
        "dashboard_admin",
        str(admin.id),
        json.dumps(
            {
                "admin": _dashboard_admin_audit_snapshot(admin),
                "session": {
                    "fingerprint": _session_fingerprint(request),
                    "had_cookie": bool(token),
                },
            },
            ensure_ascii=False,
        ),
        _client_ip(request),
    )
    response = _redirect("/login", notice="Сессия завершена")
    response.delete_cookie(
        dashboard_settings()["cookie_name"],
        httponly=True,
        samesite="lax",
        secure=dashboard_settings()["cookie_secure"],
    )
    return response


@app.get("/dashboard/overview")
async def dashboard_overview(request: Request):
    return _redirect_to_new_ui("/overview", request)


@app.get("/dashboard/users")
async def dashboard_users(request: Request):
    return _redirect_to_new_ui("/users", request)


@app.get("/dashboard/analytics")
async def dashboard_analytics(request: Request):
    return _redirect_to_new_ui("/analytics", request)


@app.get("/dashboard/vpn")
async def dashboard_vpn(request: Request):
    return _redirect_to_new_ui("/servers", request)


@app.get("/dashboard/users/{user_id}")
async def dashboard_user_detail(request: Request, user_id: int):
    return _redirect_to_new_ui("/users", request, user_id=user_id)


@app.post("/dashboard/users/{user_id}/trial")
async def user_trial(request: Request, user_id: int, admin=Depends(get_current_admin)):
    await grant_trial_to_user(user_id, admin, _client_ip(request))
    return _redirect(f"/users?user_id={user_id}", notice="Пробный доступ выдан")


@app.post("/dashboard/users/{user_id}/extend")
async def user_extend(request: Request, user_id: int, days: int = Form(...), admin=Depends(get_current_admin)):
    await extend_subscription_for_user(user_id, days, admin, _client_ip(request))
    return _redirect(f"/users?user_id={user_id}", notice="Подписка продлена")


@app.post("/dashboard/users/{user_id}/block")
async def user_block(request: Request, user_id: int, state: str = Form(...), admin=Depends(get_current_admin)):
    await set_user_block_state(user_id, state == "block", admin, _client_ip(request))
    return _redirect(f"/users?user_id={user_id}", notice="Статус пользователя обновлён")


@app.post("/dashboard/users/{user_id}/protocol")
async def user_protocol(request: Request, user_id: int, protocol: str = Form(...), admin=Depends(get_current_admin)):
    await set_user_preferred_protocol(user_id, protocol, admin, _client_ip(request))
    return _redirect(f"/users?user_id={user_id}", notice="Предпочтительный протокол обновлён")


@app.post("/dashboard/users/{user_id}/devices/create")
async def user_create_device(
    request: Request,
    user_id: int,
    device_name: str = Form(...),
    device_type: str = Form(...),
    protocol: str = Form(...),
    country_code: str = Form(...),
    admin=Depends(get_current_admin),
):
    try:
        await create_device_for_user(user_id, device_name, device_type, protocol, country_code, admin, _client_ip(request))
    except Exception as exc:
        return _redirect(f"/users?user_id={user_id}", error=str(exc))
    return _redirect(f"/users?user_id={user_id}", notice="Устройство создано")


@app.post("/dashboard/users/{user_id}/devices/{device_id}/delete")
async def user_delete_device(request: Request, user_id: int, device_id: int, admin=Depends(get_current_admin)):
    await delete_device_for_user(device_id, admin, _client_ip(request))
    return _redirect(f"/users?user_id={user_id}", notice="Устройство удалено")


@app.post("/dashboard/users/{user_id}/delete")
async def user_delete(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _redirect(f"/users?user_id={user_id}", error="Только владелец может удалять пользователей")
    try:
        deleted = await delete_user_with_access(user_id, admin, _client_ip(request))
    except Exception as exc:
        return _redirect(f"/users?user_id={user_id}", error=str(exc))
    if not deleted:
        return _redirect("/users", error="Пользователь не найден")
    return _redirect("/users", notice="Пользователь и его данные доступа удалены")


@app.get("/dashboard/support")
async def dashboard_support(request: Request):
    return _redirect_to_new_ui("/support", request)


@app.get("/dashboard/support/{ticket_user_id}")
async def dashboard_support_detail(request: Request, ticket_user_id: int):
    return _redirect_to_new_ui("/support", request, ticket_id=ticket_user_id)


@app.get("/dashboard/support/{ticket_user_id}/messages/{message_id}/attachment")
async def support_attachment(ticket_user_id: int, message_id: int, admin=Depends(get_current_admin)):
    del admin
    attachment = await get_support_attachment_content(ticket_user_id, message_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    headers = {
        "Content-Disposition": f'inline; filename="{attachment["filename"]}"',
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(iter([attachment["content"]]), media_type=attachment["media_type"], headers=headers)


@app.post("/dashboard/support/{ticket_user_id}/assign")
async def support_assign(request: Request, ticket_user_id: int, admin=Depends(get_current_admin)):
    detail = await assign_support_ticket_dashboard(ticket_user_id, admin, _client_ip(request))
    if detail is None:
        return _redirect("/support", error="Не удалось взять обращение")
    return _redirect(f"/support?ticket_id={ticket_user_id}", notice="Обращение закреплено за тобой")


@app.post("/dashboard/support/{ticket_user_id}/transfer")
async def support_transfer(
    request: Request,
    ticket_user_id: int,
    target_admin_id: int = Form(...),
    admin=Depends(get_current_admin),
):
    detail = await transfer_support_ticket_dashboard(ticket_user_id, target_admin_id, admin, _client_ip(request))
    if detail is None:
        return _redirect(f"/support?ticket_id={ticket_user_id}", error="Не удалось передать обращение")
    return _redirect(f"/support?ticket_id={ticket_user_id}", notice="Обращение передано")


@app.post("/dashboard/support/{ticket_user_id}/reply")
async def support_reply(request: Request, ticket_user_id: int, message: str = Form(...), admin=Depends(get_current_admin)):
    try:
        await send_support_reply(ticket_user_id, message.strip(), admin, _client_ip(request))
    except ValueError as exc:
        return _redirect(f"/support?ticket_id={ticket_user_id}", error=str(exc))
    return _redirect(f"/support?ticket_id={ticket_user_id}", notice="Ответ отправлен")


@app.post("/dashboard/support/{ticket_user_id}/close")
async def support_close(request: Request, ticket_user_id: int, admin=Depends(get_current_admin)):
    result = await close_support_ticket(ticket_user_id, admin, _client_ip(request))
    notice = "Обращение закрыто, пользователь уведомлён" if result.get("user_notified") else "Обращение закрыто"
    return _redirect(f"/support?ticket_id={ticket_user_id}", notice=notice)


@app.get("/dashboard/payments")
async def dashboard_payments(request: Request):
    return _redirect_to_new_ui("/payments", request)


@app.get("/dashboard/finance")
async def dashboard_finance(request: Request):
    return _redirect_to_new_ui("/payments", request)


@app.post("/dashboard/payments/create")
async def payments_create(
    request: Request,
    user_id: str = Form(""),
    payment_method: str = Form(...),
    tariff_code: str = Form(...),
    payment_status: str = Form(...),
    reference: str = Form(""),
    note: str = Form(""),
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может создавать платежи вручную")
    effective_user_id = int(user_id) if user_id.strip() else None
    await create_payment_record(
        effective_user_id,
        payment_method,
        tariff_code,
        payment_status,
        reference,
        note,
        admin,
        _client_ip(request),
    )
    return _redirect("/payments", notice="Платёж добавлен")


@app.post("/dashboard/payments/{record_id}/confirm")
async def payments_confirm(request: Request, record_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может подтверждать платежи")
    await confirm_payment_record(record_id, admin, _client_ip(request))
    return _redirect("/payments", notice="Платёж подтверждён")


@app.post("/dashboard/payments/{record_id}/reject")
async def payments_reject(
    request: Request,
    record_id: int,
    reason: str = Form(""),
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может отклонять платежи")
    await reject_payment_record(record_id, admin, _client_ip(request), reason or None)
    return _redirect("/payments", notice="Платёж отклонён")


@app.post("/dashboard/payments/ledger")
async def payments_ledger_create(
    request: Request,
    entry_type: str = Form(...),
    category: str = Form(...),
    amount: int = Form(...),
    note: str = Form(""),
    related_server: str = Form(""),
    admin=Depends(get_current_admin),
):
    if not role_has_permission(admin.role, "manage_finance"):
        return _redirect("/payments", error="Недостаточно прав")
    try:
        await create_finance_entry(entry_type, category, amount, note, related_server, admin, _client_ip(request))
    except Exception as exc:
        return _redirect("/payments", error=str(exc))
    return _redirect("/payments", notice="Транзакция учёта добавлена")


@app.post("/dashboard/finance/create")
async def finance_create(
    request: Request,
    entry_type: str = Form(...),
    category: str = Form(...),
    amount: int = Form(...),
    note: str = Form(""),
    related_server: str = Form(""),
    status: str = Form("draft"),
    counterparty_admin_id: str = Form(""),
    occurred_at: str = Form(""),
    admin=Depends(get_current_admin),
):
    if not role_has_permission(admin.role, "manage_finance"):
        return _redirect("/payments", error="Недостаточно прав")
    counterparty = int(counterparty_admin_id) if counterparty_admin_id.strip() else None
    occurred_point = None
    if occurred_at.strip():
        try:
            occurred_point = datetime.fromisoformat(occurred_at.strip())
        except ValueError:
            return _redirect("/payments", error="Некорректная дата операции")
    try:
        await create_finance_entry(
            entry_type,
            category,
            amount,
            note,
            related_server,
            admin,
            _client_ip(request),
            status=status,
            counterparty_admin_id=counterparty,
            occurred_at=occurred_point,
        )
    except Exception as exc:
        return _redirect("/payments", error=str(exc))
    return _redirect("/payments", notice="Финансовая запись добавлена")


@app.post("/dashboard/finance/{entry_id}/approve")
async def finance_approve(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может проводить запись")
    await approve_finance_entry(entry_id, admin, _client_ip(request))
    return _redirect("/payments", notice="Запись проведена")


@app.post("/dashboard/finance/{entry_id}/cancel")
async def finance_cancel(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может отменять запись")
    await cancel_finance_entry(entry_id, admin, _client_ip(request))
    return _redirect("/payments", notice="Запись отменена")


@app.post("/dashboard/finance/{entry_id}/delete")
async def finance_delete(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _redirect("/payments", error="Только владелец может удалять запись")
    deleted = await delete_finance_entry(entry_id, admin, _client_ip(request))
    if not deleted:
        return _redirect("/payments", error="Запись не найдена")
    return _redirect("/payments", notice="Финансовая запись удалена")


@app.post("/dashboard/finance/report")
async def dashboard_finance_report(request: Request, period_key: str = Form(""), admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_finance"):
        return _redirect("/payments", error="Недостаточно прав")
    report = await generate_finance_report(period_key or None, admin, _client_ip(request))
    return _redirect(f"/knowledge?doc={report['slug']}", notice="Финансовый отчёт обновлён")


@app.get("/dashboard/servers")
async def dashboard_servers(request: Request):
    return _redirect_to_new_ui("/servers", request)


@app.get("/dashboard/api/servers/snapshots")
async def dashboard_servers_api(force: int = 0, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_servers"):
        raise HTTPException(status_code=403)
    snapshots = await get_server_snapshots(force_refresh=bool(force))
    return {"snapshots": snapshots, "summary": summarize_server_snapshots(snapshots)}


@app.post("/dashboard/servers/create")
async def servers_create(
    request: Request,
    name: str = Form(...),
    host: str = Form(...),
    public_ip: str = Form(...),
    country_code: str = Form(...),
    country_name: str = Form(...),
    provider: str = Form(""),
    status: str = Form("active"),
    admin=Depends(get_current_admin),
):
    if not role_has_permission(admin.role, "manage_servers"):
        return _redirect("/servers", error="Недостаточно прав")
    await create_managed_server(name, host, public_ip, country_code, country_name, provider, status, admin, _client_ip(request))
    return _redirect("/servers", notice="Сервер добавлен")


@app.post("/dashboard/servers/{server_id}/status")
async def servers_status(request: Request, server_id: int, status: str = Form(...), admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_servers"):
        return _redirect("/servers", error="Недостаточно прав")
    await update_server_status(server_id, status, admin, _client_ip(request))
    return _redirect("/servers", notice="Статус сервера обновлён")


@app.post("/dashboard/api/servers/{server_id}/status")
async def servers_status_api(request: Request, server_id: int, status: str = Form(...), admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_servers"):
        return JSONResponse({"ok": False, "error": "Недостаточно прав"}, status_code=403)

    await update_server_status(server_id, status, admin, _client_ip(request))
    snapshots = await get_server_snapshots()
    summary = summarize_server_snapshots(snapshots)
    return JSONResponse(
        {
            "ok": True,
            "notice": "Статус сервера обновлён",
            "snapshots": snapshots,
            "summary": summary,
        }
    )


@app.get("/dashboard/services")
async def dashboard_services(request: Request):
    return _redirect_to_new_ui("/settings", request)


@app.post("/dashboard/services/action")
async def dashboard_services_action(
    request: Request,
    service_name: str = Form(...),
    action: str = Form(...),
    admin=Depends(get_current_admin),
):
    if not role_has_permission(admin.role, "manage_services"):
        return _redirect("/settings", error="Недостаточно прав")
    try:
        await run_service_action(action, service_name, admin, _client_ip(request))
    except Exception as exc:
        return _redirect("/settings", error=str(exc))
    return _redirect("/settings", notice="Команда отправлена")


@app.post("/dashboard/services/tariffs")
async def services_tariffs(
    request: Request,
    tariff_1m_rub: int = Form(...),
    tariff_3m_rub: int = Form(...),
    tariff_6m_rub: int = Form(...),
    tariff_12m_rub: int = Form(...),
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _redirect("/settings", error="Недостаточно прав")
    await update_tariffs(
        {
            "TARIFF_1M_RUB": tariff_1m_rub,
            "TARIFF_3M_RUB": tariff_3m_rub,
            "TARIFF_6M_RUB": tariff_6m_rub,
            "TARIFF_12M_RUB": tariff_12m_rub,
        },
        admin,
        _client_ip(request),
    )
    return _redirect("/settings", notice="Тарифы обновлены в .env")


@app.post("/dashboard/services/env")
async def services_env(
    request: Request,
    key: str = Form(...),
    value: str = Form(...),
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _redirect("/settings", error="Недостаточно прав")
    try:
        await update_env_value(key, value, admin, _client_ip(request))
    except Exception as exc:
        return _redirect("/settings", error=str(exc))
    return _redirect("/settings", notice="Переменная .env обновлена")


@app.get("/dashboard/docs")
async def dashboard_docs(request: Request):
    return _redirect_to_new_ui("/knowledge", request)


@app.post("/dashboard/docs/report")
async def dashboard_docs_report(request: Request, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_docs"):
        return _redirect("/knowledge", error="Недостаточно прав для генерации отчёта")

    report = await generate_operations_report(admin, _client_ip(request))
    return _redirect(f"/knowledge?doc={report['slug']}", notice="Операционный отчёт обновлён")


@app.api_route("/dashboard/api/v2/auth/request-code", methods=["GET", "POST"])
async def v2_auth_request_code(request: Request, payload: V2LoginRequest | None = Body(default=None)):
    if request.method == "GET":
        return _api_ok(
            {
                "method": "POST",
                "hint": "Используй POST с username и password, чтобы запросить код входа.",
            }
        )
    _assert_same_origin_for_cookie_request(request)
    if payload is None:
        return _api_error("Нужно передать username и password", 400)
    normalized_username = payload.username.strip()
    if await _hit_dashboard_auth_rate_limit(
        "request_code",
        request,
        normalized_username,
        limit=AUTH_REQUEST_LIMIT,
        window_seconds=AUTH_REQUEST_WINDOW_SECONDS,
    ):
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_rate_limited_v2",
            username=normalized_username,
        )
        return _api_error("Слишком много попыток. Подожди немного и попробуй снова.", 429)
    lockout = await get_dashboard_auth_lockout_state(
        "request_code",
        normalized_username,
        ip_address=_client_ip(request),
    )
    if lockout["locked"]:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_lockout_v2",
            username=normalized_username,
            details={"retry_after_seconds": int(lockout["retry_after_seconds"])},
        )
        return _api_error("Вход временно заблокирован из-за серии неудачных попыток.", 429)
    admin = await verify_admin_credentials(normalized_username, payload.password)
    if admin is None:
        await record_dashboard_auth_failure(
            "request_code",
            normalized_username,
            ip_address=_client_ip(request),
        )
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_invalid_credentials_v2",
            username=normalized_username,
        )
        return _api_error("Неверный логин или пароль", 401)
    await clear_dashboard_auth_failures(
        "request_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    if not admin.telegram_id:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_missing_telegram_v2",
            username=admin.username,
            admin_id=admin.id,
        )
        return _api_error("У администратора не указан Telegram ID", 400)

    try:
        await _request_dashboard_login_code(admin, "request_login_code_v2", _client_ip(request))
    except ValueError as exc:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_cooldown_v2",
            username=admin.username,
            admin_id=admin.id,
            details={"reason": str(exc)},
        )
        return _api_error(str(exc), 429)
    except Exception:
        await _audit_dashboard_auth_event(
            request,
            "auth_request_code_delivery_failed_v2",
            username=admin.username,
            admin_id=admin.id,
        )
        return _api_error("Не удалось отправить код в Telegram", 500)

    await clear_dashboard_auth_failures(
        "request_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    await clear_dashboard_auth_failures(
        "verify_code",
        admin.username,
        ip_address=_client_ip(request),
    )
    return _api_ok(
        {
            "username": admin.username,
            "delivery": {
                "bot": "@amonora_control_bot",
                "telegram_id": admin.telegram_id,
            },
        },
        "Код отправлен в @amonora_control_bot",
    )


@app.api_route("/dashboard/api/v2/auth/verify", methods=["GET", "POST"])
async def v2_auth_verify(request: Request, payload: V2VerifyRequest | None = Body(default=None)):
    if request.method == "GET":
        return _api_ok(
            {
                "method": "POST",
                "hint": "Используй POST с username и code, чтобы подтвердить вход.",
            }
        )
    _assert_same_origin_for_cookie_request(request)
    if payload is None:
        return _api_error("Нужно передать username и code", 400)
    username = payload.username.strip()
    if await _hit_dashboard_auth_rate_limit(
        "verify_code",
        request,
        username,
        limit=AUTH_VERIFY_LIMIT,
        window_seconds=AUTH_VERIFY_WINDOW_SECONDS,
    ):
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_rate_limited_v2",
            username=username,
        )
        return _api_error("Слишком много попыток. Запроси новый код позже.", 429)
    lockout = await get_dashboard_auth_lockout_state(
        "verify_code",
        username,
        ip_address=_client_ip(request),
    )
    if lockout["locked"]:
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_lockout_v2",
            username=username,
            details={"retry_after_seconds": int(lockout["retry_after_seconds"])},
        )
        return _api_error("Проверка кода временно заблокирована из-за серии неудачных попыток.", 429)
    await _purge_expired_pending_codes()
    pending = _PENDING_CODES.get(username)
    if pending is None:
        db_pending = await get_pending_dashboard_login_code(username)
        if db_pending is not None:
            pending = {
                "code_hash": db_pending.code_hash,
                "admin_id": db_pending.admin_id,
                "telegram_id": db_pending.telegram_id,
                "message_id": db_pending.message_id,
                "bot_key": db_pending.bot_key,
                "attempts": int(db_pending.attempts or 0),
                "expires_at": db_pending.expires_at,
                "created_at": db_pending.created_at,
            }
            _PENDING_CODES[username] = pending
    if pending is None:
        await record_dashboard_auth_failure(
            "verify_code",
            username,
            ip_address=_client_ip(request),
        )
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_code_missing_v2",
            username=username,
        )
        return _api_error("Код истёк. Войди снова.", 401)
    if not _code_matches(payload.code, pending["code_hash"]):
        updated_pending = await increment_dashboard_login_code_attempts(username)
        pending["attempts"] = int(updated_pending.attempts if updated_pending is not None else int(pending.get("attempts") or 0) + 1)
        await record_dashboard_auth_failure(
            "verify_code",
            username,
            ip_address=_client_ip(request),
        )
        if pending["attempts"] >= MAX_LOGIN_CODE_ATTEMPTS:
            await _audit_dashboard_auth_event(
                request,
                "auth_verify_attempts_exceeded_v2",
                username=username,
                admin_id=pending.get("admin_id"),
                details={"attempts": pending["attempts"]},
            )
            await _clear_pending_code(username, pending)
            return _api_error("Превышено число попыток. Запроси новый код.", 401)
        await _audit_dashboard_auth_event(
            request,
            "auth_verify_invalid_code_v2",
            username=username,
            admin_id=pending.get("admin_id"),
            details={"attempts": pending["attempts"]},
        )
        return _api_error("Неверный код", 401)

    token = generate_session_token()
    await create_session(pending["admin_id"], token)
    await _clear_pending_code(username, pending)
    await clear_dashboard_auth_failures(
        "verify_code",
        username,
        ip_address=_client_ip(request),
    )
    await clear_dashboard_auth_failures(
        "request_code",
        username,
        ip_address=_client_ip(request),
    )
    admin = await get_admin_by_session(token)
    await _audit_dashboard_auth_event(
        request,
        "auth_verify_success_v2",
        username=username,
        admin_id=pending.get("admin_id"),
    )
    response = _api_ok({"session": await get_v2_session_payload(admin)}, "Вход выполнен")
    response.set_cookie(
        dashboard_settings()["cookie_name"],
        token,
        httponly=True,
        samesite="lax",
        secure=dashboard_settings()["cookie_secure"],
        max_age=dashboard_settings()["session_hours"] * 3600,
    )
    return response


@app.post("/dashboard/api/v2/profile/avatar")
async def v2_profile_avatar(request: Request, avatar: UploadFile = File(...), admin=Depends(get_current_admin)):
    try:
        image_bytes = await avatar.read()
        updated_admin = await update_admin_avatar(admin, image_bytes, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    return _api_ok({"session": await get_v2_session_payload(updated_admin)}, "Аватар обновлён")


@app.post("/dashboard/api/v2/auth/logout")
async def v2_auth_logout(request: Request, admin=Depends(get_current_admin)):
    token = request.cookies.get(dashboard_settings()["cookie_name"])
    await delete_session(token)
    await create_audit_log(
        admin.id,
        "logout_v2",
        "dashboard_admin",
        str(admin.id),
        json.dumps(
            {
                "admin": _dashboard_admin_audit_snapshot(admin),
                "session": {
                    "fingerprint": _session_fingerprint(request),
                    "had_cookie": bool(token),
                },
            },
            ensure_ascii=False,
        ),
        _client_ip(request),
    )
    response = _api_ok(notice="Сессия завершена")
    response.delete_cookie(
        dashboard_settings()["cookie_name"],
        httponly=True,
        samesite="lax",
        secure=dashboard_settings()["cookie_secure"],
    )
    return response


@app.get("/dashboard/api/v2/session")
async def v2_session(admin=Depends(get_current_admin)):
    return _api_ok(await get_v2_session_payload(admin))


@app.get("/dashboard/api/v2/search")
async def v2_search(q: str = "", admin=Depends(get_current_admin)):
    payload = await _get_v2_cached_payload(_cache_key("search", q.strip(), admin.id), 10, lambda: get_v2_search_payload(q, admin=admin))
    return _api_ok(payload)


@app.get("/dashboard/api/v2/notifications")
async def v2_notifications(admin=Depends(get_current_admin)):
    payload = await _get_v2_cached_payload(_cache_key("notifications", admin.id), 30, get_v2_notifications_payload)
    return _api_ok(payload)


@app.get("/dashboard/api/v2/audit")
async def v2_audit(limit: int = 150, admin=Depends(get_current_admin)):
    safe_limit = min(max(int(limit or 150), 20), 300)
    payload = await _get_v2_cached_payload(_cache_key("audit", safe_limit, admin.id), 30, lambda: get_v2_audit_payload(limit=safe_limit))
    return _api_ok(payload)


@app.get("/dashboard/api/v2/overview")
async def v2_overview(admin=Depends(get_current_admin)):
    payload = await _get_v2_cached_payload("overview", 45, get_v2_overview_payload)
    return _api_ok(payload)


@app.get("/dashboard/api/v2/users")
async def v2_users(
    q: str = "",
    status: str = "all",
    plan: str = "all",
    issue: str = "all",
    page: int = 1,
    page_size: int = 100,
    admin=Depends(get_current_admin),
):
    permission_error = _require_any_permission(admin, "manage_users")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("users", q.strip(), status, plan, issue, int(page or 1), int(page_size or 100)),
        20,
        lambda: get_v2_users_payload(
            q,
            status_filter=status,
            plan_filter=plan,
            issue_filter=issue,
            page=page,
            page_size=page_size,
        ),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/users/{user_id}")
async def v2_user_detail(user_id: int, force: int = 0, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_users")
    if permission_error is not None:
        return permission_error
    detail = await _get_v2_cached_payload(
        _cache_key("user-detail", user_id),
        15,
        lambda: get_v2_user_detail_payload(user_id),
        bypass=bool(force),
    )
    if detail is None:
        return _api_error("Пользователь не найден", 404)
    return _api_ok(detail)


@app.post("/dashboard/api/v2/users/{user_id}/trial")
async def v2_user_trial(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    action_result = await grant_trial_to_user(user_id, admin, _client_ip(request))
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    payload = {**detail, "action_result": action_result} if detail else detail
    notice = "Пробный доступ выдан" if not action_result["sync_failed"] else "Пробный доступ выдан, но часть устройств требует ручной проверки"
    return _api_ok(payload, notice)


@app.post("/dashboard/api/v2/users/{user_id}/extend")
async def v2_user_extend(request: Request, user_id: int, payload: V2ExtendRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    action_result = await extend_subscription_for_user(user_id, payload.days, admin, _client_ip(request))
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    payload_data = {**detail, "action_result": action_result} if detail else detail
    notice = "Подписка продлена" if not action_result["sync_failed"] else "Подписка продлена, но часть устройств требует ручной проверки"
    return _api_ok(payload_data, notice)


@app.post("/dashboard/api/v2/users/{user_id}/block")
async def v2_user_block(request: Request, user_id: int, payload: V2BlockRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    action_result = await set_user_block_state(user_id, payload.blocked, admin, _client_ip(request))
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    payload_data = {**detail, "action_result": action_result} if detail else detail
    notice = "Статус пользователя обновлён" if not action_result["sync_failed"] else "Статус пользователя обновлён, но часть устройств требует ручной проверки"
    return _api_ok(payload_data, notice)


@app.post("/dashboard/api/v2/users/{user_id}/clear-access")
async def v2_user_clear_access(
    request: Request,
    user_id: int,
    payload: V2ClearAccessRequest | None = None,
    admin=Depends(get_current_admin),
):
    if not role_has_permission(admin.role, "clear_access"):
        return _api_error("Недостаточно прав", 403)
    try:
        action_result = await remove_user_tariff(user_id, admin, _client_ip(request))
        if payload and payload.remove_devices:
            detail_before_delete = await get_user_detail(user_id)
            if detail_before_delete:
                for device in detail_before_delete.get("devices", []):
                    await delete_device_for_user(int(device["id"]), admin, _client_ip(request))
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    payload_data = {**detail, "action_result": action_result} if detail else detail
    notice = "Тариф снят и доступ отключён" if not action_result["sync_failed"] else "Тариф снят, но часть устройств требует ручной проверки"
    return _api_ok(payload_data, notice)


@app.post("/dashboard/api/v2/users/{user_id}/repair-vpn")
async def v2_user_repair_vpn(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "run_sync"):
        return _api_error("Недостаточно прав", 403)
    try:
        result = await repair_user_vpn_access(user_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 404)

    await _invalidate_v2_cache(_cache_key("user-detail", user_id))
    notice = "Синхронизация доступа выполнена" if not result["sync_failed"] else "Доступ по-прежнему требует ручной проверки"
    return _api_ok(result, notice)


@app.post("/dashboard/api/v2/users/{user_id}/sync")
async def v2_user_sync(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "run_sync"):
        return _api_error("Недостаточно прав", 403)
    try:
        result = await sync_user_access_state(user_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 404)
    await _invalidate_v2_cache()
    notice = "Синхронизация выполнена" if not result["sync_failed"] else "Синхронизация завершилась с ошибками"
    return _api_ok(result, notice)


@app.post("/dashboard/api/v2/users/{user_id}/deep-repair")
async def v2_user_deep_repair(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "run_deep_repair"):
        return _api_error("Недостаточно прав", 403)
    try:
        result = await deep_repair_user_access(user_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 404)
    await _invalidate_v2_cache()
    notice = "Глубокий ремонт выполнен" if not result["sync_failed"] else "Глубокий ремонт завершился с ошибками"
    return _api_ok(result, notice)


@app.post("/dashboard/api/v2/users/{user_id}/protocol")
async def v2_user_protocol(request: Request, user_id: int, payload: V2ProtocolRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    await set_user_preferred_protocol(user_id, payload.protocol, admin, _client_ip(request))
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    return _api_ok(detail, "Предпочтительный протокол обновлён")


@app.post("/dashboard/api/v2/users/{user_id}/devices")
async def v2_user_create_device(request: Request, user_id: int, payload: V2CreateDeviceRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    try:
        await create_device_for_user(
            user_id,
            payload.device_name,
            payload.device_type,
            payload.protocol,
            payload.country_code,
            admin,
            _client_ip(request),
        )
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    return _api_ok(detail, "Устройство создано")


@app.post("/dashboard/api/v2/users/{user_id}/devices/{device_id}/delete")
async def v2_user_delete_device(request: Request, user_id: int, device_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    await delete_device_for_user(device_id, admin, _client_ip(request))
    await _invalidate_v2_cache()
    detail = await get_v2_user_detail_payload(user_id)
    return _api_ok(detail, "Устройство удалено")


@app.post("/dashboard/api/v2/users/{user_id}/devices/{device_id}/status")
async def v2_user_device_status(user_id: int, device_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_users"):
        return _api_error("Недостаточно прав", 403)
    payload = await get_user_device_status_payload(user_id, device_id)
    if payload is None:
        return _api_error("Устройство не найдено", 404)
    return _api_ok(payload, "Статус устройства обновлён")


@app.post("/dashboard/api/v2/users/{user_id}/delete")
async def v2_user_delete(request: Request, user_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может удалять пользователей", 403)
    try:
        deleted = await delete_user_with_access(user_id, admin, _client_ip(request))
    except Exception as exc:
        return _api_error(str(exc), 400)
    if not deleted:
        return _api_error("Пользователь не найден", 404)
    await _invalidate_v2_cache()
    return _api_ok({"deleted_user_id": user_id}, "Пользователь и его данные доступа удалены")


@app.get("/dashboard/api/v2/servers")
async def v2_servers(server_id: int | None = None, force: int = 0, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_servers")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("servers", server_id),
        45,
        lambda: get_v2_servers_payload(server_id=server_id, force_refresh=bool(force)),
        bypass=bool(force),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/servers/{server_id}")
async def v2_server_detail(server_id: int, force: int = 0, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_servers")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("servers", server_id),
        45,
        lambda: get_v2_servers_payload(server_id=server_id, force_refresh=bool(force)),
        bypass=bool(force),
    )
    if payload["selected_node"] is None:
        return _api_error("Сервер не найден", 404)
    return _api_ok(payload)


@app.post("/dashboard/api/v2/servers")
async def v2_server_create(request: Request, payload: V2CreateServerRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_servers"):
        return _api_error("Недостаточно прав", 403)
    await create_managed_server(
        payload.name,
        payload.host,
        payload.public_ip,
        payload.country_code,
        payload.country_name,
        payload.provider,
        payload.status,
        admin,
        _client_ip(request),
    )
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_servers_payload(force_refresh=True), "Сервер добавлен")


@app.post("/dashboard/api/v2/servers/{server_id}/status")
async def v2_server_status(request: Request, server_id: int, payload: V2ServerStatusRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_servers"):
        return _api_error("Недостаточно прав", 403)
    await update_server_status(server_id, payload.status, admin, _client_ip(request))
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_servers_payload(server_id=server_id, force_refresh=True), "Статус сервера обновлён")


@app.post("/dashboard/api/v2/servers/{server_id}/action")
async def v2_server_action(request: Request, server_id: int, payload: V2ServerActionRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_server_actions"):
        return _api_error("Недостаточно прав", 403)
    try:
        action_result = await run_server_action(
            server_id,
            payload.action,
            admin,
            _client_ip(request),
            target_server_id=payload.target_server_id,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(
        {
            "action_result": action_result,
            "servers": await get_v2_servers_payload(server_id=server_id, force_refresh=True),
        },
        "Серверное действие выполнено",
    )


@app.get("/dashboard/api/v2/traffic")
async def v2_traffic(force: int = 0, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_servers")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        "traffic",
        45,
        lambda: get_v2_traffic_payload(force_refresh=bool(force)),
        bypass=bool(force),
    )
    return _api_ok(payload)


@app.post("/dashboard/api/v2/traffic/reset")
async def v2_traffic_reset(request: Request, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_servers")
    if permission_error is not None:
        return permission_error
    await reset_traffic_baseline(admin, _client_ip(request))
    await _invalidate_v2_cache("traffic", "overview")
    return _api_ok(await get_v2_traffic_payload(force_refresh=True), "Накопленный трафик сброшен")


@app.get("/dashboard/api/v2/payments")
async def v2_payments(
    record_id: int | None = None,
    period_key: str = "",
    q: str = "",
    status: str = "all",
    method: str = "all",
    issue: str = "all",
    admin=Depends(get_current_admin),
):
    permission_error = _require_any_permission(admin, "manage_payments", "manage_finance", "approve_finance")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("payments", record_id, period_key or "", q.strip().lower(), status, method, issue, admin.id),
        5,
        lambda: get_v2_payments_payload(
            record_id=record_id,
            period_key=period_key or None,
            search=q,
            status_filter=status,
            method_filter=method,
            issue_filter=issue,
            admin=admin,
        ),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/analytics/campaigns")
async def v2_campaign_analytics(
    q: str = "",
    period_key: str = "",
    date_from: str = "",
    date_to: str = "",
    admin=Depends(get_current_admin),
):
    permission_error = _require_any_permission(admin, "manage_payments")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("analytics-campaigns", q.strip().lower(), period_key, date_from, date_to, admin.id),
        10,
        lambda: get_v2_campaign_analytics_payload(
            search=q,
            period_key=period_key,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/analytics/campaigns/{campaign_id}")
async def v2_campaign_analytics_detail(
    campaign_id: int,
    period_key: str = "",
    date_from: str = "",
    date_to: str = "",
    admin=Depends(get_current_admin),
):
    permission_error = _require_any_permission(admin, "manage_payments")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("analytics-campaign-detail", campaign_id, period_key, date_from, date_to, admin.id),
        10,
        lambda: get_v2_campaign_analytics_detail_payload(
            campaign_id,
            period_key=period_key,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    if payload is None:
        return _api_error("Кампания не найдена", 404)
    return _api_ok(payload)


@app.post("/dashboard/api/v2/analytics/campaigns")
async def v2_campaign_analytics_create(request: Request, payload: V2CreateCampaignRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_payments"):
        return _api_error("Недостаточно прав", 403)
    topic_brief = str(payload.topic_brief or "").strip()
    if not topic_brief:
        return _api_error("Укажи название кампании", 400)
    item = await create_channel_content_item(
        content_type=CHANNEL_CONTENT_TYPE_OFFER,
        topic_brief=topic_brief,
        scheduled_at=utcnow(),
        cta_label=str(payload.cta_label or "").strip() or "Попробовать бесплатно",
    )
    await create_audit_log(
        admin.id,
        "create_campaign_tracking",
        "channel_content_item",
        str(item.id),
        (
            f"Создал трекинг-кампанию: {topic_brief} "
            f"(CTA: {str(item.cta_label or '').strip() or 'Попробовать бесплатно'}, "
            f"token: {str(item.deep_link_token or '').strip().lower()})"
        ),
        _client_ip(request),
    )
    await _invalidate_v2_cache("analytics-campaigns", "analytics-campaign-detail")
    return _api_ok(await get_v2_campaign_analytics_detail_payload(int(item.id)), "Кампания создана")


@app.post("/dashboard/api/v2/payments")
async def v2_payments_create(request: Request, payload: V2CreatePaymentRequest, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может создавать платежи вручную", 403)
    try:
        created = await create_payment_record(
            payload.user_id,
            payload.payment_method,
            payload.tariff_code,
            payload.payment_status,
            payload.reference,
            payload.note,
            admin,
            _client_ip(request),
        )
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(
        {
            "record": await get_payment_focus(created.id if created else None),
            "payments": await get_v2_payments_payload(record_id=created.id if created else None, admin=admin),
        },
        "Платёж добавлен",
    )


@app.post("/dashboard/api/v2/payments/{record_id}/confirm")
async def v2_payments_confirm(request: Request, record_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может подтверждать платежи", 403)
    try:
        await confirm_payment_record(record_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=record_id, admin=admin), "Платёж подтверждён")


@app.post("/dashboard/api/v2/payments/{record_id}/reject")
async def v2_payments_reject(request: Request, record_id: int, payload: V2RejectPaymentRequest, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может отклонять платежи", 403)
    try:
        await reject_payment_record(record_id, admin, _client_ip(request), payload.reason or None)
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=record_id, admin=admin), "Платёж отклонён")


@app.post("/dashboard/api/v2/payments/{record_id}/status")
async def v2_payments_set_status(request: Request, record_id: int, payload: V2PaymentStatusRequest, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может менять статус платежа", 403)
    try:
        record = await set_payment_record_status(
            record_id,
            payload.payment_status,
            admin,
            _client_ip(request),
            reason=payload.reason or None,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    if record is None:
        return _api_error("Платёж не найден", 404)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=record_id, admin=admin), "Статус платежа обновлён")


@app.post("/dashboard/api/v2/payments/{record_id}/sync")
async def v2_payments_sync_provider(request: Request, record_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_payments"):
        return _api_error("Недостаточно прав", 403)
    try:
        await sync_payment_record_with_provider(record_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=record_id, admin=admin), "Платёж синхронизирован с провайдером")


@app.post("/dashboard/api/v2/payments/{record_id}/remind")
async def v2_payments_remind_user(request: Request, record_id: int, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_payments"):
        return _api_error("Недостаточно прав", 403)
    try:
        await send_manual_payment_reminder(record_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=record_id, admin=admin), "Напоминание отправлено пользователю")


@app.post("/dashboard/api/v2/payments/{record_id}/delete")
async def v2_payments_delete(request: Request, record_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может удалять платежи", 403)
    try:
        deleted = await delete_payment_record(record_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    if not deleted:
        return _api_error("Платёж не найден", 404)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(record_id=None, admin=admin), "Платёж удалён")


@app.get("/dashboard/api/v2/promocodes")
async def v2_promocodes(
    q: str = "",
    kind: str = "all",
    status: str = "all",
    admin=Depends(get_current_admin),
):
    permission_error = _require_any_permission(admin, "manage_payments")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("promocodes", q.strip().lower(), kind, status, admin.id),
        5,
        lambda: get_v2_promocodes_payload(search=q, kind_filter=kind, status_filter=status),
    )
    return _api_ok(payload)


@app.post("/dashboard/api/v2/promocodes")
async def v2_promocodes_create(payload: V2CreatePromoCodeRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_payments"):
        return _api_error("Недостаточно прав", 403)
    try:
        await create_promo_code(
            code=payload.code or None,
            kind=payload.kind,
            title=payload.title or None,
            description=payload.description or None,
            discount_percent=payload.discount_percent,
            grant_days=payload.grant_days,
            max_redemptions=payload.max_redemptions,
            created_by_admin_id=int(admin.id),
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache("promocodes")
    return _api_ok(await get_v2_promocodes_payload(), "Промокод создан")


@app.get("/dashboard/api/v2/finance")
async def v2_finance(admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_finance", "approve_finance")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("finance", admin.id),
        20,
        lambda: get_v2_payments_payload(record_id=None, admin=admin),
    )
    return _api_ok(payload["finance"])


@app.post("/dashboard/api/v2/finance")
async def v2_finance_create(request: Request, payload: V2CreateFinanceRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_finance"):
        return _api_error("Недостаточно прав", 403)
    occurred_point = None
    if payload.occurred_at.strip():
        try:
            occurred_point = datetime.fromisoformat(payload.occurred_at.strip())
        except ValueError:
            return _api_error("Некорректная дата операции")
    try:
        entry = await create_finance_entry(
            payload.entry_type,
            payload.category,
            payload.amount,
            payload.note,
            payload.related_server,
            admin,
            _client_ip(request),
            status=payload.status,
            counterparty_admin_id=payload.counterparty_admin_id,
            occurred_at=occurred_point,
        )
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok({"entry": entry, "payments": await get_v2_payments_payload(record_id=None, admin=admin)}, "Финансовая запись добавлена")


@app.post("/dashboard/api/v2/finance/{entry_id}/approve")
async def v2_finance_approve(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может проводить запись", 403)
    await approve_finance_entry(entry_id, admin, _client_ip(request))
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(admin=admin), "Запись проведена")


@app.post("/dashboard/api/v2/finance/{entry_id}/cancel")
async def v2_finance_cancel(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может отменять запись", 403)
    await cancel_finance_entry(entry_id, admin, _client_ip(request))
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(admin=admin), "Запись отменена")


@app.post("/dashboard/api/v2/finance/{entry_id}/delete")
async def v2_finance_delete(request: Request, entry_id: int, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может удалять запись", 403)
    deleted = await delete_finance_entry(entry_id, admin, _client_ip(request))
    if not deleted:
        return _api_error("Запись не найдена", 404)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_payments_payload(admin=admin), "Финансовая запись удалена")


@app.post("/dashboard/api/v2/finance/report")
async def v2_finance_report(request: Request, payload: dict | None = None, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_finance"):
        return _api_error("Недостаточно прав", 403)
    period_key = (payload or {}).get("period_key") if payload else None
    report = await generate_finance_report(period_key or None, admin, _client_ip(request))
    await _invalidate_v2_cache()
    return _api_ok(report, "Финансовый отчёт обновлён")


@app.get("/dashboard/api/v2/support")
async def v2_support(filter_mode: str = "queue", q: str = "", ticket_id: int | None = None, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("support", filter_mode, q.strip(), ticket_id, admin.id),
        8,
        lambda: get_v2_support_payload(filter_mode, q, ticket_id, admin),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/support/{ticket_user_id}")
async def v2_support_detail(ticket_user_id: int, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    detail = await _get_v2_cached_payload(
        _cache_key("support-detail", ticket_user_id),
        8,
        lambda: get_support_ticket_detail(ticket_user_id),
    )
    if detail is None:
        return _api_error("Обращение не найдено", 404)
    return _api_ok(await get_v2_support_payload(ticket_id=ticket_user_id, admin=admin))


@app.post("/dashboard/api/v2/support/{ticket_user_id}/assign")
async def v2_support_assign(request: Request, ticket_user_id: int, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    detail = await assign_support_ticket_dashboard(ticket_user_id, admin, _client_ip(request))
    if detail is None:
        return _api_error("Не удалось взять обращение", 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_support_payload(ticket_id=ticket_user_id, admin=admin), "Обращение закреплено за тобой")


@app.post("/dashboard/api/v2/support/{ticket_user_id}/transfer")
async def v2_support_transfer(request: Request, ticket_user_id: int, payload: V2SupportTransferRequest, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    try:
        detail = await transfer_support_ticket_dashboard(ticket_user_id, payload.target_admin_id, admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    if detail is None:
        return _api_error("Не удалось передать обращение", 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_support_payload(ticket_id=ticket_user_id, admin=admin), "Обращение передано")


@app.post("/dashboard/api/v2/support/{ticket_user_id}/reply")
async def v2_support_reply(request: Request, ticket_user_id: int, payload: V2SupportReplyRequest, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    try:
        await send_support_reply(ticket_user_id, payload.message.strip(), admin, _client_ip(request))
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_support_payload(ticket_id=ticket_user_id, admin=admin), "Ответ отправлен")


@app.post("/dashboard/api/v2/support/{ticket_user_id}/close")
async def v2_support_close(request: Request, ticket_user_id: int, admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_support")
    if permission_error is not None:
        return permission_error
    result = await close_support_ticket(ticket_user_id, admin, _client_ip(request))
    await _invalidate_v2_cache()
    payload = await get_v2_support_payload(admin=admin)
    if isinstance(payload, dict):
        payload = {**payload, "close_result": result}
    notice = "Обращение закрыто, пользователь уведомлён" if result.get("user_notified") else "Обращение закрыто"
    return _api_ok(payload, notice)


@app.get("/dashboard/api/v2/settings")
async def v2_settings(doc: str = "", admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_services", "manage_docs")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("settings", doc or ""),
        45,
        lambda: get_v2_settings_payload(doc or None),
    )
    return _api_ok(payload)


@app.get("/dashboard/api/v2/knowledge")
async def v2_knowledge(doc: str = "", admin=Depends(get_current_admin)):
    permission_error = _require_any_permission(admin, "manage_docs")
    if permission_error is not None:
        return permission_error
    payload = await _get_v2_cached_payload(
        _cache_key("knowledge", doc or ""),
        45,
        lambda: get_v2_knowledge_payload(doc or None),
    )
    return _api_ok(payload)


@app.post("/dashboard/api/v2/settings/services/action")
async def v2_settings_service_action(request: Request, payload: V2ServiceActionRequest, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_services"):
        return _api_error("Недостаточно прав", 403)
    try:
        action_result = await run_service_action(payload.action, payload.service_name, admin, _client_ip(request))
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    settings_payload = await get_v2_settings_payload()
    if isinstance(settings_payload, dict):
        settings_payload = {**settings_payload, "service_action_result": action_result}
    return _api_ok(settings_payload, "Команда отправлена")


@app.post("/dashboard/api/v2/settings/tariffs")
async def v2_settings_tariffs(request: Request, payload: V2TariffsRequest, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Недостаточно прав", 403)
    await update_tariffs(
        {
            "TARIFF_1M_RUB": payload.tariff_1m_rub,
            "TARIFF_3M_RUB": payload.tariff_3m_rub,
            "TARIFF_6M_RUB": payload.tariff_6m_rub,
            "TARIFF_12M_RUB": payload.tariff_12m_rub,
        },
        admin,
        _client_ip(request),
    )
    await _invalidate_v2_cache()
    return _api_ok(await get_v2_settings_payload(), "Тарифы обновлены")


@app.post("/dashboard/api/v2/settings/env")
async def v2_settings_env(request: Request, payload: V2EnvRequest, admin=Depends(get_current_admin)):
    if not _is_owner(admin):
        return _api_error("Только владелец может менять .env", 403)
    try:
        update_result = await update_env_value(
            payload.key,
            payload.value,
            admin,
            _client_ip(request),
            apply_runtime=bool(payload.apply_runtime),
        )
    except Exception as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    settings_payload = await get_v2_settings_payload()
    if isinstance(settings_payload, dict):
        settings_payload = {**settings_payload, "env_update_result": update_result}
    if update_result.get("runtime_apply") and not update_result.get("restart_required"):
        notice = "Переменная .env обновлена и применена"
    elif update_result.get("restart_required"):
        notice = "Переменная .env обновлена, нужен restart сервисов"
    else:
        notice = "Переменная .env обновлена"
    return _api_ok(settings_payload, notice)


@app.post("/dashboard/api/v2/settings/admins/{target_admin_id}")
async def v2_settings_admin_access(
    request: Request,
    target_admin_id: int,
    payload: V2UpdateAdminAccessRequest,
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _api_error("Недостаточно прав", 403)
    try:
        updated = await update_dashboard_admin_access(
            target_admin_id,
            payload.role,
            payload.is_active,
            admin,
            _client_ip(request),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    if updated is None:
        return _api_error("Администратор не найден", 404)
    await _invalidate_v2_cache()
    settings_payload = await get_v2_settings_payload()
    if isinstance(settings_payload, dict):
        settings_payload = {**settings_payload, "updated_admin": updated}
    return _api_ok(settings_payload, "Доступ администратора обновлён")


@app.post("/dashboard/api/v2/settings/notifications")
async def v2_settings_notifications(
    request: Request,
    payload: V2NotificationPreferenceRequest,
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        if int(admin.telegram_id or 0) != int(payload.telegram_id):
            return _api_error("Недостаточно прав", 403)
    before_preferences = await get_notification_preferences(int(payload.telegram_id))
    updated_preferences = await set_notification_preference(
        int(payload.telegram_id),
        payload.category,
        bool(payload.enabled),
    )
    await create_audit_log(
        admin.id,
        "update_notification_preference",
        "dashboard_admin",
        str(payload.telegram_id),
        json.dumps(
            {
                "admin": _dashboard_admin_audit_snapshot(admin),
                "before": {
                    "telegram_id": int(payload.telegram_id),
                    "category": payload.category,
                    "enabled": bool(before_preferences.get(payload.category, True)),
                    "preferences": before_preferences,
                },
                "after": {
                    "telegram_id": int(payload.telegram_id),
                    "category": payload.category,
                    "enabled": bool(payload.enabled),
                    "preferences": updated_preferences,
                },
            },
            ensure_ascii=False,
        ),
        _client_ip(request),
    )
    await _invalidate_v2_cache()
    settings_payload = await get_v2_settings_payload()
    if isinstance(settings_payload, dict):
        settings_payload = {
            **settings_payload,
            "updated_notification_preference": {
                "telegram_id": int(payload.telegram_id),
                "category": payload.category,
                "enabled": bool(payload.enabled),
                "preferences": updated_preferences,
            },
        }
    return _api_ok(settings_payload, "Настройки уведомлений обновлены")


@app.post("/dashboard/api/v2/settings/permissions")
async def v2_settings_permissions(
    request: Request,
    payload: V2RolePermissionOverrideRequest,
    admin=Depends(get_current_admin),
):
    if not _is_owner(admin):
        return _api_error("Недостаточно прав", 403)
    try:
        update_result = await update_role_permission_override(
            payload.role,
            payload.permission,
            bool(payload.enabled),
            admin,
            _client_ip(request),
        )
    except ValueError as exc:
        return _api_error(str(exc), 400)
    await _invalidate_v2_cache()
    settings_payload = await get_v2_settings_payload()
    if isinstance(settings_payload, dict):
        settings_payload = {**settings_payload, "updated_role_permission": update_result}
    return _api_ok(settings_payload, "Разрешение обновлено")


@app.post("/dashboard/api/v2/settings/docs/report")
async def v2_settings_docs_report(request: Request, admin=Depends(get_current_admin)):
    if not role_has_permission(admin.role, "manage_docs"):
        return _api_error("Недостаточно прав", 403)
    report = await generate_operations_report(admin, _client_ip(request))
    await _invalidate_v2_cache("settings")
    return _api_ok(report, "Операционный отчёт обновлён")

# ===== Маркетинговые кампании =====

@app.get("/dashboard/campaigns")
async def dashboard_campaigns(request: Request, admin=Depends(get_current_admin)):
    """Страница маркетинговых кампаний."""
    from dashboard.services import get_marketing_campaigns
    campaigns = await get_marketing_campaigns()
    return templates.TemplateResponse(
        "campaigns.html",
        {"request": request, "admin": admin, "campaigns": campaigns},
    )


@app.post("/dashboard/campaigns/create")
async def campaign_create(
    request: Request,
    name: str = Form(...),
    cta_label: str = Form("Попробовать бесплатно"),
    admin=Depends(get_current_admin),
):
    """Создать новую кампанию."""
    from dashboard.services import create_marketing_campaign
    campaign = await create_marketing_campaign(
        name=name, cta_label=cta_label, admin=admin, ip_address=_client_ip(request),
    )
    return _redirect("/dashboard/campaigns", notice=f"Кампания '{campaign.name}' создана")


@app.get("/dashboard/campaigns/{campaign_id}")
async def campaign_detail(request: Request, campaign_id: int, admin=Depends(get_current_admin)):
    """Детальная страница кампании."""
    from dashboard.services import get_marketing_campaign_detail, get_campaign_funnel
    detail = await get_marketing_campaign_detail(campaign_id)
    if detail is None:
        return _redirect("/dashboard/campaigns", error="Кампания не найдена")
    funnel = await get_campaign_funnel(detail["token"])
    return templates.TemplateResponse(
        "campaign_detail.html",
        {"request": request, "admin": admin, "campaign": detail, "funnel": funnel},
    )


@app.post("/dashboard/campaigns/{campaign_id}/toggle")
async def campaign_toggle(request: Request, campaign_id: int, admin=Depends(get_current_admin)):
    """Переключить активность кампании."""
    from dashboard.services import toggle_marketing_campaign
    result = await toggle_marketing_campaign(campaign_id, admin, _client_ip(request))
    if result is None:
        return _redirect("/dashboard/campaigns", error="Кампания не найдена")
    status = "активна" if result.is_active else "неактивна"
    return _redirect("/dashboard/campaigns", notice=f"Кампания теперь {status}")


@app.post("/dashboard/campaigns/{campaign_id}/delete")
async def campaign_delete(request: Request, campaign_id: int, admin=Depends(get_current_admin)):
    """Удалить кампанию."""
    from dashboard.services import delete_marketing_campaign
    result = await delete_marketing_campaign(campaign_id, admin, _client_ip(request))
    if not result:
        return _redirect("/dashboard/campaigns", error="Кампания не найдена")
    return _redirect("/dashboard/campaigns", notice="Кампания удалена")


# ===== Канбан-доска задач =====

@app.get("/dashboard/taskboard")
async def dashboard_taskboard(request: Request, admin=Depends(get_current_admin)):
    """Страница канбан-доски."""
    from dashboard.services import get_kanban_board
    search = request.query_params.get("search", "")
    assignee = request.query_params.get("assignee", "")
    tag = request.query_params.get("tag", "")
    priority = request.query_params.get("priority", "")
    board = await get_kanban_board(search=search, assignee_filter=assignee, tag_filter=tag, priority_filter=priority)
    return templates.TemplateResponse(
        "taskboard.html",
        {"request": request, "admin": admin, "board": board, "search": search, "assignee": assignee, "tag": tag, "priority": priority},
    )


@app.post("/dashboard/taskboard/create")
async def taskboard_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("backlog"),
    priority: str = Form("medium"),
    color: str = Form("#3b82f6"),
    assignee: str = Form(""),
    due_date: str = Form(""),
    tags: str = Form(""),
    admin=Depends(get_current_admin),
):
    """Создать новую задачу."""
    from dashboard.services import create_kanban_task
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    await create_kanban_task(
        title=title, description=description, status=status, priority=priority,
        color=color, assignee=assignee, due_date=due_date or "", tags=tags_list,
        admin=admin, ip_address=_client_ip(request),
    )
    return _redirect("/dashboard/taskboard", notice="Задача создана")


@app.post("/dashboard/taskboard/{task_id}/update")
async def taskboard_update(
    request: Request,
    task_id: int,
    status: str = Form(None),
    priority: str = Form(None),
    assignee: str = Form(None),
    title: str = Form(None),
    description: str = Form(None),
    color: str = Form(None),
    due_date: str = Form(None),
    admin=Depends(get_current_admin),
):
    """Обновить задачу."""
    from dashboard.services import update_kanban_task
    data = {}
    if status is not None: data["status"] = status
    if priority is not None: data["priority"] = priority
    if assignee is not None: data["assignee"] = assignee
    if title is not None: data["title"] = title
    if description is not None: data["description"] = description
    if color is not None: data["color"] = color
    if due_date is not None: data["due_date"] = due_date if due_date else None
    result = await update_kanban_task(task_id, data, admin, _client_ip(request))
    if result is None:
        return _redirect("/dashboard/taskboard", error="Задача не найдена")
    return _redirect("/dashboard/taskboard", notice="Задача обновлена")


@app.post("/dashboard/taskboard/{task_id}/comment")
async def taskboard_comment(
    request: Request,
    task_id: int,
    text: str = Form(...),
    admin=Depends(get_current_admin),
):
    """Добавить комментарий к задаче."""
    from dashboard.services import add_kanban_comment
    result = await add_kanban_comment(task_id, text, admin)
    if result is None:
        return _redirect("/dashboard/taskboard", error="Задача не найдена")
    return _redirect("/dashboard/taskboard", notice="Комментарий добавлен")


@app.post("/dashboard/taskboard/{task_id}/delete")
async def taskboard_delete(request: Request, task_id: int, admin=Depends(get_current_admin)):
    """Удалить задачу."""
    from dashboard.services import delete_kanban_task
    result = await delete_kanban_task(task_id, admin, _client_ip(request))
    if not result:
        return _redirect("/dashboard/taskboard", error="Задача не найдена")
    return _redirect("/dashboard/taskboard", notice="Задача удалена")


# ===== API эндпоинты для аналитики =====

@app.get("/dashboard/api/analytics/period")
async def api_analytics_period(request: Request, period: str = "30d", admin=Depends(get_current_admin)):
    """Получить аналитику за период."""
    from dashboard.services import get_period_analytics
    metrics = await get_period_analytics(period)
    return JSONResponse(metrics)


# ===== V2 API для campaigns (Next.js) =====

@app.get("/dashboard/api/v2/campaigns")
async def v2_campaigns_list(admin=Depends(get_current_admin)):
    from dashboard.services import get_marketing_campaigns
    campaigns = await get_marketing_campaigns()
    return _api_ok({"campaigns": campaigns})


@app.post("/dashboard/api/v2/campaigns/create")
async def v2_campaigns_create(request: Request, name: str = Form(...), cta_label: str = Form("Попробовать бесплатно"), admin=Depends(get_current_admin)):
    from dashboard.services import create_marketing_campaign
    campaign = await create_marketing_campaign(
        name=name,
        cta_label=cta_label,
        admin=admin,
        ip_address=_client_ip(request),
    )
    return _api_ok({"campaign": {"id": campaign.id, "name": campaign.name}}, "Кампания создана")


@app.post("/dashboard/api/v2/campaigns/{campaign_id}/toggle")
async def v2_campaigns_toggle(request: Request, campaign_id: int, admin=Depends(get_current_admin)):
    from dashboard.services import toggle_marketing_campaign
    result = await toggle_marketing_campaign(campaign_id, admin, _client_ip(request))
    if result is None:
        return _api_error("Кампания не найдена", 404)
    return _api_ok({"campaign": {"id": result.id, "is_active": result.is_active}})


@app.post("/dashboard/api/v2/campaigns/{campaign_id}/delete")
async def v2_campaigns_delete(request: Request, campaign_id: int, admin=Depends(get_current_admin)):
    from dashboard.services import delete_marketing_campaign
    result = await delete_marketing_campaign(campaign_id, admin, _client_ip(request))
    if not result:
        return _api_error("Кампания не найдена", 404)
    return _api_ok({"ok": True}, "Кампания удалена")
