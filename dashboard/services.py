import asyncio
import base64
import copy
import imghdr
import ipaddress
import json
import logging
import mimetypes
import os
import platform
import posixpath
import socket
import time
from contextvars import ContextVar, Token
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import markdown
import psutil
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import String, cast, delete, func, or_, select, update

from backend.core.analytics import EVENT_PAYMENT_FAILED, EVENT_PAYMENT_STARTED, safe_emit_analytics_event
from backend.core.database import async_session
from backend.core.models import (
    ChannelPostTouch,
    ControlBroadcastDelivery,
    ControlTriggerDeliveryLog,
    DeviceSlotEntitlement,
    Referral,
    ReferralReward,
    SupportTicket,
    SupportTicketMessage,
    User,
    UserDeletionJob,
    UserBalanceEvent,
    VpnClient,
    VpnClientActivation,
    VpnRepairEvent,
)
from backend.core.tracing import current_or_new_trace_id
from backend.core.synthetic_users import (
    is_synthetic_user as shared_is_synthetic_user,
    real_user_sql_clause as shared_real_user_sql_clause,
    synthetic_username_sql_predicates as shared_synthetic_username_sql_predicates,
)
from bot.device_compensation import enqueue_finalize_created_device_job, enqueue_restore_deleted_device_job
from bot.config import config
from bot.keyboards.tariffs import device_slot_manual_payment_reminder_keyboard, manual_payment_reminder_keyboard
from bot.public_subscription import (
    _normalize_device_type,
    _normalize_public_os_version,
    build_public_subscription_page_url,
    get_or_create_public_subscription_page_url_for_user,
)
from bot.db import (
    BALANCE_HOLD_PAYMENT_STATUSES,
    _release_reserved_balance_for_record,
    _load_payment_metadata,
    activate_trial,
    clear_vpn_repair_needed,
    create_vpn_repair_event,
    create_vpn_client,
    create_manual_payment_record,
    count_region_vpn_clients,
    delete_vpn_client_and_return,
    get_active_public_subscription_link_for_user,
    get_active_device_slot_counts_for_users,
    get_access_expires_at,
    get_open_payment_intent_for_user,
    get_payment_record_by_id,
    get_public_subscription_routes_for_user,
    get_user_by_id,
    get_vpn_client_by_id,
    get_user_by_telegram_id,
    get_user_vpn_clients,
    list_vpn_repair_events,
    mark_vpn_repair_needed,
    list_payment_records as list_payment_records_db,
    mark_manual_payment_record_submitted,
    update_vpn_client_metadata,
)
from bot.manual_payments import (
    PAYMENT_STATUS_LABELS,
    confirm_manual_payment,
    notify_support_admins_about_manual_payment,
    payment_metadata,
    payment_status_label,
    reject_manual_payment,
)
from bot.payment_flow import finalize_payment_record_product, sync_user_vpn_access_with_single_retry
from bot.platega_flow import PLATEGA_PAYMENT_METHODS, is_platega_payment_method, sync_platega_record_by_id
from bot.user_notifications import send_user_message, send_user_message_and_refresh_home
from bot.repair_reasons import (
    MANUAL_REPAIR,
    MANUAL_REPAIR_NO_ACCESS,
    MANUAL_REPAIR_NO_DEVICES,
    MANUAL_REPAIR_SYNC_FAILED,
    normalize_repair_event_reason,
    normalize_repair_event_reason_label,
    normalize_repair_outcome,
    normalize_repair_reason,
    normalize_repair_source,
    repair_outcome_label,
    repair_reason_label,
    repair_source_label,
)
from bot.utils.regions import (
    build_region_snapshot,
    get_country_name,
    get_country_panel_url,
    get_country_provider_type,
    get_country_runtime_service_name,
    get_country_runtime_type,
    get_region_limit_rule,
    get_region_anti_sharing_policy_summary,
    get_region_anti_sharing_scope_label,
    is_retired_region,
    normalize_country_code,
    parse_load_average,
    region_soft_limit_reasons,
)
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_access_status_from_user,
    get_device_limit_for_user,
    has_active_access_from_user,
)
from bot.utils.modes import MODES, infer_mode_from_protocol
from bot.utils.device_slots import DEVICE_SLOT_PRODUCT_TYPE, payment_product_type
from bot.utils.subscription import is_user_subscribed
from bot.utils.vless import build_connection_name, build_trojan_link
from bot.vpn_provisioning import get_vless_provisioner, region_supports_protocol
from bot.utils.tariffs import get_tariff, gift_duration_days
from bot.utils.texts import (
    manual_payment_method_label,
    manual_payment_reminder_text,
    subscription_extended_notification_text,
    user_blocked_notification_text,
    user_unblocked_notification_text,
)
from bot.vpn_api import XUIClient
from dashboard.finance import (
    FINANCE_ENTRY_STATUSES,
    FINANCE_ENTRY_TYPES,
    FINANCE_EXPENSE_TYPES,
    FINANCE_REPORT_SLUG,
    finance_is_expense,
    finance_signed_amount,
    finance_status_label,
    finance_type_label,
    payment_method_counts_as_revenue,
    period_key_for,
    sync_income_entry_for_payment_record,
)
from dashboard.models import (
    DashboardAdmin,
    DashboardAuditLog,
    DashboardAuthLockoutState,
    DashboardLoginCode,
    DashboardRolePermissionOverride,
    DashboardSession,
    FinanceEntry,
    ManagedServer,
    PaymentRecord,
)
from dashboard.security import hash_token, session_expiry, utcnow, verify_password
from control_bot.dispatcher import create_control_event as _create_control_event
from support_bot.storage import (
    assign_ticket,
    close_ticket,
    get_history,
    get_message_attachment,
    get_ticket,
    get_ticket_counts,
    list_tickets,
    register_admin_reply,
    transfer_ticket,
)

logger = logging.getLogger(__name__)
_CURRENT_DASHBOARD_REQUEST_ID: ContextVar[str | None] = ContextVar("dashboard_request_id", default=None)


COUNTRY_LABELS = {
    "de": "Germany",
    "ee": "Estonia",
    "dk": "Denmark",
}
DEVICE_OS_LABELS = {
    "android": "Android",
    "ios": "iPhone / iPad",
    "windows": "Windows",
    "macos": "macOS",
    "linux": "Linux",
    "tv": "Android TV",
    "desktop": "Desktop",
    "other": "Другое",
}
PROVIDER_LABELS = {
    "xui": "3x-ui",
    "xray_core": "Xray core",
    "amneziawg": "AmneziaWG",
    "retired": "Retired",
}
ANTI_SHARING_SCOPE_LABELS = {
    "xui": "3x-ui limitIp",
    "xray_core": "Xray access-log lease",
    "amneziawg": "AmneziaWG device binding",
}
RUNTIME_LABELS = {
    "xui": "3x-ui",
    "xray_core": "Xray",
    "amneziawg": "AmneziaWG",
    "retired": "Retired",
}

SERVICE_MAP = {
    "main_bot": "amonora-bot.service",
    "support_bot": "amonora-support-bot.service",
    "control_bot": "amonora-control-bot.service",
    "dashboard": "amonora-dashboard.service",
    "dashboard_ui": "amonora-dashboard-ui.service",
    "landing": "amonora-landing.service",
}
SERVICE_STATUS_MAP = {
    **SERVICE_MAP,
    "nginx": "nginx.service",
    "access_reminders_timer": "amonora-access-reminders.timer",
    "server_watchdog_timer": "amonora-server-watchdog.timer",
}
LOGIN_CODE_REQUEST_COOLDOWN_SECONDS = 30
DASHBOARD_AUTH_LOCKOUT_IDENTITY_USERNAME = "username"
DASHBOARD_AUTH_LOCKOUT_IDENTITY_IP = "ip"
DASHBOARD_AUTH_LOCKOUT_DURATION_SECONDS = max(int(os.getenv("DASHBOARD_AUTH_LOCKOUT_DURATION_SECONDS", "900") or 900), 60)
SAFE_DOC_HTML_TAGS = {
    "a", "article", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "img", "li", "ol", "p", "pre", "section", "span", "strong", "table", "tbody", "td",
    "th", "thead", "tr", "ul",
}
SAFE_DOC_HTML_GLOBAL_ATTRS = {"class", "id", "aria-label"}
SAFE_DOC_HTML_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
BLOCKED_DOC_HTML_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "meta", "link"}

MANUAL_PAYMENT_METHODS = {"sbp_manual", "crypto_manual"}
PROVIDER_SYNC_PAYMENT_METHODS = set(PLATEGA_PAYMENT_METHODS)
MANUAL_PAYMENT_REVIEW_STATUSES = {"awaiting_admin_review"}
DEVICE_STATUS_ONLINE_WINDOW = timedelta(hours=24)
DEVICE_STATUS_LABELS = {
    "healthy": "🟢 Исправен",
    "broken": "🔴 Сломан",
    "unknown": "Не проверяли",
}
MANUAL_PAYMENT_OPEN_STATUSES = {"awaiting_user_payment", "awaiting_admin_review"}
PAYMENT_PROBLEM_STATUSES = {"rejected", "expired", "disputed", "error"}
PAYMENT_STATUS_FLOW = {
    "awaiting_user_payment",
    "awaiting_admin_review",
    "confirmed",
    "rejected",
    "expired",
    "disputed",
    "error",
}
BALANCE_EVENT_REASON_LABELS = {
    "balance_payment": "Оплата с баланса",
    "balance_topup": "Пополнение баланса",
    "payment_reserved": "Резерв под платёж",
    "payment_confirmed": "Списание после оплаты",
    "payment_expired": "Резерв снят: срок истёк",
    "payment_deleted": "Резерв снят: платёж удалён",
    "referral_bonus": "Реферальный бонус",
    "referral_migration": "Миграция реферального баланса",
    "referral_backfill": "Доначисление реферального баланса",
}
BALANCE_EVENT_DIRECTION_LABELS = {
    "credit": "Начисление",
    "debit": "Списание",
    "reserve": "Резерв",
    "release": "Снятие резерва",
}

ROLE_NAMES = {
    "owner": "Владелец",
    "tech_admin": "Тех. администратор",
    "support_admin": "Менеджер",
}

ROLE_PRIORITIES = {"support_admin": 1, "tech_admin": 2, "owner": 3}
ROLE_PERMISSIONS = {
    "support_admin": {
        "manage_campaigns",
        "manage_support",
        "manage_campaigns",
        "manage_tasks",
    },
    "tech_admin": {
        "manage_campaigns",
        "manage_users",
        "manage_support",
        "manage_campaigns",
        "manage_tasks",
        "manage_servers",
        "manage_server_actions",
        "manage_payments",
        "manage_finance",
        "run_sync",
        "run_deep_repair",
        "manage_services",
        "manage_docs",
    },
    "owner": {
        "manage_campaigns",
        "manage_users",
        "delete_users",
        "manage_payments",
        "manage_support",
        "manage_campaigns",
        "manage_tasks",
        "manage_servers",
        "manage_server_actions",
        "manage_finance",
        "approve_finance",
        "run_sync",
        "run_deep_repair",
        "clear_access",
        "manage_services",
        "manage_docs",
        "delete_payments",
        "delete_finance",
    },
}
EDITABLE_PERMISSION_ROLES = {"tech_admin", "support_admin"}
ROLE_PERMISSION_OVERRIDE_ALLOWLIST = {
    "tech_admin": {
        "manage_campaigns",
        "manage_users",
        "manage_support",
        "manage_campaigns",
        "manage_tasks",
        "manage_servers",
        "manage_server_actions",
        "manage_payments",
        "manage_finance",
        "run_sync",
        "run_deep_repair",
        "manage_services",
        "manage_docs",
    },
    "support_admin": {
        "manage_campaigns",
        "manage_support",
        "manage_campaigns",
        "manage_tasks",
    },
}
_ROLE_PERMISSION_OVERRIDES_CACHE: dict[str, dict[str, bool]] = {}

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DOCS_ROOT = Path(__file__).resolve().parent.parent / "documentation"
GENERATED_DOCS_ROOT = DOCS_ROOT / "generated"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
ADMIN_AVATAR_ROOT = STATIC_ROOT / "avatars"
TRUSTED_PROXY_HOSTS = {"127.0.0.1", "::1", "localhost"}
DANGEROUS_ENV_NAME_TOKENS = {
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASS",
    "PRIVATE_KEY",
    "WEBHOOK",
}
DANGEROUS_ENV_PREFIXES = {
    "BOT_",
    "SUPPORT_BOT_",
    "PLATEGA_",
    "DB_",
    "XUI_",
    "CRYPTO_PAY_",
    "AMONORA_INTERNAL_",
}
MUTABLE_ENV_ALLOWLIST = {
    "DASHBOARD_TITLE",
    "DASHBOARD_SESSION_HOURS",
    "DASHBOARD_SESSION_IDLE_MINUTES",
    "DASHBOARD_DOCS_OWNER",
    "DASHBOARD_DOCS_REPO",
    "DASHBOARD_DOCS_BRANCH",
    "DASHBOARD_DOCS_PATH",
    "DASHBOARD_MONTHLY_SERVER_BUDGET_RUB",
    "DASHBOARD_MONTHLY_OPERATIONS_BUDGET_RUB",
    "DASHBOARD_MONTHLY_TARGET_REVENUE_RUB",
    "DASHBOARD_BACKUP_STALE_HOURS",
    "DASHBOARD_RESTORE_VALIDATION_STALE_DAYS",
    "DASHBOARD_PRIMARY_SERVER_NAME",
    "DASHBOARD_PRIMARY_SERVER_COUNTRY_CODE",
    "DASHBOARD_PRIMARY_SERVER_COUNTRY_NAME",
    "DASHBOARD_PRIMARY_SERVER_PROVIDER",
}
OPERATIONS_REPORT_SLUG = "generated/ops-report-latest.md"
PLATFORM_AUDIT_REPORT_SLUG = "generated/platform-audit-latest.md"
FINANCE_DOC_CATEGORY_HINTS = {"server", "domain", "service", "infra", "hosting"}
SSH_DIR = Path(__file__).resolve().parent.parent / ".ssh"
DEFAULT_REMOTE_SSH_KEY_PATH = SSH_DIR / "dashboard_metrics"
DEFAULT_REMOTE_KNOWN_HOSTS = SSH_DIR / "known_hosts"
BACKUP_ROOT = Path(os.getenv("DASHBOARD_BACKUP_ROOT", str(Path(__file__).resolve().parent.parent / "backups")))
BACKUP_STALE_HOURS = int(os.getenv("DASHBOARD_BACKUP_STALE_HOURS", "24"))
RESTORE_VALIDATION_STALE_DAYS = int(os.getenv("DASHBOARD_RESTORE_VALIDATION_STALE_DAYS", "30"))
SESSION_LAST_SEEN_TOUCH_INTERVAL_SECONDS = max(int(os.getenv("DASHBOARD_SESSION_TOUCH_INTERVAL_SECONDS", "60") or 60), 15)
DASHBOARD_AUTH_LOCKOUT_THRESHOLD = max(int(os.getenv("DASHBOARD_AUTH_LOCKOUT_THRESHOLD", "12") or 12), 3)
DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS = max(int(os.getenv("DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS", "900") or 900), 60)
BACKUP_SOURCE_PATHS = {
    "core": ("Core PG", "core-pg"),
    "vpn_de": ("DE node", "vpn-de"),
    "vpn_ee": ("EE node", "vpn-ee"),
    "vpn_dk": ("DK node", "vpn-dk"),
}
RESTORE_VALIDATION_SIGNAL_PATHS = (
    DOCS_ROOT / "ai" / "TASKS" / "029-restore-drill-result.md",
    DOCS_ROOT / "ai" / "TASKS" / "030-one-click-restore-script-result.md",
)
RESTORE_VALIDATION_STATUS_PATH = BACKUP_ROOT / "status" / "restore-validation.json"
RESTORE_PROOF_STATUS_PATH = BACKUP_ROOT / "status" / "restore-proof.json"
_NETWORK_SAMPLES: dict[str, tuple[float, int, int]] = {}
_DOCS_CACHE: dict[str, object] = {
    "manifest": {"expires_at": 0.0, "value": None},
    "docs": {},
}
_DOCS_CACHE_TTL = 300.0
_RUNTIME_CACHE: dict[str, dict[str, object]] = {
    "overview_metrics": {"expires_at": 0.0, "value": None},
    "service_statuses": {"expires_at": 0.0, "value": None},
    "server_snapshots": {"expires_at": 0.0, "value": None},
    "managed_region_device_stats": {"expires_at": 0.0, "value": None},
    "vpn_overview_default": {"expires_at": 0.0, "value": None},
    "xui_summary": {"expires_at": 0.0, "value": None},
    "channel_subscription_statuses": {"expires_at": 0.0, "value": None},
}
_RUNTIME_CACHE_TTL = {
    "overview_metrics": 45.0,
    "service_statuses": 30.0,
    "server_snapshots": 45.0,
    "managed_region_device_stats": 45.0,
    "vpn_overview_default": 45.0,
    "xui_summary": 45.0,
    "channel_subscription_statuses": 600.0,
    "traffic_baseline": 60.0 * 60.0 * 24.0 * 30.0,
}
ADMIN_AVATAR_MAX_BYTES = 2 * 1024 * 1024
ALLOWED_ADMIN_AVATAR_FORMATS = {"jpeg": "jpg", "png": "png", "webp": "webp"}
DASHBOARD_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")
DASHBOARD_TIMEZONE_LABEL = "Екб"
CHANNEL_SUBSCRIPTION_CONCURRENCY = 6
CHANNEL_SUBSCRIPTION_OK_TTL_SECONDS = 600.0
CHANNEL_SUBSCRIPTION_UNKNOWN_TTL_SECONDS = 120.0
CHANNEL_SUBSCRIPTION_CACHE_MAX_ITEMS = 2048


def dashboard_settings() -> dict:
    return {
        "title": os.getenv("DASHBOARD_TITLE", "Amonora Control Center"),
        "host": os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        "port": int(os.getenv("DASHBOARD_PORT", "8088")),
        "session_hours": int(os.getenv("DASHBOARD_SESSION_HOURS", "24")),
        "session_idle_minutes": int(os.getenv("DASHBOARD_SESSION_IDLE_MINUTES", "45")),
        "cookie_name": os.getenv("DASHBOARD_COOKIE_NAME", "amonora_dashboard_session"),
        "cookie_secure": os.getenv("DASHBOARD_COOKIE_SECURE", "1").strip().lower() not in {"0", "false", "no"},
    }


def documentation_settings() -> dict:
    owner = os.getenv("DASHBOARD_DOCS_OWNER", "firefox0618").strip() or "firefox0618"
    repo = os.getenv("DASHBOARD_DOCS_REPO", "amonora_bot").strip() or "amonora_bot"
    branch = os.getenv("DASHBOARD_DOCS_BRANCH", "develop").strip() or "develop"
    docs_path = (os.getenv("DASHBOARD_DOCS_PATH", "documentation").strip().strip("/") or "documentation")
    repo_url = f"https://github.com/{owner}/{repo}"
    return {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "path": docs_path,
        "repo_url": repo_url,
        "folder_url": f"{repo_url}/tree/{branch}/{docs_path}",
        "manifest_url": f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{docs_path}/manifest.json",
    }


def nav_items() -> list[dict]:
    return [
        {"key": "overview", "label": "Обзор", "icon": "◈"},
        {"key": "users", "label": "Пользователи", "icon": "◎"},
        {"key": "vpn", "label": "Доступ", "icon": "⬢"},
        {"key": "support", "label": "Поддержка", "icon": "✦"},
        {"key": "payments", "label": "Платежи", "icon": "◉"},
        {"key": "analytics", "label": "Аналитика", "icon": "◌"},
        {"key": "promocodes", "label": "Промокоды", "icon": "⌁"},
        {"key": "finance", "label": "Финансы", "icon": "◍"},
        {"key": "servers", "label": "Серверы", "icon": "⬡"},
        {"key": "services", "label": "Сервисы", "icon": "◌"},
        {"key": "docs", "label": "Документация", "icon": "⌘"},
    ]


def role_allows(role: str, required: str) -> bool:
    return ROLE_PRIORITIES.get(role, 0) >= ROLE_PRIORITIES.get(required, 0)


def all_known_permissions() -> set[str]:
    return set().union(*ROLE_PERMISSIONS.values())


def editable_permission_roles() -> tuple[str, ...]:
    return tuple(sorted(EDITABLE_PERMISSION_ROLES))


def editable_permissions_for_role(role: str) -> set[str]:
    return set(ROLE_PERMISSION_OVERRIDE_ALLOWLIST.get(role, set()))


def _effective_role_permissions(role: str) -> set[str]:
    if role == "owner":
        return set(all_known_permissions())
    allowed = set(ROLE_PERMISSIONS.get(role, set()))
    overrides = _ROLE_PERMISSION_OVERRIDES_CACHE.get(role, {})
    for permission, enabled in overrides.items():
        if enabled:
            allowed.add(permission)
        else:
            allowed.discard(permission)
    return allowed


def role_has_permission(role: str, permission: str) -> bool:
    return permission in _effective_role_permissions(role)


def role_has_any_permission(role: str, *permissions: str) -> bool:
    return any(role_has_permission(role, permission) for permission in permissions)


async def refresh_role_permission_overrides_cache() -> dict[str, dict[str, bool]]:
    async with async_session() as session:
        rows = list((await session.execute(select(DashboardRolePermissionOverride))).scalars().all())
    mapping: dict[str, dict[str, bool]] = {}
    for row in rows:
        role = str(row.role or "").strip()
        permission = str(row.permission or "").strip()
        if not role or not permission:
            continue
        mapping.setdefault(role, {})[permission] = bool(row.enabled)
    _ROLE_PERMISSION_OVERRIDES_CACHE.clear()
    _ROLE_PERMISSION_OVERRIDES_CACHE.update(mapping)
    return copy.deepcopy(_ROLE_PERMISSION_OVERRIDES_CACHE)


def get_role_permission_overrides_cache() -> dict[str, dict[str, bool]]:
    return copy.deepcopy(_ROLE_PERMISSION_OVERRIDES_CACHE)


def get_role_permission_matrix_snapshot() -> dict[str, dict[str, bool]]:
    permissions = sorted(all_known_permissions())
    matrix: dict[str, dict[str, bool]] = {}
    for role in ("owner", "tech_admin", "support_admin"):
        allowed = _effective_role_permissions(role)
        matrix[role] = {permission: permission in allowed for permission in permissions}
    return matrix


async def _system_command(*args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    return process.returncode, stdout.decode("utf-8", errors="ignore").strip()


async def _service_status(name: str) -> str:
    return (await _system_command("systemctl", "is-active", name))[1] or "unknown"


def _mask_env_value(key: str, value: str) -> str:
    secret_keys = ("TOKEN", "PASSWORD", "PASS", "SECRET", "KEY")
    if any(part in key.upper() for part in secret_keys):
        if len(value) <= 8:
            return "********"
        return f"{value[:4]}***{value[-4:]}"
    return value


def _support_attachment_url(ticket_user_id: int, message_id: int) -> str:
    return f"/dashboard/support/{ticket_user_id}/messages/{message_id}/attachment"


def _control_user_identity(user: User | None) -> str:
    if user is None:
        return "Пользователь: <b>не найден</b>"
    username = f"@{user.username}" if user.username else "без username"
    return (
        f"Пользователь: <b>{escape(username)}</b>\n"
        f"User ID: <code>{user.id}</code>\n"
        f"Telegram ID: <code>{user.telegram_id}</code>"
    )


def _decorate_support_history(ticket_user_id: int, history: list[dict]) -> list[dict]:
    decorated: list[dict] = []
    for item in history:
        attachment = item.get("attachment")
        if attachment and item.get("id") is not None:
            attachment = {
                **attachment,
                "url": _support_attachment_url(ticket_user_id, int(item["id"])),
            }
        decorated.append({**item, "attachment": attachment})
    return decorated


def _device_metadata(vpn_client: VpnClient) -> dict:
    data = json.loads(vpn_client.client_data) if vpn_client.client_data else {}
    data.setdefault("device_name", vpn_client.email)
    data.setdefault("device_type", "other")
    data.setdefault("protocol", vpn_client.protocol)
    data.setdefault("device_source_label", "Классический ключ")
    data.setdefault("can_manage", True)
    if data.get("protocol") == "vless":
        data.setdefault("stream_network", "tcp")
        data.setdefault("transport_label", "TCP")
    data.update(build_region_snapshot(data.get("country_code")))
    return data


def _public_route_metadata(route: object) -> dict:
    raw_value = str(getattr(route, "client_data", "") or "").strip()
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_retired_estonia_xui_admin_device(metadata: dict | None, *, email: str | None = None) -> bool:
    if not isinstance(metadata, dict):
        return False
    return (
        str(metadata.get("country_code") or "").strip().lower() == "ee"
        and str(metadata.get("provider_type") or "").strip().lower() == "xui"
        and bool(metadata.get("admin_visible"))
        and bool(metadata.get("reserve_only"))
        and not bool(metadata.get("user_selectable", True))
        and str(email or "").strip().startswith("dashboard_")
    )


def _stringify_device_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, (list, tuple, set)):
        flattened = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(flattened) if flattened else "—"
    if isinstance(value, dict):
        return "—"
    normalized = str(value).strip()
    return normalized or "—"


def _pick_device_value(metadata: dict | None, *keys: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    for key in keys:
        if key not in metadata:
            continue
        value = _stringify_device_value(metadata.get(key))
        if value != "—":
            return value
    return None


def _build_device_technical_payload(
    metadata: dict,
    *,
    live_ip_meta: dict[str, str],
    fallback_ip: str,
    display_ip: str,
    user_last_activity_at: datetime | None,
) -> dict[str, str]:
    device_type = str(metadata.get("device_type") or "other").strip().lower() or "other"
    country_code = normalize_country_code(metadata.get("country_code"))
    provider_type = str(
        metadata.get("provider_type") or get_country_provider_type(country_code)
    ).strip().lower() or "xui"
    max_devices = max(int(config.vpn_max_devices_per_key or 1), 1)
    max_devices_label = f"До {max_devices} активного IP" if max_devices == 1 else f"До {max_devices} активных IP"
    anti_sharing_scope_label = get_region_anti_sharing_scope_label(country_code, provider_type=provider_type)
    anti_sharing_policy_summary = get_region_anti_sharing_policy_summary(country_code, provider_type=provider_type)
    if provider_type == "xray_core":
        soft_limit_label = (
            "Soft-limit warning включён"
            if config.vpn_antisharing_soft_limit_enabled
            else "Soft-limit warning выключен"
        )
    elif provider_type == "amneziawg":
        soft_limit_label = "App/device activation binding"
    else:
        soft_limit_label = "Panel hard-limit"
    device_type_normalized = _normalize_device_type(device_type) or device_type
    raw_os_version = _pick_device_value(metadata, "os_version", "platform_version", "system_version", "os_build")
    normalized_os_version = _normalize_public_os_version(
        device_type=device_type_normalized,
        os_version=raw_os_version,
        user_agent=_pick_device_value(metadata, "user_agent"),
    )
    return {
        "os_label": DEVICE_OS_LABELS.get(device_type, device_type or "Другое"),
        "device_model": _pick_device_value(metadata, "device_model", "model", "hardware_model", "platform_model") or "—",
        "os_version": normalized_os_version or raw_os_version or "—",
        "mac_address": _pick_device_value(metadata, "mac_address", "mac", "wifi_mac", "ethernet_mac") or "—",
        "ip_address": display_ip,
        "fallback_ip_address": fallback_ip,
        "ip_history": _pick_device_value(live_ip_meta, "ip_history") or "—",
        "ip_source_label": _pick_device_value(live_ip_meta, "ip_source_label") or "—",
        "provider_label": PROVIDER_LABELS.get(provider_type, provider_type or "—"),
        "transport_label": _pick_device_value(metadata, "transport_label", "transport", "stream_network") or "—",
        "connection_profile": _pick_device_value(metadata, "connection_profile", "active_profile") or "—",
        "node_label": _pick_device_value(metadata, "country_name") or "—",
        "last_seen_at": _format_datetime(user_last_activity_at),
        "anti_sharing_limit_label": max_devices_label,
        "anti_sharing_scope_label": anti_sharing_scope_label,
        "anti_sharing_soft_limit_label": soft_limit_label,
        "anti_sharing_policy_summary": anti_sharing_policy_summary,
    }


def _build_device_mode_label(protocol: str | None, metadata: dict | None) -> str:
    mode_key = infer_mode_from_protocol(protocol, metadata)
    definition = MODES.get(mode_key)
    if definition is None:
        return "—"
    return definition.title


def _build_default_device_status_payload() -> dict[str, str | None]:
    return {
        "status_key": "unknown",
        "status_label": DEVICE_STATUS_LABELS["unknown"],
        "status_reason": "Нажмите «Статус», чтобы проверить ключ",
        "status_checked_at": None,
    }


def _build_device_status_payload(status_key: str, reason: str, *, checked_at: str | None = None) -> dict[str, str | None]:
    normalized_key = str(status_key or "unknown").strip().lower()
    if normalized_key in {"online", "offline"}:
        normalized_key = "healthy"
    if normalized_key not in DEVICE_STATUS_LABELS:
        normalized_key = "unknown"
    return {
        "status_key": normalized_key,
        "status_label": DEVICE_STATUS_LABELS[normalized_key],
        "status_reason": reason,
        "status_checked_at": checked_at,
    }


def _extract_device_ip(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("ip_address", "client_ip", "current_ip", "last_ip", "real_ip", "last_seen_ip", "source_ip", "public_client_ip"):
        value = str(metadata.get(key) or "").strip()
        if not value or value == "—":
            continue
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            continue
    return None


async def _fetch_xui_live_device_ips(
    country_code: str | None,
    email: str | None,
    *,
    provider_type: str | None = None,
) -> dict[str, str]:
    normalized_country = normalize_country_code(country_code)
    resolved_provider_type = str(provider_type or get_country_provider_type(normalized_country)).strip().lower()
    checked_at = _format_datetime(datetime.now(timezone.utc))
    if resolved_provider_type != "xui" or not normalized_country or not email:
        return {
            "ip_source": "metadata",
            "ip_source_label": "Из сохранённой метадаты",
            "ip_checked_at": checked_at,
        }

    xui = XUIClient(country_code=normalized_country)
    try:
        if not await xui.login():
            return {
                "ip_source": "xui_login_failed",
                "ip_source_label": "3x-ui недоступен",
                "ip_checked_at": checked_at,
            }
        ips = await xui.get_client_ips(email)
    except Exception:
        logger.exception("Failed to fetch live device IPs for %s in %s", email, normalized_country)
        return {
            "ip_source": "xui_error",
            "ip_source_label": "Ошибка чтения 3x-ui",
            "ip_checked_at": checked_at,
        }
    finally:
        await xui.close()

    if not ips:
        return {
            "ip_source": "xui_no_record",
            "ip_source_label": "3x-ui ещё не записал IP",
            "ip_checked_at": checked_at,
        }

    return {
        "real_ip": ips[0],
        "ip_history": ", ".join(ips[:4]),
        "ip_source": "xui_client_ips",
        "ip_source_label": "Живой IP из 3x-ui",
        "ip_checked_at": checked_at,
    }


async def _serialize_user_device(device: VpnClient, *, user_last_activity_at: datetime | None) -> dict:
    metadata = _device_metadata(device)
    fallback_ip = _extract_device_ip(metadata) or "—"
    live_ip_meta = await _fetch_xui_live_device_ips(
        metadata.get("country_code"),
        device.email,
        provider_type=metadata.get("provider_type"),
    )
    display_ip = str(live_ip_meta.get("real_ip") or fallback_ip)
    return {
        "id": device.id,
        "protocol": device.protocol,
        "created_at": _format_datetime(device.created_at),
        "mode_label": _build_device_mode_label(device.protocol, metadata),
        "metadata": {
            **metadata,
            **live_ip_meta,
            "ip_address": display_ip,
            "fallback_ip_address": fallback_ip,
            "node_label": metadata.get("country_name") or "—",
            "last_seen_at": _format_datetime(user_last_activity_at),
        },
        "technical": _build_device_technical_payload(
            metadata,
            live_ip_meta=live_ip_meta,
            fallback_ip=fallback_ip,
            display_ip=display_ip,
            user_last_activity_at=user_last_activity_at,
        ),
        **_build_default_device_status_payload(),
    }


def _preferred_public_route(slot_routes: list[object]) -> object | None:
    if not slot_routes:
        return None
    preferred_country_order = ("de", "dk", "ee")
    for country_code in preferred_country_order:
        for route in slot_routes:
            if normalize_country_code(getattr(route, "country_code", None)) == country_code:
                return route
    return slot_routes[0]


def _serialize_public_subscription_devices(
    routes: list[object],
    *,
    user_last_activity_at: datetime | None,
) -> list[dict]:
    slot_rows: dict[int, list[object]] = {}
    for route in routes:
        slot_index = int(getattr(route, "slot_index", 0) or 0)
        if slot_index <= 0:
            continue
        slot_rows.setdefault(slot_index, []).append(route)

    devices: list[dict] = []
    for slot_index in sorted(slot_rows):
        slot_routes = slot_rows[slot_index]
        metadata_candidates = [_public_route_metadata(route) for route in slot_routes]
        bound_metadata = next(
            (
                metadata
                for metadata in metadata_candidates
                if str(metadata.get("feed_device_fingerprint_hash") or "").strip()
            ),
            None,
        )
        if bound_metadata is None:
            continue

        representative_route = _preferred_public_route(slot_routes)
        if representative_route is None:
            continue

        country_names: list[str] = []
        for route in slot_routes:
            country_name = get_country_name(getattr(route, "country_code", None))
            if country_name and country_name not in country_names:
                country_names.append(country_name)
        countries_label = ", ".join(country_names) if country_names else "Единая ссылка"

        device_type = _normalize_device_type(bound_metadata.get("device_type")) or "other"
        last_seen_at = (
            _parse_iso_datetime(str(bound_metadata.get("feed_device_last_seen_at") or "").strip())
            or _parse_iso_datetime(str(bound_metadata.get("feed_device_bound_at") or "").strip())
            or user_last_activity_at
        )
        fallback_ip = (
            _extract_device_ip(bound_metadata)
            or str(bound_metadata.get("source_ip") or "").strip()
            or "—"
        )
        ip_source_label = "Из привязки единой ссылки"
        metadata = {
            **bound_metadata,
            **build_region_snapshot(normalize_country_code(getattr(representative_route, "country_code", None))),
            "device_name": str(
                bound_metadata.get("device_name")
                or bound_metadata.get("feed_device_label")
                or bound_metadata.get("device_model")
                or f"Happ #{slot_index}"
            ).strip()
            or f"Happ #{slot_index}",
            "device_type": device_type,
            "protocol": str(getattr(representative_route, "protocol", "vless") or "vless").strip().lower() or "vless",
            "country_code": normalize_country_code(getattr(representative_route, "country_code", None)),
            "country_name": countries_label,
            "country_names": country_names,
            "slot_index": int(slot_index),
            "ip_address": fallback_ip,
            "ip_source_label": ip_source_label,
            "device_source_label": "Единая ссылка",
            "delivery_mode": "public_subscription_feed",
            "subscription_route": True,
            "can_manage": False,
            "node_label": countries_label,
        }
        live_ip_meta = {
            "ip_source": "public_subscription_binding",
            "ip_source_label": ip_source_label,
            "ip_checked_at": _format_datetime(last_seen_at),
        }
        devices.append(
            {
                "id": -(100000 + int(slot_index)),
                "protocol": metadata["protocol"],
                "created_at": _format_datetime(
                    _parse_iso_datetime(str(bound_metadata.get("feed_device_bound_at") or "").strip())
                    or getattr(representative_route, "created_at", None)
                ),
                "mode_label": _build_device_mode_label(metadata["protocol"], metadata),
                "metadata": {
                    **metadata,
                    **live_ip_meta,
                    "fallback_ip_address": fallback_ip,
                    "last_seen_at": _format_datetime(last_seen_at),
                },
                "technical": _build_device_technical_payload(
                    metadata,
                    live_ip_meta=live_ip_meta,
                    fallback_ip=fallback_ip,
                    display_ip=fallback_ip,
                    user_last_activity_at=last_seen_at,
                ),
                **_build_device_status_payload(
                    "unknown",
                    "Устройство из единой ссылки отображается для просмотра",
                    checked_at=_format_datetime(last_seen_at),
                ),
            }
        )

    return devices


async def _get_last_device_activation_at(vpn_client_id: int) -> datetime | None:
    async with async_session() as session:
        activation = (
            await session.execute(
                select(VpnClientActivation)
                .where(VpnClientActivation.vpn_client_id == vpn_client_id)
                .order_by(VpnClientActivation.last_activated_at.desc(), VpnClientActivation.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if activation is None:
        return None
    return getattr(activation, "last_activated_at", None)


def _has_recent_device_activation(last_activated_at: datetime | None) -> bool:
    if last_activated_at is None:
        return False
    activation_dt = last_activated_at if last_activated_at.tzinfo is not None else last_activated_at.replace(tzinfo=timezone.utc)
    return activation_dt >= datetime.now(timezone.utc) - DEVICE_STATUS_ONLINE_WINDOW


def _xray_remote_has_client(config_payload: dict[str, object], *, client_uuid: str, email: str) -> bool:
    inbounds = config_payload.get("inbounds")
    if not isinstance(inbounds, list):
        return False
    for inbound in inbounds:
        if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
            continue
        if inbound.get("listen") != "@xhttp-dk":
            stream_settings = inbound.get("streamSettings") or {}
            if str(stream_settings.get("network") or "").strip().lower() != "xhttp":
                continue
        settings = inbound.get("settings") or {}
        clients = settings.get("clients") or []
        if not isinstance(clients, list):
            continue
        for client in clients:
            if not isinstance(client, dict):
                continue
            if client.get("id") == client_uuid or client.get("email") == email:
                return True
    return False


async def _get_device_status_payload(device: VpnClient, user: User) -> dict[str, str | None]:
    metadata = _device_metadata(device)
    checked_at = _format_datetime(datetime.now(timezone.utc))
    mode_label = _build_device_mode_label(device.protocol, metadata)
    country_code = normalize_country_code(metadata.get("country_code"))
    provider_type = str(metadata.get("provider_type") or get_country_provider_type(country_code)).strip().lower() or "xui"

    if bool(getattr(user, "vpn_repair_needed", False)):
        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "broken",
                "Доступ помечен как требующий ремонта",
                checked_at=checked_at,
            ),
        }

    if not country_code or provider_type == "retired" or is_retired_region(country_code):
        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "broken",
                "Регион устройства больше не поддерживается",
                checked_at=checked_at,
            ),
        }

    active_access = has_active_access_from_user(user)
    if not active_access:
        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "broken",
                "Доступ не активен, ключ не будет работать",
                checked_at=checked_at,
            ),
        }

    last_activated_at = await _get_last_device_activation_at(device.id)
    recent_activation = _has_recent_device_activation(last_activated_at)

    if provider_type == "xui":
        xui = XUIClient(country_code=country_code)
        try:
            if not await xui.login():
                return {
                    "device_id": device.id,
                    "mode_label": mode_label,
                    **_build_device_status_payload(
                        "broken",
                        "3x-ui недоступен",
                        checked_at=checked_at,
                    ),
                }
            normalized_protocol = "trojan" if str(device.protocol or "").strip().lower() == "trojan" else "vless"
            resolved_inbound_id = await xui.resolve_client_inbound_id(
                normalized_protocol,
                device.client_uuid,
                device.email,
                inbound_id=metadata.get("inbound_id"),
            )
            if not resolved_inbound_id:
                return {
                    "device_id": device.id,
                    "mode_label": mode_label,
                    **_build_device_status_payload(
                        "broken",
                        "Клиент не найден на сервере",
                        checked_at=checked_at,
                    ),
                }
            live_ips = await xui.get_client_ips(device.email)
            if live_ips:
                return {
                    "device_id": device.id,
                    "mode_label": mode_label,
                    **_build_device_status_payload(
                        "healthy",
                        "Есть живой IP с сервера",
                        checked_at=checked_at,
                    ),
                }
        except Exception:
            logger.exception("Failed to check XUI device status for user_id=%s device_id=%s", user.id, device.id)
            return {
                "device_id": device.id,
                "mode_label": mode_label,
                **_build_device_status_payload(
                    "broken",
                    "Ошибка чтения 3x-ui",
                    checked_at=checked_at,
                ),
            }
        finally:
            await xui.close()

        if recent_activation:
            return {
                "device_id": device.id,
                "mode_label": mode_label,
                **_build_device_status_payload(
                    "healthy",
                    "Недавно было подключение",
                    checked_at=checked_at,
                ),
            }

        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "healthy",
                "Ключ найден на сервере, явных проблем не видно",
                checked_at=checked_at,
            ),
        }

    if provider_type == "xray_core":
        provisioner = get_vless_provisioner(country_code, provider_type=provider_type)
        try:
            if not await provisioner.health_check():
                return {
                    "device_id": device.id,
                    "mode_label": mode_label,
                    **_build_device_status_payload(
                        "broken",
                        "Нода недоступна",
                        checked_at=checked_at,
                    ),
                }
            state = await provisioner._load_state()  # type: ignore[attr-defined]
            config_payload = state.get("config") if isinstance(state, dict) else {}
            if not isinstance(config_payload, dict) or not _xray_remote_has_client(
                config_payload,
                client_uuid=device.client_uuid,
                email=device.email,
            ):
                return {
                    "device_id": device.id,
                    "mode_label": mode_label,
                    **_build_device_status_payload(
                        "broken",
                        "Клиент не найден на сервере",
                        checked_at=checked_at,
                    ),
                }
        except Exception:
            logger.exception("Failed to check XRAY_CORE device status for user_id=%s device_id=%s", user.id, device.id)
            return {
                "device_id": device.id,
                "mode_label": mode_label,
                **_build_device_status_payload(
                    "broken",
                    "Ошибка чтения runtime-ноды",
                    checked_at=checked_at,
                ),
            }
        finally:
            await provisioner.close()

        if recent_activation:
            return {
                "device_id": device.id,
                "mode_label": mode_label,
                **_build_device_status_payload(
                    "healthy",
                    "Недавно было подключение",
                    checked_at=checked_at,
                ),
            }

        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "healthy",
                "Ключ найден на сервере, нода отвечает",
                checked_at=checked_at,
            ),
        }

    if recent_activation:
        return {
            "device_id": device.id,
            "mode_label": mode_label,
            **_build_device_status_payload(
                "healthy",
                "Недавно было подключение",
                checked_at=checked_at,
            ),
        }

    return {
        "device_id": device.id,
        "mode_label": mode_label,
        **_build_device_status_payload(
            "healthy",
            "Явных серверных проблем не найдено",
            checked_at=checked_at,
        ),
    }


def _dashboard_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DASHBOARD_TIMEZONE)


def dashboard_local_date(value: datetime | None) -> date | None:
    localized = _dashboard_datetime(value)
    if localized is None:
        return None
    return localized.date()


def dashboard_day_start(value: datetime | None = None) -> datetime:
    localized = _dashboard_datetime(value or utcnow())
    if localized is None:
        localized = datetime.now(DASHBOARD_TIMEZONE)
    return localized.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    localized = _dashboard_datetime(value)
    if localized is None:
        return "—"
    return localized.strftime(f"%Y-%m-%d %H:%M {DASHBOARD_TIMEZONE_LABEL}")


def format_dashboard_datetime(value: datetime | None) -> str:
    return _format_datetime(value)


def _serialize_vpn_repair_event(event) -> dict:
    outcome = normalize_repair_outcome(event.result, event.reason)
    source = normalize_repair_source(event.reason)
    return {
        "result": outcome,
        "outcome": outcome,
        "outcome_label": repair_outcome_label(event.result, event.reason),
        "source": source,
        "source_label": repair_source_label(event.reason),
        "reason": normalize_repair_event_reason(event.reason, event.result),
        "reason_label": normalize_repair_event_reason_label(event.reason, event.result),
        "created_at": _format_datetime(event.created_at),
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_synthetic_user(user: User) -> bool:
    return shared_is_synthetic_user(user)


def _synthetic_username_sql_predicates(column) -> tuple:
    return shared_synthetic_username_sql_predicates(column)


def _real_user_sql_clause(model=User):
    return shared_real_user_sql_clause(model)


def _real_user_ids_subquery():
    return select(User.id).where(_real_user_sql_clause())


def _is_synthetic_payment_record(record: PaymentRecord, users_by_id: dict[int, User]) -> bool:
    user_id = getattr(record, "user_id", None)
    if user_id is None:
        return False
    user = users_by_id.get(int(user_id))
    if user is None:
        return False
    return _is_synthetic_user(user)


async def _support_users_by_ticket_keys(keys: set[int]) -> dict[int, User]:
    normalized_keys = {int(item) for item in keys if item is not None}
    if not normalized_keys:
        return {}
    int32_max = 2_147_483_647
    user_id_keys = sorted(key for key in normalized_keys if 0 <= key <= int32_max)
    telegram_id_keys = sorted(normalized_keys)
    user_filters = []
    if user_id_keys:
        user_filters.append(User.id.in_(user_id_keys))
    if telegram_id_keys:
        user_filters.append(User.telegram_id.in_(telegram_id_keys))
    if not user_filters:
        return {}
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(User).where(or_(*user_filters))
                )
            ).scalars().all()
        )
    mapping: dict[int, User] = {}
    for row in rows:
        if getattr(row, "id", None) is not None:
            mapping[int(row.id)] = row
        if getattr(row, "telegram_id", None) is not None:
            mapping[int(row.telegram_id)] = row
    return mapping


async def _filter_support_tickets_for_real_users(tickets: list[dict]) -> list[dict]:
    if not tickets:
        return []
    users_by_key = await _support_users_by_ticket_keys(
        {int(item.get("user_id")) for item in tickets if item.get("user_id") is not None}
    )
    filtered: list[dict] = []
    for ticket in tickets:
        user = users_by_key.get(int(ticket.get("user_id")))
        if user is not None and _is_synthetic_user(user):
            continue
        filtered.append(ticket)
    return filtered


def _belongs_to_real_user(user: User | None) -> bool:
    return user is not None and not _is_synthetic_user(user)


async def _managed_region_device_stats() -> dict[str, dict[str, int]]:
    cached = _runtime_cache_get("managed_region_device_stats")
    if cached is not None:
        return cached

    async with async_session() as session:
        users = {
            item.id: item
            for item in (
                await session.execute(select(User).where(_real_user_sql_clause()))
            ).scalars().all()
        }
        clients = list(
            (
                await session.execute(
                    select(VpnClient).where(VpnClient.user_id.in_(_real_user_ids_subquery()))
                )
            ).scalars().all()
        )

    stats: dict[str, dict[str, int]] = {}
    region_user_sets: dict[str, set[int]] = {}
    region_active_user_sets: dict[str, set[int]] = {}

    for client in clients:
        user = users.get(client.user_id)
        if user is None or _is_synthetic_user(user):
            continue
        try:
            metadata = json.loads(client.client_data or "{}")
        except json.JSONDecodeError:
            metadata = {}
        country_code = normalize_country_code(metadata.get("country_code"))
        region_stats = stats.setdefault(country_code, {"total_devices": 0, "active_devices": 0, "users": 0, "active_users": 0})
        region_user_sets.setdefault(country_code, set()).add(user.id)
        region_stats["total_devices"] += 1
        if has_active_access_from_user(user) and not getattr(user, "is_blocked", False):
            region_stats["active_devices"] += 1
            region_active_user_sets.setdefault(country_code, set()).add(user.id)

    for country_code, user_ids in region_user_sets.items():
        stats.setdefault(country_code, {"total_devices": 0, "active_devices": 0, "users": 0, "active_users": 0})["users"] = len(user_ids)
    for country_code, user_ids in region_active_user_sets.items():
        stats.setdefault(country_code, {"total_devices": 0, "active_devices": 0, "users": 0, "active_users": 0})["active_users"] = len(user_ids)

    _runtime_cache_set("managed_region_device_stats", stats)
    return copy.deepcopy(stats)


async def _dashboard_region_capacity_error(country_code: str) -> str | None:
    normalized = normalize_country_code(country_code)
    if is_retired_region(normalized):
        return "Регион Эстония выведен из продуктового контура. Создай устройство в Германии или Дании."
    if normalized != "ee":
        return None

    rule = get_region_limit_rule(normalized)
    snapshots = await get_server_snapshots(force_refresh=True)
    snapshot = next((item for item in snapshots if item.get("country_code") == normalized), None)
    if snapshot is None:
        return "Сервер Эстония сейчас временно недоступен. Попробуй Германию."

    if snapshot.get("status") != "active":
        return "Сервер Эстония сейчас недоступен. Попробуй Германию."
    if snapshot.get("host_status") not in {None, "ok"} or snapshot.get("ssh_status") not in {None, "active", "ok"}:
        return "Сервер Эстония сейчас недоступен. Попробуй Германию."
    if snapshot.get("xui_status") in {"error", "failed"}:
        return "Сервер Эстония сейчас недоступен. Попробуй Германию."

    active_devices = await count_region_vpn_clients(normalized, active_only=True)
    reasons = region_soft_limit_reasons(
        rule,
        active_devices=active_devices,
        cpu_used_percent=float(snapshot.get("cpu_percent") or 0),
        memory_used_percent=float(snapshot.get("memory_used_percent") or 0),
        disk_used_percent=float(snapshot.get("disk_used_percent") or 0),
        load_average=parse_load_average(snapshot.get("load")),
    )
    if reasons or snapshot.get("overall_state") == "critical":
        return "В данный момент сервер Эстония перегружен. Попробуй Германию."
    return None


def _region_stats_key(country_code: str | None) -> str | None:
    raw = (country_code or "").strip().lower()
    if not raw:
        return None
    if raw in {"de", "ee", "dk", "se"}:
        return raw
    if raw in {"nl"}:
        return "de"
    return None


def _health_state(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    if value >= 85:
        return "critical"
    if value >= 70:
        return "warning"
    return "healthy"


def _merge_health_states(*states: str) -> str:
    if "critical" in states:
        return "critical"
    if "warning" in states:
        return "warning"
    if "healthy" in states:
        return "healthy"
    return "unknown"


def _parse_backup_signal_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _read_backup_source_signal(root: Path, source_key: str) -> dict | None:
    status_path = root / "status" / f"{source_key}.json"
    if not status_path.exists():
        return None
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_backup_status(*, backup_root: Path | None = None, now: datetime | None = None) -> dict:
    root = backup_root or BACKUP_ROOT
    current_time = now or utcnow()
    candidates: list[Path] = []
    signal_candidates: list[datetime] = []
    patterns = [
        "amonora_db*.dump",
        "pg/amonora_db*.sql.gz",
        "support_tickets*.json",
        "payments/*.json.gz",
    ]

    for pattern in patterns:
        candidates.extend(path for path in root.glob(pattern) if path.is_file())

    source_rows = []
    for key, (label, folder_name) in BACKUP_SOURCE_PATHS.items():
        folder = root / folder_name
        signal = _read_backup_source_signal(root, key) or {}
        signal_dt = _parse_backup_signal_datetime(signal.get("last_backup_at"))
        signal_offsite_dt = _parse_backup_signal_datetime(signal.get("offsite_synced_at"))
        if signal_dt is not None:
            signal_candidates.append(signal_dt)
        if not folder.exists():
            if signal_dt is not None:
                age_hours = max((current_time - signal_dt).total_seconds() / 3600, 0.0)
                stale = age_hours > BACKUP_STALE_HOURS
                source_rows.append(
                    {
                        "key": key,
                        "label": label,
                        "last_backup_at": _format_datetime(signal_dt),
                        "backup_stale": stale,
                        "status": "warning" if stale else "healthy",
                        "age_hours": round(age_hours, 1),
                        "recent_files": 0,
                        "runner": str(signal.get("runner") or "unknown"),
                        "offsite_status": str(signal.get("offsite_status") or "unknown"),
                        "offsite_synced_at": _format_datetime(signal_offsite_dt),
                    }
                )
                continue
            source_rows.append(
                {
                    "key": key,
                    "label": label,
                    "last_backup_at": "—",
                    "backup_stale": True,
                    "status": "warning",
                    "age_hours": None,
                    "recent_files": 0,
                    "runner": "unknown",
                    "offsite_status": "unknown",
                    "offsite_synced_at": "—",
                }
            )
            continue

        files = [path for path in folder.rglob("*") if path.is_file()]
        if not files:
            if signal_dt is not None:
                age_hours = max((current_time - signal_dt).total_seconds() / 3600, 0.0)
                stale = age_hours > BACKUP_STALE_HOURS
                source_rows.append(
                    {
                        "key": key,
                        "label": label,
                        "last_backup_at": _format_datetime(signal_dt),
                        "backup_stale": stale,
                        "status": "warning" if stale else "healthy",
                        "age_hours": round(age_hours, 1),
                        "recent_files": 0,
                        "runner": str(signal.get("runner") or "unknown"),
                        "offsite_status": str(signal.get("offsite_status") or "unknown"),
                        "offsite_synced_at": _format_datetime(signal_offsite_dt),
                    }
                )
                continue
            source_rows.append(
                {
                    "key": key,
                    "label": label,
                    "last_backup_at": "—",
                    "backup_stale": True,
                    "status": "warning",
                    "age_hours": None,
                    "recent_files": 0,
                    "runner": "unknown",
                    "offsite_status": "unknown",
                    "offsite_synced_at": "—",
                }
            )
            continue

        latest_file = max(files, key=lambda path: path.stat().st_mtime)
        latest_dt = datetime.fromtimestamp(latest_file.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
        age_hours = max((current_time - latest_dt).total_seconds() / 3600, 0.0)
        stale = age_hours > BACKUP_STALE_HOURS
        source_rows.append(
            {
                "key": key,
                "label": label,
                "last_backup_at": _format_datetime(latest_dt),
                "backup_stale": stale,
                "status": "warning" if stale else "healthy",
                "age_hours": round(age_hours, 1),
                "recent_files": sum(
                    1 for path in files
                    if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
                    >= current_time - timedelta(hours=BACKUP_STALE_HOURS)
                ),
                "runner": str(signal.get("runner") or "filesystem"),
                "offsite_status": str(signal.get("offsite_status") or "unknown"),
                "offsite_synced_at": _format_datetime(signal_offsite_dt),
            }
        )

    if not candidates:
        if signal_candidates:
            latest_dt = max(signal_candidates)
            age_hours = max((current_time - latest_dt).total_seconds() / 3600, 0.0)
            stale = age_hours > BACKUP_STALE_HOURS
            return {
                "last_backup_at": _format_datetime(latest_dt),
                "backup_stale": stale,
                "status": "warning" if stale else "healthy",
                "age_hours": round(age_hours, 1),
                "stale_definition_hours": BACKUP_STALE_HOURS,
                "sources": source_rows,
            }
        return {
            "last_backup_at": "—",
            "backup_stale": True,
            "status": "warning",
            "age_hours": None,
            "stale_definition_hours": BACKUP_STALE_HOURS,
            "sources": source_rows,
        }

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    latest_dt = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
    age_hours = max((current_time - latest_dt).total_seconds() / 3600, 0.0)
    stale = age_hours > BACKUP_STALE_HOURS
    return {
        "last_backup_at": _format_datetime(latest_dt),
        "backup_stale": stale,
        "status": "warning" if stale else "healthy",
        "age_hours": round(age_hours, 1),
        "stale_definition_hours": BACKUP_STALE_HOURS,
        "sources": source_rows,
    }


def _build_restore_validation_status(*, now: datetime | None = None) -> dict:
    current_time = now or utcnow()
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
    for status_path in (RESTORE_PROOF_STATUS_PATH, RESTORE_VALIDATION_STATUS_PATH):
        if not status_path.exists():
            continue
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        last_validation_raw = str(payload.get("last_restore_validation_at") or "").strip()
        last_validation = _parse_iso_datetime(last_validation_raw)
        proof_kind = str(payload.get("proof_kind") or "").strip().lower()
        proof_status = str(payload.get("proof_status") or "").strip().lower()
        proof_scope = payload.get("proof_scope")
        normalized_scope = (
            {str(item).strip().lower() for item in proof_scope}
            if isinstance(proof_scope, list)
            else set()
        )
        validated_public_tables = payload.get("validated_public_tables")
        has_real_restore_proof = (
            proof_kind == "temporary_database_restore"
            and proof_status == "verified"
            and "core_pg" in normalized_scope
            and isinstance(validated_public_tables, int)
            and validated_public_tables > 0
        )
        if last_validation is not None:
            if last_validation.tzinfo is not None:
                last_validation = last_validation.astimezone(timezone.utc).replace(tzinfo=None)
            age_days = max((current_time - last_validation).total_seconds() / 86400, 0.0)
            stale = age_days > RESTORE_VALIDATION_STALE_DAYS
            status = str(payload.get("status") or "").strip().lower() or ("warning" if stale else "healthy")
            if status not in {"healthy", "warning", "failed", "unknown"}:
                status = "warning" if stale else "healthy"
            if not has_real_restore_proof:
                status = "unknown"
                stale = True
            return {
                "last_restore_validation_at": _format_datetime(last_validation),
                "restore_validation_stale": stale,
                "status": status,
                "age_days": round(age_days, 1),
                "stale_definition_days": RESTORE_VALIDATION_STALE_DAYS,
                "signal_source": "machine-readable restore proof status",
                "proof_kind": proof_kind or "missing",
                "proof_status": proof_status or "missing",
                "proof_scope": sorted(normalized_scope),
                "validated_public_tables": validated_public_tables if isinstance(validated_public_tables, int) else None,
                "real_restore_proof": has_real_restore_proof,
            }

    return {
        "last_restore_validation_at": "—",
        "restore_validation_stale": True,
        "status": "unknown",
        "age_days": None,
        "stale_definition_days": RESTORE_VALIDATION_STALE_DAYS,
        "signal_source": "machine-readable restore proof status",
        "proof_kind": "missing",
        "proof_status": "missing",
        "proof_scope": [],
        "validated_public_tables": None,
        "real_restore_proof": False,
    }


def _ping_thresholds(country_code: str | None) -> tuple[float, float]:
    code = str(country_code or "").strip().lower()
    if code == "de":
        return 140.0, 260.0
    if code == "ee":
        return 100.0, 180.0
    return 80.0, 150.0


def _ping_state(latency_ms: float | None, country_code: str | None = None) -> str:
    if latency_ms is None:
        return "unknown"
    warning_threshold, critical_threshold = _ping_thresholds(country_code)
    if latency_ms >= critical_threshold:
        return "critical"
    if latency_ms >= warning_threshold:
        return "warning"
    return "healthy"


def _format_speed_mbps(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f} Mbps"


def _runtime_cache_get(name: str):
    slot = _RUNTIME_CACHE.get(name)
    if slot is None:
        return None
    if slot["value"] is None or float(slot["expires_at"]) <= time.time():
        return None
    return copy.deepcopy(slot["value"])


def _runtime_cache_peek(name: str):
    slot = _RUNTIME_CACHE.get(name)
    if slot is None or slot["value"] is None:
        return None
    return copy.deepcopy(slot["value"])


def _runtime_cache_set(name: str, value, ttl: float | None = None) -> None:
    slot = _RUNTIME_CACHE.setdefault(name, {"expires_at": 0.0, "value": None})
    slot["value"] = copy.deepcopy(value)
    slot["expires_at"] = time.time() + (ttl if ttl is not None else _RUNTIME_CACHE_TTL.get(name, 5.0))


def invalidate_runtime_cache(*names: str) -> None:
    keys = set(names or tuple(_RUNTIME_CACHE.keys()))
    if {"overview_metrics", "server_snapshots", "xui_summary"} & keys:
        keys.update({"managed_region_device_stats", "vpn_overview_default"})
    for name in keys:
        if name in _RUNTIME_CACHE:
            _RUNTIME_CACHE[name]["value"] = None
            _RUNTIME_CACHE[name]["expires_at"] = 0.0


def _channel_subscription_cache_snapshot() -> dict[str, dict[str, object]]:
    cached = _runtime_cache_peek("channel_subscription_statuses")
    if isinstance(cached, dict):
        return cached
    return {}


def _traffic_baseline_server_key(snapshot: dict) -> str:
    return str(
        snapshot.get("id")
        or snapshot.get("name")
        or snapshot.get("host")
        or snapshot.get("public_ip")
        or "unknown"
    )


def _traffic_snapshot_total_transfer_gb(snapshot: dict) -> float:
    if "total_transfer_gb" in snapshot and snapshot.get("total_transfer_gb") is not None:
        return float(snapshot.get("total_transfer_gb") or 0)
    return float(snapshot.get("network_sent_gb") or 0) + float(snapshot.get("network_recv_gb") or 0)


def _parse_traffic_baseline_reset_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _traffic_baseline_period_key(value: datetime | None) -> str | None:
    localized = _dashboard_datetime(value)
    if localized is None:
        return None
    return localized.strftime("%Y-%m")


def _current_traffic_baseline_period_key(now: datetime | None = None) -> str:
    return _traffic_baseline_period_key(now or utcnow()) or utcnow().strftime("%Y-%m")


def _build_traffic_baseline_payload(snapshots: list[dict], *, reset_at: datetime | None = None) -> dict[str, object]:
    effective_reset_at = reset_at or utcnow()
    return {
        "reset_at": effective_reset_at.isoformat(),
        "servers": {
            _traffic_baseline_server_key(item): _traffic_snapshot_total_transfer_gb(item)
            for item in snapshots
        },
    }


def _traffic_baseline_is_current(baseline: dict[str, object] | None, *, now: datetime | None = None) -> bool:
    if not isinstance(baseline, dict):
        return False
    reset_at = _parse_traffic_baseline_reset_at(baseline.get("reset_at"))
    if reset_at is None:
        return False
    return _traffic_baseline_period_key(reset_at) == _current_traffic_baseline_period_key(now)


def get_traffic_baseline() -> dict[str, object]:
    baseline = _runtime_cache_peek("traffic_baseline")
    if isinstance(baseline, dict):
        return baseline
    return {"reset_at": None, "servers": {}}


def apply_traffic_baseline_to_snapshots(snapshots: list[dict]) -> tuple[list[dict], dict[str, object]]:
    baseline = get_traffic_baseline()
    baseline_servers = baseline.get("servers", {}) if isinstance(baseline, dict) else {}
    if not isinstance(baseline_servers, dict):
        baseline_servers = {}
    adjusted: list[dict] = []
    for item in snapshots:
        current_transfer = _traffic_snapshot_total_transfer_gb(item)
        baseline_value = float(baseline_servers.get(_traffic_baseline_server_key(item)) or 0)
        adjusted_transfer = max(round(current_transfer - baseline_value, 2), 0.0)
        adjusted.append({**item, "total_transfer_gb": adjusted_transfer})
    return adjusted, baseline


async def ensure_current_traffic_baseline(snapshots: list[dict] | None = None) -> dict[str, object]:
    cached = get_traffic_baseline()
    if _traffic_baseline_is_current(cached):
        return cached

    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DashboardAuditLog)
                    .where(
                        DashboardAuditLog.target_type == "traffic",
                        DashboardAuditLog.action.in_(("reset_traffic_baseline", "auto_reset_traffic_baseline")),
                    )
                    .order_by(DashboardAuditLog.created_at.desc(), DashboardAuditLog.id.desc())
                    .limit(6)
                )
            ).scalars().all()
        )
    for row in rows:
        try:
            parsed = json.loads(row.details_text or "{}")
        except json.JSONDecodeError:
            continue
        if _traffic_baseline_is_current(parsed):
            _runtime_cache_set("traffic_baseline", parsed)
            return parsed

    if snapshots is None:
        snapshots = await get_server_snapshots(force_refresh=True)
    baseline = _build_traffic_baseline_payload(snapshots)
    _runtime_cache_set("traffic_baseline", baseline)
    await create_audit_log(
        None,
        "auto_reset_traffic_baseline",
        "traffic",
        None,
        json.dumps({"before": cached, "after": baseline}, ensure_ascii=False),
        None,
    )
    return baseline


async def reset_traffic_baseline(admin: DashboardAdmin, ip_address: str | None) -> dict[str, object]:
    previous_baseline = get_traffic_baseline()
    snapshots = await get_server_snapshots(force_refresh=True)
    baseline = _build_traffic_baseline_payload(snapshots)
    _runtime_cache_set("traffic_baseline", baseline)
    await create_audit_log(
        admin.id,
        "reset_traffic_baseline",
        "traffic",
        None,
        json.dumps({"before": previous_baseline, "after": baseline}, ensure_ascii=False),
        ip_address,
    )
    return baseline


def _channel_subscription_cache_entry_is_fresh(entry: dict[str, object] | None) -> bool:
    if not entry:
        return False
    checked_at_ts = float(entry.get("checked_at_ts") or 0.0)
    if checked_at_ts <= 0:
        return False
    ttl_seconds = (
        CHANNEL_SUBSCRIPTION_UNKNOWN_TTL_SECONDS
        if str(entry.get("status") or "unknown") == "unknown"
        else CHANNEL_SUBSCRIPTION_OK_TTL_SECONDS
    )
    return (time.time() - checked_at_ts) <= ttl_seconds


def _channel_subscription_unknown_payload() -> dict[str, object]:
    now = utcnow()
    checked_at_ts = time.time()
    return {
        "status": "unknown",
        "label": "Не проверено",
        "checked_at": format_dashboard_datetime(now),
        "checked_at_ts": checked_at_ts,
    }


def _store_channel_subscription_entries(entries: dict[int, dict[str, object]]) -> None:
    if not entries:
        return
    cache_map = _channel_subscription_cache_snapshot()
    for telegram_id, payload in entries.items():
        cache_map[str(int(telegram_id))] = dict(payload)
    if len(cache_map) > CHANNEL_SUBSCRIPTION_CACHE_MAX_ITEMS:
        ordered = sorted(
            cache_map.items(),
            key=lambda item: float(item[1].get("checked_at_ts") or 0.0),
            reverse=True,
        )[:CHANNEL_SUBSCRIPTION_CACHE_MAX_ITEMS]
        cache_map = dict(ordered)
    _runtime_cache_set("channel_subscription_statuses", cache_map, ttl=CHANNEL_SUBSCRIPTION_OK_TTL_SECONDS)


async def _fetch_channel_subscription_status(bot: Bot, telegram_id: int) -> dict[str, object]:
    now = utcnow()
    checked_at_ts = time.time()
    try:
        subscribed = await asyncio.wait_for(
            is_user_subscribed(bot=bot, channel_id=config.channel_id, user_id=int(telegram_id)),
            timeout=3.0,
        )
    except (asyncio.TimeoutError, TelegramBadRequest, TelegramForbiddenError):
        subscribed = None
    except Exception:
        logger.exception("Failed to resolve channel subscription status telegram_id=%s", telegram_id)
        subscribed = None

    if subscribed is None:
        return {
            "status": "unknown",
            "label": "Не проверено",
            "checked_at": format_dashboard_datetime(now),
            "checked_at_ts": checked_at_ts,
        }
    return {
        "status": "subscribed" if subscribed else "not_subscribed",
        "label": "Подписан" if subscribed else "Не подписан",
        "checked_at": format_dashboard_datetime(now),
        "checked_at_ts": checked_at_ts,
    }


async def get_channel_subscription_statuses(
    telegram_ids: list[int | None],
    *,
    force_refresh: bool = False,
) -> dict[int, dict[str, object]]:
    normalized_ids = sorted({int(value) for value in telegram_ids if value is not None and int(value) > 0})
    if not normalized_ids:
        return {}

    cached = _channel_subscription_cache_snapshot()
    results: dict[int, dict[str, object]] = {}
    pending: list[int] = []
    for telegram_id in normalized_ids:
        entry = cached.get(str(telegram_id))
        if not force_refresh and _channel_subscription_cache_entry_is_fresh(entry):
            results[telegram_id] = dict(entry)
        else:
            pending.append(telegram_id)

    if not pending:
        return results

    if not config.bot_token or not config.channel_id:
        for telegram_id in pending:
            results[telegram_id] = _channel_subscription_unknown_payload()
        return results

    semaphore = asyncio.Semaphore(CHANNEL_SUBSCRIPTION_CONCURRENCY)
    bot = Bot(config.bot_token)
    fetched: dict[int, dict[str, object]] = {}

    async def _worker(telegram_id: int) -> tuple[int, dict[str, object]]:
        async with semaphore:
            return telegram_id, await _fetch_channel_subscription_status(bot, telegram_id)

    try:
        resolved = await asyncio.gather(*[_worker(telegram_id) for telegram_id in pending])
    finally:
        await bot.session.close()

    for telegram_id, payload in resolved:
        fetched[telegram_id] = payload
        results[telegram_id] = dict(payload)

    _store_channel_subscription_entries(fetched)
    return results


def invalidate_docs_cache(*slugs: str) -> None:
    manifest_cache = _DOCS_CACHE["manifest"]
    manifest_cache["value"] = None
    manifest_cache["expires_at"] = 0.0
    docs_cache: dict = _DOCS_CACHE["docs"]
    if not slugs:
        docs_cache.clear()
        return
    for slug in slugs:
        docs_cache.pop(slug, None)


def _read_int_env(name: str, default: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except (TypeError, ValueError, AttributeError):
        return default


def _format_rub(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def payment_status_is_open(status: str | None) -> bool:
    return str(status or "").strip().lower() in MANUAL_PAYMENT_OPEN_STATUSES


def payment_status_holds_balance(status: str | None) -> bool:
    return str(status or "").strip().lower() in BALANCE_HOLD_PAYMENT_STATUSES


def dashboard_user_status(user: User, *, latest_payment_status: str | None = None) -> dict[str, str]:
    access_status = get_access_status_from_user(user)
    repair_reason = normalize_repair_reason(getattr(user, "vpn_repair_reason", None))

    if getattr(user, "is_blocked", False):
        return {"code": "blocked", "label": "Заблокирован"}
    if getattr(user, "vpn_repair_needed", False):
        if repair_reason and "sync" in repair_reason:
            return {"code": "sync_error", "label": "Ошибка синхронизации"}
        return {"code": "repair_needed", "label": "Требует ремонта"}
    if access_status in {"paid_active", "vip_active"}:
        return {"code": "active", "label": "Активен"}
    if access_status == "trial_active":
        return {"code": "trial", "label": "Пробный"}
    if payment_status_is_open(latest_payment_status):
        return {"code": "awaiting_payment", "label": "Ожидает оплату"}
    return {"code": "no_access", "label": "Без доступа"}


def dashboard_server_state(snapshot: dict) -> dict[str, str]:
    status = str(snapshot.get("status") or "").strip().lower()
    overall_state = str(snapshot.get("overall_state") or "").strip().lower()
    runtime_state = _runtime_service_health_state(snapshot)
    monitoring_gap = _has_remote_monitoring_gap(snapshot)

    if status == "maintenance":
        return {"code": "maintenance", "label": "Обслуживание"}
    if status in {"disabled", "down"}:
        return {"code": "down", "label": "Down"}
    if monitoring_gap:
        return {"code": "degradation", "label": "Деградация мониторинга"}
    if runtime_state == "critical":
        return {"code": "degradation", "label": "Деградация runtime"}
    if overall_state in {"warning", "critical"}:
        return {"code": "degradation", "label": "Деградация"}
    return {"code": "active", "label": "Активна"}


def _read_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    rows: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows[key] = value
    return rows


def get_runtime_tariffs() -> dict[str, int]:
    env_map = _read_env_map()

    def read_value(key: str, fallback: int) -> int:
        try:
            return int(env_map.get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    return {
        "tariff_1m_rub": read_value("TARIFF_1M_RUB", config.tariff_1m_rub or 0),
        "tariff_3m_rub": read_value("TARIFF_3M_RUB", config.tariff_3m_rub or 0),
        "tariff_6m_rub": read_value("TARIFF_6M_RUB", config.tariff_6m_rub or 0),
        "tariff_12m_rub": read_value("TARIFF_12M_RUB", config.tariff_12m_rub or 0),
    }


def get_runtime_tariffs_list() -> list[dict]:
    runtime = get_runtime_tariffs()
    return [
        {"code": "1m", "title": "1 месяц", "rub_price": runtime["tariff_1m_rub"], "duration_days": 30},
        {"code": "3m", "title": "3 месяца", "rub_price": runtime["tariff_3m_rub"], "duration_days": gift_duration_days(90, "3m")},
        {"code": "6m", "title": "6 месяцев", "rub_price": runtime["tariff_6m_rub"], "duration_days": gift_duration_days(180, "6m")},
        {"code": "12m", "title": "12 месяцев", "rub_price": runtime["tariff_12m_rub"], "duration_days": gift_duration_days(365, "12m")},
    ]


def _payment_method_label(method: str) -> str:
    if method == "telegram_stars":
        return "⭐ Telegram Stars"
    if method == "crypto_bot":
        return "💎 Crypto Bot"
    if method == "sbp_platega":
        return "💳 СБП (Platega)"
    if method == "crypto_platega":
        return "💎 Криптовалюта (Platega)"
    return manual_payment_method_label(method)


def _provider_payment_fields(record: PaymentRecord, metadata: dict | None = None) -> dict:
    meta = metadata or _load_payment_metadata(record.metadata_json)
    is_provider_payment = is_platega_payment_method(record.payment_method)
    return {
        "provider_name": meta.get("provider_name") if is_provider_payment else None,
        "provider_transaction_id": record.external_payment_id if is_provider_payment else None,
        "provider_status": meta.get("provider_status") if is_provider_payment else None,
        "checkout_url": meta.get("checkout_url") if is_provider_payment else None,
        "last_provider_sync_at": meta.get("last_synced_at") if is_provider_payment else None,
        "can_sync_provider": bool(is_provider_payment and record.external_payment_id),
        "provider_sync_problem": meta.get("provider_sync_problem") if is_provider_payment else None,
    }


def _get_runtime_tariff(code: str):
    runtime_map = {item["code"]: item for item in get_runtime_tariffs_list()}
    item = runtime_map.get(code)
    if item is None:
        return get_tariff(code)
    return type("RuntimeTariff", (), item)()


def _manual_payment_breakdown(payment_rows: list[PaymentRecord]) -> dict[str, list[PaymentRecord]]:
    return {
        "confirmed": [item for item in payment_rows if item.payment_status == "confirmed"],
        "awaiting_user_payment": [item for item in payment_rows if item.payment_status == "awaiting_user_payment"],
        "awaiting_admin_review": [item for item in payment_rows if item.payment_status == "awaiting_admin_review"],
        "rejected": [item for item in payment_rows if item.payment_status == "rejected"],
        "open_manual": [item for item in payment_rows if item.payment_status in MANUAL_PAYMENT_OPEN_STATUSES],
    }


def _payment_record_counts_as_revenue(record: PaymentRecord) -> bool:
    return record.payment_status == "confirmed" and payment_method_counts_as_revenue(record.payment_method)


def _remote_ssh_settings() -> dict:
    return {
        "user": os.getenv("DASHBOARD_REMOTE_SSH_USER", "root").strip() or "root",
        "port": int(os.getenv("DASHBOARD_REMOTE_SSH_PORT", "22")),
        "key_path": Path(os.getenv("DASHBOARD_REMOTE_SSH_KEY_PATH", str(DEFAULT_REMOTE_SSH_KEY_PATH))),
        "known_hosts": Path(os.getenv("DASHBOARD_REMOTE_SSH_KNOWN_HOSTS", str(DEFAULT_REMOTE_KNOWN_HOSTS))),
        "timeout": float(os.getenv("DASHBOARD_REMOTE_SSH_TIMEOUT", "6")),
    }


async def _ssh_command(
    host: str,
    *remote_args: str,
    stdin_data: str | None = None,
) -> tuple[int, str]:
    settings = _remote_ssh_settings()
    command = [
        "ssh",
        "-i",
        str(settings["key_path"]),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={settings['known_hosts']}",
        "-o",
        f"ConnectTimeout={int(settings['timeout'])}",
        "-p",
        str(settings["port"]),
        f"{settings['user']}@{host}",
        *remote_args,
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate(stdin_data.encode("utf-8") if stdin_data is not None else None)
    return process.returncode, stdout.decode("utf-8", errors="ignore").strip()


def _remote_speed_snapshot(sample_key: str, tx_bytes: int | None, rx_bytes: int | None) -> dict:
    now = time.perf_counter()
    previous = _NETWORK_SAMPLES.get(sample_key)
    _NETWORK_SAMPLES[sample_key] = (now, int(tx_bytes or 0), int(rx_bytes or 0))
    if previous is None:
        return {
            "tx_mbps": 0.0,
            "rx_mbps": 0.0,
            "tx_label": "0.00 Mbps",
            "rx_label": "0.00 Mbps",
        }

    previous_time, previous_sent, previous_recv = previous
    elapsed = max(now - previous_time, 0.001)
    tx_mbps = max((((int(tx_bytes or 0) - previous_sent) * 8) / elapsed) / 1_000_000, 0.0)
    rx_mbps = max((((int(rx_bytes or 0) - previous_recv) * 8) / elapsed) / 1_000_000, 0.0)
    return {
        "tx_mbps": round(tx_mbps, 2),
        "rx_mbps": round(rx_mbps, 2),
        "tx_label": _format_speed_mbps(tx_mbps),
        "rx_label": _format_speed_mbps(rx_mbps),
    }


def _normalize_doc_slug(slug: str | None) -> str | None:
    if slug is None:
        return None
    normalized = posixpath.normpath(slug.replace("\\", "/")).lstrip("/")
    if normalized in {"", "."}:
        return None
    if normalized.startswith("..") or "/.." in normalized or not normalized.endswith(".md"):
        return None
    return normalized


def _local_docs_manifest_path() -> Path:
    return DOCS_ROOT / "manifest.json"


def _local_docs_file_path(slug: str) -> Path:
    return DOCS_ROOT / slug


def _docs_raw_url(slug: str) -> str:
    settings = documentation_settings()
    return (
        f"https://raw.githubusercontent.com/"
        f"{settings['owner']}/{settings['repo']}/{settings['branch']}/{settings['path']}/{slug}"
    )


def _docs_blob_url(slug: str) -> str:
    settings = documentation_settings()
    return (
        f"https://github.com/"
        f"{settings['owner']}/{settings['repo']}/blob/{settings['branch']}/{settings['path']}/{slug}"
    )


def _generated_report_item() -> dict | None:
    report_path = DOCS_ROOT / OPERATIONS_REPORT_SLUG
    if not report_path.exists():
        return None
    generated_at = datetime.fromtimestamp(report_path.stat().st_mtime)
    return {
        "slug": OPERATIONS_REPORT_SLUG,
        "title": "Операционный отчёт",
        "icon": "⬣",
        "summary": "Автоматическая сводка по серверам, бюджету, пользователям, поддержке и сервисам.",
        "github_url": None,
        "raw_url": None,
        "source_kind": "generated",
        "generated_at_label": _format_datetime(generated_at),
    }


def _generated_finance_report_item() -> dict | None:
    report_path = DOCS_ROOT / FINANCE_REPORT_SLUG
    if not report_path.exists():
        return None
    generated_at = datetime.fromtimestamp(report_path.stat().st_mtime)
    return {
        "slug": FINANCE_REPORT_SLUG,
        "title": "Финансовый отчёт",
        "icon": "◍",
        "summary": "Управленческая сводка по доходам, расходам, зарплатам, взаиморасчётам и чистому результату.",
        "github_url": None,
        "raw_url": None,
        "source_kind": "generated",
        "generated_at_label": _format_datetime(generated_at),
    }


def _generated_platform_audit_report_item() -> dict | None:
    report_path = DOCS_ROOT / PLATFORM_AUDIT_REPORT_SLUG
    if not report_path.exists():
        return None
    generated_at = datetime.fromtimestamp(report_path.stat().st_mtime)
    return {
        "slug": PLATFORM_AUDIT_REPORT_SLUG,
        "title": "Платформенный аудит",
        "icon": "◎",
        "summary": "Проверка кнопок, функций, уведомлений, безопасности и связности экосистемы Amonora.",
        "github_url": None,
        "raw_url": None,
        "source_kind": "generated",
        "generated_at_label": _format_datetime(generated_at),
    }


def _generated_docs_sections() -> list[dict]:
    items = [
        item
        for item in [
            _generated_report_item(),
            _generated_finance_report_item(),
            _generated_platform_audit_report_item(),
        ]
        if item is not None
    ]
    if not items:
        return []
    return [{"title": "Автоотчёты", "items": items}]


def _normalize_docs_manifest(manifest: dict | None) -> dict:
    manifest = manifest or {}
    sections = []
    total_docs = 0
    for section in manifest.get("sections", []):
        items = []
        for item in section.get("items", []):
            slug = _normalize_doc_slug(item.get("slug"))
            if not slug:
                continue
            source_kind = item.get("source_kind", "github")
            github_url = item["github_url"] if "github_url" in item else None
            raw_url = item["raw_url"] if "raw_url" in item else None
            items.append(
                {
                    "slug": slug,
                    "title": item.get("title", Path(slug).stem.replace("-", " ").title()),
                    "icon": item.get("icon", "•"),
                    "summary": item.get("summary", ""),
                    "github_url": github_url if github_url is not None else (_docs_blob_url(slug) if source_kind != "generated" else None),
                    "raw_url": raw_url if raw_url is not None else (_docs_raw_url(slug) if source_kind != "generated" else None),
                    "source_kind": source_kind,
                    "generated_at_label": item.get("generated_at_label"),
                }
            )
        if items:
            sections.append({"title": section.get("title", "Раздел"), "items": items})
            total_docs += len(items)
    return {
        "title": manifest.get("title", "Amonora Documentation"),
        "description": manifest.get(
            "description",
            "База знаний по Amonora: бот, dashboard, инфраструктура, deployment и инструкции.",
        ),
        "sections": sections,
        "total_docs": total_docs,
    }


def _flatten_doc_items(sections: list[dict]) -> list[dict]:
    items: list[dict] = []
    for section in sections:
        items.extend(section.get("items", []))
    return items


def _merge_doc_manifests(primary: dict, secondary: dict) -> dict:
    merged_sections = copy.deepcopy(primary.get("sections", []))
    seen_slugs = {item["slug"] for item in _flatten_doc_items(merged_sections)}
    section_map = {section["title"]: section for section in merged_sections}

    for section in secondary.get("sections", []):
        new_items = [copy.deepcopy(item) for item in section.get("items", []) if item["slug"] not in seen_slugs]
        if not new_items:
            continue
        seen_slugs.update(item["slug"] for item in new_items)
        existing = section_map.get(section["title"])
        if existing is None:
            new_section = {"title": section["title"], "items": new_items}
            merged_sections.append(new_section)
            section_map[section["title"]] = new_section
        else:
            existing["items"].extend(new_items)

    return {
        **primary,
        "sections": merged_sections,
        "total_docs": len(seen_slugs),
    }


def _read_local_docs_manifest() -> dict:
    manifest_path = _local_docs_manifest_path()
    if not manifest_path.exists():
        return _normalize_docs_manifest({})
    try:
        return _normalize_docs_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return _normalize_docs_manifest({})


def _read_local_doc(slug: str) -> str:
    path = _local_docs_file_path(slug)
    if not path.exists():
        raise FileNotFoundError(slug)
    return path.read_text(encoding="utf-8")


async def _fetch_remote_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": "AmonoraDashboard/1.0",
                "Accept": "text/plain, application/json",
            },
        )
        response.raise_for_status()
        return response.text


async def get_documentation_manifest() -> dict:
    cached = _DOCS_CACHE["manifest"]
    now = time.time()
    if cached["value"] is not None and cached["expires_at"] > now:
        return copy.deepcopy(cached["value"])

    try:
        manifest_text = await _fetch_remote_text(documentation_settings()["manifest_url"])
        manifest = _normalize_docs_manifest(json.loads(manifest_text))
    except Exception:
        manifest = _read_local_docs_manifest()

    manifest = _merge_doc_manifests(manifest, _read_local_docs_manifest())
    generated_sections = _generated_docs_sections()
    if generated_sections:
        manifest = _merge_doc_manifests(
            manifest,
            {
                "title": manifest["title"],
                "description": manifest["description"],
                "sections": generated_sections,
            },
        )

    cached["value"] = manifest
    cached["expires_at"] = now + _DOCS_CACHE_TTL
    return copy.deepcopy(manifest)


async def _get_document_text(slug: str) -> tuple[str, str]:
    docs_cache: dict = _DOCS_CACHE["docs"]
    now = time.time()
    cached = docs_cache.get(slug)
    if cached is not None and cached["expires_at"] > now:
        return cached["text"], cached["source"]

    if slug.startswith("generated/"):
        text = _read_local_doc(slug)
        source = "generated"
    else:
        try:
            text = await _fetch_remote_text(_docs_raw_url(slug))
            source = "github"
        except Exception:
            text = _read_local_doc(slug)
            source = "local"

    docs_cache[slug] = {
        "text": text,
        "source": source,
        "expires_at": now + _DOCS_CACHE_TTL,
    }
    return text, source


def _is_safe_doc_html_url(value: str | None) -> bool:
    normalized = "".join(str(value or "").split()).lower()
    return not normalized.startswith(("javascript:", "data:", "vbscript:"))


class _DocumentationHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def _clean_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = SAFE_DOC_HTML_ATTRS.get(tag, set())
        cleaned: list[tuple[str, str]] = []
        has_rel = False
        href_value = ""
        for name, value in attrs:
            attr_name = str(name or "").strip().lower()
            if not attr_name or attr_name.startswith("on"):
                continue
            if attr_name not in SAFE_DOC_HTML_GLOBAL_ATTRS and attr_name not in allowed:
                continue
            attr_value = "" if value is None else str(value)
            if attr_name in {"href", "src"} and not _is_safe_doc_html_url(attr_value):
                continue
            if tag == "a" and attr_name == "href":
                href_value = attr_value
            if tag == "a" and attr_name == "rel":
                has_rel = True
            cleaned.append((attr_name, attr_value))

        if tag == "a" and href_value.startswith(("http://", "https://")) and not has_rel:
            cleaned.append(("rel", "noopener noreferrer"))

        return "".join(f' {name}="{escape(value, quote=True)}"' for name, value in cleaned)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = str(tag or "").strip().lower()
        if normalized in BLOCKED_DOC_HTML_TAGS:
            self.blocked_depth += 1
            return
        if self.blocked_depth or normalized not in SAFE_DOC_HTML_TAGS:
            return
        self.parts.append(f"<{normalized}{self._clean_attrs(normalized, attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = str(tag or "").strip().lower()
        if normalized in BLOCKED_DOC_HTML_TAGS or self.blocked_depth or normalized not in SAFE_DOC_HTML_TAGS:
            return
        self.parts.append(f"<{normalized}{self._clean_attrs(normalized, attrs)} />")

    def handle_endtag(self, tag: str) -> None:
        normalized = str(tag or "").strip().lower()
        if normalized in BLOCKED_DOC_HTML_TAGS:
            self.blocked_depth = max(self.blocked_depth - 1, 0)
            return
        if self.blocked_depth or normalized not in SAFE_DOC_HTML_TAGS:
            return
        self.parts.append(f"</{normalized}>")

    def handle_data(self, data: str) -> None:
        if self.blocked_depth:
            return
        self.parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if self.blocked_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.blocked_depth:
            return
        self.parts.append(f"&#{name};")


def _sanitize_documentation_html(raw_html: str) -> str:
    sanitizer = _DocumentationHTMLSanitizer()
    sanitizer.feed(str(raw_html or ""))
    sanitizer.close()
    return "".join(sanitizer.parts)


async def get_documentation_page(selected_slug: str | None = None) -> dict:
    manifest = await get_documentation_manifest()
    items = _flatten_doc_items(manifest["sections"])
    settings = documentation_settings()
    if not items:
        return {
            "title": manifest["title"],
            "description": manifest["description"],
            "sections": [],
            "total_docs": 0,
            "current": None,
            "repo_url": settings["repo_url"],
            "folder_url": settings["folder_url"],
            "branch": settings["branch"],
            "source": "local",
            "source_label": "Локальная копия",
            "report_item": None,
        }

    normalized_slug = _normalize_doc_slug(selected_slug)
    current = next((item for item in items if item["slug"] == normalized_slug), items[0])
    markdown_text, source = await _get_document_text(current["slug"])
    current = {
        **current,
        "markdown": markdown_text,
        "html": _sanitize_documentation_html(
            markdown.markdown(
                markdown_text,
                extensions=["extra", "fenced_code", "tables", "sane_lists", "toc"],
            )
        ),
    }
    source_label = {
        "github": "GitHub",
        "local": "Локальная копия",
        "generated": "Сгенерированный отчёт",
    }.get(source, "Локальная копия")
    report_item = next((item for item in items if item["slug"] == OPERATIONS_REPORT_SLUG), None)
    return {
        "title": manifest["title"],
        "description": manifest["description"],
        "sections": manifest["sections"],
        "total_docs": manifest["total_docs"],
        "current": current,
        "repo_url": settings["repo_url"],
        "folder_url": settings["folder_url"],
        "branch": settings["branch"],
        "source": source,
        "source_label": source_label,
        "report_item": report_item,
    }


async def generate_operations_report(admin: DashboardAdmin | None, ip_address: str | None) -> dict:
    async with async_session() as session:
        user_rows = list((await session.execute(select(User).where(_real_user_sql_clause()))).scalars().all())
        client_rows = list(
            (
                await session.execute(
                    select(VpnClient).where(VpnClient.user_id.in_(_real_user_ids_subquery()))
                )
            ).scalars().all()
        )
        payment_rows = list(
            (
                await session.execute(
                    select(PaymentRecord).where(
                        or_(
                            PaymentRecord.user_id.is_(None),
                            PaymentRecord.user_id.in_(_real_user_ids_subquery()),
                        )
                    )
                )
            ).scalars().all()
        )
        audit_rows = list(
            (
                await session.execute(
                    select(DashboardAuditLog).order_by(DashboardAuditLog.created_at.desc()).limit(12)
                )
            ).scalars().all()
        )

    users_by_id = {user.id: user for user in user_rows}
    user_rows = [user for user in user_rows if not _is_synthetic_user(user)]
    client_rows = [client for client in client_rows if _belongs_to_real_user(users_by_id.get(client.user_id))]
    payment_rows = [record for record in payment_rows if not _is_synthetic_payment_record(record, users_by_id)]

    support_counts, service_statuses, server_snapshots = await asyncio.gather(
        get_ticket_counts(),
        get_service_statuses(force_refresh=True),
        get_server_snapshots(force_refresh=True),
    )

    now = utcnow()
    generated_at = _format_datetime(now)
    active_access = sum(1 for user in user_rows if has_active_access_from_user(user))
    active_trials = sum(1 for user in user_rows if get_access_status_from_user(user) == "trial_active")
    active_paid = sum(1 for user in user_rows if get_access_status_from_user(user) == "paid_active")
    blocked_users = sum(1 for user in user_rows if getattr(user, "is_blocked", False))
    expiring_soon = sum(
        1
        for user in user_rows
        if (access_expires_at := get_access_expires_at_from_user(user)) is not None
        and access_expires_at <= now + timedelta(days=7)
    )

    device_users = {client.user_id for client in client_rows}
    total_devices = len(client_rows)
    vless_devices = sum(1 for client in client_rows if client.protocol == "vless")
    trojan_devices = sum(1 for client in client_rows if client.protocol == "trojan")
    germany_devices = 0
    estonia_devices = 0
    for client in client_rows:
        country_code = (_device_metadata(client).get("country_code") or "").lower()
        if country_code == "de":
            germany_devices += 1
        elif country_code == "ee":
            estonia_devices += 1

    payment_breakdown = _manual_payment_breakdown(payment_rows)
    confirmed_payments = payment_breakdown["confirmed"]
    pending_payments = payment_breakdown["awaiting_admin_review"]
    awaiting_user_payments = payment_breakdown["awaiting_user_payment"]
    open_manual_payments = payment_breakdown["open_manual"]
    revenue_payments = [item for item in confirmed_payments if payment_method_counts_as_revenue(item.payment_method)]
    revenue_total = sum(item.amount for item in revenue_payments)
    revenue_30d = sum(
        item.amount for item in revenue_payments if item.confirmed_at and item.confirmed_at >= now - timedelta(days=30)
    )
    average_payment = round(revenue_total / len(revenue_payments), 1) if revenue_payments else 0

    payment_methods: dict[str, dict[str, int]] = {}
    for item in payment_rows:
        bucket = payment_methods.setdefault(item.payment_method, {"count": 0, "confirmed_amount": 0})
        bucket["count"] += 1
        if _payment_record_counts_as_revenue(item):
            bucket["confirmed_amount"] += item.amount

    monthly_server_budget = _read_int_env("DASHBOARD_MONTHLY_SERVER_BUDGET_RUB", 0)
    monthly_operations_budget = _read_int_env("DASHBOARD_MONTHLY_OPERATIONS_BUDGET_RUB", 0)
    monthly_target_revenue = _read_int_env("DASHBOARD_MONTHLY_TARGET_REVENUE_RUB", 0)
    monthly_total_budget = monthly_server_budget + monthly_operations_budget
    budget_delta = revenue_30d - monthly_total_budget
    budget_coverage = round((revenue_30d / monthly_total_budget) * 100, 1) if monthly_total_budget else None

    server_summary = summarize_server_snapshots(server_snapshots)
    server_rows = []
    for item in server_snapshots:
        server_rows.append(
            "| {name} | {country} | {status} | {cpu}% | {memory}% | {disk}% | {ping} | {load} | {clients} |".format(
                name=item.get("name", "—"),
                country=item.get("country_name", "—"),
                status=item.get("overall_state", item.get("status", "unknown")),
                cpu=item.get("cpu_percent", "—"),
                memory=item.get("memory_used_percent", "—"),
                disk=item.get("disk_used_percent", "—"),
                ping=item.get("ping_label", "—"),
                load=item.get("load", "—"),
                clients=item.get("xui_clients", "—"),
            )
        )

    service_rows = [
        f"| {item['label']} | {item['status']} |"
        for item in service_statuses.values()
    ]

    payment_method_rows = [
        f"| {_payment_method_label(method)} | {values['count']} | {_format_rub(values['confirmed_amount'])} |"
        for method, values in sorted(payment_methods.items(), key=lambda row: (-row[1]["confirmed_amount"], row[0]))
    ]

    recommendations = []
    if open_manual_payments:
        recommendations.append(
            f"- Разобрать ручные платежи: открыто {len(open_manual_payments)} заявок, из них {len(pending_payments)} ждут подтверждение."
        )
    if server_summary["critical"]:
        recommendations.append(f"- Есть критичные серверы: {server_summary['critical']} шт. Нужна быстрая проверка нагрузки и диска.")
    if support_counts.get("new", 0):
        recommendations.append(f"- Новые обращения поддержки: {support_counts['new']}. Стоит разгрузить очередь.")
    if monthly_total_budget == 0:
        recommendations.append("- Бюджет не настроен: добавь `DASHBOARD_MONTHLY_SERVER_BUDGET_RUB` и `DASHBOARD_MONTHLY_OPERATIONS_BUDGET_RUB` в `.env`.")
    elif budget_delta < 0:
        recommendations.append(f"- Выручка за 30 дней ниже бюджета на {_format_rub(abs(budget_delta))}. Нужен контроль затрат или рост конверсии.")
    if expiring_soon:
        recommendations.append(f"- В ближайшие 7 дней истекает доступ у {expiring_soon} пользователей. Можно готовить воронку продления.")
    if not recommendations:
        recommendations.append("- Критичных отклонений не найдено. Контур выглядит устойчиво.")

    report_lines = [
        "# Операционный отчёт Amonora",
        "",
        f"_Сформирован: {generated_at}_",
        "",
        "## 1. Executive summary",
        "",
        f"- Пользователей в базе: **{len(user_rows)}**",
        f"- Активный доступ: **{active_access}**",
        f"- Платные подписки: **{active_paid}**",
        f"- Пробный доступ: **{active_trials}**",
        f"- Устройств: **{total_devices}**",
        f"- Подтверждённая выручка за 30 дней: **{_format_rub(revenue_30d)}**",
        f"- Активных серверов: **{server_summary['active']} / {server_summary['total']}**",
        "",
        "## 2. Пользователи и доступ",
        "",
        "| Метрика | Значение |",
        "| --- | ---: |",
        f"| Всего пользователей | {len(user_rows)} |",
        f"| Активный доступ | {active_access} |",
        f"| Пробный доступ | {active_trials} |",
        f"| Платный доступ | {active_paid} |",
        f"| Заблокированные пользователи | {blocked_users} |",
        f"| Истекают в ближайшие 7 дней | {expiring_soon} |",
        f"| Пользователи без устройств | {max(len(user_rows) - len(device_users), 0)} |",
        "",
        "## 3. Доступ и устройства",
        "",
        "| Метрика | Значение |",
        "| --- | ---: |",
        f"| Всего устройств | {total_devices} |",
        f"| VLESS | {vless_devices} |",
        f"| Trojan + TLS | {trojan_devices} |",
        f"| Германия | {germany_devices} |",
        f"| Эстония | {estonia_devices} |",
        "",
        "## 4. Платежи и бюджет",
        "",
        "| Метрика | Значение |",
        "| --- | ---: |",
        f"| Подтверждённые платежи | {len(confirmed_payments)} |",
        f"| Заявки ждут подтверждение | {len(pending_payments)} |",
        f"| Заявки ждут оплату от клиента | {len(awaiting_user_payments)} |",
        f"| Выручка всего | {_format_rub(revenue_total)} |",
        f"| Выручка за 30 дней | {_format_rub(revenue_30d)} |",
        f"| Средний чек | {_format_rub(average_payment)} |",
        f"| Бюджет серверов / месяц | {_format_rub(monthly_server_budget)} |",
        f"| Операционный бюджет / месяц | {_format_rub(monthly_operations_budget)} |",
        f"| Общий бюджет / месяц | {_format_rub(monthly_total_budget)} |",
        f"| Целевая выручка / месяц | {_format_rub(monthly_target_revenue)} |",
        f"| Дельта к бюджету | {_format_rub(budget_delta)} |",
        f"| Покрытие бюджета | {str(budget_coverage) + '%' if budget_coverage is not None else 'не настроено'} |",
        "",
        "### Методы оплаты",
        "",
        "| Метод | Платежей | Подтверждённая сумма |",
        "| --- | ---: | ---: |",
        *(payment_method_rows or ["| — | 0 | 0 ₽ |"]),
        "",
        "## 5. Серверный контур",
        "",
        "| Сервер | Страна | Состояние | CPU | RAM | Disk | Ping | Load | Клиенты 3x-ui |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: |",
        *(server_rows or ["| — | — | — | 0% | 0% | 0% | — | — | 0 |"]),
        "",
        "## 6. Сервисы и поддержка",
        "",
        f"- Новые тикеты: **{support_counts.get('new', 0)}**",
        f"- В работе: **{support_counts.get('in_progress', 0)}**",
        f"- Закрытые: **{support_counts.get('closed', 0)}**",
        "",
        "| Сервис | Статус |",
        "| --- | --- |",
        *(service_rows or ["| — | unknown |"]),
        "",
        "## 7. Последний аудит",
        "",
    ]

    if audit_rows:
        report_lines.extend(
            f"- `{_format_datetime(item.created_at)}` · **{item.action}** · {item.target_type or 'system'}"
            for item in audit_rows
        )
    else:
        report_lines.append("- Аудит пока пуст.")

    report_lines.extend(
        [
            "",
            "## 8. Рекомендации",
            "",
            *recommendations,
            "",
            "## 9. Что входит в этот отчёт",
            "",
            "- Серверная сводка: состояние нод, ping, load, CPU, RAM, Disk, 3x-ui клиенты.",
            "- Финансовый блок: платежи, подтверждённая выручка и бюджетные ориентиры.",
            "- Пользовательская статистика: доступы, устройства, блокировки, истечения.",
            "- Операционный слой: support, статусы сервисов, свежий аудит.",
            "",
        ]
    )

    GENERATED_DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_ROOT / OPERATIONS_REPORT_SLUG
    previous_report = None
    if report_path.exists():
        stat_result = report_path.stat()
        previous_report = {
            "path": str(report_path),
            "size_bytes": int(stat_result.st_size),
            "updated_at": _format_datetime(
                datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).replace(tzinfo=None)
            ),
        }
    report_text = "\n".join(report_lines).strip() + "\n"
    report_path.write_text(report_text, encoding="utf-8")
    invalidate_docs_cache(OPERATIONS_REPORT_SLUG)

    if admin is not None:
        await create_audit_log(
            admin.id,
            "generate_operations_report",
            "documentation",
            OPERATIONS_REPORT_SLUG,
            json.dumps(
                {
                    "before": previous_report,
                    "after": {
                        "slug": OPERATIONS_REPORT_SLUG,
                        "path": str(report_path),
                        "generated_at": generated_at,
                        "size_bytes": int(report_path.stat().st_size),
                    },
                },
                ensure_ascii=False,
            ),
            ip_address,
        )

    return {
        "slug": OPERATIONS_REPORT_SLUG,
        "path": str(report_path),
        "generated_at": generated_at,
    }


def _measure_tcp_ping(host: str, port: int = 22, timeout: float = 1.5) -> float | None:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - started) * 1000, 1)
    except OSError:
        return None


def _runtime_probe_ports(country_code: str | None, *, is_local: bool = False) -> tuple[int, ...]:
    if is_local:
        return (22,)

    runtime_type = get_country_runtime_type(country_code)
    if runtime_type == "xray_core":
        return (443, 8443)
    if runtime_type == "xui":
        return (443,)
    return (22,)


def _measure_best_tcp_ping(
    host: str,
    ports: tuple[int, ...],
    *,
    timeout: float = 1.0,
) -> tuple[float | None, int | None]:
    best_latency: float | None = None
    best_port: int | None = None
    seen_ports: set[int] = set()
    for raw_port in ports:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            continue
        if port <= 0 or port in seen_ports:
            continue
        seen_ports.add(port)
        latency = _measure_tcp_ping(host, port=port, timeout=timeout)
        if latency is None:
            continue
        if best_latency is None or latency < best_latency:
            best_latency = latency
            best_port = port
    return best_latency, best_port


def _ping_snapshot(host: str, country_code: str | None, *, is_local: bool = False) -> dict[str, object]:
    ports = _runtime_probe_ports(country_code, is_local=is_local)
    ping_ms, ping_port = _measure_best_tcp_ping(host, ports, timeout=1.5 if is_local else 1.0)
    effective_port = ping_port or (ports[0] if ports else None)
    ping_target = f"{host}:{effective_port}" if effective_port else host
    return {
        "ping_ms": ping_ms,
        "ping_label": f"{ping_ms:.1f} ms" if ping_ms is not None else "—",
        "ping_state": _ping_state(ping_ms, country_code),
        "ping_port": effective_port,
        "ping_target": ping_target,
    }


def _network_speed_snapshot(sample_key: str) -> dict:
    counters = psutil.net_io_counters()
    now = time.perf_counter()
    previous = _NETWORK_SAMPLES.get(sample_key)
    _NETWORK_SAMPLES[sample_key] = (now, counters.bytes_sent, counters.bytes_recv)

    if previous is None:
        return {
            "tx_mbps": 0.0,
            "rx_mbps": 0.0,
            "tx_label": "0.00 Mbps",
            "rx_label": "0.00 Mbps",
        }

    previous_time, previous_sent, previous_recv = previous
    elapsed = max(now - previous_time, 0.001)
    tx_mbps = max(((counters.bytes_sent - previous_sent) * 8) / elapsed / 1_000_000, 0.0)
    rx_mbps = max(((counters.bytes_recv - previous_recv) * 8) / elapsed / 1_000_000, 0.0)
    return {
        "tx_mbps": round(tx_mbps, 2),
        "rx_mbps": round(rx_mbps, 2),
        "tx_label": _format_speed_mbps(tx_mbps),
        "rx_label": _format_speed_mbps(rx_mbps),
    }


async def create_audit_log(
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details_text: str | None = None,
    ip_address: str | None = None,
) -> None:
    async with async_session() as session:
        session.add(
            DashboardAuditLog(
                admin_id=admin_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details_text=details_text,
                request_id=get_current_audit_request_id(),
                ip_address=ip_address,
            )
        )
        await session.commit()


def set_current_audit_request_id(request_id: str | None) -> Token:
    normalized = str(request_id or "").strip()[:64] or None
    return _CURRENT_DASHBOARD_REQUEST_ID.set(normalized)


def reset_current_audit_request_id(token: Token) -> None:
    _CURRENT_DASHBOARD_REQUEST_ID.reset(token)


def get_current_audit_request_id() -> str | None:
    value = _CURRENT_DASHBOARD_REQUEST_ID.get()
    return str(value).strip()[:64] if value else None


async def create_control_event(*, request_id: str | None = None, **kwargs):
    effective_request_id = str(request_id or get_current_audit_request_id() or "").strip()[:64] or None
    return await _create_control_event(request_id=effective_request_id, **kwargs)


def dashboard_auth_lockout_actions(scope: str) -> tuple[str, ...]:
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope == "verify_code":
        return (
            "auth_verify_invalid_code",
            "auth_verify_invalid_code_v2",
            "auth_verify_code_missing",
            "auth_verify_code_missing_v2",
            "auth_verify_lockout",
            "auth_verify_lockout_v2",
        )
    return (
        "auth_request_code_invalid_credentials",
        "auth_request_code_invalid_credentials_v2",
        "auth_request_code_rate_limited",
        "auth_request_code_rate_limited_v2",
        "auth_request_code_lockout",
        "auth_request_code_lockout_v2",
    )


def _normalize_dashboard_auth_lockout_scope(scope: str) -> str:
    return str(scope or "").strip().lower()


def _normalize_dashboard_auth_lockout_username(username: str | None) -> str | None:
    normalized = str(username or "").strip().lower()
    return normalized or None


def _normalize_dashboard_auth_lockout_ip(ip_address: str | None) -> str | None:
    normalized = str(ip_address or "").strip().lower()[:64]
    return normalized or None


def _dashboard_auth_lockout_identity_specs(
    scope: str,
    username: str | None,
    *,
    ip_address: str | None = None,
) -> tuple[tuple[str, str, str], ...]:
    normalized_scope = _normalize_dashboard_auth_lockout_scope(scope)
    normalized_username = _normalize_dashboard_auth_lockout_username(username)
    normalized_ip = _normalize_dashboard_auth_lockout_ip(ip_address)
    specs: list[tuple[str, str, str]] = []
    if normalized_username:
        specs.append((normalized_scope, DASHBOARD_AUTH_LOCKOUT_IDENTITY_USERNAME, normalized_username))
    if normalized_ip:
        specs.append((normalized_scope, DASHBOARD_AUTH_LOCKOUT_IDENTITY_IP, normalized_ip))
    return tuple(specs)


async def _get_dashboard_auth_lockout_row(
    session,
    scope: str,
    identity_type: str,
    identity_value: str,
) -> DashboardAuthLockoutState | None:
    result = await session.execute(
        select(DashboardAuthLockoutState).where(
            DashboardAuthLockoutState.scope == scope,
            DashboardAuthLockoutState.identity_type == identity_type,
            DashboardAuthLockoutState.identity_value == identity_value,
        )
    )
    if hasattr(result, "scalar_one_or_none"):
        return result.scalar_one_or_none()
    if hasattr(result, "_scalar"):
        return result._scalar
    return None


def _effective_dashboard_auth_lockout_row_state(
    row: DashboardAuthLockoutState | None,
    *,
    now_utc: datetime,
) -> dict[str, object]:
    if row is None:
        return {"locked": False, "failure_count": 0, "retry_after_seconds": 0}
    failure_count = int(getattr(row, "failure_count", 0) or 0)
    locked_until = getattr(row, "locked_until", None)
    if isinstance(locked_until, datetime):
        retry_after_seconds = max(int((locked_until - now_utc).total_seconds()), 0)
        if retry_after_seconds > 0:
            return {
                "locked": True,
                "failure_count": max(failure_count, DASHBOARD_AUTH_LOCKOUT_THRESHOLD),
                "retry_after_seconds": retry_after_seconds,
            }
    last_failure_at = getattr(row, "last_failure_at", None)
    cutoff = now_utc - timedelta(seconds=DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS)
    if isinstance(last_failure_at, datetime) and last_failure_at >= cutoff:
        return {"locked": False, "failure_count": failure_count, "retry_after_seconds": 0}
    return {"locked": False, "failure_count": 0, "retry_after_seconds": 0}


def _merge_dashboard_auth_lockout_states(states: list[dict[str, object]]) -> dict[str, object]:
    if not states:
        return {"locked": False, "failure_count": 0, "retry_after_seconds": 0}
    locked = any(bool(state.get("locked")) for state in states)
    failure_count = max(int(state.get("failure_count", 0) or 0) for state in states)
    retry_after_seconds = max(int(state.get("retry_after_seconds", 0) or 0) for state in states)
    return {
        "locked": locked,
        "failure_count": failure_count,
        "retry_after_seconds": retry_after_seconds if locked else 0,
    }


async def record_dashboard_auth_failure(
    scope: str,
    username: str,
    *,
    ip_address: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    specs = _dashboard_auth_lockout_identity_specs(scope, username, ip_address=ip_address)
    if not specs:
        return {"locked": False, "failure_count": 0, "retry_after_seconds": 0}

    current = now_utc or utcnow()
    cutoff = current - timedelta(seconds=DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS)
    states: list[dict[str, object]] = []
    async with async_session() as session:
        for normalized_scope, identity_type, identity_value in specs:
            row = await _get_dashboard_auth_lockout_row(session, normalized_scope, identity_type, identity_value)
            if row is None:
                row = DashboardAuthLockoutState(
                    scope=normalized_scope,
                    identity_type=identity_type,
                    identity_value=identity_value,
                    failure_count=0,
                    first_failure_at=current,
                    created_at=current,
                    updated_at=current,
                )
                session.add(row)
            last_failure_at = getattr(row, "last_failure_at", None)
            locked_until = getattr(row, "locked_until", None)
            if isinstance(last_failure_at, datetime) and last_failure_at < cutoff and (
                not isinstance(locked_until, datetime) or locked_until <= current
            ):
                row.failure_count = 0
                row.first_failure_at = current
                row.locked_until = None
            if not isinstance(getattr(row, "first_failure_at", None), datetime) or (
                isinstance(last_failure_at, datetime) and last_failure_at < cutoff
            ):
                row.first_failure_at = current
            row.failure_count = int(getattr(row, "failure_count", 0) or 0) + 1
            row.last_failure_at = current
            if row.failure_count >= DASHBOARD_AUTH_LOCKOUT_THRESHOLD:
                candidate_lock = current + timedelta(seconds=DASHBOARD_AUTH_LOCKOUT_DURATION_SECONDS)
                if isinstance(locked_until, datetime) and locked_until > candidate_lock:
                    row.locked_until = locked_until
                else:
                    row.locked_until = candidate_lock
            row.updated_at = current
            states.append(_effective_dashboard_auth_lockout_row_state(row, now_utc=current))
        await session.commit()
    return _merge_dashboard_auth_lockout_states(states)


async def clear_dashboard_auth_failures(
    scope: str,
    username: str,
    *,
    ip_address: str | None = None,
    now_utc: datetime | None = None,
) -> None:
    specs = _dashboard_auth_lockout_identity_specs(scope, username, ip_address=ip_address)
    if not specs:
        return
    current = now_utc or utcnow()
    async with async_session() as session:
        dirty = False
        for normalized_scope, identity_type, identity_value in specs:
            row = await _get_dashboard_auth_lockout_row(session, normalized_scope, identity_type, identity_value)
            if row is None:
                continue
            row.failure_count = 0
            row.first_failure_at = None
            row.last_failure_at = None
            row.locked_until = None
            row.updated_at = current
            dirty = True
        if dirty:
            await session.commit()


async def get_dashboard_auth_lockout_state(
    scope: str,
    username: str,
    *,
    ip_address: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    normalized_username = _normalize_dashboard_auth_lockout_username(username)
    normalized_ip = _normalize_dashboard_auth_lockout_ip(ip_address)
    if not normalized_username:
        return {"locked": False, "failure_count": 0, "retry_after_seconds": 0}

    current = now_utc or utcnow()
    persisted_states: list[dict[str, object]] = []
    async with async_session() as session:
        username_row = await _get_dashboard_auth_lockout_row(
            session,
            _normalize_dashboard_auth_lockout_scope(scope),
            DASHBOARD_AUTH_LOCKOUT_IDENTITY_USERNAME,
            normalized_username,
        )
        if username_row is not None:
            persisted_states.append(_effective_dashboard_auth_lockout_row_state(username_row, now_utc=current))
        if normalized_ip:
            ip_row_state = await _get_dashboard_auth_lockout_row(
                session,
                _normalize_dashboard_auth_lockout_scope(scope),
                DASHBOARD_AUTH_LOCKOUT_IDENTITY_IP,
                normalized_ip,
            )
            if ip_row_state is not None:
                persisted_states.append(_effective_dashboard_auth_lockout_row_state(ip_row_state, now_utc=current))
        if persisted_states:
            return _merge_dashboard_auth_lockout_states(persisted_states)

    cutoff = current - timedelta(seconds=DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS)
    actions = dashboard_auth_lockout_actions(scope)
    async with async_session() as session:
        username_result = await session.execute(
            select(
                func.count(DashboardAuditLog.id),
                func.max(DashboardAuditLog.created_at),
            ).where(
                DashboardAuditLog.target_type == "dashboard_auth",
                func.lower(func.coalesce(DashboardAuditLog.target_id, "")) == normalized_username,
                DashboardAuditLog.action.in_(actions),
                DashboardAuditLog.created_at >= cutoff,
            )
        )
        ip_row = None
        if normalized_ip:
            ip_result = await session.execute(
                select(
                    func.count(DashboardAuditLog.id),
                    func.max(DashboardAuditLog.created_at),
                ).where(
                    DashboardAuditLog.target_type == "dashboard_auth",
                    func.lower(func.coalesce(DashboardAuditLog.ip_address, "")) == normalized_ip.lower(),
                    DashboardAuditLog.action.in_(actions),
                    DashboardAuditLog.created_at >= cutoff,
                )
            )
            if hasattr(ip_result, "one"):
                ip_row = ip_result.one()
            elif hasattr(ip_result, "first"):
                ip_row = ip_result.first()
            elif hasattr(ip_result, "_scalar"):
                ip_row = ip_result._scalar
        username_row = None
        if hasattr(username_result, "one"):
            username_row = username_result.one()
        elif hasattr(username_result, "first"):
            username_row = username_result.first()
        elif hasattr(username_result, "_scalar"):
            username_row = username_result._scalar

    username_failures = 0
    username_latest_failure = None
    if isinstance(username_row, tuple):
        username_failures, username_latest_failure = username_row
    ip_failures = 0
    ip_latest_failure = None
    if isinstance(ip_row, tuple):
        ip_failures, ip_latest_failure = ip_row

    failures = max(int(username_failures or 0), int(ip_failures or 0))
    latest_failure_candidates = [
        value
        for value in (username_latest_failure, ip_latest_failure)
        if isinstance(value, datetime)
    ]
    latest_failure = max(latest_failure_candidates) if latest_failure_candidates else None
    if failures < DASHBOARD_AUTH_LOCKOUT_THRESHOLD or latest_failure is None:
        return {"locked": False, "failure_count": failures, "retry_after_seconds": 0}

    retry_after_seconds = max(
        int((latest_failure + timedelta(seconds=DASHBOARD_AUTH_LOCKOUT_WINDOW_SECONDS) - current).total_seconds()),
        0,
    )
    return {
        "locked": retry_after_seconds > 0,
        "failure_count": failures,
        "retry_after_seconds": retry_after_seconds,
    }


def _audit_datetime(value: datetime | None) -> str | None:
    return _format_datetime(value) if value is not None else None


def _user_audit_snapshot(user: User | None) -> dict[str, object] | None:
    if user is None:
        return None
    return {
        "id": int(getattr(user, "id", 0) or 0),
        "telegram_id": getattr(user, "telegram_id", None),
        "username": getattr(user, "username", None),
        "is_blocked": bool(getattr(user, "is_blocked", False)),
        "balance_rub": int(getattr(user, "balance_rub", 0) or 0),
        "preferred_protocol": getattr(user, "preferred_protocol", None),
        "subscription_status": getattr(user, "subscription_status", None),
        "subscription_source": getattr(user, "subscription_source", None),
        "subscription_started_at": _audit_datetime(getattr(user, "subscription_started_at", None)),
        "subscription_expires_at": _audit_datetime(getattr(user, "subscription_expires_at", None)),
        "trial_expires_at": _audit_datetime(getattr(user, "trial_expires_at", None)),
        "trial_used": bool(getattr(user, "trial_used", False)),
        "trial_activity_level": getattr(user, "trial_activity_level", None),
        "vpn_repair_needed": bool(getattr(user, "vpn_repair_needed", False)),
        "vpn_repair_reason": getattr(user, "vpn_repair_reason", None),
        "last_activity_at": _audit_datetime(getattr(user, "last_activity_at", None)),
    }


def _payment_record_audit_snapshot(record: PaymentRecord | None) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "id": int(getattr(record, "id", 0) or 0),
        "user_id": getattr(record, "user_id", None),
        "payment_method": getattr(record, "payment_method", None),
        "payment_status": getattr(record, "payment_status", None),
        "tariff_code": getattr(record, "tariff_code", None),
        "amount": getattr(record, "amount", None),
        "currency": getattr(record, "currency", None),
        "reference": getattr(record, "reference", None),
        "reviewed_by_actor_name": getattr(record, "reviewed_by_actor_name", None),
        "rejection_reason": getattr(record, "rejection_reason", None),
        "created_at": _audit_datetime(getattr(record, "created_at", None)),
        "confirmed_at": _audit_datetime(getattr(record, "confirmed_at", None)),
        "reviewed_at": _audit_datetime(getattr(record, "reviewed_at", None)),
        "expires_at": _audit_datetime(getattr(record, "expires_at", None)),
    }


def _vpn_client_audit_snapshot(device: VpnClient | object | None, *, metadata_override: dict | None = None) -> dict[str, object] | None:
    if device is None:
        return None
    metadata = metadata_override or {}
    if not metadata:
        try:
            metadata = _device_metadata(device)  # type: ignore[arg-type]
        except Exception:
            metadata = {}
    return {
        "id": getattr(device, "id", None),
        "user_id": getattr(device, "user_id", None),
        "email": getattr(device, "email", None),
        "protocol": getattr(device, "protocol", None),
        "client_uuid": getattr(device, "client_uuid", None),
        "xui_client_id": getattr(device, "xui_client_id", None),
        "country_code": metadata.get("country_code"),
        "country_name": metadata.get("country_name"),
        "device_name": metadata.get("device_name"),
        "device_type": metadata.get("device_type"),
        "created_at": _audit_datetime(getattr(device, "created_at", None)),
    }


def _support_ticket_audit_snapshot(ticket: dict | None) -> dict[str, object] | None:
    if ticket is None:
        return None
    return {
        "user_id": ticket.get("user_id"),
        "status": ticket.get("status"),
        "assigned_admin_id": ticket.get("assigned_admin_id"),
        "assigned_admin_name": ticket.get("assigned_admin_name"),
        "messages_count": ticket.get("messages_count"),
        "updated_at": ticket.get("updated_at"),
        "closed_at": ticket.get("closed_at"),
    }


def _finance_entry_audit_snapshot(entry: FinanceEntry | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "id": int(getattr(entry, "id", 0) or 0),
        "entry_type": getattr(entry, "entry_type", None),
        "status": getattr(entry, "status", None),
        "category": getattr(entry, "category", None),
        "amount": getattr(entry, "amount", None),
        "currency": getattr(entry, "currency", None),
        "related_server": getattr(entry, "related_server", None),
        "source_type": getattr(entry, "source_type", None),
        "source_id": getattr(entry, "source_id", None),
        "counterparty_admin_id": getattr(entry, "counterparty_admin_id", None),
        "approved_by_admin_id": getattr(entry, "approved_by_admin_id", None),
        "approved_at": _audit_datetime(getattr(entry, "approved_at", None)),
        "occurred_at": _audit_datetime(getattr(entry, "occurred_at", None)),
        "period_key": getattr(entry, "period_key", None),
    }


def _managed_server_audit_snapshot(server: ManagedServer | None) -> dict[str, object] | None:
    if server is None:
        return None
    return {
        "id": int(getattr(server, "id", 0) or 0),
        "name": getattr(server, "name", None),
        "host": getattr(server, "host", None),
        "public_ip": getattr(server, "public_ip", None),
        "country_code": getattr(server, "country_code", None),
        "country_name": getattr(server, "country_name", None),
        "provider": getattr(server, "provider", None),
        "status": getattr(server, "status", None),
        "is_local": bool(getattr(server, "is_local", False)),
        "updated_at": _audit_datetime(getattr(server, "updated_at", None)),
    }


def _role_permission_override_audit_snapshot(
    role: str,
    permission: str,
    enabled: bool | None,
    *,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "role": str(role or "").strip().lower(),
        "permission": str(permission or "").strip(),
        "enabled": None if enabled is None else bool(enabled),
        "updated_at": _audit_datetime(updated_at),
    }


def _selected_env_snapshot(values: dict[str, int | str], current_env: dict[str, str | None]) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for key in sorted(values):
        snapshot[key] = current_env.get(key)
    return snapshot


def _user_audit_subject(candidate: object | None, fallback: User | object | None = None) -> User | object | None:
    if candidate is None:
        return fallback
    candidate_id = getattr(candidate, "id", None)
    if isinstance(candidate_id, int) and (
        hasattr(candidate, "username")
        or hasattr(candidate, "telegram_id")
        or hasattr(candidate, "subscription_status")
        or hasattr(candidate, "vpn_repair_needed")
    ):
        return candidate
    return fallback


async def get_admin_by_username(username: str) -> DashboardAdmin | None:
    async with async_session() as session:
        result = await session.execute(select(DashboardAdmin).where(DashboardAdmin.username == username))
        return result.scalar_one_or_none()


async def get_admin_by_id(admin_id: int) -> DashboardAdmin | None:
    async with async_session() as session:
        result = await session.execute(select(DashboardAdmin).where(DashboardAdmin.id == admin_id))
        return result.scalar_one_or_none()


async def update_dashboard_admin_access(
    target_admin_id: int,
    role: str,
    is_active: bool,
    actor: DashboardAdmin,
    ip_address: str | None,
) -> dict | None:
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLE_NAMES:
        raise ValueError("Неизвестная роль")

    previous_state: dict[str, object] | None = None
    async with async_session() as session:
        target = await session.get(DashboardAdmin, int(target_admin_id))
        if target is None:
            return None
        if target.id == actor.id and (normalized_role != "owner" or not is_active):
            raise ValueError("Нельзя понизить или отключить собственную учётную запись")

        previous_state = {
            "role": target.role,
            "is_active": bool(target.is_active),
        }
        target.role = normalized_role
        target.is_active = bool(is_active)
        await session.commit()
        await session.refresh(target)

    sessions_revoked = bool(
        previous_state and (
        previous_state.get("role") != normalized_role or bool(previous_state.get("is_active")) != bool(is_active)
        )
    )
    if sessions_revoked:
        await delete_sessions_for_admin(int(target_admin_id))

    await create_audit_log(
        actor.id,
        "update_dashboard_admin_access",
        "dashboard_admin",
        str(target_admin_id),
        json.dumps(
            {
                "before": previous_state or {},
                "after": {"role": normalized_role, "is_active": bool(is_active)},
                "sessions_revoked": sessions_revoked,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return {
        "id": target.id,
        "display_name": target.display_name,
        "username": target.username,
        "role": target.role,
        "role_name": ROLE_NAMES.get(target.role, target.role),
        "telegram_id": target.telegram_id,
        "is_active": target.is_active,
    }


async def update_role_permission_override(
    role: str,
    permission: str,
    enabled: bool,
    actor: DashboardAdmin,
    ip_address: str | None,
) -> dict[str, object]:
    normalized_role = str(role or "").strip().lower()
    normalized_permission = str(permission or "").strip()
    if normalized_role not in EDITABLE_PERMISSION_ROLES:
        raise ValueError("Можно менять только разрешения техадмина и менеджера")
    if normalized_permission not in all_known_permissions():
        raise ValueError("Неизвестное разрешение")
    if normalized_permission not in editable_permissions_for_role(normalized_role):
        raise ValueError("Это разрешение нельзя менять для выбранной роли")

    before_snapshot: dict[str, object] | None = None
    after_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        row = (
            await session.execute(
                select(DashboardRolePermissionOverride).where(
                    DashboardRolePermissionOverride.role == normalized_role,
                    DashboardRolePermissionOverride.permission == normalized_permission,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            before_snapshot = _role_permission_override_audit_snapshot(
                row.role,
                row.permission,
                row.enabled,
                updated_at=row.updated_at,
            )
        if row is None:
            row = DashboardRolePermissionOverride(
                role=normalized_role,
                permission=normalized_permission,
                enabled=bool(enabled),
                updated_at=utcnow(),
            )
            session.add(row)
        else:
            row.enabled = bool(enabled)
            row.updated_at = utcnow()
        await session.commit()
        after_snapshot = _role_permission_override_audit_snapshot(
            row.role,
            row.permission,
            row.enabled,
            updated_at=row.updated_at,
        )

    await refresh_role_permission_overrides_cache()
    await create_audit_log(
        actor.id,
        "update_role_permission_override",
        "role_permission",
        f"{normalized_role}:{normalized_permission}",
        json.dumps(
            {
                "before": before_snapshot,
                "after": after_snapshot,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return {
        "role": normalized_role,
        "permission": normalized_permission,
        "enabled": bool(enabled),
    }


async def verify_admin_credentials(username: str, password: str) -> DashboardAdmin | None:
    admin = await get_admin_by_username(username)
    if admin is None or not admin.is_active:
        return None
    if not verify_password(password, admin.password_hash):
        return None
    return admin


async def create_session(admin_id: int, token: str) -> None:
    now = utcnow()
    async with async_session() as session:
        session.add(
            DashboardSession(
                admin_id=admin_id,
                token_hash=hash_token(token),
                expires_at=session_expiry(dashboard_settings()["session_hours"]),
                last_seen_at=now,
            )
        )
        result = await session.execute(select(DashboardAdmin).where(DashboardAdmin.id == admin_id))
        admin = result.scalar_one_or_none()
        if admin is not None:
            admin.last_login_at = now
        await session.commit()


async def get_pending_dashboard_login_code(username: str) -> DashboardLoginCode | None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(DashboardLoginCode).where(DashboardLoginCode.username == normalized_username)
        )
        return result.scalar_one_or_none()


async def upsert_dashboard_login_code(
    *,
    username: str,
    admin_id: int,
    code_hash: str,
    telegram_id: int | None,
    message_id: int | None,
    bot_key: str | None,
    expires_at: datetime,
    now_utc: datetime | None = None,
) -> DashboardLoginCode:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("username is required")
    current = now_utc or utcnow()
    async with async_session() as session:
        row = (
            await session.execute(
                select(DashboardLoginCode).where(DashboardLoginCode.username == normalized_username)
            )
        ).scalar_one_or_none()
        if row is None:
            row = DashboardLoginCode(
                username=normalized_username,
                admin_id=int(admin_id),
                code_hash=code_hash,
                telegram_id=telegram_id,
                message_id=message_id,
                bot_key=bot_key,
                attempts=0,
                expires_at=expires_at,
                created_at=current,
                updated_at=current,
            )
            session.add(row)
        else:
            row.admin_id = int(admin_id)
            row.code_hash = code_hash
            row.telegram_id = telegram_id
            row.message_id = message_id
            row.bot_key = bot_key
            row.attempts = 0
            row.expires_at = expires_at
            row.updated_at = current
        await session.commit()
        await session.refresh(row)
        return row


async def increment_dashboard_login_code_attempts(username: str, *, now_utc: datetime | None = None) -> DashboardLoginCode | None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return None
    current = now_utc or utcnow()
    async with async_session() as session:
        row = (
            await session.execute(
                select(DashboardLoginCode).where(DashboardLoginCode.username == normalized_username)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.attempts = int(row.attempts or 0) + 1
        row.updated_at = current
        await session.commit()
        await session.refresh(row)
        return row


async def delete_dashboard_login_code(username: str) -> DashboardLoginCode | None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return None
    async with async_session() as session:
        row = (
            await session.execute(
                select(DashboardLoginCode).where(DashboardLoginCode.username == normalized_username)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        payload = DashboardLoginCode(
            id=row.id,
            username=row.username,
            admin_id=row.admin_id,
            code_hash=row.code_hash,
            telegram_id=row.telegram_id,
            message_id=row.message_id,
            bot_key=row.bot_key,
            attempts=row.attempts,
            expires_at=row.expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        await session.execute(delete(DashboardLoginCode).where(DashboardLoginCode.id == row.id))
        await session.commit()
        return payload


async def purge_expired_dashboard_login_codes(*, now_utc: datetime | None = None) -> list[DashboardLoginCode]:
    current = now_utc or utcnow()
    async with async_session() as session:
        rows = list(
            (
                await session.execute(
                    select(DashboardLoginCode).where(DashboardLoginCode.expires_at <= current)
                )
            ).scalars().all()
        )
        if not rows:
            return []
        payload = [
            DashboardLoginCode(
                id=row.id,
                username=row.username,
                admin_id=row.admin_id,
                code_hash=row.code_hash,
                telegram_id=row.telegram_id,
                message_id=row.message_id,
                bot_key=row.bot_key,
                attempts=row.attempts,
                expires_at=row.expires_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
        await session.execute(delete(DashboardLoginCode).where(DashboardLoginCode.expires_at <= current))
        await session.commit()
        return payload


async def get_admin_by_session(token: str | None) -> DashboardAdmin | None:
    if not token:
        return None
    now = utcnow()
    idle_timeout = timedelta(minutes=max(dashboard_settings()["session_idle_minutes"], 1))
    async with async_session() as session:
        result = await session.execute(
            select(DashboardSession).where(DashboardSession.token_hash == hash_token(token))
        )
        db_session = result.scalar_one_or_none()
        if db_session is None:
            return None
        if db_session.expires_at <= now or (db_session.last_seen_at and db_session.last_seen_at <= now - idle_timeout):
            await session.execute(delete(DashboardSession).where(DashboardSession.id == db_session.id))
            await session.commit()
            return None

        admin_result = await session.execute(select(DashboardAdmin).where(DashboardAdmin.id == db_session.admin_id))
        admin = admin_result.scalar_one_or_none()
        if admin is None or not admin.is_active:
            await session.execute(delete(DashboardSession).where(DashboardSession.id == db_session.id))
            await session.commit()
            return None

        last_seen_at = getattr(db_session, "last_seen_at", None)
        should_touch = (
            last_seen_at is None
            or (now - last_seen_at).total_seconds() >= SESSION_LAST_SEEN_TOUCH_INTERVAL_SECONDS
        )
        if should_touch:
            db_session.last_seen_at = now
            await session.commit()
        return admin


async def delete_session(token: str | None) -> None:
    if not token:
        return
    async with async_session() as session:
        await session.execute(delete(DashboardSession).where(DashboardSession.token_hash == hash_token(token)))
        await session.commit()


async def delete_sessions_for_admin(admin_id: int) -> None:
    async with async_session() as session:
        await session.execute(delete(DashboardSession).where(DashboardSession.admin_id == int(admin_id)))
        await session.commit()


def _delete_avatar_file(avatar_path: str | None) -> None:
    if not avatar_path:
        return
    prefix = "/dashboard/static/avatars/"
    if not avatar_path.startswith(prefix):
        return
    filename = avatar_path.removeprefix(prefix)
    target = ADMIN_AVATAR_ROOT / filename
    try:
        if target.exists():
            target.unlink()
    except OSError:
        pass


async def update_admin_avatar(
    admin: DashboardAdmin,
    image_bytes: bytes,
    ip_address: str | None,
) -> DashboardAdmin:
    if not image_bytes:
        raise ValueError("Файл изображения пуст")
    if len(image_bytes) > ADMIN_AVATAR_MAX_BYTES:
        raise ValueError("Файл слишком большой. Максимум 2 MB")

    detected = imghdr.what(None, image_bytes)
    extension = ALLOWED_ADMIN_AVATAR_FORMATS.get(detected or "")
    if extension is None:
        raise ValueError("Поддерживаются только JPG, PNG и WEBP")

    ADMIN_AVATAR_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"admin-{admin.id}-{utcnow().strftime('%Y%m%d%H%M%S%f')}.{extension}"
    file_path = ADMIN_AVATAR_ROOT / filename
    file_path.write_bytes(image_bytes)
    public_path = f"/dashboard/static/avatars/{filename}"

    async with async_session() as session:
        db_admin = await session.get(DashboardAdmin, admin.id)
        if db_admin is None:
            raise ValueError("Администратор не найден")
        before_snapshot = {
            "id": int(db_admin.id),
            "username": db_admin.username,
            "avatar_path": db_admin.avatar_path,
        }
        old_avatar = db_admin.avatar_path
        db_admin.avatar_path = public_path
        await session.commit()
        await session.refresh(db_admin)

    if old_avatar and old_avatar != public_path:
        _delete_avatar_file(old_avatar)

    await create_audit_log(
        admin.id,
        "update_admin_avatar",
        "dashboard_admin",
        str(admin.id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": {
                    "id": int(db_admin.id),
                    "username": db_admin.username,
                    "avatar_path": db_admin.avatar_path,
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return db_admin


async def overview_metrics(force_refresh: bool = False, *, source_rows: dict | None = None) -> dict:
    use_cache = source_rows is None
    if use_cache and not force_refresh:
        cached = _runtime_cache_get("overview_metrics")
        if cached is not None:
            return cached

    if source_rows is None:
        async with async_session() as session:
            user_rows = list((await session.execute(select(User).where(_real_user_sql_clause()))).scalars().all())
            client_rows = list(
                (
                    await session.execute(
                        select(VpnClient).where(VpnClient.user_id.in_(_real_user_ids_subquery()))
                    )
                ).scalars().all()
            )
            payment_rows = list(
                (
                    await session.execute(
                        select(PaymentRecord).where(
                            or_(
                                PaymentRecord.user_id.is_(None),
                                PaymentRecord.user_id.in_(_real_user_ids_subquery()),
                            )
                        )
                    )
                ).scalars().all()
            )
    else:
        user_rows = list(source_rows.get("users") or [])
        client_rows = list(source_rows.get("clients") or [])
        payment_rows = list(source_rows.get("payments") or [])
    audit_rows = await recent_audit_logs(8)

    user_rows = [user for user in user_rows if not _is_synthetic_user(user)]
    users_by_id = {user.id: user for user in user_rows}
    real_user_ids = {int(user_id) for user_id in users_by_id}
    client_rows = [
        client
        for client in client_rows
        if _belongs_to_real_user(users_by_id.get(int(getattr(client, "user_id", 0) or 0)))
    ]
    payment_rows = [
        record
        for record in payment_rows
        if getattr(record, "user_id", None) is None or int(getattr(record, "user_id", 0) or 0) in real_user_ids
    ]

    active_access = sum(1 for user in user_rows if has_active_access_from_user(user))
    active_trials = sum(1 for user in user_rows if get_access_status_from_user(user) == "trial_active")
    active_paid = sum(1 for user in user_rows if get_access_status_from_user(user) == "paid_active")
    blocked_users = sum(1 for user in user_rows if getattr(user, "is_blocked", False))

    support_counts, service_statuses, server_snapshot = await asyncio.gather(
        get_support_dashboard_counts(),
        get_service_statuses(force_refresh=force_refresh),
        get_server_snapshots(force_refresh=force_refresh),
    )

    payment_breakdown = _manual_payment_breakdown(payment_rows)
    successful_payments = payment_breakdown["confirmed"]
    pending_payments = payment_breakdown["awaiting_admin_review"]
    awaiting_user_payments = payment_breakdown["awaiting_user_payment"]
    open_manual_payments = payment_breakdown["open_manual"]
    revenue_30d = sum(
        item.amount
        for item in successful_payments
        if payment_method_counts_as_revenue(item.payment_method)
        and (item.confirmed_at or item.created_at) >= utcnow() - timedelta(days=30)
    )

    alerts: list[dict] = []
    for service in service_statuses.values():
        if service["status"] != "active":
            alerts.append(
                {
                    "title": "Проверить сервис",
                    "text": f"{service['label']} не активен",
                    "href": "/settings",
                    "action": "Открыть сервисы",
                }
            )
    for server in server_snapshot:
        if server.get("status") == "maintenance":
            alerts.append(
                {
                    "title": "Сервер в обслуживании",
                    "text": f"{server['name']} находится в maintenance",
                    "href": "/servers",
                    "action": "Открыть серверы",
                }
            )
        if server.get("disk_used_percent", 0) >= 85:
            alerts.append(
                {
                    "title": "Почти заполнен диск",
                    "text": f"{server['name']} почти заполнил диск",
                    "href": "/servers",
                    "action": "Смотреть ноду",
                }
            )
        if server.get("cpu_percent", 0) >= 85:
            alerts.append(
                {
                    "title": "Высокая CPU-нагрузка",
                    "text": f"{server['name']} перегружен по CPU",
                    "href": "/servers",
                    "action": "Смотреть ноду",
                }
            )
    if support_counts.get("new", 0) > 0:
        alerts.append(
            {
                "title": "Новые обращения",
                "text": f"Новых обращений: {support_counts['new']}",
                "href": "/support?filter_mode=new",
                "action": "Открыть поддержку",
            }
        )
    if open_manual_payments:
        alerts.append(
            {
                "title": "Очередь ручных оплат",
                "text": f"Открыто заявок: {len(open_manual_payments)}, на подтверждении: {len(pending_payments)}",
                "href": "/payments",
                "action": "Открыть платежи",
            }
        )

    result = {
        "total_users": len(user_rows),
        "active_access": active_access,
        "active_trials": active_trials,
        "active_paid": active_paid,
        "blocked_users": blocked_users,
        "total_devices": len(client_rows),
        "vless_devices": sum(1 for client in client_rows if client.protocol == "vless"),
        "trojan_devices": sum(1 for client in client_rows if client.protocol == "trojan"),
        "support_counts": support_counts,
        "payment_counts": {
            "confirmed": len(successful_payments),
            "pending": len(pending_payments),
            "awaiting_user_payment": len(awaiting_user_payments),
            "open_manual": len(open_manual_payments),
            "revenue_30d": revenue_30d,
        },
        "backup_status": _build_backup_status(),
        "restore_validation_status": _build_restore_validation_status(),
        "alerts": alerts[:8],
        "service_statuses": service_statuses,
        "servers": server_snapshot,
        "recent_audit": audit_rows[:8],
    }
    if use_cache:
        _runtime_cache_set("overview_metrics", result)
    return copy.deepcopy(result)


async def get_users(search: str = "") -> list[dict]:
    search_value = search.strip().lower()
    async with async_session() as session:
        query = select(User).where(_real_user_sql_clause()).order_by(User.created_at.desc())
        if search_value:
            search_pattern = f"%{search_value}%"
            query = query.where(
                or_(
                    cast(User.id, String).like(search_pattern),
                    cast(User.telegram_id, String).like(search_pattern),
                    func.lower(func.coalesce(User.username, "")).like(search_pattern),
                )
            )
        rows = list((await session.execute(query)).scalars().all())

    result = []
    for user in rows:
        if _is_synthetic_user(user):
            continue
        status = get_access_status_from_user(user)
        result.append(
            {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username or "—",
                "status": status,
                "is_blocked": getattr(user, "is_blocked", False),
                "preferred_protocol": user.preferred_protocol,
                "subscription_expires_at": _format_datetime(user.subscription_expires_at),
                "trial_expires_at": _format_datetime(user.trial_expires_at),
                "created_at": _format_datetime(user.created_at),
            }
        )
    return result


async def get_user_detail(user_id: int) -> dict | None:
    user = await get_user_by_id(user_id)
    if user is None:
        return None
    if _is_synthetic_user(user):
        return None
    active_extra_slots = await get_active_device_slot_counts_for_users([user.id])
    setattr(user, "active_device_slot_addons", int(active_extra_slots.get(user.id, 0)))
    devices, public_routes, subscription_link, vpn_repair_events, payment_rows = await asyncio.gather(
        get_user_vpn_clients(user.id),
        get_public_subscription_routes_for_user(user.id),
        get_active_public_subscription_link_for_user(user.id),
        list_vpn_repair_events(user.id, limit=5),
        get_payment_records(user_id=user.id),
    )
    subscription_link_url = (
        build_public_subscription_page_url(str(subscription_link.token))
        if subscription_link is not None
        else await get_or_create_public_subscription_page_url_for_user(user.id)
    )
    if subscription_link is None:
        subscription_link = await get_active_public_subscription_link_for_user(user.id)
    support_ticket_user_id = int(user.telegram_id)
    support_ticket = await get_ticket(support_ticket_user_id)
    support_history = await get_history(support_ticket_user_id) if support_ticket is not None else []
    support_history = _decorate_support_history(support_ticket_user_id, support_history)
    if support_ticket is not None:
        support_ticket = {
            **support_ticket,
            "status_label": {
                "new": "Новый",
                "in_progress": "В работе",
                "closed": "Закрыт",
            }.get(support_ticket.get("status", "new"), support_ticket.get("status", "new")),
            "updated_at_label": _format_datetime(_parse_iso_datetime(support_ticket.get("updated_at"))),
        }
    payment_counts = {
        "total": len(payment_rows),
        "confirmed": sum(1 for row in payment_rows if row.payment_status == "confirmed"),
        "reviewable": sum(1 for row in payment_rows if row.payment_status == "awaiting_admin_review"),
    }
    serialized_legacy_devices = await asyncio.gather(
        *[_serialize_user_device(device, user_last_activity_at=getattr(user, "last_activity_at", None)) for device in devices]
    )
    serialized_devices = [
        *_serialize_public_subscription_devices(public_routes, user_last_activity_at=getattr(user, "last_activity_at", None)),
        *serialized_legacy_devices,
    ]
    return {
        "user": user,
        "status": get_access_status_from_user(user),
        "access_expires_at": _format_datetime(get_access_expires_at_from_user(user)),
        "subscription_link_url": subscription_link_url,
        "subscription_link_token": str(getattr(subscription_link, "token", "") or "").strip() or None,
        "subscription_link_last_viewed_at": _format_datetime(getattr(subscription_link, "last_viewed_at", None)),
        "subscription_link_last_feed_accessed_at": _format_datetime(getattr(subscription_link, "last_feed_accessed_at", None)),
        "vpn_repair_state": {
            "repair_needed": bool(getattr(user, "vpn_repair_needed", False)),
            "reason": normalize_repair_reason(getattr(user, "vpn_repair_reason", None)),
            "reason_label": repair_reason_label(getattr(user, "vpn_repair_reason", None)),
            "source": normalize_repair_source(getattr(user, "vpn_repair_reason", None)),
            "source_label": repair_source_label(getattr(user, "vpn_repair_reason", None)),
            "marked_at": _format_datetime(getattr(user, "vpn_repair_marked_at", None)),
        },
        "vpn_repair_events": [_serialize_vpn_repair_event(event) for event in vpn_repair_events],
        "devices": serialized_devices,
        "payments": payment_rows,
        "payment_counts": payment_counts,
        "support_ticket": support_ticket,
        "support_history": support_history[:6],
    }


async def get_user_device_status_payload(user_id: int, device_id: int) -> dict | None:
    user = await get_user_by_id(user_id)
    if user is None or _is_synthetic_user(user):
        return None
    checked_at = _format_datetime(datetime.now(timezone.utc))
    if int(device_id) <= -100000:
        return {
            "device_id": int(device_id),
            "mode_label": "—",
            **_build_device_status_payload(
                "unknown",
                "Устройство из единой ссылки пока доступно только для просмотра",
                checked_at=checked_at,
            ),
        }
    device = await get_vpn_client_by_id(device_id)
    if device is None:
        return {
            "device_id": int(device_id),
            "mode_label": "—",
            **_build_device_status_payload(
                "unknown",
                "Устройство уже удалено или карточка устарела. Обновите пользователя.",
                checked_at=checked_at,
            ),
        }
    if int(getattr(device, "user_id", 0) or 0) != int(user_id):
        return {
            "device_id": int(device_id),
            "mode_label": "—",
            **_build_device_status_payload(
                "unknown",
                "Карточка устройства устарела или относится к другому пользователю. Обновите карточку пользователя.",
                checked_at=checked_at,
            ),
        }
    return await _get_device_status_payload(device, user)


def _balance_event_reason_label(reason: str | None) -> str:
    normalized = str(reason or "").strip().lower()
    if normalized in BALANCE_EVENT_REASON_LABELS:
        return BALANCE_EVENT_REASON_LABELS[normalized]
    if not normalized:
        return "Изменение баланса"
    return normalized.replace("_", " ")


async def get_user_balance_history(user_id: int, *, limit: int = 20) -> list[dict]:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            return []
        events = list(
            (
                await session.execute(
                    select(UserBalanceEvent)
                    .where(UserBalanceEvent.user_id == user_id)
                    .order_by(UserBalanceEvent.created_at.asc(), UserBalanceEvent.id.asc())
                )
            ).scalars().all()
        )

    if not events:
        return []

    replay_total = 0
    replay_reserved = 0
    for event in events:
        amount = int(getattr(event, "amount", 0) or 0)
        direction = str(getattr(event, "direction", "") or "").strip().lower()
        if direction == "credit":
            replay_total += amount
        elif direction == "debit":
            replay_total -= amount
        elif direction == "reserve":
            replay_reserved += amount
        elif direction == "release":
            replay_reserved -= amount

    current_total = int(getattr(user, "balance_rub", 0) or 0)
    current_reserved = int(getattr(user, "balance_reserved_rub", 0) or 0)
    total = current_total - replay_total
    reserved = current_reserved - replay_reserved

    rows: list[dict] = []
    for event in events:
        amount = int(getattr(event, "amount", 0) or 0)
        direction = str(getattr(event, "direction", "") or "").strip().lower()
        before_total = total
        before_reserved = reserved
        before_available = max(before_total - before_reserved, 0)

        if direction == "credit":
            total += amount
        elif direction == "debit":
            total -= amount
        elif direction == "reserve":
            reserved += amount
        elif direction == "release":
            reserved -= amount

        after_total = total
        after_reserved = reserved
        after_available = max(after_total - after_reserved, 0)
        rows.append(
            {
                "id": event.id,
                "created_at": _format_datetime(event.created_at),
                "direction": direction,
                "direction_label": BALANCE_EVENT_DIRECTION_LABELS.get(direction, direction or "Изменение"),
                "reason": event.reason,
                "reason_label": _balance_event_reason_label(event.reason),
                "amount": amount,
                "balance_before": before_total,
                "balance_after": after_total,
                "reserved_before": before_reserved,
                "reserved_after": after_reserved,
                "available_before": before_available,
                "available_after": after_available,
                "reference_type": event.reference_type,
                "reference_id": event.reference_id,
                "note": event.note,
            }
        )

    return list(reversed(rows[-max(int(limit), 1):]))


async def get_vpn_overview(search: str = "", protocol: str = "all", country: str = "all") -> dict:
    cacheable = not str(search or "").strip() and protocol == "all" and country == "all"
    if cacheable:
        cached = _runtime_cache_get("vpn_overview_default")
        if cached is not None:
            return cached

    async with async_session() as session:
        users = list((await session.execute(select(User).where(_real_user_sql_clause()))).scalars().all())
        devices = list(
            (
                await session.execute(
                    select(VpnClient)
                    .where(VpnClient.user_id.in_(_real_user_ids_subquery()))
                    .order_by(VpnClient.created_at.desc())
                )
            ).scalars().all()
        )

    user_map = {user.id: user for user in users}
    filtered_items = []
    base_counts = {
        "total_devices": 0,
        "vless": 0,
        "trojan": 0,
        "germany": 0,
        "estonia": 0,
        "active_access": 0,
        "blocked_users": 0,
        "expiring_soon": 0,
    }
    blocked_users_seen = set()
    now = utcnow()
    search_value = search.strip().lower()

    for device in devices:
        metadata = _device_metadata(device)
        user = user_map.get(device.user_id)
        if user is not None and _is_synthetic_user(user):
            continue
        country_code = (metadata.get("country_code") or "").lower()
        access_status = get_access_status_from_user(user) if user else "unknown"
        access_expires_at = get_access_expires_at_from_user(user) if user else None
        username = user.username if user and user.username else "—"
        telegram_id = user.telegram_id if user else None
        is_blocked = bool(getattr(user, "is_blocked", False)) if user else False

        base_counts["total_devices"] += 1
        if device.protocol == "vless":
            base_counts["vless"] += 1
        elif device.protocol == "trojan":
            base_counts["trojan"] += 1

        if country_code == "de":
            base_counts["germany"] += 1
        elif country_code == "ee":
            base_counts["estonia"] += 1

        if access_status in {"paid_active", "trial_active"}:
            base_counts["active_access"] += 1
        if access_expires_at and access_expires_at <= now + timedelta(days=7):
            base_counts["expiring_soon"] += 1
        if is_blocked and user is not None and user.id not in blocked_users_seen:
            blocked_users_seen.add(user.id)
            base_counts["blocked_users"] += 1

        if protocol != "all" and device.protocol != protocol:
            continue
        if country != "all" and country_code != country:
            continue

        haystack = " ".join(
            [
                str(device.id),
                str(device.user_id),
                str(telegram_id or ""),
                username,
                metadata.get("device_name") or "",
                metadata.get("device_type") or "",
                metadata.get("country_name") or "",
                device.protocol,
            ]
        ).lower()
        if search_value and search_value not in haystack:
            continue

        filtered_items.append(
            {
                "id": device.id,
                "user_id": device.user_id,
                "telegram_id": telegram_id or "—",
                "username": username,
                "device_name": metadata.get("device_name") or device.email,
                "device_type": metadata.get("device_type") or "other",
                "country_name": metadata.get("country_name") or "—",
                "country_code": country_code or "—",
                "protocol": device.protocol,
                "created_at": _format_datetime(device.created_at),
                "access_status": access_status,
                "access_expires_at": _format_datetime(access_expires_at),
                "is_blocked": is_blocked,
            }
        )

    total_devices = max(base_counts["total_devices"], 1)
    payload = {
        "summary": {
            **base_counts,
            "filtered_devices": len(filtered_items),
            "vless_percent": round((base_counts["vless"] / total_devices) * 100),
            "trojan_percent": round((base_counts["trojan"] / total_devices) * 100),
            "germany_percent": round((base_counts["germany"] / total_devices) * 100),
            "estonia_percent": round((base_counts["estonia"] / total_devices) * 100),
        },
        "items": filtered_items,
        "filters": {
            "query": search,
            "protocol": protocol,
            "country": country,
        },
    }
    if cacheable:
        _runtime_cache_set("vpn_overview_default", payload)
    return copy.deepcopy(payload)


def _build_sync_result_entry(
    device: VpnClient,
    metadata: dict,
    *,
    action: str,
    status: str,
    error: str | None = None,
) -> dict:
    return {
        "device_id": int(device.id),
        "email": device.email,
        "protocol": device.protocol,
        "country_code": normalize_country_code(metadata.get("country_code")) or "unknown",
        "device_name": metadata.get("device_name") or device.email,
        "action": action,
        "status": status,
        "error": error,
    }


async def _sync_single_device_access(device: VpnClient, access_expires_at: datetime | None) -> dict:
    metadata = _device_metadata(device)
    action = "enable" if access_expires_at is not None else "disable"
    client_uuid = device.xui_client_id or device.client_uuid
    original_metadata = dict(metadata)

    try:
        if device.protocol == "vless":
            provider_type = metadata.get("provider_type")
            if provider_type == "xui":
                xui = XUIClient(country_code=metadata.get("country_code"))
                try:
                    if not await xui.login():
                        raise ValueError("3x-ui login failed")
                    result = await xui.sync_vless_client_expiry(
                        inbound_id=int(metadata.get("inbound_id") or 0),
                        client_uuid=client_uuid,
                        email=device.email,
                        access_expires_at=access_expires_at,
                    )
                    resolved_inbound_id = result.get("inbound_id")
                finally:
                    await xui.close()
                if resolved_inbound_id:
                    metadata["inbound_id"] = int(resolved_inbound_id)
            else:
                provisioner = get_vless_provisioner(metadata.get("country_code"), provider_type)
                try:
                    if not await provisioner.health_check():
                        raise ValueError("Provisioner health-check failed")
                    await provisioner.sync_vless_client(
                        client_uuid=client_uuid,
                        email=device.email,
                        metadata=metadata,
                        access_expires_at=access_expires_at,
                    )
                finally:
                    await provisioner.close()
            if metadata != original_metadata:
                await update_vpn_client_metadata(device.id, metadata)
            return _build_sync_result_entry(device, metadata, action=action, status="success")

        if device.protocol == "trojan":
            xui = XUIClient(country_code=metadata.get("country_code"))
            try:
                if not await xui.login():
                    raise ValueError("3x-ui login failed")
                result = await xui.sync_trojan_client_expiry(
                    inbound_id=int(metadata.get("inbound_id") or 0),
                    client_uuid=client_uuid,
                    email=device.email,
                    access_expires_at=access_expires_at,
                )
                resolved_inbound_id = result.get("inbound_id")
            finally:
                await xui.close()
            if resolved_inbound_id:
                metadata["inbound_id"] = int(resolved_inbound_id)
            if metadata != original_metadata:
                await update_vpn_client_metadata(device.id, metadata)
            return _build_sync_result_entry(device, metadata, action=action, status="success")

        raise ValueError(f"Unsupported protocol: {device.protocol}")
    except Exception as exc:
        return _build_sync_result_entry(device, metadata, action=action, status="failed", error=str(exc))


async def _restore_device_remote_state(
    device: VpnClient,
    metadata: dict,
    access_expires_at: datetime | None,
) -> bool:
    client_uuid = device.xui_client_id or device.client_uuid

    try:
        if device.protocol == "vless":
            provider_type = metadata.get("provider_type")
            if provider_type == "xui":
                xui = XUIClient(country_code=metadata.get("country_code"))
                try:
                    if not await xui.login():
                        return False
                    resolved_inbound_id = await xui.resolve_client_inbound_id(
                        "vless",
                        client_uuid,
                        device.email,
                        metadata.get("inbound_id"),
                    )
                    if resolved_inbound_id is None:
                        inbound = await xui.find_inbound("vless", 443)
                        if inbound is None:
                            return False
                        expiry_time_ms = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
                        result = await xui.add_vless_client(
                            inbound_id=int(inbound["id"]),
                            email=device.email,
                            client_uuid=client_uuid,
                            expiry_time_ms=expiry_time_ms,
                        )
                        if not result.get("success"):
                            return False
                        await update_vpn_client_metadata(device.id, {**metadata, "inbound_id": int(inbound["id"])})
                        return True
                    await xui.sync_vless_client_expiry(
                        inbound_id=resolved_inbound_id,
                        client_uuid=client_uuid,
                        email=device.email,
                        access_expires_at=access_expires_at,
                    )
                    if resolved_inbound_id != metadata.get("inbound_id"):
                        await update_vpn_client_metadata(device.id, {**metadata, "inbound_id": resolved_inbound_id})
                    return True
                finally:
                    await xui.close()

            provisioner = get_vless_provisioner(metadata.get("country_code"), provider_type)
            try:
                if not await provisioner.health_check():
                    return False
                await provisioner.sync_vless_client(
                    client_uuid=client_uuid,
                    email=device.email,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                )
                return True
            finally:
                await provisioner.close()

        if device.protocol == "trojan":
            xui = XUIClient(country_code=metadata.get("country_code"))
            try:
                if not await xui.login():
                    return False
                resolved_inbound_id = await xui.resolve_client_inbound_id(
                    "trojan",
                    client_uuid,
                    device.email,
                    metadata.get("inbound_id"),
                )
                if resolved_inbound_id is not None:
                    await xui.sync_trojan_client_expiry(
                        inbound_id=resolved_inbound_id,
                        client_uuid=client_uuid,
                        email=device.email,
                        access_expires_at=access_expires_at,
                    )
                    if resolved_inbound_id != metadata.get("inbound_id"):
                        await update_vpn_client_metadata(device.id, {**metadata, "inbound_id": resolved_inbound_id})
                    return True

                inbound = await xui.find_inbound("trojan", 8443)
                if inbound is None:
                    return False
                expiry_time_ms = int(access_expires_at.timestamp() * 1000) if access_expires_at else 0
                result = await xui.add_trojan_client(
                    inbound_id=int(inbound["id"]),
                    email=device.email,
                    password=client_uuid,
                    expiry_time_ms=expiry_time_ms,
                )
                if not result.get("success"):
                    return False
                await update_vpn_client_metadata(device.id, {**metadata, "inbound_id": int(inbound["id"])})
                return True
            finally:
                await xui.close()
    except Exception:
        return False

    return False


async def _delete_remote_state_snapshot(snapshot: dict) -> bool:
    protocol = str(snapshot.get("protocol") or "").strip().lower()
    country_code = snapshot.get("country_code")
    provider_type = snapshot.get("provider_type")
    client_uuid = snapshot.get("client_uuid")
    email = snapshot.get("email")
    inbound_id = int(snapshot.get("inbound_id") or 0)

    if not protocol or not client_uuid or not email:
        return False

    try:
        if protocol == "vless":
            provisioner = get_vless_provisioner(country_code, provider_type)
            try:
                await provisioner.delete_vless_client(
                    client_uuid=client_uuid,
                    email=email,
                    metadata={
                        "country_code": country_code,
                        "provider_type": provider_type,
                        "inbound_id": inbound_id,
                    },
                )
                return True
            finally:
                await provisioner.close()

        if protocol == "trojan":
            xui = XUIClient(country_code=country_code)
            try:
                if not await xui.login():
                    return False
                await xui.delete_trojan_client(inbound_id, client_uuid, email=email)
                return True
            finally:
                await xui.close()
    except Exception:
        return False

    return False


async def grant_trial_to_user(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    before_user = await get_user_by_id(user_id)
    updated_user = await activate_trial(user_id)
    if updated_user is None:
        raise ValueError("Пользователь не найден")
    sync_result = await sync_user_clients_access(user_id)
    if sync_result["sync_failed"]:
        await mark_vpn_repair_needed(user_id, MANUAL_REPAIR_SYNC_FAILED)
    else:
        await clear_vpn_repair_needed(user_id, emit_control_event=False)
    invalidate_runtime_cache("overview_metrics")
    await create_audit_log(
        admin.id,
        "grant_trial",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": _user_audit_snapshot(before_user),
                "after": _user_audit_snapshot(updated_user),
                "sync_result": {
                    "sync_failed": bool(sync_result.get("sync_failed")),
                    "processed_devices": int(sync_result.get("processed_devices", 0) or 0),
                    "failed_devices": int(sync_result.get("failed_devices", 0) or 0),
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return sync_result


async def extend_subscription_for_user(
    user_id: int,
    days: int,
    admin: DashboardAdmin,
    ip_address: str | None,
    source: str = "dashboard_manual",
) -> dict:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return

        before_snapshot = _user_audit_snapshot(user)
        now = utcnow()
        current_base = user.subscription_expires_at if user.subscription_expires_at and user.subscription_expires_at > now else now
        user.subscription_started_at = user.subscription_started_at or now
        user.subscription_expires_at = current_base + timedelta(days=days)
        user.subscription_status = "active"
        user.subscription_source = source
        await session.commit()

    sync_result = await sync_user_clients_access(user_id)
    if sync_result["sync_failed"]:
        await mark_vpn_repair_needed(user_id, MANUAL_REPAIR_SYNC_FAILED)
    else:
        await clear_vpn_repair_needed(user_id, emit_control_event=False)
    invalidate_runtime_cache("overview_metrics")
    await create_control_event(
        category="users",
        severity="INFO",
        event_type="subscription_extended_by_admin",
        title="Подписка продлена через панель",
        message=(
            f"{_control_user_identity(user)}\n"
            f"Продление: <b>{days} дней</b>\n"
            f"Источник: <b>{escape(source)}</b>\n"
            f"Администратор: <b>{escape(admin.display_name)}</b>"
        ),
        entity_type="user",
        entity_id=str(user_id),
        payload={
            "user_id": user_id,
            "telegram_id": user.telegram_id,
            "days": days,
            "source": source,
            "admin_id": admin.id,
            "admin_name": admin.display_name,
        },
        dedupe_key=f"dashboard-user:{user_id}:extend:{source}:{days}",
        cooldown_seconds=0,
    )
    await create_audit_log(
        admin.id,
        "extend_subscription",
        "user",
        str(user_id),
        json.dumps(
            {
                "days": int(days),
                "source": source,
                "before": before_snapshot,
                "after": _user_audit_snapshot(user),
                "sync_result": {
                    "sync_failed": bool(sync_result.get("sync_failed")),
                    "processed_devices": int(sync_result.get("processed_devices", 0) or 0),
                    "failed_devices": int(sync_result.get("failed_devices", 0) or 0),
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    expires_text = user.subscription_expires_at.strftime("%Y-%m-%d %H:%M:%S") if user.subscription_expires_at else "—"
    if user.telegram_id:
        await send_user_message_and_refresh_home(
            int(user.telegram_id),
            subscription_extended_notification_text(days=days, expires_at=expires_text),
        )
    return sync_result


async def set_user_block_state(user_id: int, is_blocked: bool, admin: DashboardAdmin, ip_address: str | None) -> dict:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return
        before_snapshot = _user_audit_snapshot(user)
        user.is_blocked = is_blocked
        await session.commit()

    sync_result = await sync_user_clients_access(user_id)
    if sync_result["sync_failed"]:
        await mark_vpn_repair_needed(user_id, MANUAL_REPAIR_SYNC_FAILED)
    else:
        await clear_vpn_repair_needed(user_id)
    invalidate_runtime_cache("overview_metrics")
    await create_control_event(
        category="users",
        severity="WARNING" if is_blocked else "INFO",
        event_type="user_blocked" if is_blocked else "user_unblocked",
        title="Пользователь заблокирован" if is_blocked else "Пользователь разблокирован",
        message=(
            f"{_control_user_identity(user)}\n"
            f"Действие: <b>{'Блокировка доступа' if is_blocked else 'Разблокировка доступа'}</b>\n"
            f"Администратор: <b>{escape(admin.display_name)}</b>"
        ),
        entity_type="user",
        entity_id=str(user_id),
        payload={
            "user_id": user_id,
            "telegram_id": user.telegram_id,
            "blocked": is_blocked,
            "admin_id": admin.id,
            "admin_name": admin.display_name,
        },
        dedupe_key=f"dashboard-user:{user_id}:blocked:{int(is_blocked)}",
        resolve_dedupe_key=f"dashboard-user:{user_id}:blocked:{0 if is_blocked else 1}",
        cooldown_seconds=0,
    )
    await create_audit_log(
        admin.id,
        "block_user" if is_blocked else "unblock_user",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(user),
                "sync_result": {
                    "sync_failed": bool(sync_result.get("sync_failed")),
                    "processed_devices": int(sync_result.get("processed_devices", 0) or 0),
                    "failed_devices": int(sync_result.get("failed_devices", 0) or 0),
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    if user.telegram_id:
        await send_user_message_and_refresh_home(
            int(user.telegram_id),
            user_blocked_notification_text() if is_blocked else user_unblocked_notification_text(),
        )
    return sync_result


async def remove_user_tariff(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("User not found")

        before_snapshot = _user_audit_snapshot(user)
        had_trial = bool(user.trial_expires_at and user.trial_expires_at > utcnow())
        user.subscription_status = "inactive"
        user.subscription_source = None
        user.subscription_started_at = None
        user.subscription_expires_at = None
        user.trial_expires_at = None
        user.trial_used = bool(user.trial_used or had_trial)
        await session.commit()

    sync_result = await sync_user_clients_access(user_id)
    if sync_result["sync_failed"]:
        await mark_vpn_repair_needed(user_id, MANUAL_REPAIR_SYNC_FAILED)
    else:
        await clear_vpn_repair_needed(user_id)
    invalidate_runtime_cache("overview_metrics", "server_snapshots", "xui_summary")
    await create_audit_log(
        admin.id,
        "remove_user_tariff",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(user),
                "sync_result": {
                    "sync_failed": bool(sync_result.get("sync_failed")),
                    "processed_devices": int(sync_result.get("processed_devices", 0) or 0),
                    "failed_devices": int(sync_result.get("failed_devices", 0) or 0),
                },
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return sync_result


async def set_user_preferred_protocol(user_id: int, protocol: str, admin: DashboardAdmin, ip_address: str | None) -> None:
    normalized_protocol = str(protocol or "").strip().lower()
    if normalized_protocol not in {"vless", "trojan"}:
        raise ValueError("Некорректный протокол")
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return
        before_snapshot = _user_audit_snapshot(user)
        user.preferred_protocol = normalized_protocol
        await session.commit()

    invalidate_runtime_cache("overview_metrics")
    await create_audit_log(
        admin.id,
        "set_preferred_protocol",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(user),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )


async def repair_user_vpn_access(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    user = await get_user_by_id(user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    before_snapshot = _user_audit_snapshot(user)

    access_expires_at = await get_access_expires_at(user_id)
    devices = await get_user_vpn_clients(user_id)

    if access_expires_at is None:
        reason = MANUAL_REPAIR_NO_ACCESS
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await create_audit_log(
            admin.id,
            "repair_vpn_access",
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": False,
                    "checked_devices": 0,
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {"sync_failed": True, "repair_needed": True, "reason": reason}

    if not devices:
        reason = MANUAL_REPAIR_NO_DEVICES
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await create_audit_log(
            admin.id,
            "repair_vpn_access",
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": True,
                    "checked_devices": 0,
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {"sync_failed": True, "repair_needed": True, "reason": reason}

    sync_result = await sync_user_vpn_access_with_single_retry(user_id, access_expires_at)
    sync_failed = sync_result["sync_failed"]
    if sync_failed:
        reason = MANUAL_REPAIR_SYNC_FAILED
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "failed", reason)
    else:
        reason = None
        updated_user = await clear_vpn_repair_needed(user_id)
        await create_vpn_repair_event(user_id, "success", MANUAL_REPAIR)

    await create_audit_log(
        admin.id,
        "repair_vpn_access",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                "reason": reason,
                "sync_failed": bool(sync_failed),
                "checked_access": True,
                "checked_devices": len(devices),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return {"sync_failed": sync_failed, "repair_needed": sync_failed, "reason": reason}


async def sync_user_clients_access(user_id: int) -> dict:
    user = await get_user_by_id(user_id)
    if user is None:
        return {
            "sync_failed": False,
            "processed_devices": 0,
            "successful_devices": 0,
            "failed_devices": 0,
            "results": [],
        }

    access_expires_at = get_access_expires_at_from_user(user)
    devices = await get_user_vpn_clients(user_id)
    if not devices:
        return {
            "sync_failed": False,
            "processed_devices": 0,
            "successful_devices": 0,
            "failed_devices": 0,
            "results": [],
        }

    results: list[dict] = []
    for device in devices:
        results.append(await _sync_single_device_access(device, access_expires_at))

    failed_devices = [item for item in results if item["status"] != "success"]
    return {
        "sync_failed": bool(failed_devices),
        "processed_devices": len(results),
        "successful_devices": len(results) - len(failed_devices),
        "failed_devices": len(failed_devices),
        "results": results,
    }


async def _update_existing_vpn_client_record(
    device_id: int,
    *,
    user_id: int,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None = None,
    client_data: dict | None = None,
):
    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == device_id))
        vpn_client = result.scalar_one_or_none()
        if vpn_client is None:
            raise ValueError("Access client not found")
        vpn_client.user_id = user_id
        vpn_client.protocol = protocol
        vpn_client.client_uuid = client_uuid
        vpn_client.email = email
        vpn_client.xui_client_id = xui_client_id
        vpn_client.client_data = json.dumps(client_data, ensure_ascii=False) if client_data else None
        await session.commit()
        await session.refresh(vpn_client)
        return vpn_client


async def _delete_device_remote_state(device: VpnClient, metadata: dict) -> None:
    client_uuid = device.xui_client_id or device.client_uuid
    inbound_id = int(metadata.get("inbound_id") or 0)
    if device.protocol == "vless":
        if _is_retired_estonia_xui_admin_device(metadata, email=getattr(device, "email", None)):
            logger.info(
                "Skipping remote delete for retired Estonia xui admin device device_id=%s email=%s",
                getattr(device, "id", None),
                getattr(device, "email", None),
            )
            return
        provisioner = get_vless_provisioner(metadata.get("country_code"), metadata.get("provider_type"))
        try:
            await provisioner.delete_vless_client(
                client_uuid=client_uuid,
                email=device.email,
                metadata=metadata,
            )
        finally:
            await provisioner.close()
        return

    if device.protocol == "trojan":
        xui = XUIClient(country_code=metadata.get("country_code"))
        try:
            if not await xui.login():
                raise ValueError("3x-ui login failed")
            await xui.delete_trojan_client(inbound_id, client_uuid, email=device.email)
        finally:
            await xui.close()


async def _reissue_existing_device(device: VpnClient, *, target_country_code: str | None = None) -> dict:
    metadata = _device_metadata(device)
    current_country_code = normalize_country_code(metadata.get("country_code"))
    resolved_country_code = normalize_country_code(target_country_code or current_country_code)
    if not region_supports_protocol(resolved_country_code, device.protocol):
        raise ValueError("Этот регион не поддерживает выбранный протокол")

    access_expires_at = await get_access_expires_at(device.user_id)
    if access_expires_at is None:
        raise ValueError("У пользователя нет активного доступа")

    base_metadata = {
        **metadata,
        "device_name": metadata.get("device_name") or device.email,
        "device_type": metadata.get("device_type") or "other",
        "protocol": device.protocol,
    }
    region = build_region_snapshot(resolved_country_code)
    original_record = {
        "client_uuid": device.client_uuid,
        "email": device.email,
        "xui_client_id": device.xui_client_id,
        "client_data": json.loads(device.client_data) if device.client_data else None,
    }
    replacement_remote_state: dict | None = None
    record_changed = False

    await _delete_device_remote_state(device, metadata)

    try:
        if device.protocol == "trojan":
            xui = XUIClient(country_code=resolved_country_code)
            try:
                if not await xui.login():
                    raise ValueError("3x-ui login failed")
                inbound = await xui.find_inbound("trojan", 8443)
                if inbound is None:
                    raise ValueError("Trojan inbound not found")
                password = str(uuid4())
                expiry_time_ms = int(access_expires_at.timestamp() * 1000)
                result = await xui.add_trojan_client(
                    inbound_id=inbound["id"],
                    email=device.email,
                    password=password,
                    expiry_time_ms=expiry_time_ms,
                )
                if not result.get("success"):
                    raise ValueError("3x-ui failed to recreate Trojan client")
                replacement_remote_state = {
                    "protocol": "trojan",
                    "country_code": resolved_country_code,
                    "provider_type": region["provider_type"],
                    "inbound_id": inbound["id"],
                    "client_uuid": password,
                    "email": device.email,
                }
                await _update_existing_vpn_client_record(
                    device.id,
                    user_id=device.user_id,
                    protocol="trojan",
                    client_uuid=password,
                    email=device.email,
                    xui_client_id=password,
                    client_data={"inbound_id": inbound["id"]},
                )
                record_changed = True
                connection_name = build_connection_name(
                    country_code=resolved_country_code,
                    country_name=region["country_name"],
                    email=device.email,
                )
                trojan_link = build_trojan_link(
                    inbound=inbound,
                    password=password,
                    email=device.email,
                    connection_name=connection_name,
                    country_code=resolved_country_code,
                )
            finally:
                await xui.close()
            await update_vpn_client_metadata(
                device.id,
                {
                    **base_metadata,
                    **region,
                    "provider_type": region["provider_type"],
                    "inbound_id": inbound["id"],
                    "trojan_link": trojan_link,
                },
            )
        else:
            provisioner = get_vless_provisioner(resolved_country_code, region.get("provider_type"))
            try:
                result = await provisioner.provision_vless_client(
                    user_id=device.user_id,
                    email=device.email,
                    access_expires_at=access_expires_at,
                    save_callback=lambda **kwargs: _update_existing_vpn_client_record(device.id, **kwargs),
                    country_code=resolved_country_code,
                )
                replacement_remote_state = {
                    "protocol": "vless",
                    "country_code": resolved_country_code,
                    "provider_type": result.metadata.get("provider_type") or region["provider_type"],
                    "inbound_id": result.metadata.get("inbound_id"),
                    "client_uuid": result.client_uuid,
                    "email": result.email,
                }
                record_changed = True
            finally:
                await provisioner.close()
            await update_vpn_client_metadata(
                device.id,
                {
                    **base_metadata,
                    **region,
                    **result.metadata,
                },
            )
    except Exception as exc:
        replacement_cleanup_ok = True
        if replacement_remote_state is not None:
            replacement_cleanup_ok = await _delete_remote_state_snapshot(replacement_remote_state)

        record_restore_ok = True
        if record_changed:
            try:
                await _update_existing_vpn_client_record(
                    device.id,
                    user_id=device.user_id,
                    protocol=device.protocol,
                    client_uuid=original_record["client_uuid"],
                    email=original_record["email"],
                    xui_client_id=original_record["xui_client_id"],
                    client_data=original_record["client_data"],
                )
                await update_vpn_client_metadata(device.id, metadata)
            except Exception:
                record_restore_ok = False

        remote_restore_ok = await _restore_device_remote_state(device, metadata, access_expires_at)
        rollback_bits = []
        if not replacement_cleanup_ok:
            rollback_bits.append("cleanup_failed")
        if not record_restore_ok:
            rollback_bits.append("db_restore_failed")
        if not remote_restore_ok:
            rollback_bits.append("remote_restore_failed")
        if rollback_bits:
            raise ValueError(f"{exc} (rollback: {', '.join(rollback_bits)})") from exc
        raise

    return {
        "device_id": device.id,
        "country_code": resolved_country_code,
        "country_name": region["country_name"],
        "node_rebound": resolved_country_code != current_country_code,
    }


async def reissue_vpn_client_device(device_id: int) -> dict:
    device = await get_vpn_client_by_id(device_id)
    if device is None:
        raise ValueError("Устройство не найдено")
    return await _reissue_existing_device(device)


async def _emit_user_repair_alert(
    *,
    user: User,
    admin: DashboardAdmin,
    operation: str,
    failures: list[dict],
) -> None:
    await create_control_event(
        category="access",
        severity="WARNING",
        event_type="user_access_repair_failed",
        title="Пользователь требует ремонта",
        message=(
            f"{_control_user_identity(user)}\n"
            f"Операция: <b>{escape(operation)}</b>\n"
            f"Ошибок устройств: <b>{len(failures)}</b>\n"
            f"Администратор: <b>{escape(admin.display_name)}</b>"
        ),
        entity_type="user",
        entity_id=str(user.id),
        payload={
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "operation": operation,
            "failures": failures,
            "admin_id": admin.id,
            "admin_name": admin.display_name,
        },
        dedupe_key=f"dashboard-user:{user.id}:repair-needed",
        cooldown_seconds=0,
    )


async def _run_user_repair_operation(
    user_id: int,
    admin: DashboardAdmin,
    ip_address: str | None,
    *,
    operation: str,
) -> dict:
    user = await get_user_by_id(user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    before_snapshot = _user_audit_snapshot(user)
    before_snapshot = _user_audit_snapshot(user)

    access_expires_at = await get_access_expires_at(user_id)
    payments = await get_payment_records(user_id=user_id)
    devices = await get_user_vpn_clients(user_id)

    if access_expires_at is None:
        reason = MANUAL_REPAIR_NO_ACCESS
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await _emit_user_repair_alert(
            user=user,
            admin=admin,
            operation=operation,
            failures=[{"reason": reason}],
        )
        await create_audit_log(
            admin.id,
            operation,
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": False,
                    "checked_devices": 0,
                    "operation_state": "skipped",
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {
            "sync_failed": True,
            "repair_needed": True,
            "reason": reason,
            "operation": operation,
            "checked_access": False,
            "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
            "checked_devices": 0,
            "reissued_devices": 0,
            "node_rebound": False,
            "failed_devices": 0,
        }

    if not devices:
        reason = MANUAL_REPAIR_NO_DEVICES
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await _emit_user_repair_alert(
            user=user,
            admin=admin,
            operation=operation,
            failures=[{"reason": reason}],
        )
        await create_audit_log(
            admin.id,
            operation,
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": True,
                    "checked_devices": 0,
                    "operation_state": "skipped",
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {
            "sync_failed": True,
            "repair_needed": True,
            "reason": reason,
            "operation": operation,
            "checked_access": True,
            "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
            "checked_devices": 0,
            "reissued_devices": 0,
            "node_rebound": False,
            "failed_devices": 0,
        }

    results: list[dict] = []
    failures: list[dict] = []
    for device in devices:
        try:
            results.append(await _reissue_existing_device(device))
        except Exception as exc:
            failures.append({"device_id": device.id, "error": str(exc)})

    if failures:
        reason = MANUAL_REPAIR_SYNC_FAILED
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "failed", reason)
        await _emit_user_repair_alert(user=user, admin=admin, operation=operation, failures=failures)
    else:
        reason = None
        updated_user = await clear_vpn_repair_needed(user_id)
        await create_vpn_repair_event(user_id, "success", MANUAL_REPAIR)
        await create_control_event(
            category="access",
            severity="INFO",
            event_type="user_access_repair_completed",
            title="Состояние пользователя восстановлено",
            message=(
                f"{_control_user_identity(user)}\n"
                f"Операция: <b>{escape(operation)}</b>\n"
                f"Устройств пересобрано: <b>{len(results)}</b>\n"
                f"Администратор: <b>{escape(admin.display_name)}</b>"
            ),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "operation": operation,
                "reissued_devices": len(results),
                "node_rebound": any(item["node_rebound"] for item in results),
                "admin_id": admin.id,
                "admin_name": admin.display_name,
            },
            resolve_dedupe_key=f"dashboard-user:{user.id}:repair-needed",
            dedupe_key=f"dashboard-user:{user.id}:{operation}:success",
            cooldown_seconds=0,
        )

    await create_audit_log(
        admin.id,
        operation,
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                "devices": len(devices),
                "reissued_devices": len(results),
                "failed_devices": len(failures),
                "node_rebound": any(item["node_rebound"] for item in results),
                "reason": reason,
                "operation_state": "failed" if failures else "success",
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "server_snapshots", "xui_summary")
    return {
        "sync_failed": bool(failures),
        "repair_needed": bool(failures),
        "reason": reason,
        "operation": operation,
        "checked_access": True,
        "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
        "checked_devices": len(devices),
        "reissued_devices": len(results),
        "node_rebound": any(item["node_rebound"] for item in results),
        "failed_devices": len(failures),
    }


async def _run_soft_user_sync_operation(
    user_id: int,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> dict:
    user = await get_user_by_id(user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    before_snapshot = _user_audit_snapshot(user)

    access_expires_at = await get_access_expires_at(user_id)
    payments = await get_payment_records(user_id=user_id)
    devices = await get_user_vpn_clients(user_id)

    if access_expires_at is None:
        reason = MANUAL_REPAIR_NO_ACCESS
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await _emit_user_repair_alert(
            user=user,
            admin=admin,
            operation="sync_user_access",
            failures=[{"reason": reason}],
        )
        await create_audit_log(
            admin.id,
            "sync_user_access",
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": False,
                    "checked_devices": 0,
                    "operation_state": "skipped",
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {
            "sync_failed": True,
            "repair_needed": True,
            "reason": reason,
            "operation": "sync_user_access",
            "checked_access": False,
            "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
            "checked_devices": 0,
            "processed_devices": 0,
            "successful_devices": 0,
            "failed_devices": 0,
            "reissued_devices": 0,
            "node_rebound": False,
            "results": [],
            "auto_retry_attempted": False,
            "auto_retry_succeeded": False,
        }

    if not devices:
        reason = MANUAL_REPAIR_NO_DEVICES
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "skipped", reason)
        await _emit_user_repair_alert(
            user=user,
            admin=admin,
            operation="sync_user_access",
            failures=[{"reason": reason}],
        )
        await create_audit_log(
            admin.id,
            "sync_user_access",
            "user",
            str(user_id),
            json.dumps(
                {
                    "before": before_snapshot,
                    "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                    "reason": reason,
                    "checked_access": True,
                    "checked_devices": 0,
                    "operation_state": "skipped",
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        return {
            "sync_failed": True,
            "repair_needed": True,
            "reason": reason,
            "operation": "sync_user_access",
            "checked_access": True,
            "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
            "checked_devices": 0,
            "processed_devices": 0,
            "successful_devices": 0,
            "failed_devices": 0,
            "reissued_devices": 0,
            "node_rebound": False,
            "results": [],
            "auto_retry_attempted": False,
            "auto_retry_succeeded": False,
        }

    sync_result = await sync_user_clients_access(user_id)
    auto_retry_attempted = False
    auto_retry_succeeded = False
    if sync_result["sync_failed"]:
        auto_retry_attempted = True
        retry_result = await sync_user_clients_access(user_id)
        if not retry_result["sync_failed"]:
            sync_result = retry_result
            auto_retry_succeeded = True
        else:
            sync_result = retry_result

    if sync_result["sync_failed"]:
        reason = MANUAL_REPAIR_SYNC_FAILED
        failed_results = [item for item in sync_result.get("results", []) if item.get("status") != "success"]
        updated_user = await mark_vpn_repair_needed(user_id, reason)
        await create_vpn_repair_event(user_id, "failed", reason)
        await _emit_user_repair_alert(
            user=user,
            admin=admin,
            operation="sync_user_access",
            failures=failed_results or [{"reason": reason}],
        )
        await create_control_event(
            category="access",
            severity="WARNING",
            event_type="user_access_sync_failed",
            title="Синхронизация доступа завершилась с ошибками",
            message=(
                f"{_control_user_identity(user)}\n"
                f"Устройств обработано: <b>{sync_result.get('processed_devices', 0)}</b>\n"
                f"Ошибок: <b>{sync_result.get('failed_devices', 0)}</b>\n"
                f"Администратор: <b>{escape(admin.display_name)}</b>"
            ),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "processed_devices": sync_result.get("processed_devices", 0),
                "failed_devices": sync_result.get("failed_devices", 0),
                "auto_retry_attempted": auto_retry_attempted,
                "auto_retry_succeeded": auto_retry_succeeded,
                "admin_id": admin.id,
                "admin_name": admin.display_name,
            },
            dedupe_key=f"dashboard-user:{user.id}:sync:failed",
            cooldown_seconds=0,
        )
    else:
        reason = None
        updated_user = await clear_vpn_repair_needed(user_id)
        await create_control_event(
            category="access",
            severity="INFO",
            event_type="user_access_synced",
            title="Доступ пользователя синхронизирован",
            message=(
                f"{_control_user_identity(user)}\n"
                f"Устройств обработано: <b>{sync_result.get('processed_devices', 0)}</b>\n"
                f"Повторная попытка: <b>{'да' if auto_retry_attempted else 'нет'}</b>\n"
                f"Администратор: <b>{escape(admin.display_name)}</b>"
            ),
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "processed_devices": sync_result.get("processed_devices", 0),
                "failed_devices": sync_result.get("failed_devices", 0),
                "auto_retry_attempted": auto_retry_attempted,
                "auto_retry_succeeded": auto_retry_succeeded,
                "admin_id": admin.id,
                "admin_name": admin.display_name,
            },
            resolve_dedupe_key=f"dashboard-user:{user.id}:repair-needed",
            dedupe_key=f"dashboard-user:{user.id}:sync:success",
            cooldown_seconds=0,
        )

    await create_audit_log(
        admin.id,
        "sync_user_access",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _user_audit_snapshot(_user_audit_subject(updated_user, user)),
                "mode": "soft_sync",
                "devices": len(devices),
                "processed_devices": sync_result.get("processed_devices", 0),
                "successful_devices": sync_result.get("successful_devices", 0),
                "failed_devices": sync_result.get("failed_devices", 0),
                "auto_retry_attempted": auto_retry_attempted,
                "auto_retry_succeeded": auto_retry_succeeded,
                "reason": reason,
                "operation_state": "failed" if sync_result.get("sync_failed") else "success",
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "server_snapshots", "xui_summary")
    return {
        **sync_result,
        "sync_failed": bool(sync_result.get("sync_failed")),
        "repair_needed": bool(sync_result.get("sync_failed")),
        "reason": reason,
        "operation": "sync_user_access",
        "checked_access": True,
        "checked_tariff": any(row.payment_status == "confirmed" for row in payments),
        "checked_devices": len(devices),
        "reissued_devices": 0,
        "node_rebound": False,
        "auto_retry_attempted": auto_retry_attempted,
        "auto_retry_succeeded": auto_retry_succeeded,
    }


async def sync_user_access_state(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    return await _run_soft_user_sync_operation(user_id, admin, ip_address)


async def deep_repair_user_access(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    result = await _run_user_repair_operation(user_id, admin, ip_address, operation="deep_repair_user_access")
    if not result["sync_failed"]:
        post_sync_result = await sync_user_clients_access(user_id)
        if post_sync_result["sync_failed"]:
            result = {
                **result,
                "sync_failed": True,
                "repair_needed": True,
                "reason": MANUAL_REPAIR_SYNC_FAILED,
                "post_sync_result": post_sync_result,
                "failed_devices": max(int(result.get("failed_devices", 0)), int(post_sync_result["failed_devices"])),
            }
            await mark_vpn_repair_needed(user_id, MANUAL_REPAIR_SYNC_FAILED)
            await create_vpn_repair_event(user_id, "failed", MANUAL_REPAIR_SYNC_FAILED)
        else:
            result = {**result, "post_sync_result": post_sync_result}
    return result


async def create_device_for_user(
    user_id: int,
    device_name: str,
    device_type: str,
    protocol: str,
    country_code: str,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> dict:
    user = await get_user_by_id(user_id)
    if user is None:
        raise ValueError("User not found")

    access_expires_at = await get_access_expires_at(user_id)
    if access_expires_at is None:
        raise ValueError("User does not have active access")
    active_extra_slots = await get_active_device_slot_counts_for_users([user.id])
    setattr(user, "active_device_slot_addons", int(active_extra_slots.get(user.id, 0)))
    devices = await get_user_vpn_clients(user.id)
    if len(devices) >= get_device_limit_for_user(user):
        raise ValueError("User has reached the current device limit")

    region = build_region_snapshot(country_code)
    country_code = region["country_code"]
    country_name = region["country_name"]
    provision_request_id = current_or_new_trace_id(get_current_audit_request_id(), prefix="dev")
    capacity_error = await _dashboard_region_capacity_error(country_code)
    if capacity_error:
        raise ValueError(capacity_error)
    if not region_supports_protocol(country_code, protocol):
        raise ValueError("Этот регион пока не поддерживает выбранный протокол")
    created_device_id: int | None = None
    created_client_uuid: str | None = None
    created_email: str | None = None
    created_xui_client_id: str | None = None
    if protocol == "trojan":
        xui = XUIClient(country_code=country_code)
        try:
            if not await xui.login():
                raise ValueError("3x-ui login failed")
            inbound = await xui.find_inbound("trojan", 8443)
            if inbound is None:
                raise ValueError("Trojan inbound not found")
            email = f"dashboard_trojan_{user_id}_{uuid4().hex[:12]}"
            result = await xui.provision_trojan_client(
                user_id=user_id,
                email=email,
                access_expires_at=access_expires_at,
                save_callback=create_vpn_client,
            )
        finally:
            await xui.close()
        created_device_id = int(result["vpn_client_id"])
        created_client_uuid = str(result["client_uuid"])
        created_email = str(result["email"])
        created_xui_client_id = str(result["client_uuid"])
        connection_name = build_connection_name(country_code=country_code, country_name=country_name, email=result["email"])
        link = build_trojan_link(
            inbound=inbound,
            password=result["client_uuid"],
            email=result["email"],
            connection_name=connection_name,
            country_code=country_code,
        )
        metadata = {
            "device_name": device_name,
            "device_type": device_type,
            "protocol": protocol,
            "inbound_id": result["inbound_id"],
            "trojan_link": link,
            **region,
        }
        try:
            await update_vpn_client_metadata(result["vpn_client_id"], metadata)
        except Exception:
            cleaned = await _cleanup_dashboard_created_device_after_failure(
                device_id=created_device_id,
                protocol=protocol,
                client_uuid=created_client_uuid,
                email=created_email,
                xui_client_id=created_xui_client_id,
                metadata=metadata,
            )
            if not cleaned:
                await enqueue_finalize_created_device_job(
                    device_id=created_device_id,
                    user_id=int(user.id),
                    protocol=protocol,
                    client_uuid=created_client_uuid,
                    email=created_email,
                    xui_client_id=created_xui_client_id,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                    request_id=provision_request_id,
                )
                logger.warning(
                    "Dashboard Trojan create finalize queued device_id=%s user_id=%s request_id=%s",
                    created_device_id,
                    user_id,
                    provision_request_id,
                )
            raise
        created = result
    else:
        email = f"dashboard_{user_id}_{uuid4().hex[:12]}"
        provisioner = get_vless_provisioner(country_code, region.get("provider_type"))
        try:
            result = await provisioner.provision_vless_client(
                user_id=user_id,
                email=email,
                access_expires_at=access_expires_at,
                save_callback=create_vpn_client,
                country_code=country_code,
            )
        finally:
            await provisioner.close()
        created_device_id = int(result.vpn_client_id)
        created_client_uuid = str(result.client_uuid)
        created_email = str(result.email)
        metadata = {
            "device_name": device_name,
            "device_type": device_type,
            "protocol": protocol,
            **region,
            **result.metadata,
        }
        try:
            await update_vpn_client_metadata(result.vpn_client_id, metadata)
        except Exception:
            cleaned = await _cleanup_dashboard_created_device_after_failure(
                device_id=created_device_id,
                protocol=protocol,
                client_uuid=created_client_uuid,
                email=created_email,
                xui_client_id=created_xui_client_id,
                metadata=metadata,
            )
            if not cleaned:
                await enqueue_finalize_created_device_job(
                    device_id=created_device_id,
                    user_id=int(user.id),
                    protocol=protocol,
                    client_uuid=created_client_uuid,
                    email=created_email,
                    xui_client_id=created_xui_client_id,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                    request_id=provision_request_id,
                )
                logger.warning(
                    "Dashboard VLESS create finalize queued device_id=%s user_id=%s request_id=%s",
                    created_device_id,
                    user_id,
                    provision_request_id,
                )
            raise
        created = result

    created_snapshot = _vpn_client_audit_snapshot(
        SimpleNamespace(
            id=created_device_id,
            user_id=user_id,
            email=created_email,
            protocol=protocol,
            client_uuid=created_client_uuid,
            xui_client_id=created_xui_client_id,
        ),
        metadata_override=metadata,
    )
    await create_audit_log(
        admin.id,
        "create_device",
        "user",
        str(user_id),
        json.dumps({"before": None, "after": created_snapshot}, ensure_ascii=False),
        ip_address,
    )
    await create_control_event(
        category="access",
        severity="INFO",
        event_type="admin_device_created",
        title="Устройство создано через панель",
        message=(
            f"{_control_user_identity(user)}\n"
            f"Устройство: <b>{escape(device_name)}</b>\n"
            f"Протокол: <b>{escape(protocol)}</b>\n"
            f"Нода: <b>{escape(country_name)}</b>\n"
            f"Администратор: <b>{escape(admin.display_name)}</b>"
        ),
        entity_type="user",
        entity_id=str(user_id),
        payload={
            "user_id": user_id,
            "telegram_id": user.telegram_id,
            "device_name": device_name,
            "protocol": protocol,
            "country_code": country_code,
            "admin_id": admin.id,
            "admin_name": admin.display_name,
        },
        dedupe_key=f"dashboard-device:{user_id}:created:{protocol}:{country_code}:{device_name}",
        cooldown_seconds=0,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary", "server_snapshots")
    return created


async def delete_device_for_user(device_id: int, admin: DashboardAdmin, ip_address: str | None) -> None:
    async with async_session() as session:
        result = await session.execute(select(VpnClient).where(VpnClient.id == device_id))
        device = result.scalar_one_or_none()
        if device is None:
            return
        await session.refresh(device)

    metadata = _device_metadata(device)
    before_snapshot = _vpn_client_audit_snapshot(device, metadata_override=metadata)
    access_expires_at = await get_access_expires_at(device.user_id)
    await _delete_device_remote_state(device, metadata)

    try:
        async with async_session() as session:
            result = await session.execute(select(VpnClient).where(VpnClient.id == device_id))
            db_device = result.scalar_one_or_none()
            if db_device is not None:
                await session.delete(db_device)
                await session.commit()
    except Exception as exc:
        restored = await _restore_device_remote_state(device, metadata, access_expires_at)
        if not restored:
            await enqueue_restore_deleted_device_job(
                device=device,
                metadata=metadata,
                access_expires_at=access_expires_at,
                request_id=get_current_audit_request_id(),
            )
            raise ValueError(f"Удаление устройства прервано после снятия remote state: {exc}") from exc
        raise

    await create_audit_log(
        admin.id,
        "delete_device",
        "vpn_client",
        str(device_id),
        json.dumps({"before": before_snapshot, "after": None}, ensure_ascii=False),
        ip_address,
    )
    user = await get_user_by_id(device.user_id)
    await create_control_event(
        category="access",
        severity="INFO",
        event_type="device_deleted",
        title="Устройство удалено через панель",
        message=(
            f"{_control_user_identity(user)}\n"
            f"Протокол: <b>{escape(device.protocol)}</b>\n"
            f"Email: <code>{escape(device.email or '—')}</code>\n"
            f"Нода: <b>{escape(get_country_name(metadata.get('country_code')))}</b>\n"
            f"Администратор: <b>{escape(admin.display_name)}</b>"
        ),
        entity_type="vpn_client",
        entity_id=str(device_id),
        payload={
            "user_id": device.user_id,
            "telegram_id": getattr(user, "telegram_id", None),
            "device_id": device_id,
            "protocol": device.protocol,
            "country_code": metadata.get("country_code"),
            "admin_id": admin.id,
            "admin_name": admin.display_name,
        },
        dedupe_key=f"dashboard-device:{device_id}:deleted",
        cooldown_seconds=0,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary", "server_snapshots")


async def _cleanup_dashboard_created_device_after_failure(
    *,
    device_id: int,
    protocol: str,
    client_uuid: str,
    email: str,
    xui_client_id: str | None,
    metadata: dict,
) -> bool:
    device = await get_vpn_client_by_id(device_id)
    remote_device = device or SimpleNamespace(
        id=device_id,
        protocol=protocol,
        client_uuid=client_uuid,
        email=email,
        xui_client_id=xui_client_id,
    )

    try:
        await _delete_device_remote_state(remote_device, metadata)
    except Exception:
        logger.exception(
            "Failed to cleanup dashboard-created remote device state device_id=%s protocol=%s",
            device_id,
            protocol,
        )
        return False

    try:
        deleted = await delete_vpn_client_and_return(int(device_id))
    except Exception:
        logger.exception("Failed to cleanup dashboard-created local device row device_id=%s", device_id)
        return False

    return deleted is not None or await get_vpn_client_by_id(int(device_id)) is None


async def get_payment_records(
    user_id: int | None = None,
    *,
    search: str = "",
    status_filter: str = "all",
    method_filter: str = "all",
    issue_filter: str = "all",
) -> list[PaymentRecord]:
    normalized_search = str(search or "").strip().lower()
    normalized_status = str(status_filter or "all").strip().lower() or "all"
    normalized_method = str(method_filter or "all").strip().lower() or "all"
    normalized_issue = str(issue_filter or "all").strip().lower() or "all"
    async with async_session() as session:
        query = (
            select(PaymentRecord)
            .outerjoin(User, User.id == PaymentRecord.user_id)
            .where(
                or_(
                    PaymentRecord.user_id.is_(None),
                    PaymentRecord.user_id.in_(_real_user_ids_subquery()),
                )
            )
            .order_by(PaymentRecord.created_at.desc())
        )
        if user_id is not None:
            query = query.where(PaymentRecord.user_id == int(user_id))
        if normalized_status != "all":
            query = query.where(func.lower(func.coalesce(PaymentRecord.payment_status, "")) == normalized_status)
        if normalized_method != "all":
            query = query.where(func.lower(func.coalesce(PaymentRecord.payment_method, "")) == normalized_method)
        if normalized_issue == "review":
            query = query.where(PaymentRecord.payment_status == "awaiting_admin_review")
        elif normalized_issue == "waiting":
            query = query.where(PaymentRecord.payment_status.in_(("awaiting_user_payment", "pending")))
        elif normalized_issue == "problem":
            query = query.where(PaymentRecord.payment_status.in_(("rejected", "expired", "disputed", "error", "cancelled")))
        elif normalized_issue == "confirmed":
            query = query.where(PaymentRecord.payment_status == "confirmed")
        if normalized_search:
            pattern = f"%{normalized_search}%"
            query = query.where(
                or_(
                    cast(PaymentRecord.id, String).ilike(pattern),
                    func.lower(func.coalesce(User.username, "")).like(pattern),
                    cast(func.coalesce(User.telegram_id, ""), String).ilike(pattern),
                    func.lower(func.coalesce(PaymentRecord.tariff_code, "")).like(pattern),
                    func.lower(func.coalesce(PaymentRecord.payment_method, "")).like(pattern),
                    func.lower(func.coalesce(PaymentRecord.reference, "")).like(pattern),
                    func.lower(func.coalesce(PaymentRecord.note, "")).like(pattern),
                )
            )
        rows = list((await session.execute(query)).scalars().all())
    return rows


async def _finalize_confirmed_payment_access(record: PaymentRecord, *, payment_source: str) -> dict:
    if record.user_id is None:
        raise ValueError("Подтверждённый платёж не привязан к пользователю")

    payment_result = await finalize_payment_record_product(
        user_id=record.user_id,
        payment_source=payment_source,
        payment_record_id=record.id,
        tariff_code=record.tariff_code,
        payment_id=str(record.reference or record.external_payment_id or record.id),
    )
    if payment_result is None:
        raise ValueError("Платёж подтверждён, но доступ не удалось активировать")
    return payment_result


async def create_payment_record(
    user_id: int | None,
    payment_method: str,
    tariff_code: str,
    payment_status: str,
    reference: str,
    note: str,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> PaymentRecord | None:
    tariff = _get_runtime_tariff(tariff_code)
    if tariff is None:
        raise ValueError("Тариф не найден")

    if user_id is None or int(user_id) <= 0:
        raise ValueError("Для ручной заявки из дашборда нужен user_id")
    user_id = int(user_id)

    async with async_session() as session:
        user_exists = (await session.execute(select(User.id).where(User.id == user_id))).scalar_one_or_none()
    if user_exists is None:
        raise ValueError("Пользователь не найден")

    if payment_method in PROVIDER_SYNC_PAYMENT_METHODS:
        raise ValueError("Platega-счета не создаются из панели. Используй пользовательский flow и синхронизацию.")

    existing_intent = await get_open_payment_intent_for_user(
        user_id=user_id,
        tariff_code=tariff.code,
        list_price_amount=int(tariff.rub_price),
        duration_days=int(tariff.duration_days),
        product_type=payment_product_type(tariff_code=tariff.code),
    )
    if existing_intent is not None:
        raise ValueError(
            f"У пользователя уже есть открытый платёж #{existing_intent.id} "
            f"по этому продукту. Заверши его или дождись истечения."
        )

    normalized_status = str(payment_status or "").strip().lower()
    if normalized_status not in PAYMENT_STATUS_FLOW:
        raise ValueError("Некорректный статус платежа")
    if payment_method not in MANUAL_PAYMENT_METHODS and normalized_status == "confirmed":
        raise ValueError("Подтверждённый не-ручной платёж нельзя создавать сразу из панели. Сначала создай запись, затем подтверждай отдельно.")

    if payment_method in MANUAL_PAYMENT_METHODS:
        record = await create_manual_payment_record(
            user_id=user_id,
            tariff_code=tariff.code,
            payment_method=payment_method,
            amount=tariff.rub_price,
            currency="RUB",
            duration_days=tariff.duration_days,
            note=note,
            expires_at=utcnow() + timedelta(hours=max(int(getattr(config, "manual_payment_review_hours", 24) or 24), 1)),
            metadata={
                "tariff_title": tariff.title,
                "created_from": "dashboard",
            },
        )
        if normalized_status in {"awaiting_admin_review", "confirmed"}:
            record = await mark_manual_payment_record_submitted(
                record.id,
                reference=reference,
                note=note,
                metadata={"submitted_from": "dashboard"},
            )
        if normalized_status == "awaiting_admin_review" and record is not None:
            await notify_support_admins_about_manual_payment(record.id)
        if normalized_status == "confirmed" and record is not None:
            await confirm_manual_payment(
                record.id,
                reviewer_actor_id=f"dashboard:{admin.id}",
                reviewer_actor_name=admin.display_name,
            )
        if normalized_status in PAYMENT_PROBLEM_STATUSES and record is not None:
            record = await set_payment_record_status(record.id, normalized_status, admin, ip_address, reason=note or None)
    else:
        async with async_session() as session:
            record = PaymentRecord(
                user_id=user_id,
                created_by_admin_id=admin.id,
                payment_method=payment_method,
                payment_status=normalized_status,
                tariff_code=tariff.code,
                amount=tariff.rub_price,
                currency="RUB",
                duration_days=tariff.duration_days,
                note=note,
                reference=reference or None,
                confirmed_at=utcnow() if normalized_status == "confirmed" else None,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        if normalized_status == "confirmed":
            await _finalize_confirmed_payment_access(
                record,
                payment_source=f"dashboard_{payment_method}",
            )
            await sync_income_entry_for_payment_record(record.id)

    final_record = await get_payment_record_by_id(record.id)
    if final_record is not None:
        await safe_emit_analytics_event(
            event_name=EVENT_PAYMENT_STARTED,
            occurred_at=getattr(final_record, "created_at", None) or utcnow(),
            user_id=int(final_record.user_id) if getattr(final_record, "user_id", None) is not None else None,
            dedupe_key=f"payment-started:{int(final_record.id)}",
            payment_record_id=int(final_record.id),
            tariff_code=getattr(final_record, "tariff_code", None),
            payment_method=getattr(final_record, "payment_method", None),
            payload={
                "amount_rub": int(getattr(final_record, "amount", 0) or 0),
                "list_price_amount": int(getattr(final_record, "list_price_amount", 0) or getattr(final_record, "amount", 0) or 0),
                "product_type": payment_product_type(tariff_code=getattr(final_record, "tariff_code", None)),
                "created_from": "dashboard",
            },
        )
    await create_audit_log(
        admin.id,
        "create_payment_record",
        "payment_record",
        str(record.id),
        json.dumps(
            {
                "before": None,
                "after": _payment_record_audit_snapshot(final_record),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary")
    return final_record


async def confirm_payment_record(record_id: int, admin: DashboardAdmin, ip_address: str | None) -> None:
    record = await get_payment_record_by_id(record_id)
    if record is None:
        return
    before_snapshot = _payment_record_audit_snapshot(record)

    if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS:
        raise ValueError("Авто-платёж нельзя подтверждать вручную. Используй синхронизацию с провайдером.")

    if record.payment_method in MANUAL_PAYMENT_METHODS:
        if record.payment_status != "awaiting_admin_review":
            raise ValueError("Заявка уже обработана")
        result = await confirm_manual_payment(
            record_id,
            reviewer_actor_id=f"dashboard:{admin.id}",
            reviewer_actor_name=admin.display_name,
        )
        if result and result["record"].payment_status == "confirmed":
            await sync_income_entry_for_payment_record(record_id)
    else:
        async with async_session() as session:
            result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
            db_record = result.scalar_one_or_none()
            if db_record is None:
                return
            just_confirmed = False
            if db_record.payment_status != "confirmed":
                db_record.payment_status = "confirmed"
                db_record.confirmed_at = utcnow()
                just_confirmed = True
                await session.commit()
            payment_method = db_record.payment_method

        if just_confirmed:
            refreshed_record = await get_payment_record_by_id(record_id)
            if refreshed_record is None:
                raise ValueError("Платёж не найден после подтверждения")
            await _finalize_confirmed_payment_access(
                refreshed_record,
                payment_source=f"dashboard_{payment_method}",
            )
            await sync_income_entry_for_payment_record(record_id)
            record = refreshed_record

    final_record = await get_payment_record_by_id(record_id)
    await create_audit_log(
        admin.id,
        "confirm_payment_record",
        "payment_record",
        str(record_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _payment_record_audit_snapshot(final_record),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary")


async def reject_payment_record(record_id: int, admin: DashboardAdmin, ip_address: str | None, reason: str | None = None) -> None:
    record = await get_payment_record_by_id(record_id)
    if record is None or record.payment_method not in MANUAL_PAYMENT_METHODS:
        return
    if record.payment_status != "awaiting_admin_review":
        raise ValueError("Заявка уже обработана")
    before_snapshot = _payment_record_audit_snapshot(record)

    await reject_manual_payment(
        record_id,
        reviewer_actor_id=f"dashboard:{admin.id}",
        reviewer_actor_name=admin.display_name,
        reason=reason or "Отклонено через дашборд",
    )
    final_record = await get_payment_record_by_id(record_id)
    if final_record is not None:
        await safe_emit_analytics_event(
            event_name=EVENT_PAYMENT_FAILED,
            occurred_at=getattr(final_record, "reviewed_at", None) or getattr(final_record, "expires_at", None) or utcnow(),
            user_id=int(final_record.user_id) if getattr(final_record, "user_id", None) is not None else None,
            dedupe_key=f"payment-failed:{int(final_record.id)}:{str(final_record.payment_status or '').strip().lower()}",
            payment_record_id=int(final_record.id),
            tariff_code=getattr(final_record, "tariff_code", None),
            payment_method=getattr(final_record, "payment_method", None),
            payload={
                "payment_status": str(getattr(final_record, "payment_status", "") or "").strip().lower(),
                "product_type": payment_product_type(tariff_code=getattr(final_record, "tariff_code", None)),
                "review_source": "dashboard",
            },
        )
    await create_audit_log(
        admin.id,
        "reject_payment_record",
        "payment_record",
        str(record_id),
        json.dumps(
            {
                "reason": reason,
                "before": before_snapshot,
                "after": _payment_record_audit_snapshot(final_record),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary")


async def set_payment_record_status(
    record_id: int,
    payment_status: str,
    admin: DashboardAdmin,
    ip_address: str | None,
    *,
    reason: str | None = None,
) -> PaymentRecord | None:
    normalized_status = str(payment_status or "").strip().lower()
    if normalized_status not in PAYMENT_STATUS_FLOW:
        raise ValueError("Некорректный статус платежа")

    record = await get_payment_record_by_id(record_id)
    if record is None:
        return None
    before_snapshot = _payment_record_audit_snapshot(record)
    if record.payment_method in PROVIDER_SYNC_PAYMENT_METHODS:
        raise ValueError("Статус авто-платежа обновляется только через синхронизацию с провайдером")
    if record.payment_status == "confirmed" and normalized_status != "confirmed":
        raise ValueError("Подтверждённый платёж нельзя понижать по статусу без отдельного компенсационного сценария")

    if normalized_status == "confirmed":
        await confirm_payment_record(record_id, admin, ip_address)
        return await get_payment_record_by_id(record_id)
    if normalized_status == "rejected" and record.payment_method in MANUAL_PAYMENT_METHODS and record.payment_status == "awaiting_admin_review":
        await reject_payment_record(record_id, admin, ip_address, reason=reason)
        return await get_payment_record_by_id(record_id)

    async with async_session() as session:
        result = await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            return None
        previous_status = str(record.payment_status or "").strip().lower()
        if previous_status == "confirmed" and normalized_status != "confirmed":
            raise ValueError("Подтверждённый платёж нельзя понижать по статусу без отдельного компенсационного сценария")
        if payment_status_holds_balance(previous_status) and not payment_status_holds_balance(normalized_status) and normalized_status != "confirmed":
            await _release_reserved_balance_for_record(session, record, reason=f"payment_{normalized_status}")
        record.payment_status = normalized_status
        record.reviewed_by_actor_id = f"dashboard:{admin.id}"
        record.reviewed_by_actor_name = admin.display_name
        record.reviewed_at = utcnow()
        if normalized_status == "expired":
            record.expires_at = record.expires_at or utcnow()
        if normalized_status in PAYMENT_PROBLEM_STATUSES and reason:
            record.rejection_reason = reason
        await session.commit()
        await session.refresh(record)

    await create_audit_log(
        admin.id,
        "set_payment_record_status",
        "payment_record",
        str(record_id),
        json.dumps(
            {
                "reason": reason,
                "before": before_snapshot,
                "after": _payment_record_audit_snapshot(record),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    if record is not None and normalized_status in PAYMENT_PROBLEM_STATUSES:
        await safe_emit_analytics_event(
            event_name=EVENT_PAYMENT_FAILED,
            occurred_at=getattr(record, "reviewed_at", None) or getattr(record, "expires_at", None) or utcnow(),
            user_id=int(record.user_id) if getattr(record, "user_id", None) is not None else None,
            dedupe_key=f"payment-failed:{int(record.id)}:{normalized_status}",
            payment_record_id=int(record.id),
            tariff_code=getattr(record, "tariff_code", None),
            payment_method=getattr(record, "payment_method", None),
            payload={
                "payment_status": normalized_status,
                "product_type": payment_product_type(tariff_code=getattr(record, "tariff_code", None)),
                "review_source": "dashboard",
                "reason": reason,
            },
        )
    invalidate_runtime_cache("overview_metrics", "xui_summary")
    return record


async def sync_payment_record_with_provider(record_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    record = await get_payment_record_by_id(record_id)
    if record is None:
        raise ValueError("Платёж не найден")
    if record.payment_method not in PROVIDER_SYNC_PAYMENT_METHODS:
        raise ValueError("Синхронизация с провайдером доступна только для авто-платежей Platega")

    before_snapshot = _payment_record_audit_snapshot(record)
    result = await sync_platega_record_by_id(record_id, notify_user=False)
    refreshed = await get_payment_record_by_id(record_id)
    await create_audit_log(
        admin.id,
        "sync_payment_record_provider",
        "payment_record",
        str(record_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _payment_record_audit_snapshot(refreshed),
                "provider_status": result["provider_status"],
                "just_confirmed": result["just_confirmed"],
                "provider_sync_problem": result["provider_sync_problem"],
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary")
    return {
        "record": refreshed,
        "provider_status": result["provider_status"],
        "just_confirmed": result["just_confirmed"],
        "provider_sync_problem": result["provider_sync_problem"],
    }


def _can_send_manual_payment_reminder(record: PaymentRecord) -> bool:
    return (
        str(getattr(record, "payment_method", "") or "").strip().lower() == "sbp_manual"
        and str(getattr(record, "payment_status", "") or "").strip().lower() in MANUAL_PAYMENT_OPEN_STATUSES
    )


async def send_manual_payment_reminder(record_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    record = await get_payment_record_by_id(record_id)
    if record is None:
        raise ValueError("Платёж не найден")
    if not _can_send_manual_payment_reminder(record):
        raise ValueError("Напоминание доступно только для открытых заявок Ручная СБП.")
    if not record.tariff_code:
        raise ValueError("У заявки не указан тариф")
    if record.user_id is None:
        raise ValueError("У заявки не указан пользователь")

    user = await get_user_by_id(record.user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    if not user.telegram_id:
        raise ValueError("У пользователя не указан Telegram ID")

    tariff = get_tariff(record.tariff_code or "")
    metadata = payment_metadata(record)
    tariff_title = metadata.get("tariff_title") or (tariff.title if tariff else record.tariff_code or "Тариф")
    product_type = payment_product_type(metadata, tariff_code=record.tariff_code)
    delivered = await send_user_message(
        int(user.telegram_id),
        manual_payment_reminder_text(
            tariff_title=tariff_title,
            request_id=record.id,
            method_label=record.payment_method,
            payment_status=record.payment_status,
        ),
        reply_markup=(
            device_slot_manual_payment_reminder_keyboard(record.id)
            if product_type == DEVICE_SLOT_PRODUCT_TYPE
            else manual_payment_reminder_keyboard(record.id, record.tariff_code)
        ),
    )
    if not delivered:
        raise ValueError("Не удалось доставить напоминание пользователю в Telegram.")

    before_snapshot = _payment_record_audit_snapshot(record)
    await create_audit_log(
        admin.id,
        "send_payment_reminder",
        "payment_record",
        str(record_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": _payment_record_audit_snapshot(record),
                "payment_method": record.payment_method,
                "payment_status": record.payment_status,
                "user_id": record.user_id,
                "telegram_id": user.telegram_id,
                "delivered": True,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return {
        "record": await get_payment_record_by_id(record_id),
        "user_id": record.user_id,
        "telegram_id": user.telegram_id,
    }


async def delete_payment_record(record_id: int, admin: DashboardAdmin, ip_address: str | None) -> bool:
    async with async_session() as session:
        record = (await session.execute(select(PaymentRecord).where(PaymentRecord.id == record_id).with_for_update())).scalar_one_or_none()
        if record is None:
            return False
        before_snapshot = _payment_record_audit_snapshot(record)
        if str(record.payment_status or "").strip().lower() == "confirmed":
            raise ValueError("Подтверждённый платёж нельзя удалять без отдельного compensation flow")
        if payment_status_holds_balance(record.payment_status):
            await _release_reserved_balance_for_record(session, record, reason="payment_deleted")

        linked_finance_rows = list(
            (
                await session.execute(
                    select(FinanceEntry).where(
                        FinanceEntry.source_type == "payment_record",
                        FinanceEntry.source_id == str(record_id),
                    )
                )
            ).scalars().all()
        )
        for entry in linked_finance_rows:
            await session.delete(entry)

        snapshot = json.dumps(
            {
                "before": before_snapshot,
                "after": None,
                "finance_entries_removed": [entry.id for entry in linked_finance_rows],
            },
            ensure_ascii=False,
        )
        await session.delete(record)
        await session.commit()

    await create_audit_log(admin.id, "delete_payment_record", "payment_record", str(record_id), snapshot, ip_address)
    invalidate_runtime_cache("overview_metrics", "xui_summary")
    return True


def _serialize_payment_record(record: PaymentRecord, users: dict[int, User] | None = None) -> dict:
    metadata = _load_payment_metadata(record.metadata_json)
    user = users.get(record.user_id) if users and record.user_id is not None else None
    tariff_label = (
        metadata.get("product_title")
        or metadata.get("tariff_title")
        or record.tariff_code
    )
    payload = {
        "id": record.id,
        "user_id": record.user_id,
        "username": user.username if user and user.username else None,
        "telegram_id": user.telegram_id if user else None,
        "tariff_code": record.tariff_code,
        "tariff_label": tariff_label,
        "payment_method": record.payment_method,
        "payment_method_label": _payment_method_label(record.payment_method),
        "payment_status": record.payment_status,
        "payment_status_label": payment_status_label(record.payment_status),
        "amount": record.amount,
        "list_price_amount": getattr(record, "list_price_amount", 0) or record.amount,
        "balance_reserved_amount": getattr(record, "balance_reserved_amount", 0) or 0,
        "balance_applied_amount": getattr(record, "balance_applied_amount", 0) or 0,
        "currency": record.currency,
        "duration_days": record.duration_days,
        "reference": record.reference,
        "note": record.note,
        "metadata": metadata,
        "reviewed_by_actor_name": record.reviewed_by_actor_name,
        "reviewed_at": _format_datetime(record.reviewed_at),
        "reviewed_at_raw": record.reviewed_at,
        "rejection_reason": record.rejection_reason,
        "expires_at": _format_datetime(record.expires_at),
        "expires_at_raw": record.expires_at,
        "confirmed_at": _format_datetime(record.confirmed_at),
        "confirmed_at_raw": record.confirmed_at,
        "created_at": _format_datetime(record.created_at),
        "created_at_raw": record.created_at,
        "is_reviewable": record.payment_status == "awaiting_admin_review",
        "is_waiting_user": record.payment_status in {"awaiting_user_payment", "pending"},
        "can_send_reminder": _can_send_manual_payment_reminder(record),
    }
    payload.update(_provider_payment_fields(record, metadata))
    return payload


async def get_payment_focus(record_id: int | None) -> dict | None:
    if record_id is None:
        return None

    record = await get_payment_record_by_id(record_id)
    if record is None:
        return None

    users: dict[int, User] = {}
    if record.user_id is not None:
        user = await get_user_by_id(record.user_id)
        if user is not None:
            users[user.id] = user
    return _serialize_payment_record(record, users)


async def _get_active_dashboard_admins() -> list[DashboardAdmin]:
    async with async_session() as session:
        result = await session.execute(
            select(DashboardAdmin)
            .where(DashboardAdmin.is_active.is_(True))
            .order_by(DashboardAdmin.role.asc(), DashboardAdmin.display_name.asc(), DashboardAdmin.username.asc())
        )
        return list(result.scalars().all())


def _normalize_finance_status(status: str) -> str:
    normalized = (status or "draft").strip().lower()
    if normalized not in FINANCE_ENTRY_STATUSES:
        raise ValueError("Некорректный статус записи")
    return normalized


def _is_recurring_finance_entry(entry: FinanceEntry) -> bool:
    haystack = " ".join(filter(None, [entry.category, entry.related_server, entry.note or ""])).lower()
    return any(hint in haystack for hint in FINANCE_DOC_CATEGORY_HINTS)


def _serialize_finance_entry(entry: FinanceEntry, admin_map: dict[int, DashboardAdmin]) -> dict:
    created_by = admin_map.get(entry.created_by_admin_id) if entry.created_by_admin_id is not None else None
    counterparty = admin_map.get(entry.counterparty_admin_id) if entry.counterparty_admin_id is not None else None
    approved_by = admin_map.get(entry.approved_by_admin_id) if entry.approved_by_admin_id is not None else None
    return {
        "id": entry.id,
        "entry_type": entry.entry_type,
        "entry_type_label": finance_type_label(entry.entry_type),
        "status": entry.status,
        "status_label": finance_status_label(entry.status),
        "category": entry.category,
        "amount": entry.amount,
        "currency": entry.currency,
        "signed_amount": finance_signed_amount(entry.entry_type, entry.amount),
        "note": entry.note,
        "related_server": entry.related_server,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "period_key": entry.period_key or period_key_for(entry.occurred_at),
        "occurred_at": _format_datetime(entry.occurred_at),
        "occurred_at_raw": entry.occurred_at,
        "approved_at": _format_datetime(entry.approved_at),
        "approved_at_raw": entry.approved_at,
        "created_by_name": created_by.display_name if created_by else "—",
        "counterparty_name": counterparty.display_name if counterparty else "—",
        "approved_by_name": approved_by.display_name if approved_by else "—",
        "is_recurring": _is_recurring_finance_entry(entry),
    }


def _finance_income_counts_towards_summary(entry: FinanceEntry, payment_records_by_id: dict[str, PaymentRecord]) -> bool:
    if entry.entry_type != "income":
        return False
    if entry.source_type != "payment_record":
        return True
    payment_record = payment_records_by_id.get(str(entry.source_id or ""))
    if payment_record is None:
        return False
    return payment_method_counts_as_revenue(payment_record.payment_method)


async def _finance_payment_records_map(entries: list[FinanceEntry]) -> dict[str, PaymentRecord]:
    payment_ids: set[int] = set()
    for entry in entries:
        if entry.source_type != "payment_record":
            continue
        try:
            payment_id = int(entry.source_id or 0)
        except (TypeError, ValueError):
            continue
        if payment_id > 0:
            payment_ids.add(payment_id)
    if not payment_ids:
        return {}
    async with async_session() as session:
        rows = list(
            (
                await session.execute(select(PaymentRecord).where(PaymentRecord.id.in_(sorted(payment_ids))))
            ).scalars().all()
        )
        user_ids = sorted({int(item.user_id) for item in rows if getattr(item, "user_id", None) is not None})
        users = {}
        if user_ids:
            users = {
                item.id: item
                for item in (
                    await session.execute(select(User).where(User.id.in_(user_ids)))
                ).scalars().all()
            }
    return {str(item.id): item for item in rows if not _is_synthetic_payment_record(item, users)}


def _finance_summary_from_entries(entries: list[FinanceEntry], payment_records_by_id: dict[str, PaymentRecord] | None = None) -> dict:
    payment_records = payment_records_by_id or {}
    posted_entries = [entry for entry in entries if entry.status == "posted"]
    income = sum(entry.amount for entry in posted_entries if _finance_income_counts_towards_summary(entry, payment_records))
    expense = sum(entry.amount for entry in posted_entries if finance_is_expense(entry.entry_type))
    salaries = sum(entry.amount for entry in posted_entries if entry.entry_type == "salary")
    settlements = sum(entry.amount for entry in posted_entries if entry.entry_type == "settlement")
    transfers = sum(entry.amount for entry in posted_entries if entry.entry_type == "transfer")
    recurring = sum(entry.amount for entry in posted_entries if _is_recurring_finance_entry(entry))
    draft_count = sum(1 for entry in entries if entry.status == "draft")
    cancelled_count = sum(1 for entry in entries if entry.status == "cancelled")
    net = income - expense
    return {
        "income": income,
        "expense": expense,
        "salaries": salaries,
        "settlements": settlements,
        "transfers": transfers,
        "recurring": recurring,
        "net": net,
        "draft_count": draft_count,
        "cancelled_count": cancelled_count,
        "count": len(entries),
    }


async def get_finance_entries(
    limit: int = 30,
    *,
    period_key: str | None = None,
    entry_type: str = "all",
    status: str = "all",
    admin_id: int | None = None,
    category: str = "",
) -> list[dict]:
    async with async_session() as session:
        query = select(FinanceEntry).order_by(FinanceEntry.occurred_at.desc(), FinanceEntry.created_at.desc())
        if period_key:
            query = query.where(FinanceEntry.period_key == period_key)
        if entry_type != "all":
            query = query.where(FinanceEntry.entry_type == entry_type)
        if status != "all":
            query = query.where(FinanceEntry.status == status)
        if admin_id is not None:
            query = query.where(FinanceEntry.created_by_admin_id == admin_id)
        if category.strip():
            lowered = category.strip().lower()
            rows = list((await session.execute(query)).scalars().all())
            admin_rows = await _get_active_dashboard_admins()
            admin_map = {row.id: row for row in admin_rows}
            filtered = [
                _serialize_finance_entry(entry, admin_map)
                for entry in rows
                if lowered in " ".join(filter(None, [entry.category, entry.related_server, entry.note or ""])).lower()
            ]
            return filtered[:limit]

        rows = list((await session.execute(query.limit(limit))).scalars().all())

    admin_rows = await _get_active_dashboard_admins()
    admin_map = {row.id: row for row in admin_rows}
    return [_serialize_finance_entry(entry, admin_map) for entry in rows]


async def get_finance_summary(period_key: str | None = None) -> dict:
    async with async_session() as session:
        query = select(FinanceEntry)
        if period_key:
            query = query.where(FinanceEntry.period_key == period_key)
        rows = list((await session.execute(query)).scalars().all())
    payment_records = await _finance_payment_records_map(rows)
    summary = _finance_summary_from_entries(rows, payment_records)
    recent = await get_finance_entries(limit=8, period_key=period_key)
    summary["recent"] = recent
    return summary


async def get_finance_dashboard(
    period_key: str | None = None,
    entry_type: str = "all",
    status: str = "all",
    admin_id: int | None = None,
    category: str = "",
    selected_entry_id: int | None = None,
) -> dict:
    async with async_session() as session:
        rows = list(
            (
                await session.execute(select(FinanceEntry).order_by(FinanceEntry.occurred_at.desc(), FinanceEntry.created_at.desc()))
            ).scalars().all()
        )
    admins = await _get_active_dashboard_admins()
    admin_map = {row.id: row for row in admins}
    periods = sorted({entry.period_key or period_key_for(entry.occurred_at) for entry in rows}, reverse=True)
    effective_period = period_key or (periods[0] if periods else period_key_for(utcnow()))

    filtered_rows = []
    category_query = category.strip().lower()
    for entry in rows:
        entry_period = entry.period_key or period_key_for(entry.occurred_at)
        if effective_period and entry_period != effective_period:
            continue
        if entry_type != "all" and entry.entry_type != entry_type:
            continue
        if status != "all" and entry.status != status:
            continue
        if admin_id is not None and entry.created_by_admin_id != admin_id:
            continue
        haystack = " ".join(filter(None, [entry.category, entry.related_server, entry.note or ""])).lower()
        if category_query and category_query not in haystack:
            continue
        filtered_rows.append(entry)

    serialized_rows = [_serialize_finance_entry(entry, admin_map) for entry in filtered_rows]
    selected_entry = None
    if selected_entry_id is not None:
        selected_entry = next((item for item in serialized_rows if item["id"] == selected_entry_id), None)

    if selected_entry is None and serialized_rows:
        selected_entry = serialized_rows[0]

    recurring_rows = [item for item in serialized_rows if item["is_recurring"]][:6]
    payment_records = await _finance_payment_records_map(filtered_rows)
    return {
        "summary": _finance_summary_from_entries(filtered_rows, payment_records),
        "entries": serialized_rows,
        "selected_entry": selected_entry,
        "periods": periods or [effective_period],
        "admins": [
            {
                "id": row.id,
                "display_name": row.display_name,
                "role_name": ROLE_NAMES.get(row.role, row.role),
            }
            for row in admins
        ],
        "filters": {
            "period_key": effective_period,
            "entry_type": entry_type,
            "status": status,
            "admin_id": admin_id,
            "category": category,
        },
        "recurring_rows": recurring_rows,
    }


async def create_finance_entry(
    entry_type: str,
    category: str,
    amount: int,
    note: str,
    related_server: str,
    admin: DashboardAdmin,
    ip_address: str | None,
    *,
    status: str = "draft",
    counterparty_admin_id: int | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    normalized_type = entry_type.strip().lower()
    if normalized_type not in FINANCE_ENTRY_TYPES:
        raise ValueError("Некорректный тип транзакции")
    normalized_status = _normalize_finance_status(status)
    normalized_amount = max(0, int(amount))
    if normalized_amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")

    is_owner = str(getattr(admin, "role", "") or "").strip() == "owner"
    approved_by_admin_id = admin.id if normalized_status == "posted" and is_owner else None
    approved_at = utcnow() if approved_by_admin_id is not None else None
    if not is_owner and normalized_status == "posted":
        normalized_status = "draft"
        approved_by_admin_id = None
        approved_at = None

    async with async_session() as session:
        entry = FinanceEntry(
            created_by_admin_id=admin.id,
            counterparty_admin_id=counterparty_admin_id,
            entry_type=normalized_type,
            category=category.strip() or "operations",
            amount=normalized_amount,
            currency="RUB",
            note=note.strip() or None,
            related_server=related_server.strip() or None,
            status=normalized_status,
            source_type=source_type.strip() if source_type else None,
            source_id=source_id.strip() if source_id else None,
            approved_by_admin_id=approved_by_admin_id,
            approved_at=approved_at,
            period_key=period_key_for(occurred_at),
            occurred_at=occurred_at or utcnow(),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

    await create_audit_log(
        admin.id,
        "create_finance_entry",
        "finance_entry",
        str(entry.id),
        json.dumps(
            {
                "before": None,
                "after": _finance_entry_audit_snapshot(entry),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    admin_map = {row.id: row for row in await _get_active_dashboard_admins()}
    return _serialize_finance_entry(entry, admin_map)


async def approve_finance_entry(entry_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict | None:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        entry = (await session.execute(select(FinanceEntry).where(FinanceEntry.id == entry_id))).scalar_one_or_none()
        if entry is None:
            return None
        before_snapshot = _finance_entry_audit_snapshot(entry)
        entry.status = "posted"
        entry.approved_by_admin_id = admin.id
        entry.approved_at = utcnow()
        if not entry.period_key:
            entry.period_key = period_key_for(entry.occurred_at)
        await session.commit()
        await session.refresh(entry)
    await create_audit_log(
        admin.id,
        "approve_finance_entry",
        "finance_entry",
        str(entry_id),
        json.dumps({"before": before_snapshot, "after": _finance_entry_audit_snapshot(entry)}, ensure_ascii=False),
        ip_address,
    )
    admin_map = {row.id: row for row in await _get_active_dashboard_admins()}
    return _serialize_finance_entry(entry, admin_map)


async def cancel_finance_entry(entry_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict | None:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        entry = (await session.execute(select(FinanceEntry).where(FinanceEntry.id == entry_id))).scalar_one_or_none()
        if entry is None:
            return None
        before_snapshot = _finance_entry_audit_snapshot(entry)
        entry.status = "cancelled"
        entry.approved_by_admin_id = admin.id
        entry.approved_at = utcnow()
        await session.commit()
        await session.refresh(entry)
    await create_audit_log(
        admin.id,
        "cancel_finance_entry",
        "finance_entry",
        str(entry_id),
        json.dumps({"before": before_snapshot, "after": _finance_entry_audit_snapshot(entry)}, ensure_ascii=False),
        ip_address,
    )
    admin_map = {row.id: row for row in await _get_active_dashboard_admins()}
    return _serialize_finance_entry(entry, admin_map)


async def delete_finance_entry(entry_id: int, admin: DashboardAdmin, ip_address: str | None) -> bool:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        entry = (await session.execute(select(FinanceEntry).where(FinanceEntry.id == entry_id))).scalar_one_or_none()
        if entry is None:
            return False
        before_snapshot = _finance_entry_audit_snapshot(entry)
        await session.delete(entry)
        await session.commit()
    await create_audit_log(
        admin.id,
        "delete_finance_entry",
        "finance_entry",
        str(entry_id),
        json.dumps({"before": before_snapshot, "after": None}, ensure_ascii=False),
        ip_address,
    )
    return True


async def generate_finance_report(period_key: str | None, admin: DashboardAdmin | None, ip_address: str | None) -> dict:
    finance = await get_finance_dashboard(period_key=period_key)
    summary = finance["summary"]
    selected_period = finance["filters"]["period_key"]
    report_lines = [
        "# Финансовый отчёт Amonora",
        "",
        f"- Период: `{selected_period}`",
        f"- Сформирован: `{_format_datetime(utcnow())}`",
        "",
        "## Сводка",
        "",
        f"- Доходы: `{summary['income']} ₽`",
        f"- Расходы: `{summary['expense']} ₽`",
        f"- Зарплаты: `{summary['salaries']} ₽`",
        f"- Взаиморасчёты: `{summary['settlements']} ₽`",
        f"- Переводы: `{summary['transfers']} ₽`",
        f"- Регулярные затраты: `{summary['recurring']} ₽`",
        f"- Чистый результат: `{summary['net']} ₽`",
        f"- Черновики: `{summary['draft_count']}`",
        f"- Отменённые записи: `{summary['cancelled_count']}`",
        "",
        "## Журнал",
        "",
        "| ID | Тип | Статус | Категория | Сумма | Инициатор | Комментарий |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in finance["entries"][:50]:
        report_lines.append(
            f"| {item['id']} | {item['entry_type_label']} | {item['status_label']} | "
            f"{item['category']} | {item['signed_amount']} {item['currency']} | "
            f"{item['created_by_name']} | {(item['note'] or '—').replace('|', '/')} |"
        )

    report_lines.extend(
        [
            "",
            "## Риски и замечания",
            "",
            f"- Непроведённых записей: `{summary['draft_count']}`",
            f"- Регулярные расходы в периоде: `{summary['recurring']} ₽`",
            "- Для управленческого учёта это операционный ledger, а не бухгалтерский контур.",
            "",
        ]
    )

    GENERATED_DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_ROOT / FINANCE_REPORT_SLUG
    before_exists = report_path.exists()
    before_size = report_path.stat().st_size if before_exists else 0
    report_path.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    invalidate_docs_cache(FINANCE_REPORT_SLUG)

    if admin is not None:
        await create_audit_log(
            admin.id,
            "generate_finance_report",
            "documentation",
            FINANCE_REPORT_SLUG,
            json.dumps(
                {
                    "before": {
                        "path": str(report_path),
                        "exists": before_exists,
                        "size_bytes": before_size,
                    },
                    "after": {
                        "path": str(report_path),
                        "period_key": selected_period,
                        "size_bytes": report_path.stat().st_size,
                    },
                },
                ensure_ascii=False,
            ),
            ip_address,
        )

    return {
        "slug": FINANCE_REPORT_SLUG,
        "path": str(report_path),
        "period_key": selected_period,
    }


async def _create_user_deletion_job(
    *,
    user,
    admin: DashboardAdmin,
    ip_address: str | None,
    before_snapshot: dict,
    device_ids: list[int],
) -> UserDeletionJob:
    async with async_session() as session:
        now_point = utcnow()
        job = UserDeletionJob(
            user_id=int(getattr(user, "id", 0) or 0) or None,
            telegram_id=int(getattr(user, "telegram_id", 0) or 0) or None,
            admin_id=int(getattr(admin, "id", 0) or 0) or None,
            status="running",
            stage="prepared",
            ip_address=str(ip_address or "").strip()[:64] or None,
            payload_json=json.dumps(
                {
                    "before": before_snapshot,
                    "device_ids": [int(item) for item in device_ids],
                },
                ensure_ascii=False,
            ),
            created_at=now_point,
            updated_at=now_point,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def _update_user_deletion_job(
    job_id: int,
    *,
    stage: str,
    status: str | None = None,
    payload_merge: dict | None = None,
    last_error: str | None = None,
    completed: bool = False,
) -> UserDeletionJob | None:
    async with async_session() as session:
        job = (
            await session.execute(select(UserDeletionJob).where(UserDeletionJob.id == job_id).with_for_update())
        ).scalar_one_or_none()
        if job is None:
            return None

        payload: dict = {}
        raw_payload = str(getattr(job, "payload_json", "") or "").strip()
        if raw_payload:
            try:
                loaded = json.loads(raw_payload)
            except json.JSONDecodeError:
                loaded = {}
            if isinstance(loaded, dict):
                payload = loaded
        if payload_merge:
            payload.update(payload_merge)

        now_point = utcnow()
        job.stage = str(stage or "").strip() or job.stage
        if status:
            job.status = str(status).strip() or job.status
        job.payload_json = json.dumps(payload, ensure_ascii=False)
        job.last_error = str(last_error or "").strip()[:4000] or None
        job.updated_at = now_point
        if completed:
            job.completed_at = now_point
        await session.commit()
        await session.refresh(job)
        return job


async def delete_user_with_access(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> bool:
    user = await get_user_by_id(user_id)
    if user is None:
        return False
    if user.telegram_id in set(config.admin_ids) | set(config.support_admin_ids):
        raise ValueError("Нельзя удалить администратора через дашборд")

    before_snapshot = _user_audit_snapshot(user)
    devices = await get_user_vpn_clients(user_id)
    device_snapshots = [(device, _device_metadata(device)) for device in devices]
    device_ids = [int(device.id) for device in devices if getattr(device, "id", None) is not None]
    access_expires_at = get_access_expires_at_from_user(user)
    deletion_job = await _create_user_deletion_job(
        user=user,
        admin=admin,
        ip_address=ip_address,
        before_snapshot=before_snapshot,
        device_ids=device_ids,
    )
    deleted_remote_devices: list[tuple[VpnClient, dict]] = []
    try:
        for device, metadata in device_snapshots:
            await _delete_device_remote_state(device, metadata)
            deleted_remote_devices.append((device, metadata))
        await _update_user_deletion_job(
            int(deletion_job.id),
            stage="remote_deleted",
            payload_merge={
                "deleted_remote_device_ids": [int(getattr(device, "id", 0) or 0) for device, _ in deleted_remote_devices],
            },
        )

        support_user_keys = {int(user_id)}
        if getattr(user, "telegram_id", None) is not None:
            support_user_keys.add(int(user.telegram_id))

        async with async_session() as session:
            payment_ids = list(
                (
                    await session.execute(select(PaymentRecord.id).where(PaymentRecord.user_id == user_id))
                ).scalars().all()
            )
            support_ticket_ids = list(
                (
                    await session.execute(
                        select(SupportTicket.id).where(SupportTicket.user_id.in_(sorted(support_user_keys)))
                    )
                ).scalars().all()
            )
            payment_source_ids = [str(int(record_id)) for record_id in payment_ids]

            await session.execute(
                update(User).where(User.referred_by_user_id == user_id).values(referred_by_user_id=None)
            )
            await session.execute(
                update(ControlBroadcastDelivery)
                .where(ControlBroadcastDelivery.user_id == user_id)
                .values(user_id=None)
            )
            await session.execute(
                update(ControlTriggerDeliveryLog)
                .where(ControlTriggerDeliveryLog.user_id == user_id)
                .values(user_id=None)
            )
            await session.execute(
                delete(ReferralReward).where(
                    (ReferralReward.referrer_user_id == user_id) | (ReferralReward.invited_user_id == user_id)
                )
            )
            await session.execute(
                delete(Referral).where((Referral.referrer_user_id == user_id) | (Referral.invited_user_id == user_id))
            )
            if support_ticket_ids:
                await session.execute(
                    delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id.in_(support_ticket_ids))
                )
            await session.execute(delete(SupportTicket).where(SupportTicket.user_id.in_(sorted(support_user_keys))))
            await session.execute(delete(UserBalanceEvent).where(UserBalanceEvent.user_id == user_id))
            await session.execute(delete(VpnRepairEvent).where(VpnRepairEvent.user_id == user_id))
            await session.execute(delete(ChannelPostTouch).where(ChannelPostTouch.user_id == user_id))
            await session.execute(delete(DeviceSlotEntitlement).where(DeviceSlotEntitlement.user_id == user_id))
            if device_ids:
                await session.execute(delete(VpnClientActivation).where(VpnClientActivation.vpn_client_id.in_(device_ids)))
            if payment_source_ids:
                await session.execute(
                    delete(FinanceEntry).where(
                        FinanceEntry.source_type == "payment_record",
                        FinanceEntry.source_id.in_(payment_source_ids),
                    )
                )
            await _update_user_deletion_job(
                int(deletion_job.id),
                stage="local_delete_committing",
                payload_merge={
                    "payment_records_deleted": len(payment_ids),
                    "support_tickets_deleted": len(support_ticket_ids),
                    "device_count": len(device_ids),
                },
            )
            await session.execute(delete(PaymentRecord).where(PaymentRecord.user_id == user_id))
            await session.execute(delete(VpnClient).where(VpnClient.user_id == user_id))
            # Delete the user row only after the separate job-update transaction finishes.
            # Otherwise PostgreSQL can lock the same user_deletion_jobs row via ON DELETE SET NULL
            # and the helper's FOR UPDATE waits on itself until the request times out.
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await _update_user_deletion_job(
            int(deletion_job.id),
            stage="completed",
            status="completed",
            payload_merge={
                "payment_records_deleted": len(payment_ids),
                "support_tickets_deleted": len(support_ticket_ids),
                "devices_deleted": len(device_ids),
            },
            completed=True,
        )
    except Exception as exc:
        rollback_failures: list[int] = []
        queued_restore_device_ids: list[int] = []
        for device, metadata in reversed(deleted_remote_devices):
            restored = await _restore_device_remote_state(device, metadata, access_expires_at)
            if not restored:
                rollback_failures.append(int(getattr(device, "id", 0) or 0))
                await enqueue_restore_deleted_device_job(
                    device=device,
                    metadata=metadata,
                    access_expires_at=access_expires_at,
                    request_id=get_current_audit_request_id(),
                )
                queued_restore_device_ids.append(int(getattr(device, "id", 0) or 0))
        await _update_user_deletion_job(
            int(deletion_job.id),
            stage="failed",
            status="failed",
            payload_merge={
                "deleted_remote_device_ids": [int(getattr(device, "id", 0) or 0) for device, _ in deleted_remote_devices],
                "rollback_failures": rollback_failures,
                "queued_restore_device_ids": queued_restore_device_ids,
            },
            last_error=str(exc),
        )
        if rollback_failures:
            raise ValueError(
                f"Удаление пользователя прервано после снятия remote state; restore failed for devices: {rollback_failures}"
            ) from exc
        if deleted_remote_devices:
            raise ValueError("Удаление пользователя прервано, remote state устройств восстановлен.") from exc
        raise ValueError("Удаление пользователя прервано до завершения локального удаления.") from exc

    await create_audit_log(
        admin.id,
        "delete_user",
        "user",
        str(user_id),
        json.dumps(
            {
                "before": before_snapshot,
                "after": None,
                "devices_deleted": len(device_ids),
                "payment_records_deleted": len(payment_ids),
                "support_tickets_deleted": len(support_ticket_ids),
                "deletion_job_id": int(deletion_job.id),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics", "xui_summary", "server_snapshots")
    return True


async def get_support_tickets(filter_mode: str = "queue", search: str = "", admin: DashboardAdmin | None = None) -> list[dict]:
    telegram_id = admin.telegram_id if admin else None
    query = search.strip().lower()
    source_filter = filter_mode
    if query and filter_mode == "queue":
        source_filter = "all"
    return await list_tickets(
        source_filter,
        admin_id=telegram_id,
        search=query,
        exclude_synthetic=True,
    )


async def get_support_dashboard_counts(admin: DashboardAdmin | None = None) -> dict[str, int]:
    telegram_id = admin.telegram_id if admin else None
    return await get_ticket_counts(admin_id=telegram_id, exclude_synthetic=True)


async def get_support_admin_choices(current_admin: DashboardAdmin | None = None) -> list[dict]:
    current_telegram_id = current_admin.telegram_id if current_admin else None
    async with async_session() as session:
        result = await session.execute(
            select(DashboardAdmin)
            .where(DashboardAdmin.is_active.is_(True), DashboardAdmin.telegram_id.is_not(None))
            .order_by(DashboardAdmin.role.asc(), DashboardAdmin.display_name.asc(), DashboardAdmin.username.asc())
        )
        admins = list(result.scalars().all())

    choices: list[dict] = []
    seen: set[int] = set()
    for row in admins:
        if row.telegram_id is None:
            continue
        seen.add(row.telegram_id)
        choices.append(
            {
                "telegram_id": row.telegram_id,
                "display_name": row.display_name,
                "role_name": ROLE_NAMES.get(row.role, row.role),
                "is_current": row.telegram_id == current_telegram_id,
            }
        )

    for admin_id in config.support_admin_ids:
        if admin_id in seen:
            continue
        choices.append(
            {
                "telegram_id": admin_id,
                "display_name": f"Admin {admin_id}",
                "role_name": "Поддержка",
                "is_current": admin_id == current_telegram_id,
            }
        )

    return choices


async def get_support_ticket_detail(user_id: int) -> dict | None:
    ticket = await get_ticket(user_id)
    if ticket is None:
        return None
    history = _decorate_support_history(user_id, await get_history(user_id))
    if user_id > 2_147_483_647:
        user = await get_user_by_telegram_id(user_id)
    else:
        user = await get_user_by_id(user_id)
        if user is None:
            user = await get_user_by_telegram_id(user_id)
    if user is not None and _is_synthetic_user(user):
        return None
    payments = await list_payment_records_db(user_id=user.id) if user is not None else []
    payment_rows = [_serialize_payment_record(payment, {user.id: user} if user else None) for payment in payments[:8]]
    return {
        "ticket": ticket,
        "history": history,
        "user": user,
        "payments": payment_rows,
        "payment_counts": {
            "total": len(payments),
            "reviewable": sum(1 for row in payments if row.payment_status == "awaiting_admin_review"),
            "confirmed": sum(1 for row in payments if row.payment_status == "confirmed"),
        },
    }


async def assign_support_ticket_dashboard(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict | None:
    if admin.telegram_id is None:
        raise ValueError("У администратора не указан Telegram ID")
    before_ticket = await get_ticket(user_id)
    ticket = await assign_ticket(user_id, admin.telegram_id, admin.display_name)
    if ticket is not None:
        await create_audit_log(
            admin.id,
            "assign_support_ticket",
            "support_ticket",
            str(user_id),
            json.dumps(
                {
                    "before": _support_ticket_audit_snapshot(before_ticket),
                    "after": _support_ticket_audit_snapshot(ticket),
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        invalidate_runtime_cache("overview_metrics")
    return ticket


async def transfer_support_ticket_dashboard(
    user_id: int,
    to_admin_telegram_id: int,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> dict | None:
    admin_choices = await get_support_admin_choices()
    target = next((item for item in admin_choices if item["telegram_id"] == to_admin_telegram_id), None)
    if target is None:
        raise ValueError("Нельзя передать тикет неактивному или неизвестному администратору")
    target_name = target["display_name"]
    before_ticket = await get_ticket(user_id)
    ticket = await transfer_ticket(user_id, to_admin_telegram_id, target_name)
    if ticket is not None:
        await create_audit_log(
            admin.id,
            "transfer_support_ticket",
            "support_ticket",
            str(user_id),
            json.dumps(
                {
                    "to_admin_telegram_id": to_admin_telegram_id,
                    "to_admin_name": target_name,
                    "before": _support_ticket_audit_snapshot(before_ticket),
                    "after": _support_ticket_audit_snapshot(ticket),
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
        invalidate_runtime_cache("overview_metrics")
    return ticket


async def send_support_reply(user_id: int, text: str, admin: DashboardAdmin, ip_address: str | None) -> None:
    if not config.support_bot_token:
        raise ValueError("Support bot token is not configured")
    before_ticket = await get_ticket(user_id)
    if before_ticket is None:
        raise ValueError("Тикет не найден")

    bot = Bot(config.support_bot_token)
    try:
        try:
            await bot.send_message(
                user_id,
                f"💬 <b>Ответ поддержки Amonora</b>\n\n{escape(text)}",
                parse_mode="HTML",
            )
        except TelegramForbiddenError as exc:
            logger.warning("Support reply delivery blocked for user_id=%s: %s", user_id, exc)
            raise ValueError("Не удалось доставить ответ: пользователь заблокировал support-бота.") from exc
        except TelegramBadRequest as exc:
            logger.warning("Support reply delivery rejected by Telegram for user_id=%s: %s", user_id, exc)
            raise ValueError(f"Telegram не принял ответ пользователю: {exc}") from exc
    finally:
        await bot.session.close()

    try:
        saved = await register_admin_reply(
            user_id,
            admin.telegram_id or admin.id,
            admin.display_name,
            text,
            "text",
        )
    except Exception:
        logger.exception("Support reply delivery succeeded but local history save failed for user_id=%s", user_id)
        try:
            await create_control_event(
                category="support",
                severity="CRITICAL",
                event_type="support_reply_history_failed",
                title="Ответ поддержки не сохранён в истории",
                message=(
                    f"Пользователь: <code>{user_id}</code>\n"
                    f"Администратор: <b>{escape(admin.display_name)}</b>\n"
                    "Сообщение было доставлено в Telegram, но запись в support history завершилась ошибкой."
                ),
                entity_type="support_ticket",
                entity_id=str(user_id),
                payload={"user_id": user_id, "admin_id": admin.id},
                dedupe_key=f"support-reply-history-failed:{user_id}",
                cooldown_seconds=0,
            )
        except Exception:
            logger.exception("Failed to create control event for support history save failure user_id=%s", user_id)
        raise ValueError("Ответ доставлен, но не был сохранён в support history")
    if saved is None:
        logger.error("Support reply delivery succeeded but no local ticket was saved for user_id=%s", user_id)
        raise ValueError("Ответ доставлен, но не был сохранён в support history")
    after_ticket = await get_ticket(user_id)
    await create_audit_log(
        admin.id,
        "support_reply",
        "support_ticket",
        str(user_id),
        json.dumps(
            {
                "before": _support_ticket_audit_snapshot(before_ticket),
                "after": _support_ticket_audit_snapshot(after_ticket),
                "message_preview": text[:180],
                "message_length": len(text),
                "delivered": True,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics")


async def get_support_attachment_content(ticket_user_id: int, message_id: int) -> dict | None:
    attachment = await get_message_attachment(ticket_user_id, message_id)
    if attachment is None:
        return None
    if not config.support_bot_token:
        raise ValueError("Support bot token is not configured")

    bot = Bot(config.support_bot_token)
    try:
        telegram_file = await bot.get_file(attachment["file_id"])
    except (TelegramBadRequest, TelegramForbiddenError):
        return None
    finally:
        await bot.session.close()

    file_path = getattr(telegram_file, "file_path", None)
    if not file_path:
        return None

    file_url = f"https://api.telegram.org/file/bot{config.support_bot_token}/{file_path}"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(file_url)
            response.raise_for_status()
            content = response.content
    except httpx.HTTPError:
        return None

    filename = attachment.get("name") or posixpath.basename(file_path) or f"support-{message_id}"
    media_type = (
        attachment.get("mime_type")
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    return {
        "filename": filename,
        "media_type": media_type,
        "content": content,
    }


async def _notify_support_user_closed(user_id: int) -> bool:
    if not config.support_bot_token:
        return False

    bot = Bot(config.support_bot_token)
    try:
        await bot.send_message(
            user_id,
            (
                "🔒 <b>Обращение закрыто</b>\n\n"
                "Если вопрос ещё остался, просто напиши в этот бот снова — обращение откроется заново."
            ),
            parse_mode="HTML",
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    finally:
        await bot.session.close()


async def close_support_ticket(user_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict:
    before_ticket = await get_ticket(user_id)
    await close_ticket(user_id)
    after_ticket = await get_ticket(user_id)
    user_notified = await _notify_support_user_closed(user_id)
    admin_label = escape(getattr(admin, "display_name", None) or f"Admin {getattr(admin, 'id', '—')}")
    try:
        await create_control_event(
            category="support",
            severity="INFO",
            event_type="support_ticket_closed",
            title="Обращение закрыто",
            message=(
                f"User ID: <code>{user_id}</code>\n"
                f"Закрыл: <b>{admin_label}</b>\n"
                f"Пользователь уведомлён: <b>{'да' if user_notified else 'нет'}</b>"
            ),
            entity_type="support_ticket",
            entity_id=str(user_id),
            dedupe_key=f"support-ticket:{user_id}:closed",
            resolve_dedupe_key=f"support-ticket:{user_id}:open",
            cooldown_seconds=0,
        )
    except Exception as exc:
        logger.warning("Failed to emit support close control event user_id=%s: %s", user_id, exc)
    await create_audit_log(
        admin.id,
        "close_support_ticket",
        "support_ticket",
        str(user_id),
        json.dumps(
            {
                "user_notified": user_notified,
                "before": _support_ticket_audit_snapshot(before_ticket),
                "after": _support_ticket_audit_snapshot(after_ticket),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("overview_metrics")
    return {"closed": True, "user_notified": user_notified}


async def get_server_snapshot_by_id(server_id: int) -> dict | None:
    snapshots = await get_server_snapshots()
    for item in snapshots:
        if int(item.get("id") or 0) == int(server_id):
            return item
    return None


async def get_service_statuses(force_refresh: bool = False) -> dict:
    if not force_refresh:
        cached = _runtime_cache_get("service_statuses")
        if cached is not None:
            return cached

    statuses = {}
    for key, service_name in SERVICE_STATUS_MAP.items():
        code, output = await _system_command("systemctl", "is-active", service_name)
        statuses[key] = {
            "label": service_name,
            "status": output.strip() if code == 0 else (output.strip() or "unknown"),
        }
    _runtime_cache_set("service_statuses", statuses)
    return copy.deepcopy(statuses)


async def service_logs(service_name: str, lines: int = 30) -> str:
    _, output = await _system_command("journalctl", "-u", service_name, "-n", str(lines), "--no-pager")
    return output or "No logs available."


async def service_action(action: str, service_name: str, admin: DashboardAdmin, ip_address: str | None) -> dict:
    if service_name not in SERVICE_MAP.values():
        raise ValueError("Unsupported service")
    normalized_action = str(action or "").strip().lower()
    status_before = None
    if normalized_action in {"status", "refresh"}:
        status_code, status_output = await _system_command("systemctl", "is-active", service_name)
        current_status = status_output.strip() if status_code == 0 else (status_output.strip() or "unknown")
        await create_audit_log(
            admin.id,
            "service_status_refresh",
            "service",
            service_name,
            json.dumps({"before": None, "after": {"status": current_status}}, ensure_ascii=False),
            ip_address,
        )
        invalidate_runtime_cache("service_statuses", "overview_metrics")
        return {"service_name": service_name, "action": "refresh", "status": current_status}

    if normalized_action not in {"start", "stop", "restart"}:
        raise ValueError("Unsupported action")
    before_code, before_output = await _system_command("systemctl", "is-active", service_name)
    status_before = before_output.strip() if before_code == 0 else (before_output.strip() or "unknown")
    await _system_command("systemctl", normalized_action, service_name)
    status_code, status_output = await _system_command("systemctl", "is-active", service_name)
    current_status = status_output.strip() if status_code == 0 else (status_output.strip() or "unknown")
    await create_audit_log(
        admin.id,
        "service_action",
        "service",
        service_name,
        json.dumps(
            {
                "action": normalized_action,
                "before_status": status_before,
                "after_status": current_status,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("service_statuses", "overview_metrics")
    return {"service_name": service_name, "action": normalized_action, "status": current_status}


def read_masked_env() -> list[tuple[str, str]]:
    if not ENV_PATH.exists():
        return []
    rows = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows.append((key, _mask_env_value(key, value)))
    return rows


def _is_dangerous_env_key(key: str) -> bool:
    normalized = str(key or "").strip().upper()
    if not normalized:
        return True
    if any(token in normalized for token in DANGEROUS_ENV_NAME_TOKENS):
        return True
    return any(normalized.startswith(prefix) for prefix in DANGEROUS_ENV_PREFIXES)


def _is_allowed_mutable_env_key(key: str) -> bool:
    normalized = str(key or "").strip().upper()
    if not normalized:
        return False
    return normalized in MUTABLE_ENV_ALLOWLIST


def _atomic_write_env_lines(lines: list[str]) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ENV_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).strip() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, ENV_PATH)


async def _apply_env_runtime_changes(affected_services: list[str]) -> dict:
    applied_services: list[str] = []
    verified_services: list[str] = []
    failed_services: list[dict[str, str]] = []

    for service_name in affected_services:
        try:
            await _system_command("systemctl", "restart", service_name)
            applied_services.append(service_name)
            status_code, status_output = await _system_command("systemctl", "is-active", service_name)
            current_status = status_output.strip() if status_code == 0 else (status_output.strip() or "unknown")
            if current_status != "active":
                raise ValueError(current_status or "unknown")
            verified_services.append(service_name)
        except Exception as exc:
            failed_services.append(
                {
                    "service_name": service_name,
                    "error": str(exc) or "restart_failed",
                }
            )

    return {
        "applied_services": applied_services,
        "verified_services": verified_services,
        "failed_services": failed_services,
        "applied_ok": not failed_services,
    }


def _format_env_runtime_failures(failed_services: list[dict[str, str]]) -> str:
    details = [
        f"{item.get('service_name') or 'unknown'} ({item.get('error') or 'restart_failed'})"
        for item in failed_services
    ]
    return ", ".join(details) if details else "unknown failure"


async def _rollback_env_runtime_changes(previous_lines: list[str], affected_services: list[str]) -> dict:
    _atomic_write_env_lines(previous_lines)
    return await _apply_env_runtime_changes(affected_services)


async def update_env_value(
    key: str,
    value: str,
    admin: DashboardAdmin,
    ip_address: str | None,
    *,
    apply_runtime: bool = False,
) -> dict:
    normalized_key = key.strip()
    if not normalized_key or "=" in normalized_key or " " in normalized_key or "\n" in normalized_key or "\r" in normalized_key:
        raise ValueError("Некорректное имя переменной")
    if not _is_allowed_mutable_env_key(normalized_key):
        raise ValueError("Эту переменную нельзя менять через панель")
    if _is_dangerous_env_key(normalized_key):
        raise ValueError("Эту переменную нельзя менять через панель")

    normalized_value = value.strip()
    if "\n" in normalized_value or "\r" in normalized_value:
        raise ValueError("Значение переменной не должно содержать перевод строки")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    updated = []
    found = False
    previous_value = None

    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            updated.append(line)
            continue
        env_key, _ = line.split("=", 1)
        if env_key == normalized_key:
            previous_value = line.split("=", 1)[1]
            updated.append(f"{normalized_key}={normalized_value}")
            found = True
        else:
            updated.append(line)

    if not found:
        updated.append(f"{normalized_key}={normalized_value}")

    affected_services = [
        "amonora-bot.service",
        "amonora-dashboard.service",
        "amonora-landing.service",
        "amonora-support-bot.service",
        "amonora-control-bot.service",
    ]

    # Dashboard-side env writes always go through staged apply+verify to avoid
    # disk/runtime split-brain where `.env` is new but services still run on old state.
    _atomic_write_env_lines(updated)
    runtime_apply_result = await _apply_env_runtime_changes(affected_services)
    restart_required = False
    audit_payload = {
        "before": _mask_env_value(normalized_key, previous_value or ""),
        "after": _mask_env_value(normalized_key, normalized_value),
        "restart_required": restart_required,
        "requested_apply_runtime": bool(apply_runtime),
        "effective_apply_runtime": True,
        "runtime_apply": runtime_apply_result,
    }
    if not runtime_apply_result.get("applied_ok"):
        rollback_result = await _rollback_env_runtime_changes(lines, affected_services)
        runtime_apply_result = {
            **runtime_apply_result,
            "rolled_back": True,
            "rollback_ok": bool(rollback_result.get("applied_ok")),
            "rollback_verified_services": rollback_result.get("verified_services", []),
            "rollback_failed_services": rollback_result.get("failed_services", []),
            "runtime_state": "rolled_back" if rollback_result.get("applied_ok") else "rollback_failed",
        }
        audit_payload["runtime_apply"] = runtime_apply_result
        await create_audit_log(
            admin.id,
            "update_env_value",
            "env",
            normalized_key,
            json.dumps(audit_payload, ensure_ascii=False),
            ip_address,
        )
        failure_summary = _format_env_runtime_failures(runtime_apply_result.get("failed_services", []))
        if rollback_result.get("applied_ok"):
            raise ValueError(f"Не удалось применить .env; изменения откатили: {failure_summary}")
        rollback_summary = _format_env_runtime_failures(runtime_apply_result.get("rollback_failed_services", []))
        raise RuntimeError(
            "Не удалось применить .env и откат не сошёлся: "
            f"{failure_summary}; rollback: {rollback_summary}"
        )
    await create_audit_log(
        admin.id,
        "update_env_value",
        "env",
        normalized_key,
        json.dumps(audit_payload, ensure_ascii=False),
        ip_address,
    )
    return {
        "key": normalized_key,
        "restart_required": restart_required,
        "affected_services": affected_services,
        "runtime_apply": {
            **runtime_apply_result,
            "rolled_back": False,
            "rollback_ok": None,
            "rollback_verified_services": [],
            "rollback_failed_services": [],
            "runtime_state": "applied",
        },
    }


async def update_tariffs(values: dict[str, int], admin: DashboardAdmin, ip_address: str | None) -> None:
    if not ENV_PATH.exists():
        return

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    before_map: dict[str, str | None] = {}
    updated = []
    keys = set(values.keys())
    existing = set()
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            updated.append(line)
            continue
        key, current_value = line.split("=", 1)
        if key in values:
            before_map[key] = current_value
            updated.append(f"{key}={values[key]}")
            existing.add(key)
        else:
            updated.append(line)
    for key in keys - existing:
        before_map.setdefault(key, None)
        updated.append(f"{key}={values[key]}")

    _atomic_write_env_lines(updated)
    affected_services = [
        "amonora-bot.service",
        "amonora-landing.service",
    ]
    await create_audit_log(
        admin.id,
        "update_tariffs",
        "env",
        None,
        json.dumps(
            {
                "before": _selected_env_snapshot(values, before_map),
                "after": {key: values[key] for key in sorted(values)},
                "affected_services": affected_services,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    await _system_command("systemctl", "restart", "amonora-bot.service")
    await _system_command("systemctl", "restart", "amonora-landing.service")
    invalidate_runtime_cache("overview_metrics")


async def get_managed_servers() -> list[ManagedServer]:
    async with async_session() as session:
        return list((await session.execute(select(ManagedServer).order_by(ManagedServer.created_at.asc()))).scalars().all())


async def create_managed_server(
    name: str,
    host: str,
    public_ip: str,
    country_code: str,
    country_name: str,
    provider: str,
    status: str,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> None:
    async with async_session() as session:
        server = ManagedServer(
            name=name,
            host=host,
            public_ip=public_ip,
            country_code=country_code,
            country_name=country_name,
            provider=provider,
            status=status,
            is_local=False,
            xui_url=get_country_panel_url(country_code),
        )
        session.add(server)
        await session.commit()
        await session.refresh(server)

    await create_audit_log(
        admin.id,
        "create_managed_server",
        "server",
        str(server.id),
        json.dumps({"before": None, "after": _managed_server_audit_snapshot(server)}, ensure_ascii=False),
        ip_address,
    )
    invalidate_runtime_cache("server_snapshots", "overview_metrics")


async def update_server_status(server_id: int, status: str, admin: DashboardAdmin, ip_address: str | None) -> None:
    before_snapshot: dict[str, object] | None = None
    async with async_session() as session:
        result = await session.execute(select(ManagedServer).where(ManagedServer.id == server_id))
        server = result.scalar_one_or_none()
        if server is None:
            return
        before_snapshot = _managed_server_audit_snapshot(server)
        server.status = status
        server.updated_at = utcnow()
        await session.commit()
        await session.refresh(server)
    await create_audit_log(
        admin.id,
        "update_server_status",
        "server",
        str(server_id),
        json.dumps({"before": before_snapshot, "after": _managed_server_audit_snapshot(server)}, ensure_ascii=False),
        ip_address,
    )
    invalidate_runtime_cache("server_snapshots", "overview_metrics")


def _server_runtime_service_name(server: ManagedServer) -> str:
    return get_country_runtime_service_name(server.country_code)


async def server_health_check(server_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict | None:
    async with async_session() as session:
        server_row = (await session.execute(select(ManagedServer).where(ManagedServer.id == server_id))).scalar_one_or_none()
    snapshots = await get_server_snapshots(force_refresh=True)
    snapshot = next((item for item in snapshots if int(item.get("id") or 0) == int(server_id)), None)
    if snapshot is not None:
        await create_audit_log(
            admin.id,
            "server_health_check",
            "server",
            str(server_id),
            json.dumps(
                {
                    "before": _managed_server_audit_snapshot(server_row),
                    "after": snapshot,
                },
                ensure_ascii=False,
            ),
            ip_address,
        )
    invalidate_runtime_cache("server_snapshots", "overview_metrics")
    return snapshot


async def restart_server_runtime(server_id: int, admin: DashboardAdmin, ip_address: str | None) -> dict | None:
    async with async_session() as session:
        server = (await session.execute(select(ManagedServer).where(ManagedServer.id == server_id))).scalar_one_or_none()
    if server is None:
        return None

    runtime_service = _server_runtime_service_name(server)
    if runtime_service == "retired":
        raise ValueError("Эстония больше не является продуктовой нодой. Перезапуск runtime для неё отключён.")
    before_snapshot = await get_server_snapshot_by_id(server_id)
    if server.is_local:
        services_to_restart = {
            runtime_service,
            server.bot_service_name,
            server.support_bot_service_name,
            server.dashboard_service_name,
        }
        for service_name in services_to_restart:
            if service_name and service_name != "n/a":
                await _system_command("systemctl", "restart", service_name)
    else:
        restart_code, restart_output = await _ssh_command(server.public_ip or server.host, "systemctl", "restart", runtime_service)
        if restart_code != 0:
            raise ValueError(restart_output or f"Не удалось перезапустить {runtime_service}")
        check_code, check_output = await _ssh_command(server.public_ip or server.host, "systemctl", "is-active", runtime_service)
        if check_code != 0 or (check_output.strip() and check_output.strip() != "active"):
            raise ValueError(check_output or f"{runtime_service} не активен после restart")

    await create_audit_log(
        admin.id,
        "restart_server_runtime",
        "server",
        str(server_id),
        json.dumps(
            {
                "runtime_service": runtime_service,
                "before": before_snapshot,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("server_snapshots", "overview_metrics", "xui_summary")
    after_snapshot = await server_health_check(server_id, admin, ip_address)
    await create_audit_log(
        admin.id,
        "restart_server_runtime_result",
        "server",
        str(server_id),
        json.dumps(
            {
                "runtime_service": runtime_service,
                "before": before_snapshot,
                "after": after_snapshot,
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    return after_snapshot


async def migrate_server_region_access(
    server_id: int,
    target_server_id: int,
    admin: DashboardAdmin,
    ip_address: str | None,
) -> dict:
    async with async_session() as session:
        source = (await session.execute(select(ManagedServer).where(ManagedServer.id == server_id))).scalar_one_or_none()
        target = (await session.execute(select(ManagedServer).where(ManagedServer.id == target_server_id))).scalar_one_or_none()
        devices = list((await session.execute(select(VpnClient))).scalars().all())

    if source is None or target is None:
        raise ValueError("Сервер для миграции не найден")
    if source.id == target.id:
        raise ValueError("Нужно выбрать другую целевую ноду")

    source_country = normalize_country_code(source.country_code)
    target_country = normalize_country_code(target.country_code)
    if source_country == target_country:
        raise ValueError("Миграция между одинаковыми регионами не требуется")

    migrated = 0
    skipped = 0
    unbound_devices = 0
    failures: list[dict] = []
    for device in devices:
        metadata = _device_metadata(device)
        explicit_server_id = metadata.get("managed_server_id") or metadata.get("server_id")
        if explicit_server_id is not None and int(explicit_server_id) != int(server_id):
            continue
        if explicit_server_id is None:
            if normalize_country_code(metadata.get("country_code")) != source_country:
                continue
            skipped += 1
            unbound_devices += 1
            failures.append({"device_id": device.id, "error": "missing_source_server_binding"})
            continue
        if not region_supports_protocol(target_country, device.protocol):
            skipped += 1
            failures.append({"device_id": device.id, "error": "protocol_not_supported_in_target"})
            continue
        try:
            await _reissue_existing_device(device, target_country_code=target_country)
            migrated += 1
        except Exception as exc:
            failures.append({"device_id": device.id, "error": str(exc)})

    if failures:
        await create_control_event(
            category="nodes",
            severity="WARNING",
            event_type="server_region_migration_failed",
            title="Миграция устройств завершилась с ошибками",
            message=(
                f"Source: <b>{escape(source.name)}</b>\n"
                f"Target: <b>{escape(target.name)}</b>\n"
                f"Migrated: <b>{migrated}</b>\n"
                f"Skipped: <b>{skipped}</b>\n"
                f"Failed: <b>{len(failures)}</b>"
            ),
            entity_type="server",
            entity_id=str(server_id),
            payload={
                "source_server_id": server_id,
                "target_server_id": target_server_id,
                "migrated": migrated,
                "skipped": skipped,
                "unbound_devices": unbound_devices,
                "failed": len(failures),
            },
            dedupe_key=f"server-migration:{server_id}:{target_server_id}:failed",
            cooldown_seconds=0,
        )
    elif migrated > 0 and skipped == 0:
        await update_server_status(server_id, "maintenance", admin, ip_address)
    await create_audit_log(
        admin.id,
        "migrate_server_region_access",
        "server",
        str(server_id),
        json.dumps(
            {
                "before": _managed_server_audit_snapshot(source),
                "target": _managed_server_audit_snapshot(target),
                "target_server_id": target_server_id,
                "migrated": migrated,
                "skipped": skipped,
                "unbound_devices": unbound_devices,
                "failed": len(failures),
            },
            ensure_ascii=False,
        ),
        ip_address,
    )
    invalidate_runtime_cache("server_snapshots", "overview_metrics", "xui_summary")
    return {
        "source_server_id": server_id,
        "target_server_id": target_server_id,
        "migrated_devices": migrated,
        "skipped_devices": skipped,
        "unbound_devices": unbound_devices,
        "failed_devices": len(failures),
        "requires_manual_review": bool(failures or skipped),
        "failures": failures[:10],
    }


async def run_server_action(
    server_id: int,
    action: str,
    admin: DashboardAdmin,
    ip_address: str | None,
    *,
    target_server_id: int | None = None,
) -> dict:
    normalized_action = str(action or "").strip().lower()
    if normalized_action in {"health_check", "refresh"}:
        snapshot = await server_health_check(server_id, admin, ip_address)
        if snapshot is None:
            raise ValueError("Сервер не найден")
        return {"action": "refresh" if normalized_action == "refresh" else "health_check", "snapshot": snapshot}
    if normalized_action == "restart":
        snapshot = await restart_server_runtime(server_id, admin, ip_address)
        if snapshot is None:
            raise ValueError("Сервер не найден")
        return {"action": normalized_action, "snapshot": snapshot}
    if normalized_action == "maintenance":
        await update_server_status(server_id, "maintenance", admin, ip_address)
        snapshot = await server_health_check(server_id, admin, ip_address)
        return {"action": normalized_action, "snapshot": snapshot}
    if normalized_action == "migrate":
        if target_server_id is None:
            raise ValueError("Нужно выбрать целевую ноду")
        migration = await migrate_server_region_access(server_id, target_server_id, admin, ip_address)
        snapshot = await server_health_check(server_id, admin, ip_address)
        return {"action": normalized_action, "snapshot": snapshot, "migration": migration}
    raise ValueError("Unsupported server action")


def _service_pills_for_server(base: dict, server: ManagedServer) -> list[dict]:
    runtime_type = get_country_runtime_type(server.country_code)
    runtime_label = RUNTIME_LABELS.get(runtime_type, "Access runtime")
    if runtime_type == "retired":
        runtime_status = "retired"
        clients_value = "n/a"
    elif runtime_type == "xray_core":
        runtime_status = base.get("xray_service_status", "n/a")
        clients_value = str(base.get("xui_clients", "n/a"))
    elif runtime_type == "amneziawg":
        runtime_status = base.get("awg_service_status", "n/a")
        clients_value = "n/a"
    else:
        runtime_status = base.get("xui_service_status", "n/a")
        clients_value = str(base.get("xui_clients", "n/a"))
    if server.is_local:
        pills = [
            {"label": runtime_label, "value": runtime_status},
            {"label": "Clients", "value": clients_value},
            {"label": "Main bot", "value": base.get("bot_status", "n/a")},
            {"label": "Support", "value": base.get("support_bot_status", "n/a")},
            {"label": "Dashboard", "value": base.get("dashboard_status", "n/a")},
        ]
        if runtime_type == "xui":
            pills.insert(1, {"label": "Panel", "value": base.get("xui_status", "n/a")})
        return pills

    pills = [
        {"label": runtime_label, "value": runtime_status},
        {"label": "Clients", "value": clients_value},
        {"label": "SSH", "value": base.get("ssh_status", "n/a")},
        {"label": "Docker", "value": base.get("docker_status", "n/a")},
        {"label": "Host", "value": base.get("host_status", "n/a")},
    ]
    if runtime_type == "xui":
        pills.insert(1, {"label": "Panel", "value": base.get("xui_status", "n/a")})
    return pills


def _status_message_for_state(state: str) -> str:
    return {
        "critical": "Нужна быстрая реакция: один из ресурсов близок к пределу.",
        "warning": "Есть повышенная нагрузка, стоит присмотреть за сервером.",
        "healthy": "Сервер работает стабильно и без перегруза.",
    }.get(state, "Метрики недоступны.")


def _runtime_service_health_state(snapshot: dict) -> str:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type == "retired":
        return "healthy"
    if runtime_type == "amneziawg":
        runtime_state = str(snapshot.get("awg_service_status") or "").strip().lower()
    elif runtime_type == "xray_core":
        runtime_state = str(snapshot.get("xray_service_status") or "").strip().lower()
    else:
        runtime_state = str(snapshot.get("xui_service_status") or "").strip().lower()
        if runtime_state in {"", "unknown"}:
            runtime_state = str(snapshot.get("xui_status") or "").strip().lower()

    if runtime_state in {"failed", "inactive", "error", "dead", "not-found"}:
        return "critical"
    if runtime_state in {"unknown"}:
        return "warning"
    if runtime_state in {"active", "ok", "n/a"}:
        return "healthy"
    return "unknown"


def _provider_runtime_status_value(snapshot: dict) -> str:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type == "retired":
        return "retired"
    if runtime_type == "amneziawg":
        runtime_state = str(snapshot.get("awg_service_status") or "").strip().lower()
        return runtime_state or "unknown"
    if runtime_type == "xray_core":
        return str(snapshot.get("xray_service_status") or "").strip().lower()
    runtime_state = str(snapshot.get("xui_service_status") or "").strip().lower()
    if runtime_state in {"", "unknown"}:
        runtime_state = str(snapshot.get("xui_status") or "").strip().lower()
    return runtime_state


def _provider_control_plane_status_value(snapshot: dict) -> str:
    runtime_type = get_country_runtime_type(snapshot.get("country_code"))
    if runtime_type != "xui":
        return _provider_runtime_status_value(snapshot)
    runtime_state = str(snapshot.get("xui_status") or "").strip().lower()
    if runtime_state in {"", "unknown"}:
        runtime_state = str(snapshot.get("xui_service_status") or "").strip().lower()
    return runtime_state


def _runtime_control_plane_healthy(snapshot: dict) -> bool:
    return _provider_control_plane_status_value(snapshot) in {"active", "ok"}


def _has_remote_monitoring_gap(snapshot: dict) -> bool:
    host_status = str(snapshot.get("host_status") or "").strip().lower()
    ssh_status = str(snapshot.get("ssh_status") or "").strip().lower()
    transport_failed = host_status not in {"", "ok"} or ssh_status not in {"", "active", "ok"}
    return transport_failed and _runtime_control_plane_healthy(snapshot)


def _recalculate_snapshot_health(base: dict) -> None:
    base["cpu_state"] = _health_state(base.get("cpu_percent"))
    base["memory_state"] = _health_state(base.get("memory_used_percent"))
    base["disk_state"] = _health_state(base.get("disk_used_percent"))
    base["ping_state"] = _ping_state(base.get("ping_ms"), base.get("country_code"))
    base["runtime_state"] = _runtime_service_health_state(base)
    base["overall_state"] = _merge_health_states(
        base["cpu_state"],
        base["memory_state"],
        base["disk_state"],
        base["ping_state"],
        base["runtime_state"],
    )
    base["warning_count"] = sum(
        1
        for state in (
            base["cpu_state"],
            base["memory_state"],
            base["disk_state"],
            base["ping_state"],
            base["runtime_state"],
        )
        if state in {"warning", "critical"}
    )
    base["status_message"] = (
        "SSH-мониторинг ноды недоступен, но runtime доступа продолжает отвечать."
        if _has_remote_monitoring_gap(base)
        else _status_message_for_state(base["overall_state"])
    )


def _build_remote_metrics_script(public_host: str) -> str:
    return f"""
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

def cpu_percent():
    def read():
        with open('/proc/stat', 'r', encoding='utf-8') as fh:
            parts = fh.readline().split()[1:]
        values = [int(item) for item in parts]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total
    samples = []
    for _ in range(3):
        idle_1, total_1 = read()
        time.sleep(0.15)
        idle_2, total_2 = read()
        total_delta = max(total_2 - total_1, 1)
        idle_delta = idle_2 - idle_1
        samples.append(max(0.0, (1 - (idle_delta / total_delta)) * 100))
    return round(sum(samples) / len(samples), 1)

def memory():
    values = {{}}
    with open('/proc/meminfo', 'r', encoding='utf-8') as fh:
        for line in fh:
            key, raw_value = line.split(':', 1)
            values[key] = int(raw_value.strip().split()[0])
    total = values.get('MemTotal', 0)
    available = values.get('MemAvailable', values.get('MemFree', 0))
    used = max(total - available, 0)
    percent = round((used / total) * 100, 1) if total else 0.0
    return percent, round(total / 1024 / 1024, 2)

def uptime_label():
    seconds = int(float(Path('/proc/uptime').read_text(encoding='utf-8').split()[0]))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{{days}}d {{hours:02d}}:{{minutes:02d}}:{{seconds:02d}}"
    return f"{{hours:02d}}:{{minutes:02d}}:{{seconds:02d}}"

def net_bytes():
    rx_total = 0
    tx_total = 0
    with open('/proc/net/dev', 'r', encoding='utf-8') as fh:
        for line in fh.readlines()[2:]:
            if ':' not in line:
                continue
            iface, payload = line.split(':', 1)
            iface = iface.strip()
            if iface == 'lo':
                continue
            parts = payload.split()
            rx_total += int(parts[0])
            tx_total += int(parts[8])
    return tx_total, rx_total

def service_state(name, fallback_process=None):
    result = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
    value = (result.stdout or result.stderr).strip()
    value = value or 'unknown'
    if fallback_process and value in {{'inactive', 'unknown', 'not-found', 'failed'}}:
        probe = subprocess.run(['pgrep', '-f', fallback_process], capture_output=True, text=True)
        if probe.returncode == 0:
            return 'active'
    return value

disk = shutil.disk_usage('/')
mem_percent, mem_total_gb = memory()
tx_bytes, rx_bytes = net_bytes()
data = {{
    'hostname': subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip(),
    'platform': platform.platform(),
    'cpu_percent': cpu_percent(),
    'cpu_count': os.cpu_count() or 0,
    'memory_used_percent': mem_percent,
    'memory_total_gb': mem_total_gb,
    'disk_used_percent': round((disk.used / disk.total) * 100, 1) if disk.total else 0.0,
    'disk_total_gb': round(disk.total / (1024 ** 3), 2) if disk.total else 0.0,
    'tx_bytes': tx_bytes,
    'rx_bytes': rx_bytes,
    'uptime': uptime_label(),
    'load': ' / '.join(f'{{value:.2f}}' for value in os.getloadavg()),
    'ping_target': {public_host!r},
    'host_status': 'ok',
    'ssh_status': service_state('ssh', 'sshd'),
    'docker_status': service_state('docker', 'dockerd'),
    'xui_service_status': service_state('3x-ui', '/app/x-ui'),
    'xray_service_status': service_state('xray', 'xray'),
    'awg_service_status': service_state('awg-quick@awg0', 'awg-quick'),
}}
print(json.dumps(data, ensure_ascii=False))
""".strip()


async def remote_server_snapshot(sample_key: str, server: ManagedServer) -> dict:
    code, output = await _ssh_command(server.public_ip or server.host, "python3", "-", stdin_data=_build_remote_metrics_script(server.public_ip or server.host))
    base = _ping_snapshot(server.public_ip or server.host, server.country_code)
    if code != 0:
        base.update(
            {
                "cpu_state": "unknown",
                "memory_state": "unknown",
                "disk_state": "unknown",
                "overall_state": base["ping_state"] if base["ping_state"] != "unknown" else "critical",
                "warning_count": 1,
                "status_message": "SSH-подключение к ноде недоступно, live-метрики не получены.",
                "host_status": "error",
                "ssh_status": "error",
                "docker_status": "unknown",
                "xui_service_status": "unknown",
                "xray_service_status": "unknown",
                "awg_service_status": "unknown",
                "rx_mbps": 0.0,
                "tx_mbps": 0.0,
                "rx_label": "—",
                "tx_label": "—",
            }
        )
        return base

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        base.update(
            {
                "cpu_state": "unknown",
                "memory_state": "unknown",
                "disk_state": "unknown",
                "overall_state": "unknown",
                "warning_count": 1,
                "status_message": "Нода вернула некорректный формат метрик.",
                "host_status": "error",
                "ssh_status": "error",
                "docker_status": "unknown",
                "xui_service_status": "unknown",
                "xray_service_status": "unknown",
                "awg_service_status": "unknown",
                "rx_mbps": 0.0,
                "tx_mbps": 0.0,
                "rx_label": "—",
                "tx_label": "—",
            }
        )
        return base

    speed = _remote_speed_snapshot(sample_key, payload.get("tx_bytes"), payload.get("rx_bytes"))
    base.update(
        {
            "hostname": payload.get("hostname", server.host),
            "platform": payload.get("platform", "Linux"),
            "cpu_percent": payload.get("cpu_percent"),
            "cpu_count": payload.get("cpu_count", 0),
            "memory_used_percent": payload.get("memory_used_percent"),
            "memory_total_gb": payload.get("memory_total_gb"),
            "disk_used_percent": payload.get("disk_used_percent"),
            "disk_total_gb": payload.get("disk_total_gb"),
            "network_sent_gb": round(float(payload.get("tx_bytes") or 0) / (1024 ** 3), 2),
            "network_recv_gb": round(float(payload.get("rx_bytes") or 0) / (1024 ** 3), 2),
            "uptime": payload.get("uptime", "—"),
            "load": payload.get("load", "—"),
            "host_status": payload.get("host_status", "ok"),
            "ssh_status": payload.get("ssh_status", "unknown"),
            "docker_status": payload.get("docker_status", "unknown"),
            "xui_service_status": payload.get("xui_service_status", "unknown"),
            "xray_service_status": payload.get("xray_service_status", "unknown"),
            "awg_service_status": payload.get("awg_service_status", "unknown"),
            **speed,
        }
    )
    _recalculate_snapshot_health(base)
    return base


async def xui_summary(base_url: str | None = None, force_refresh: bool = False) -> dict:
    cache_name = "xui_summary" if not base_url or base_url.rstrip("/") == config.xui_url.rstrip("/") else f"xui_summary::{base_url.rstrip('/')}"
    if not force_refresh:
        cached = _runtime_cache_get(cache_name)
        if cached is not None:
            return cached

    xui = XUIClient(base_url=base_url)
    try:
        if not await xui.login():
            result = {"healthy": False, "total_clients": 0}
            _runtime_cache_set(cache_name, result)
            return copy.deepcopy(result)
        inbounds = await xui.get_inbounds()
    except Exception:
        result = {"healthy": False, "total_clients": 0}
        _runtime_cache_set(cache_name, result)
        return copy.deepcopy(result)
    finally:
        await xui.close()

    total = 0
    if inbounds.get("success"):
        for inbound in inbounds.get("obj", []):
            protocol = inbound.get("protocol")
            try:
                settings = json.loads(inbound.get("settings") or "{}")
            except json.JSONDecodeError:
                settings = {}
            if protocol in {"vless", "trojan"}:
                total += len(settings.get("clients", []))
    result = {"healthy": True, "total_clients": total}
    _runtime_cache_set(cache_name, result)
    return copy.deepcopy(result)


async def get_server_snapshots(force_refresh: bool = False) -> list[dict]:
    if not force_refresh:
        cached = _runtime_cache_get("server_snapshots")
        if cached is not None:
            return cached

    servers = await get_managed_servers()
    if not servers:
        _runtime_cache_set("server_snapshots", [])
        return []

    async def build_snapshot(server: ManagedServer) -> dict:
        base = {
            "id": server.id,
            "name": server.name,
            "country_code": server.country_code,
            "country_name": server.country_name or COUNTRY_LABELS.get(server.country_code or "", "Unknown"),
            "public_ip": server.public_ip,
            "provider": server.provider or "—",
            "status": server.status,
            "host": server.host,
            "is_local": server.is_local,
        }

        xui_task = None if normalize_country_code(server.country_code) == "ee" else (
            xui_summary(server.xui_url, force_refresh=force_refresh) if server.xui_url else None
        )

        if server.is_local:
            base.update(local_server_snapshot(str(server.id), server.public_ip or server.host))
            bot_status, support_status, dashboard_status = await asyncio.gather(
                _service_status(server.bot_service_name),
                _service_status(server.support_bot_service_name),
                _service_status(server.dashboard_service_name),
            )
            base["bot_status"] = bot_status
            base["support_bot_status"] = support_status
            base["dashboard_status"] = dashboard_status
            if xui_task is not None:
                xui_clients = await xui_task
                base["xui_status"] = "ok" if xui_clients["healthy"] else "error"
                base["xui_clients"] = xui_clients["total_clients"]
            else:
                base["xui_status"] = "n/a"
                base["xui_clients"] = 0
            _recalculate_snapshot_health(base)
        else:
            if xui_task is not None:
                remote_metrics, xui_clients = await asyncio.gather(
                    remote_server_snapshot(f"remote::{server.id}", server),
                    xui_task,
                )
                base.update(remote_metrics)
                base["xui_status"] = "ok" if xui_clients["healthy"] else "error"
                base["xui_clients"] = xui_clients["total_clients"]
                _recalculate_snapshot_health(base)
            else:
                base.update(await remote_server_snapshot(f"remote::{server.id}", server))
                base["xui_status"] = "n/a"
                base["xui_clients"] = 0
                _recalculate_snapshot_health(base)
            base["bot_status"] = "n/a"
            base["support_bot_status"] = "n/a"
            base["dashboard_status"] = "n/a"

        base["service_pills"] = _service_pills_for_server(base, server)
        return base

    snapshots = list(await asyncio.gather(*(build_snapshot(server) for server in servers)))
    region_stats = await _managed_region_device_stats()
    for snapshot in snapshots:
        region = region_stats.get(_region_stats_key(snapshot.get("country_code")) or "", {})
        snapshot["active_devices"] = int(region.get("active_devices", 0))
        snapshot["total_devices"] = int(region.get("total_devices", 0))
        snapshot["active_users"] = int(region.get("active_users", 0))
        snapshot["active_connections"] = snapshot["active_devices"]
    _runtime_cache_set("server_snapshots", snapshots)
    return copy.deepcopy(snapshots)


def summarize_server_snapshots(snapshots: list[dict]) -> dict:
    if not snapshots:
        return {
            "total": 0,
            "active": 0,
            "maintenance": 0,
            "critical": 0,
            "warning": 0,
            "avg_cpu": 0,
            "avg_memory": 0,
            "avg_disk": 0,
            "xui_clients": 0,
        }

    total = len(snapshots)
    active = sum(1 for item in snapshots if item.get("status") == "active")
    maintenance = sum(1 for item in snapshots if item.get("status") == "maintenance")
    critical = sum(1 for item in snapshots if item.get("overall_state") == "critical")
    warning = sum(1 for item in snapshots if item.get("overall_state") == "warning")
    avg_cpu = round(sum(float(item.get("cpu_percent") or 0) for item in snapshots) / total, 1)
    avg_memory = round(sum(float(item.get("memory_used_percent") or 0) for item in snapshots) / total, 1)
    avg_disk = round(sum(float(item.get("disk_used_percent") or 0) for item in snapshots) / total, 1)
    xui_clients = sum(int(item.get("xui_clients") or 0) for item in snapshots)

    return {
        "total": total,
        "active": active,
        "maintenance": maintenance,
        "critical": critical,
        "warning": warning,
        "avg_cpu": avg_cpu,
        "avg_memory": avg_memory,
        "avg_disk": avg_disk,
        "xui_clients": xui_clients,
    }


def local_server_snapshot(sample_key: str, public_host: str) -> dict:
    boot_at = datetime.fromtimestamp(psutil.boot_time())
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    network = psutil.net_io_counters()
    network_speed = _network_speed_snapshot(sample_key)
    ping = _ping_snapshot(public_host, None, is_local=True)
    load_1, load_5, load_15 = os.getloadavg()
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_percent": round(psutil.cpu_percent(interval=0.05), 1),
        "cpu_count": psutil.cpu_count() or 0,
        "memory_used_percent": round(memory.percent, 1),
        "memory_total_gb": round(memory.total / (1024 ** 3), 2),
        "disk_used_percent": round(disk.percent, 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "network_sent_gb": round(network.bytes_sent / (1024 ** 3), 2),
        "network_recv_gb": round(network.bytes_recv / (1024 ** 3), 2),
        **ping,
        **network_speed,
        "uptime": str(datetime.utcnow() - boot_at).split(".")[0],
        "load": f"{load_1:.2f} / {load_5:.2f} / {load_15:.2f}",
    }


async def recent_audit_logs(limit: int = 30) -> list[DashboardAuditLog]:
    async with async_session() as session:
        return list(
            (
                await session.execute(
                    select(DashboardAuditLog).order_by(DashboardAuditLog.created_at.desc()).limit(limit)
                )
            ).scalars().all()
        )


# ===== Маркетинговые кампании =====

async def get_marketing_campaigns(limit: int = 50, offset: int = 0) -> list[dict]:
    """Получить список кампаний."""
    from dashboard.campaigns import list_campaigns
    return await list_campaigns(limit=limit, offset=offset)


async def create_marketing_campaign(
    name: str,
    cta_label: str = "Попробовать бесплатно",
    admin = None,
    ip_address: str | None = None,
):
    """Создать кампанию."""
    from dashboard.campaigns import create_campaign
    return await create_campaign(name=name, cta_label=cta_label, admin=admin, ip_address=ip_address)


async def get_marketing_campaign_detail(campaign_id: int) -> dict | None:
    """Детали кампании."""
    from dashboard.campaigns import get_campaign_detail
    return await get_campaign_detail(campaign_id)


async def toggle_marketing_campaign(campaign_id: int, admin, ip_address: str | None):
    """Переключить активность кампании."""
    from dashboard.campaigns import toggle_campaign_active
    return await toggle_campaign_active(campaign_id, admin=admin, ip_address=ip_address)


async def delete_marketing_campaign(campaign_id: int, admin, ip_address: str | None) -> bool:
    """Удалить кампанию."""
    from dashboard.campaigns import delete_campaign
    return await delete_campaign(campaign_id, admin=admin, ip_address=ip_address)


async def get_campaign_funnel(token: str) -> list[dict]:
    """Воронка конверсии."""
    from dashboard.campaigns import get_funnel_data
    return await get_funnel_data(token)


# ===== Доска задач (Kanban) =====

async def get_kanban_board(
    search: str = "",
    assignee_filter: str = "",
    tag_filter: str = "",
    priority_filter: str = "",
) -> dict:
    """Канбан-доска."""
    from dashboard.taskboard import get_kanban_data
    return await get_kanban_data(search=search, assignee_filter=assignee_filter, tag_filter=tag_filter, priority_filter=priority_filter)


async def create_kanban_task(
    title: str,
    description: str = "",
    status: str = "backlog",
    priority: str = "medium",
    color: str = "#3b82f6",
    assignee: str = "",
    due_date: str = "",
    tags: list | None = None,
    admin = None,
    ip_address: str | None = None,
):
    """Создать задачу."""
    from dashboard.taskboard import create_task
    return await create_task(title=title, description=description, status=status, priority=priority, color=color, assignee=assignee, due_date=due_date, tags=tags, admin=admin, ip_address=ip_address)


async def update_kanban_task(task_id: int, data: dict, admin, ip_address: str | None):
    """Обновить задачу."""
    from dashboard.taskboard import update_task
    return await update_task(task_id, data=data, admin=admin, ip_address=ip_address)


async def add_kanban_comment(task_id: int, text: str, admin = None):
    """Добавить комментарий."""
    from dashboard.taskboard import add_task_comment
    return await add_task_comment(task_id=task_id, text=text, admin=admin)


async def delete_kanban_task(task_id: int, admin, ip_address: str | None) -> bool:
    """Удалить задачу."""
    from dashboard.taskboard import delete_task
    return await delete_task(task_id, admin=admin, ip_address=ip_address)


# ===== Аналитика =====

async def get_period_analytics(period_key: str = "30d") -> dict:
    """Аналитика за период."""
    from dashboard.analytics import calculate_period_metrics
    return await calculate_period_metrics(period_key)
