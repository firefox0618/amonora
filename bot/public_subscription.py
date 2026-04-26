from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import secrets
from datetime import datetime, timedelta
from typing import Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from bot.db import (
    bind_public_subscription_device_slot,
    clear_public_subscription_device_slot_binding,
    create_public_subscription_route,
    get_active_public_subscription_link_for_user,
    get_or_create_public_subscription_link,
    get_public_subscription_link_by_token,
    get_public_subscription_routes_for_user,
    get_user_by_id,
    get_user_vpn_clients,
    touch_public_subscription_link,
    update_public_subscription_route,
)
from bot.keyboards.devices import HAPP_STORE_URLS
from bot.utils.access import (
    get_access_expires_at_from_user,
    get_device_limit_for_user,
    has_active_access_from_user,
    has_admin_complimentary_access_from_user,
    utcnow,
)
from bot.utils.regions import get_country_flag, get_country_name, normalize_country_code
from bot.utils.texts import CHANNEL_URL, SUPPORT_URL
from bot.utils.vless import build_trojan_link_from_metadata, build_vless_link_from_metadata
from bot.vpn_api import XUIClient
from bot.vpn_provisioning import get_vless_provisioner


logger = logging.getLogger(__name__)

PUBLIC_CLIENT_BASE_URL = "https://client.amonoraconnect.com"
PUBLIC_CLIENT_HOST = "client.amonoraconnect.com"
PUBLIC_CLIENT_HAPP_ADD_PATH = "/happ/add"
PUBLIC_SUBSCRIPTION_BOT_URL = "https://t.me/amonora_v_2_0_bot"
PUBLIC_SUBSCRIPTION_COUNTRY_CODES = ("de", "dk", "ee")
PUBLIC_SUBSCRIPTION_FAILOVER_ORDER: dict[str, tuple[str, ...]] = {
    "de": ("de", "dk", "ee"),
    "dk": ("dk", "de", "ee"),
    "ee": ("ee", "dk", "de"),
}
PUBLIC_SUBSCRIPTION_MAX_SLOTS = 3
PUBLIC_SUBSCRIPTION_UPDATE_INTERVAL_HOURS = 12
PUBLIC_SUBSCRIPTION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
PUBLIC_SUBSCRIPTION_FORCE_FEED_VALUES = {"1", "true", "yes", "sub", "subscription", "feed", "raw"}
PUBLIC_SUBSCRIPTION_CLIENT_MARKERS = (
    "happ",
    "happ-proxy",
    "happ proxy",
    "happ-proxy-utility",
)
PUBLIC_SUBSCRIPTION_ANNOUNCE_TEXT = "Все самое лучшее для Вас 😊"
PUBLIC_SUBSCRIPTION_COMPLIMENTARY_DAYS = 3650
PUBLIC_SUBSCRIPTION_EXTRA_SERVERS: tuple[dict[str, str], ...] = (
    {
        "label": "#1 Обход белых списков",
        "uri": (
            "vless://07cd21cc-1836-4f35-9654-5afc70923d45@158.160.20.200:8443"
            "?security=reality&type=xhttp&headerType=&path=%2F&host=&flow=&mode=auto"
            "&sni=www.ads.x5.ru&fp=&pbk=MMnYv9Q-AwwYXOFbAZXpNLz0LUdYFSW3s4yqfX8Owxc&sid=76c6260a"
        ),
    },
)
PUBLIC_SUBSCRIPTION_OS_VERSION_ALIASES: dict[tuple[str, str], str] = {
    ("windows", "2603201341504"): "11_10.0.26200",
    ("android", "1743595"): "15",
}
PUBLIC_SUBSCRIPTION_BINDING_METADATA_KEYS = {
    "feed_device_fingerprint_hash",
    "feed_device_label",
    "device_name",
    "device_model",
    "device_type",
    "platform_name",
    "os_name",
    "os_version",
    "app_version",
    "source_ip",
    "user_agent",
    "install_id",
    "feed_device_bound_at",
    "feed_device_last_seen_at",
    "subscription_client",
}


def is_valid_public_subscription_token(token: str | None) -> bool:
    return bool(PUBLIC_SUBSCRIPTION_TOKEN_RE.fullmatch(str(token or "").strip()))


def generate_public_subscription_token() -> str:
    token = secrets.token_urlsafe(18)
    normalized = token.replace("=", "").strip()
    if not is_valid_public_subscription_token(normalized):
        raise ValueError("Generated public subscription token is invalid")
    return normalized


def build_public_subscription_page_url(token: str) -> str:
    return f"{PUBLIC_CLIENT_BASE_URL}/{str(token).strip()}"


def build_public_subscription_feed_url(token: str) -> str:
    return build_public_subscription_page_url(token)


def extract_public_subscription_token_from_url(value: str | None) -> str | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    parsed = urlsplit(raw_value)
    if str(parsed.scheme or "").strip().lower() != "https":
        return None
    if str(parsed.hostname or "").strip().lower() != PUBLIC_CLIENT_HOST:
        return None

    path_parts = [part for part in str(parsed.path or "").split("/") if part]
    if not path_parts:
        return None

    token: str | None = None
    if len(path_parts) == 1:
        token = path_parts[0]
    elif len(path_parts) == 2 and path_parts[0] == "sub":
        token = path_parts[1]

    if token is None or not is_valid_public_subscription_token(token):
        return None
    return token


def normalize_public_subscription_page_url(value: str | None) -> str | None:
    token = extract_public_subscription_token_from_url(value)
    if token is None:
        return None
    return build_public_subscription_page_url(token)


def build_public_subscription_happ_wrapper_url(public_subscription_url: str) -> str:
    normalized_url = normalize_public_subscription_page_url(public_subscription_url)
    if normalized_url is None:
        raise ValueError("Invalid public subscription URL")
    query = urlencode({"sub": normalized_url})
    return f"{PUBLIC_CLIENT_BASE_URL}{PUBLIC_CLIENT_HAPP_ADD_PATH}?{query}"


def _public_install_links() -> list[dict[str, object]]:
    return [
        {
            "key": "android",
            "title": "Android",
            "description": (
                "Откройте страницу в Google Play и установите Happ. "
                "Если Google Play недоступен, используйте прямую установку из APK-файла."
            ),
            "links": [
                {"label": "Открыть в Google Play", "url": HAPP_STORE_URLS["android"]},
                {
                    "label": "Скачать APK",
                    "url": "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
                },
            ],
        },
        {
            "key": "ios",
            "title": "iOS",
            "description": (
                "Откройте Happ в App Store и установите приложение. "
                "После первого запуска подтвердите запрос на добавление системного профиля подключения "
                "и введите пароль устройства."
            ),
            "links": [
                {
                    "label": "App Store (RU)",
                    "url": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
                },
                {
                    "label": "App Store (Global)",
                    "url": "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
                },
            ],
        },
        {
            "key": "windows",
            "title": "Windows",
            "description": (
                "Скачайте установщик для Windows, запустите его и завершите установку Happ. "
                "После установки вернитесь к этой подписке и добавьте её в приложение."
            ),
            "links": [
                {
                    "label": "Windows x64",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
                },
            ],
        },
        {
            "key": "macos",
            "title": "macOS",
            "description": (
                "Откройте страницу Happ в App Store, установите приложение и подтвердите "
                "разрешение на системный профиль подключения, если macOS покажет такой запрос."
            ),
            "links": [
                {
                    "label": "App Store (RU)",
                    "url": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
                },
                {
                    "label": "App Store (Global)",
                    "url": "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
                },
            ],
        },
        {
            "key": "linux",
            "title": "Linux",
            "description": (
                "Выберите пакет под вашу систему и архитектуру, установите Happ, "
                "затем вернитесь на страницу подписки и добавьте ссылку в приложение."
            ),
            "links": [
                {
                    "label": "Linux x64 (.deb)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb",
                },
                {
                    "label": "Linux arm64 (.deb)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.deb",
                },
                {
                    "label": "Linux x64 (.rpm)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm",
                },
                {
                    "label": "Linux arm64 (.rpm)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.rpm",
                },
                {
                    "label": "Arch Linux x64 (.pkg.tar.zst)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.pkg.tar.zst",
                },
                {
                    "label": "Arch Linux arm64 (.pkg.tar.zst)",
                    "url": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.arm64.pkg.tar.zst",
                },
            ],
        },
        {
            "key": "apple_tv",
            "title": "Apple TV",
            "description": (
                "Откройте страницу Happ в App Store на Apple TV, установите приложение "
                "и при необходимости подтвердите системный запрос на подключение."
            ),
            "links": [
                {
                    "label": "Магазин приложений",
                    "url": "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274",
                },
            ],
        },
        {
            "key": "android_tv",
            "title": "Android TV",
            "description": (
                "Откройте страницу Happ в Google Play и установите приложение. "
                "Если магазин не работает, используйте прямую установку из APK."
            ),
            "links": [
                {"label": "Открыть в Google Play", "url": HAPP_STORE_URLS["android"]},
                {
                    "label": "Скачать APK",
                    "url": "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
                },
            ],
        },
    ]


def _display_name_for_user(user) -> str:
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        if username.startswith("@"):
            return username
        return f"@{username}"
    return f"tg_{int(getattr(user, 'telegram_id', 0) or 0)}"


def _page_status_payload(user) -> dict[str, object]:
    now = utcnow()
    access_expires_at = _resolved_public_access_expires_at(user)
    active_access = access_expires_at is not None or has_admin_complimentary_access_from_user(user)
    if getattr(user, "is_blocked", False):
        return {
            "status_key": "inactive",
            "status_label": "Не активна",
            "expires_at": None,
            "days_left": 0,
            "expires_human": "Доступ остановлен",
        }
    if active_access:
        if access_expires_at is None and has_admin_complimentary_access_from_user(user):
            return {
                "status_key": "active",
                "status_label": "Активна",
                "expires_at": None,
                "days_left": None,
                "expires_human": "Без ограничения",
            }
        days_left = 0
        if access_expires_at is not None:
            remaining_seconds = max((access_expires_at - now).total_seconds(), 0)
            days_left = int(max(math.ceil(remaining_seconds / 86400), 0))
        return {
            "status_key": "active",
            "status_label": "Активна",
            "expires_at": access_expires_at,
            "days_left": days_left,
            "expires_human": "Без ограничения" if access_expires_at is None else access_expires_at.isoformat(),
        }
    historical_expiry = getattr(user, "subscription_expires_at", None) or getattr(user, "trial_expires_at", None)
    if historical_expiry is not None:
        return {
            "status_key": "expired",
            "status_label": "Истекла",
            "expires_at": historical_expiry,
            "days_left": 0,
            "expires_human": historical_expiry.isoformat(),
        }
    return {
        "status_key": "inactive",
        "status_label": "Не активна",
        "expires_at": None,
        "days_left": 0,
        "expires_human": "Подписка не активирована",
    }


def _route_label(country_code: str, slot_index: int) -> str:
    normalized_country = normalize_country_code(country_code)
    return f"{get_country_flag(normalized_country)} #{int(slot_index)} {get_country_name(normalized_country)}"


def _user_server_label(country_code: str, ordinal: int) -> str:
    normalized_country = normalize_country_code(country_code)
    return f"{get_country_flag(normalized_country)} #{int(ordinal)} {get_country_name(normalized_country)}"


def _protocol_label(route_protocol: str | None, metadata: Mapping[str, object] | None = None) -> str:
    normalized_protocol = str(route_protocol or "").strip().lower() or "vless"
    payload = metadata or {}
    if normalized_protocol == "trojan":
        return "Trojan TCP"

    stream_network = str(payload.get("stream_network") or payload.get("transport_label") or payload.get("transport") or "").strip().lower()
    if "xhttp" in stream_network:
        return "VLESS XHTTP"
    return "VLESS TCP"


def _route_email(user_id: int, country_code: str, slot_index: int) -> str:
    return f"device_feed_{int(user_id)}_{normalize_country_code(country_code)}_{int(slot_index)}"


def _load_route_metadata(route) -> dict:
    raw_value = getattr(route, "client_data", None)
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _rewrite_public_vless_uri(
    uri: str,
    *,
    label: str,
    query_overrides: Mapping[str, str] | None = None,
    remove_keys: set[str] | None = None,
) -> str:
    raw_uri = str(uri or "").strip()
    if not raw_uri:
        return raw_uri
    parsed = urlsplit(raw_uri)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_overrides = {
        str(key or "").strip().lower(): str(value or "").strip()
        for key, value in dict(query_overrides or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    normalized_removals = {str(key or "").strip().lower() for key in (remove_keys or set()) if str(key or "").strip()}
    rewritten_query: list[tuple[str, str]] = []
    seen_override_keys: set[str] = set()

    for key, value in query_items:
        key_text = str(key or "").strip()
        lower_key = key_text.lower()
        if lower_key in normalized_removals:
            continue
        if lower_key in normalized_overrides:
            rewritten_query.append((key_text, normalized_overrides[lower_key]))
            seen_override_keys.add(lower_key)
            continue
        rewritten_query.append((key_text, str(value)))

    for lower_key, value in normalized_overrides.items():
        if lower_key in seen_override_keys:
            continue
        rewritten_query.append((lower_key, value))

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(rewritten_query, doseq=True, safe=","),
            quote(label),
        )
    )


def _rewrite_public_trojan_uri(uri: str, *, label: str) -> str:
    raw_uri = str(uri or "").strip()
    if not raw_uri:
        return raw_uri
    parsed = urlsplit(raw_uri)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_query: list[tuple[str, str]] = []
    peer_value = ""
    sni_value = ""
    for key, value in query_items:
        key_text = str(key or "").strip()
        lower_key = key_text.lower()
        if lower_key == "peer" and value:
            peer_value = str(value)
        if lower_key == "sni" and value:
            sni_value = str(value)
        # Keep the public Trojan feed close to the widely-supported
        # trojan:// URI shape so Happ can use the remark instead of
        # falling back to the hostname in the list view.
        if lower_key in {"security", "type", "sni"}:
            continue
        normalized_query.append((key_text, str(value)))
    if not sni_value:
        sni_value = str(parsed.hostname or "").strip()
    if sni_value and not peer_value:
        normalized_query.append(("peer", sni_value))
    rewritten_query = urlencode(normalized_query, doseq=True, safe=",")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            rewritten_query,
            quote(label),
        )
    )


def _rewrite_public_hysteria2_uri(uri: str, *, label: str) -> str:
    raw_uri = str(uri or "").strip()
    if not raw_uri:
        return raw_uri
    parsed = urlsplit(raw_uri)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.query,
            quote(label),
        )
    )


def _header_value(headers: Mapping[str, object] | None, *names: str) -> str:
    if not headers:
        return ""
    for name in names:
        raw_value = headers.get(name)
        if raw_value is None:
            raw_value = headers.get(str(name).lower())
        if raw_value is None:
            raw_value = headers.get(str(name).title())
        value = str(raw_value or "").strip()
        if value:
            return value
    return ""


def _query_value(query_params: Mapping[str, object] | None, *names: str) -> str:
    if not query_params:
        return ""
    for name in names:
        value = str(query_params.get(name) or "").strip()
        if value:
            return value
    return ""


def is_public_subscription_client_request(
    headers: Mapping[str, object] | None,
    *,
    query_params: Mapping[str, object] | None = None,
) -> bool:
    if query_params:
        for key in ("format", "mode", "raw", "feed"):
            value = str(query_params.get(key) or "").strip().lower()
            if value in PUBLIC_SUBSCRIPTION_FORCE_FEED_VALUES:
                return True

    explicit_client = _header_value(
        headers,
        "x-amonora-subscription-client",
        "x-subscription-client",
        "x-happ-client",
    ).lower()
    if explicit_client in PUBLIC_SUBSCRIPTION_FORCE_FEED_VALUES or explicit_client in {"happ", "happ-proxy"}:
        return True

    user_agent = _header_value(headers, "user-agent").lower()
    return any(marker in user_agent for marker in PUBLIC_SUBSCRIPTION_CLIENT_MARKERS)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _normalize_device_type(value: str | None) -> str | None:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return None
    if raw_value in {"iphone", "ipad", "ios"}:
        return "ios"
    if raw_value in {"android", "windows", "macos", "linux"}:
        return raw_value
    return raw_value


def _normalize_public_os_version(
    *,
    device_type: str | None,
    os_version: str | None,
    user_agent: str | None = None,
) -> str | None:
    normalized_type = _normalize_device_type(device_type)
    raw_value = str(os_version or "").strip().strip('"').strip("'")
    if not raw_value:
        return None

    alias = PUBLIC_SUBSCRIPTION_OS_VERSION_ALIASES.get((str(normalized_type or ""), raw_value))
    if alias:
        return alias

    if normalized_type == "android":
        android_match = re.search(r"(?:android[ /])?([0-9]{1,2})(?:[._][0-9]+)?", raw_value, re.IGNORECASE)
        if android_match:
            return android_match.group(1)
        return raw_value

    if normalized_type == "ios":
        return raw_value.replace("_", ".")

    if normalized_type == "windows":
        if re.fullmatch(r"(?:10|11)_[0-9.]+", raw_value):
            return raw_value
        if re.fullmatch(r"(?:10|11)", raw_value):
            return raw_value
        windows_match = re.search(r"(10\.0\.[0-9]+)", raw_value)
        if windows_match:
            return f"11_{windows_match.group(1)}"
        user_agent_text = str(user_agent or "").strip()
        if user_agent_text:
            ua_alias = PUBLIC_SUBSCRIPTION_OS_VERSION_ALIASES.get((str(normalized_type or ""), user_agent_text.rsplit('/', 1)[-1]))
            if ua_alias:
                return ua_alias
        return raw_value

    return raw_value


def _parse_user_agent_device_fields(user_agent: str) -> dict[str, str | None]:
    normalized = str(user_agent or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return {
            "device_type": None,
            "os_name": None,
            "device_model": None,
            "os_version": None,
            "app_version": None,
        }

    app_version = None
    happ_match = re.search(r"happ(?:[-/ ]proxy)?(?:[-/ ]utility)?[ /]([0-9][0-9A-Za-z._-]*)", normalized, re.IGNORECASE)
    if happ_match:
        app_version = happ_match.group(1)

    android_match = re.search(r"Android[ /]([0-9][0-9A-Za-z._-]*)", normalized, re.IGNORECASE)
    if android_match:
        model_match = re.search(r"Android[ /][^;)]*[; ]+([^;()]+?)(?:\s+Build/|[;)]|$)", normalized, re.IGNORECASE)
        return {
            "device_type": "android",
            "os_name": "Android",
            "device_model": (model_match.group(1).strip() if model_match else "Android"),
            "os_version": android_match.group(1).strip(),
            "app_version": app_version,
        }

    ios_match = re.search(r"\b(iPhone|iPad|iOS)\b.*?\bOS ([0-9_]+)", normalized, re.IGNORECASE)
    if ios_match:
        return {
            "device_type": "ios",
            "os_name": "iOS",
            "device_model": ios_match.group(1).strip(),
            "os_version": ios_match.group(2).replace("_", "."),
            "app_version": app_version,
        }

    windows_happ_match = re.search(r"(?:^|[/;( ])Windows(?:[/ ]+([0-9][0-9A-Za-z._-]*))", normalized, re.IGNORECASE)
    if windows_happ_match:
        return {
            "device_type": "windows",
            "os_name": "Windows",
            "device_model": "Windows PC",
            "os_version": (windows_happ_match.group(1) or "").strip() or None,
            "app_version": app_version,
        }

    windows_match = re.search(r"Windows NT ([0-9.]+)", normalized, re.IGNORECASE)
    if windows_match:
        return {
            "device_type": "windows",
            "os_name": "Windows",
            "device_model": "Windows PC",
            "os_version": windows_match.group(1).strip(),
            "app_version": app_version,
        }

    macos_match = re.search(r"Mac OS X ([0-9_]+)", normalized, re.IGNORECASE)
    if macos_match:
        return {
            "device_type": "macos",
            "os_name": "macOS",
            "device_model": "Mac",
            "os_version": macos_match.group(1).replace("_", "."),
            "app_version": app_version,
        }

    if "linux" in lowered:
        return {
            "device_type": "linux",
            "os_name": "Linux",
            "device_model": "Linux device",
            "os_version": None,
            "app_version": app_version,
        }

    return {
        "device_type": None,
        "os_name": None,
        "device_model": None,
        "os_version": None,
        "app_version": app_version,
    }


def build_public_subscription_request_context(
    *,
    headers: Mapping[str, object] | None,
    source_ip: str | None,
    query_params: Mapping[str, object] | None = None,
) -> dict[str, str | None]:
    user_agent = _header_value(headers, "user-agent")
    parsed = _parse_user_agent_device_fields(user_agent)
    install_id = str(
        _query_value(query_params, "installid", "install_id", "installId")
        or _header_value(headers, "x-install-id", "x-happ-install-id")
    ).strip()
    explicit_device_id = _header_value(
        headers,
        "x-hwid",
        "x-happ-hwid",
        "x-device-id",
        "x-amonora-device-id",
    ).strip()
    device_type = _normalize_device_type(
        _query_value(query_params, "device_os", "deviceOs", "os", "platform")
        or _header_value(headers, "x-device-os", "x-happ-device-os", "sec-ch-ua-platform")
        or parsed["device_type"]
    )
    os_name = (
        _query_value(query_params, "device_os_name", "deviceOsName", "os_name", "osName", "platform_name", "platformName")
        or _header_value(headers, "x-device-os-name", "x-happ-device-os-name")
        or parsed["os_name"]
        or ("iOS" if device_type == "ios" else (str(device_type or "").capitalize() or None))
    )
    device_model = (
        _query_value(query_params, "device_model", "deviceModel", "model", "device_name", "deviceName")
        or _header_value(headers, "x-device-model", "x-happ-device-model", "sec-ch-ua-model")
        or parsed["device_model"]
        or (os_name or "Happ device")
    )
    os_version = (
        _query_value(
            query_params,
            "device_os_version",
            "deviceOsVersion",
            "os_version",
            "osVersion",
            "platform_version",
            "platformVersion",
            "device_version",
            "deviceVersion",
            "version",
        )
        or _header_value(
            headers,
            "x-device-os-version",
            "x-happ-device-os-version",
            "x-os-version",
            "x-platform-version",
            "sec-ch-ua-platform-version",
            "x-device-version",
            "x-client-os-version",
        )
        or parsed["os_version"]
        or None
    )
    os_version = _normalize_public_os_version(
        device_type=device_type,
        os_version=os_version,
        user_agent=user_agent,
    )
    app_version = (
        _query_value(query_params, "app_version", "appVersion", "client_version", "clientVersion")
        or _header_value(headers, "x-app-version", "x-happ-app-version")
        or parsed["app_version"]
        or None
    )
    fingerprint_source = install_id or explicit_device_id or "|".join(
        part
        for part in (
            "happ",
            str(device_type or "").lower(),
            str(device_model or "").lower(),
            str(os_version or "").lower(),
            str(app_version or "").lower(),
            str(user_agent or "").lower(),
            str(source_ip or "").lower(),
        )
        if str(part or "").strip()
    )
    if not fingerprint_source:
        fingerprint_source = str(source_ip or "").strip() or "unknown-device"
    fingerprint_hash = _sha256_hex(fingerprint_source)
    device_label = str(device_model or os_name or "Happ device").strip() or "Happ device"
    return {
        "client_kind": "happ",
        "device_type": device_type,
        "os_name": os_name,
        "device_model": device_model,
        "os_version": os_version,
        "app_version": app_version,
        "device_label": device_label,
        "user_agent": user_agent or None,
        "source_ip": str(source_ip or "").strip() or None,
        "install_id": install_id or None,
        "fingerprint_hash": fingerprint_hash,
    }


def _sync_expiry_for_user(user) -> datetime | None:
    access_expires_at = get_access_expires_at_from_user(user)
    if access_expires_at is not None:
        return access_expires_at
    if has_admin_complimentary_access_from_user(user):
        return utcnow() + timedelta(days=PUBLIC_SUBSCRIPTION_COMPLIMENTARY_DAYS)
    return None


def _desired_public_slot_count_for_user(user) -> int:
    if getattr(user, "is_blocked", False):
        return 0
    has_resolved_access = _resolved_public_access_expires_at(user) is not None
    if not has_resolved_access and not has_active_access_from_user(user) and not has_admin_complimentary_access_from_user(user):
        return 0
    return max(1, int(get_device_limit_for_user(user) or PUBLIC_SUBSCRIPTION_MAX_SLOTS))


def _augment_route_metadata(
    metadata: dict,
    *,
    country_code: str,
    slot_index: int,
) -> dict:
    payload = dict(metadata or {})
    payload["delivery_mode"] = "public_subscription_feed"
    payload["public_subscription_route"] = True
    payload["country_code"] = normalize_country_code(country_code)
    payload["feed_slot_index"] = int(slot_index)
    payload["feed_route_label"] = _route_label(country_code, slot_index)
    return payload


def _build_feed_headers(
    *,
    page_url: str,
    display_name: str,
    expires_at: datetime | None,
    upload_bytes: int = 0,
    download_bytes: int = 0,
) -> dict[str, str]:
    expire_ts = int(expires_at.timestamp()) if expires_at is not None else 0
    del display_name
    return {
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "profile-title": "Amonora",
        "profile-update-interval": str(PUBLIC_SUBSCRIPTION_UPDATE_INTERVAL_HOURS),
        "profile-web-page-url": page_url,
        "support-url": PUBLIC_SUBSCRIPTION_BOT_URL,
        "subscription-userinfo": f"upload={int(upload_bytes)}; download={int(download_bytes)}; total=0; expire={expire_ts}",
        "announce": PUBLIC_SUBSCRIPTION_ANNOUNCE_TEXT,
    }


def _slot_device_payload(request_context: Mapping[str, object]) -> dict[str, object]:
    current = utcnow()
    return {
        "feed_device_fingerprint_hash": str(request_context.get("fingerprint_hash") or "").strip().lower(),
        "feed_device_label": str(request_context.get("device_label") or "").strip() or "Happ device",
        "device_name": str(request_context.get("device_label") or "").strip() or "Happ device",
        "device_model": str(request_context.get("device_model") or "").strip() or "Happ device",
        "device_type": _normalize_device_type(str(request_context.get("device_type") or "").strip()) or "other",
        "platform_name": str(request_context.get("os_name") or "").strip() or None,
        "os_name": str(request_context.get("os_name") or "").strip() or None,
        "os_version": str(request_context.get("os_version") or "").strip() or None,
        "app_version": str(request_context.get("app_version") or "").strip() or None,
        "source_ip": str(request_context.get("source_ip") or "").strip() or None,
        "user_agent": str(request_context.get("user_agent") or "").strip() or None,
        "install_id": str(request_context.get("install_id") or "").strip() or None,
        "feed_device_bound_at": current.isoformat(),
        "feed_device_last_seen_at": current.isoformat(),
        "subscription_client": str(request_context.get("client_kind") or "happ"),
    }


def _trojan_metadata_from_existing(payload: Mapping[str, object] | None) -> dict[str, object]:
    metadata = dict(payload or {})
    alpn = metadata.get("trojan_alpn")
    if isinstance(alpn, str):
        alpn = [item.strip() for item in alpn.split(",") if item.strip()]
    elif not isinstance(alpn, list):
        alpn = []
    return {
        "port": int(metadata.get("trojan_port") or 8443),
        "server_name": str(metadata.get("trojan_server_name") or metadata.get("server_name") or "").strip(),
        "alpn": alpn,
    }


def _trojan_metadata_from_inbound(inbound: Mapping[str, object]) -> dict[str, object]:
    stream_settings_raw = inbound.get("streamSettings") or "{}"
    try:
        stream_settings = json.loads(stream_settings_raw)
    except (TypeError, json.JSONDecodeError):
        stream_settings = {}
    tls_settings = stream_settings.get("tlsSettings") or {}
    alpn = tls_settings.get("alpn") or []
    if isinstance(alpn, str):
        alpn = [item.strip() for item in alpn.split(",") if item.strip()]
    elif not isinstance(alpn, list):
        alpn = []
    return {
        "port": int(inbound.get("port") or 8443),
        "server_name": str(tls_settings.get("serverName") or "").strip(),
        "alpn": alpn,
    }


async def _ensure_public_trojan_metadata(
    metadata: dict[str, object],
    *,
    user_id: int,
    country_code: str,
    slot_index: int,
    access_expires_at: datetime | None,
) -> dict[str, object]:
    if str(metadata.get("provider_type") or "").strip().lower() != "xui":
        return metadata

    xui = XUIClient(country_code=country_code)
    try:
        if not await xui.login():
            return metadata

        trojan_uuid = str(metadata.get("trojan_client_uuid") or "").strip()
        trojan_email = str(metadata.get("trojan_email") or f"feed_trojan_{int(user_id)}_{normalize_country_code(country_code)}_{int(slot_index)}").strip()
        trojan_inbound_id = int(metadata.get("trojan_inbound_id") or 0) or None
        trojan_transport = _trojan_metadata_from_existing(metadata)

        if trojan_uuid:
            result = await xui.sync_trojan_client_expiry(
                trojan_inbound_id or 0,
                trojan_uuid,
                trojan_email,
                access_expires_at,
            )
            if result.get("inbound_id") is not None:
                trojan_inbound_id = int(result["inbound_id"])
        elif access_expires_at is not None:
            inbound = await xui.find_inbound("trojan", 8443)
            if inbound is None:
                return metadata
            trojan_uuid = str(uuid4())
            result = await xui.add_trojan_client(
                inbound_id=int(inbound["id"]),
                email=trojan_email,
                password=trojan_uuid,
                expiry_time_ms=int(access_expires_at.timestamp() * 1000),
            )
            if not result.get("success"):
                return metadata
            trojan_inbound_id = int(inbound["id"])
            trojan_transport = _trojan_metadata_from_inbound(inbound)

        if not trojan_uuid:
            return metadata

        merged_transport = dict(trojan_transport)
        trojan_link = build_trojan_link_from_metadata(
            merged_transport,
            password=trojan_uuid,
            email=trojan_email,
            connection_name=str(metadata.get("feed_route_label") or _route_label(country_code, slot_index)),
            country_code=country_code,
        )
        metadata["trojan_client_uuid"] = trojan_uuid
        metadata["trojan_email"] = trojan_email
        metadata["trojan_inbound_id"] = trojan_inbound_id
        metadata["trojan_port"] = int(merged_transport.get("port") or 8443)
        metadata["trojan_server_name"] = str(merged_transport.get("server_name") or "").strip() or None
        metadata["trojan_alpn"] = merged_transport.get("alpn") or []
        metadata["trojan_link"] = trojan_link
        return metadata
    finally:
        await xui.close()


async def get_or_create_public_subscription_link_for_user(user_id: int):
    existing = await get_active_public_subscription_link_for_user(int(user_id))
    if existing is not None:
        return existing
    return await get_or_create_public_subscription_link(int(user_id), token=generate_public_subscription_token())


async def get_or_create_public_subscription_page_url_for_user(user_id: int) -> str:
    link = await get_or_create_public_subscription_link_for_user(int(user_id))
    return build_public_subscription_page_url(link.token)


async def get_or_create_public_subscription_happ_wrapper_url_for_user(user_id: int) -> str:
    page_url = await get_or_create_public_subscription_page_url_for_user(int(user_id))
    return build_public_subscription_happ_wrapper_url(page_url)


async def touch_public_subscription_surface(token: str, *, feed_access: bool = False) -> bool:
    link = await get_public_subscription_link_by_token(token, active_only=True)
    if link is None:
        return False
    current = utcnow()
    await touch_public_subscription_link(
        int(link.id),
        viewed_at=None if feed_access else current,
        feed_accessed_at=current if feed_access else None,
    )
    return True


async def clear_public_subscription_bound_device_for_user(user_id: int, slot_index: int) -> bool:
    return await clear_public_subscription_device_slot_binding(
        int(user_id),
        slot_index=int(slot_index),
        binding_keys=PUBLIC_SUBSCRIPTION_BINDING_METADATA_KEYS,
    )


async def bind_public_subscription_request_slot(
    token: str,
    *,
    request_context: Mapping[str, object],
) -> dict[str, object] | None:
    if not is_valid_public_subscription_token(token):
        return None

    link = await get_public_subscription_link_by_token(token, active_only=True)
    if link is None:
        return None

    user = await get_user_by_id(int(link.user_id))
    if user is None:
        return None

    if not has_active_access_from_user(user) or getattr(user, "is_blocked", False):
        return None

    slot_limit = _desired_public_slot_count_for_user(user)
    if slot_limit <= 0:
        return None

    binding = await bind_public_subscription_device_slot(
        int(user.id),
        fingerprint_hash=str(request_context.get("fingerprint_hash") or ""),
        device_payload=_slot_device_payload(request_context),
        max_slots=slot_limit,
    )
    if str(binding.get("status") or "").strip().lower() != "limit_reached":
        return binding

    routes = await get_public_subscription_routes_for_user(int(user.id))
    recovery_slot = _first_recoverable_public_slot_index(routes, slot_limit=slot_limit)
    if recovery_slot is None:
        return binding

    logger.info(
        "Recovering public subscription bind for user_id=%s token=%s slot=%s after transient limit_reached",
        int(user.id),
        str(token).strip(),
        recovery_slot,
    )
    await sync_public_subscription_slot_access(
        int(user.id),
        slot_index=int(recovery_slot),
        create_missing=True,
    )
    return await bind_public_subscription_device_slot(
        int(user.id),
        fingerprint_hash=str(request_context.get("fingerprint_hash") or ""),
        device_payload=_slot_device_payload(request_context),
        max_slots=slot_limit,
    )


async def _provision_public_route(user, *, country_code: str, slot_index: int, access_expires_at: datetime):
    provisioner = get_vless_provisioner(country_code)
    try:
        if not await provisioner.health_check():
            return None

        async def _save_callback(**kwargs):
            return await create_public_subscription_route(
                user_id=int(user.id),
                country_code=country_code,
                slot_index=slot_index,
                protocol=str(kwargs.get("protocol") or "vless"),
                client_uuid=str(kwargs.get("client_uuid") or "").strip(),
                email=str(kwargs.get("email") or "").strip(),
                xui_client_id=str(kwargs.get("xui_client_id") or "").strip() or None,
                client_data=kwargs.get("client_data"),
                status="active",
            )

        result = await provisioner.provision_vless_client(
            user_id=int(user.id),
            email=_route_email(int(user.id), country_code, slot_index),
            access_expires_at=access_expires_at,
            save_callback=_save_callback,
            country_code=country_code,
        )
        metadata = _augment_route_metadata(result.metadata, country_code=country_code, slot_index=slot_index)
        metadata = await _ensure_public_trojan_metadata(
            metadata,
            user_id=int(user.id),
            country_code=country_code,
            slot_index=slot_index,
            access_expires_at=access_expires_at,
        )
        updated = await update_public_subscription_route(
            int(result.vpn_client_id),
            client_data=metadata,
            status="active",
            disabled_at=None,
        )
        return updated
    finally:
        await provisioner.close()


async def _sync_public_route(route, *, access_expires_at: datetime | None) -> bool:
    metadata = _load_route_metadata(route)
    country_code = normalize_country_code(getattr(route, "country_code", None))
    slot_index = int(getattr(route, "slot_index", 1) or 1)
    provider_type = str(metadata.get("provider_type") or "").strip().lower() or None
    provisioner = get_vless_provisioner(country_code, provider_type)
    try:
        if not await provisioner.health_check():
            await update_public_subscription_route(int(route.id), status="broken")
            return False

        if route.protocol != "vless":
            await update_public_subscription_route(int(route.id), status="broken")
            return False

        if not metadata or "vless_link" not in metadata:
            rebuilt = await provisioner.build_vless_metadata(
                client_uuid=str(route.xui_client_id or route.client_uuid),
                email=str(route.email),
                country_code=country_code,
                base_metadata=metadata,
            )
            metadata = rebuilt

        metadata = _augment_route_metadata(metadata, country_code=country_code, slot_index=slot_index)
        await provisioner.sync_vless_client(
            client_uuid=str(route.xui_client_id or route.client_uuid),
            email=str(route.email),
            metadata=metadata,
            access_expires_at=access_expires_at,
        )
        metadata = await _ensure_public_trojan_metadata(
            metadata,
            user_id=int(getattr(route, "user_id", 0) or 0),
            country_code=country_code,
            slot_index=slot_index,
            access_expires_at=access_expires_at,
        )
        await update_public_subscription_route(
            int(route.id),
            client_data=metadata,
            status="active" if access_expires_at is not None else "disabled",
            disabled_at=None if access_expires_at is not None else utcnow(),
        )
        return True
    except Exception:
        logger.exception(
            "Failed to sync public subscription route route_id=%s user_id=%s country=%s slot=%s",
            getattr(route, "id", None),
            getattr(route, "user_id", None),
            country_code,
            slot_index,
        )
        await update_public_subscription_route(int(route.id), status="broken")
        return False
    finally:
        await provisioner.close()


async def sync_public_subscription_access(
    user_id: int,
    *,
    create_missing: bool,
) -> bool:
    user = await get_user_by_id(int(user_id))
    if user is None:
        return False

    routes = await get_public_subscription_routes_for_user(int(user_id))
    if not create_missing and not routes:
        link = await get_active_public_subscription_link_for_user(int(user_id))
        if link is None:
            return False

    desired_slot_count = _desired_public_slot_count_for_user(user)
    sync_expiry = _sync_expiry_for_user(user) if desired_slot_count > 0 else None
    existing_by_key = {
        (normalize_country_code(getattr(route, "country_code", None)), int(getattr(route, "slot_index", 1) or 1)): route
        for route in routes
    }
    desired_keys = {
        (country_code, slot_index)
        for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES
        for slot_index in range(1, desired_slot_count + 1)
    }
    sync_failed = False

    for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES:
        for slot_index in range(1, desired_slot_count + 1):
            route = existing_by_key.get((country_code, slot_index))
            if route is None:
                if not create_missing or sync_expiry is None:
                    continue
                route = await _provision_public_route(
                    user,
                    country_code=country_code,
                    slot_index=slot_index,
                    access_expires_at=sync_expiry,
                )
                if route is None:
                    sync_failed = True
                    continue
            if not await _sync_public_route(route, access_expires_at=sync_expiry):
                sync_failed = True

    for key, route in existing_by_key.items():
        if key in desired_keys:
            continue
        if not await _sync_public_route(route, access_expires_at=None):
            sync_failed = True

    return sync_failed


async def sync_public_subscription_slot_access(
    user_id: int,
    *,
    slot_index: int,
    create_missing: bool,
) -> bool:
    user = await get_user_by_id(int(user_id))
    if user is None:
        return False

    safe_slot_index = int(slot_index or 0)
    desired_slot_count = _desired_public_slot_count_for_user(user)
    if safe_slot_index <= 0 or safe_slot_index > desired_slot_count:
        return False

    routes = await get_public_subscription_routes_for_user(int(user_id))
    sync_expiry = _sync_expiry_for_user(user) if desired_slot_count > 0 else None
    existing_by_country = {
        normalize_country_code(getattr(route, "country_code", None)): route
        for route in routes
        if int(getattr(route, "slot_index", 0) or 0) == safe_slot_index
    }
    sync_failed = False

    for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES:
        route = existing_by_country.get(country_code)
        if route is None:
            if not create_missing or sync_expiry is None:
                sync_failed = True
                continue
            route = await _provision_public_route(
                user,
                country_code=country_code,
                slot_index=safe_slot_index,
                access_expires_at=sync_expiry,
            )
            if route is None:
                sync_failed = True
                continue
        if not await _sync_public_route(route, access_expires_at=sync_expiry):
            sync_failed = True

    return sync_failed


def _append_labeled_uri(uris: list[str], raw_uri: str, *, label: str) -> None:
    uri = str(raw_uri or "").strip()
    if uri.startswith("hysteria2://"):
        uri = _rewrite_public_hysteria2_uri(uri, label=label)
    elif uri.startswith("trojan://"):
        uri = _rewrite_public_trojan_uri(uri, label=label)
    else:
        uri = _rewrite_public_vless_uri(uri, label=label)
    if uri and uri not in uris:
        uris.append(uri)


def _build_germany_vision_uri(raw_uri: str) -> str:
    uri = str(raw_uri or "").strip()
    if not uri.startswith("vless://"):
        return ""
    return _rewrite_public_vless_uri(
        uri,
        label=_user_server_label("de", 2),
        query_overrides={"flow": "xtls-rprx-vision"},
    )


def _build_hysteria2_uri(
    *,
    password: str,
    host: str,
    port: int,
    label: str,
    sni: str | None = None,
    alpn: str | None = None,
) -> str:
    normalized_password = str(password or "").strip()
    normalized_host = str(host or "").strip()
    if not normalized_password or not normalized_host:
        return ""

    query_parts: list[str] = []
    normalized_sni = str(sni or "").strip()
    normalized_alpn = str(alpn or "").strip()
    if normalized_sni:
        query_parts.append(f"sni={quote(normalized_sni, safe='')}")
    if normalized_alpn:
        query_parts.append(f"alpn={quote(normalized_alpn, safe=',')}")

    base_uri = f"hysteria2://{quote(normalized_password, safe='')}@{normalized_host}:{int(port)}"
    if query_parts:
        base_uri = f"{base_uri}?{'&'.join(query_parts)}"
    return f"{base_uri}#{quote(label)}"


def _build_germany_hysteria2_uri(route, metadata: Mapping[str, object] | None = None) -> str:
    payload = dict(metadata or {})
    password = str(payload.get("hysteria2_password") or payload.get("hy2_password") or "").strip()
    if not password:
        return ""
    host = str(payload.get("hysteria2_host") or payload.get("hy2_host") or "ffconnect.amonoraconnect.com").strip()
    if not host:
        return ""
    try:
        port = int(payload.get("hysteria2_port") or payload.get("hy2_port") or 9443)
    except (TypeError, ValueError):
        port = 9443
    sni = str(payload.get("hysteria2_sni") or payload.get("hy2_sni") or host).strip()
    alpn = str(payload.get("hysteria2_alpn") or payload.get("hy2_alpn") or "h3").strip()
    return _build_hysteria2_uri(
        password=password,
        host=host,
        port=port,
        label=_user_server_label("de", 2),
        sni=sni,
        alpn=alpn,
    )


def _active_public_routes_by_country(routes: list[object]) -> dict[str, list[object]]:
    by_country: dict[str, list[object]] = {country_code: [] for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES}
    ordered_routes = sorted(
        routes,
        key=lambda route: (
            normalize_country_code(getattr(route, "country_code", None)),
            int(getattr(route, "slot_index", 0) or 0),
        ),
    )
    for route in ordered_routes:
        if str(getattr(route, "status", "") or "").strip().lower() != "active":
            continue
        country_code = normalize_country_code(getattr(route, "country_code", None))
        if country_code not in by_country:
            continue
        by_country[country_code].append(route)
    return by_country


def _public_route_vless_uri(
    route,
    *,
    label: str,
    use_reserve: bool = False,
    query_overrides: Mapping[str, str] | None = None,
) -> str:
    metadata = _load_route_metadata(route)
    raw_link = ""
    if use_reserve:
        raw_link = str(metadata.get("reserve_vless_link") or "").strip()
    else:
        raw_link = str(metadata.get("vless_link") or "").strip()
        if not raw_link:
            raw_link = build_vless_link_from_metadata(
                metadata=metadata,
                client_uuid=str(getattr(route, "xui_client_id", None) or getattr(route, "client_uuid", "")),
                email=str(getattr(route, "email", "")),
                connection_name=label,
                country_code=normalize_country_code(getattr(route, "country_code", None)),
            )
    if not raw_link and use_reserve:
        return _public_route_vless_uri(route, label=label, use_reserve=False, query_overrides=query_overrides)
    if not raw_link:
        return ""
    if query_overrides:
        return _rewrite_public_vless_uri(raw_link, label=label, query_overrides=query_overrides)
    return raw_link


def _build_public_server_entries(routes: list[object]) -> list[dict[str, str]]:
    routes_by_country = _active_public_routes_by_country(routes)
    entries: list[dict[str, str]] = []

    for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES:
        candidate_routes = routes_by_country.get(country_code) or []
        if not candidate_routes:
            continue

        label = _user_server_label(country_code, 1)
        uri = _public_route_vless_uri(candidate_routes[0], label=label)
        if uri:
            entries.append({"label": label, "uri": uri})

    return entries


def _build_feed_uris(routes: list[object]) -> list[str]:
    uris: list[str] = []
    for entry in _build_public_server_entries(routes):
        _append_labeled_uri(uris, entry.get("uri") or "", label=str(entry.get("label") or "").strip())
    return uris


def _route_protocol_labels(routes: list[object]) -> list[str]:
    labels: list[str] = []
    for route in routes:
        if str(getattr(route, "status", "") or "").strip().lower() != "active":
            continue
        metadata = _load_route_metadata(route)
        for label in (
            _protocol_label(getattr(route, "protocol", None), metadata),
            "Trojan TCP" if str(metadata.get("trojan_link") or "").strip() else None,
        ):
            if label and label not in labels:
                labels.append(label)
    return labels


def _coerce_non_negative_int(value: object) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _humanize_bytes(value: int) -> str:
    size = max(int(value or 0), 0)
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    index = 0
    amount = float(size)
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024
        index += 1
    if index == 0:
        return f"{int(amount)} {units[index]}"
    return f"{amount:.1f} {units[index]}".replace(".0 ", " ")


def _humanize_public_traffic(value: int) -> str:
    size = max(int(value or 0), 0)
    if size < 1024 * 1024:
        return "0 МБ"

    amount = float(size) / (1024 * 1024)
    units = ["МБ", "ГБ", "ТБ"]
    index = 0
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024
        index += 1
    return f"{amount:.1f} {units[index]}".replace(".0 ", " ")


def _resolved_public_access_expires_at(user) -> datetime | None:
    expires_at = get_access_expires_at_from_user(user)
    if expires_at is not None:
        return expires_at
    if str(getattr(user, "subscription_status", "") or "").strip().lower() == "active":
        return getattr(user, "subscription_expires_at", None)
    return getattr(user, "trial_expires_at", None)


def _traffic_totals_from_routes(routes: list[object]) -> tuple[int, int]:
    upload_bytes = 0
    download_bytes = 0
    for route in routes:
        if str(getattr(route, "status", "") or "").strip().lower() != "active":
            continue
        metadata = _load_route_metadata(route)
        upload_bytes += _coerce_non_negative_int(
            metadata.get("upload_bytes")
            or metadata.get("upload")
            or metadata.get("up")
        )
        download_bytes += _coerce_non_negative_int(
            metadata.get("download_bytes")
            or metadata.get("download")
            or metadata.get("down")
        )
    return upload_bytes, download_bytes


def _account_device_status_fields(status: Mapping[str, object] | None) -> dict[str, str]:
    payload = status or {}
    status_key = str(payload.get("status_key") or "inactive").strip().lower() or "inactive"
    status_label = str(payload.get("status_label") or "Не активна").strip() or "Не активна"
    return {
        "status_key": status_key,
        "status_label": status_label,
    }


def _legacy_device_connection_uri(device, metadata: Mapping[str, object]) -> str | None:
    raw_link = str(
        metadata.get("connection_uri")
        or metadata.get("vless_link")
        or metadata.get("trojan_link")
        or ""
    ).strip()
    return raw_link or None


def _bound_public_devices_from_routes(
    routes: list[object],
    *,
    status: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    status_fields = _account_device_status_fields(status)
    slot_rows: dict[int, list[object]] = {}
    for route in routes:
        slot_index = int(getattr(route, "slot_index", 0) or 0)
        if slot_index <= 0:
            continue
        slot_rows.setdefault(slot_index, []).append(route)

    devices: list[dict[str, object]] = []
    for slot_index in sorted(slot_rows):
        metadata_candidates = [_load_route_metadata(route) for route in slot_rows[slot_index]]
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
        device_type = _normalize_device_type(bound_metadata.get("device_type")) or "other"
        os_name = str(bound_metadata.get("os_name") or bound_metadata.get("platform_name") or device_type).strip()
        device_model = str(bound_metadata.get("device_model") or bound_metadata.get("device_name") or "Happ device").strip()
        os_version = _normalize_public_os_version(
            device_type=device_type,
            os_version=bound_metadata.get("os_version"),
            user_agent=bound_metadata.get("user_agent"),
        )
        devices.append(
            {
                "kind": "public_slot",
                "id": int(slot_index),
                "slot_index": int(slot_index),
                "title": device_model or f"Happ #{slot_index}",
                "device_model": device_model or f"Happ #{slot_index}",
                "device_type": device_type,
                "os_name": os_name or device_type,
                "os_version": str(os_version or "—").strip() or "—",
                "app_version": str(bound_metadata.get("app_version") or "").strip() or None,
                "source_ip": str(bound_metadata.get("source_ip") or "").strip() or None,
                "bound_at": str(bound_metadata.get("feed_device_bound_at") or "").strip() or None,
                "country_name": "Единая подписка",
                "source_label": "Happ / единая ссылка",
                **status_fields,
            }
        )
    return tuple(devices)


def _legacy_public_devices_from_vpn_clients(
    devices: list[object],
    *,
    status: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    status_fields = _account_device_status_fields(status)
    serialized: list[dict[str, object]] = []
    for device in devices:
        metadata = {}
        try:
            metadata = json.loads(getattr(device, "client_data", None) or "{}")
        except json.JSONDecodeError:
            metadata = {}

        device_type = _normalize_device_type(
            metadata.get("device_type")
            or metadata.get("os_type")
            or metadata.get("platform")
            or metadata.get("platform_name")
        ) or "other"
        os_name = str(
            metadata.get("os_name")
            or metadata.get("platform_name")
            or ("iOS" if device_type == "ios" else ("macOS" if device_type == "macos" else (str(device_type).capitalize() if device_type != "other" else "Устройство")))
        ).strip() or "Устройство"
        device_model = str(
            metadata.get("device_name")
            or metadata.get("device_model")
            or metadata.get("device_label")
            or getattr(device, "email", None)
            or "Классическое устройство"
        ).strip() or "Классическое устройство"
        os_version = _normalize_public_os_version(
            device_type=device_type,
            os_version=metadata.get("os_version") or metadata.get("platform_version"),
            user_agent=metadata.get("user_agent"),
        )
        created_at = getattr(device, "created_at", None)
        serialized.append(
            {
                "kind": "legacy_device",
                "id": int(getattr(device, "id", 0) or 0),
                "slot_index": 0,
                "title": device_model,
                "device_model": device_model,
                "device_type": device_type,
                "os_name": os_name,
                "os_version": str(os_version or "—").strip() or "—",
                "app_version": str(metadata.get("app_version") or "").strip() or None,
                "source_ip": str(metadata.get("source_ip") or "").strip() or None,
                "bound_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
                "country_name": str(metadata.get("country_name") or metadata.get("country_code") or "Классический ключ").strip()
                or "Классический ключ",
                "source_label": "Классический ключ",
                "connection_uri": _legacy_device_connection_uri(device, metadata),
                **status_fields,
            }
        )
    return tuple(serialized)


def _build_account_devices_payload(
    user,
    *,
    routes: list[object],
    legacy_devices: list[object],
) -> tuple[dict[str, object], ...]:
    status = _page_status_payload(user)
    bound_devices = _bound_public_devices_from_routes(routes, status=status)
    legacy_rows = _legacy_public_devices_from_vpn_clients(legacy_devices, status=status)
    return (*bound_devices, *legacy_rows)


def _active_public_route_keys(routes: list[object]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for route in routes:
        if str(getattr(route, "status", "") or "").strip().lower() != "active":
            continue
        country_code = normalize_country_code(getattr(route, "country_code", None))
        slot_index = int(getattr(route, "slot_index", 0) or 0)
        if country_code not in PUBLIC_SUBSCRIPTION_COUNTRY_CODES or slot_index <= 0:
            continue
        keys.add((country_code, slot_index))
    return keys


def _failover_chain_for_country(country_code: str) -> tuple[str, ...]:
    normalized_country = normalize_country_code(country_code)
    preferred_chain = PUBLIC_SUBSCRIPTION_FAILOVER_ORDER.get(normalized_country) or (normalized_country,)
    normalized_chain: list[str] = []
    for candidate_country in preferred_chain:
        normalized_candidate = normalize_country_code(candidate_country)
        if normalized_candidate in PUBLIC_SUBSCRIPTION_COUNTRY_CODES and normalized_candidate not in normalized_chain:
            normalized_chain.append(normalized_candidate)
    if not normalized_chain and normalized_country in PUBLIC_SUBSCRIPTION_COUNTRY_CODES:
        normalized_chain.append(normalized_country)
    return tuple(normalized_chain)


def _has_ready_public_routes(
    routes: list[object],
    *,
    slot_limit: int,
    slot_index: int | None = None,
) -> bool:
    active_slots_by_country: dict[str, set[int]] = {country_code: set() for country_code in PUBLIC_SUBSCRIPTION_COUNTRY_CODES}
    for country_code, current_slot in _active_public_route_keys(routes):
        active_slots_by_country.setdefault(country_code, set()).add(int(current_slot))

    if slot_index is not None:
        safe_slot = int(slot_index or 0)
        expected_slots = {safe_slot} if safe_slot > 0 else set()
    else:
        expected_slots = set(range(1, max(int(slot_limit or 0), 0) + 1))
    if not expected_slots:
        return False

    for current_slot in sorted(expected_slots):
        for logical_country in PUBLIC_SUBSCRIPTION_COUNTRY_CODES:
            failover_chain = _failover_chain_for_country(logical_country)
            if not failover_chain:
                return False
            if any(int(current_slot) in active_slots_by_country.get(candidate_country, set()) for candidate_country in failover_chain):
                continue
            return False
    return True


def _first_recoverable_public_slot_index(
    routes: list[object],
    *,
    slot_limit: int,
) -> int | None:
    safe_limit = max(int(slot_limit or 0), 0)
    if safe_limit <= 0:
        return None
    occupied_slots: set[int] = set()
    for route in routes:
        slot_index = int(getattr(route, "slot_index", 0) or 0)
        if slot_index <= 0 or slot_index > safe_limit:
            continue
        metadata = _load_route_metadata(route)
        if str(metadata.get("feed_device_fingerprint_hash") or "").strip():
            occupied_slots.add(slot_index)
    for candidate in range(1, safe_limit + 1):
        if candidate not in occupied_slots:
            return candidate
    return None


async def get_public_subscription_bound_devices_for_user(user_id: int) -> tuple[dict[str, object], ...]:
    routes = await get_public_subscription_routes_for_user(int(user_id))
    return _bound_public_devices_from_routes(routes)


async def get_account_devices_for_user(user_id: int) -> tuple[dict[str, object], ...]:
    user = await get_user_by_id(int(user_id))
    if user is None:
        return ()
    routes, legacy_devices = await asyncio.gather(
        get_public_subscription_routes_for_user(int(user.id)),
        get_user_vpn_clients(int(user.id)),
    )
    return _build_account_devices_payload(user, routes=routes, legacy_devices=legacy_devices)


async def get_public_subscription_summary_by_token(token: str) -> dict | None:
    if not is_valid_public_subscription_token(token):
        return None

    link = await get_public_subscription_link_by_token(token, active_only=True)
    if link is None:
        return None

    user = await get_user_by_id(int(link.user_id))
    if user is None:
        return None

    routes, legacy_devices = await asyncio.gather(
        get_public_subscription_routes_for_user(int(user.id)),
        get_user_vpn_clients(int(user.id)),
    )
    slot_limit = _desired_public_slot_count_for_user(user)
    # Do not block page rendering with heavy auto-repair.
    # Feed requests still run full sync if needed.
    if not _has_ready_public_routes(routes, slot_limit=slot_limit):
        await sync_public_subscription_access(int(user.id), create_missing=True)
        routes = await get_public_subscription_routes_for_user(int(user.id))
    status = _page_status_payload(user)
    page_url = build_public_subscription_page_url(token)
    feed_url = page_url
    upload_bytes, download_bytes = _traffic_totals_from_routes(routes)
    traffic_total_bytes = upload_bytes + download_bytes
    account_devices = list(_build_account_devices_payload(user, routes=routes, legacy_devices=legacy_devices))
    bound_devices = [device for device in account_devices if str(device.get("kind") or "").strip().lower() == "public_slot"]
    server_entries = _build_public_server_entries(routes)

    return {
        "display_name": _display_name_for_user(user),
        "telegram_id": int(getattr(user, "telegram_id", 0) or 0) or None,
        "status": status["status_key"],
        "status_label": status["status_label"],
        "expires_at": status["expires_at"].isoformat() if isinstance(status["expires_at"], datetime) else None,
        "days_left": status["days_left"],
        "traffic_used": _humanize_public_traffic(traffic_total_bytes),
        "traffic_limit": "∞",
        "feed_url": feed_url,
        "page_url": page_url,
        "bot_url": PUBLIC_SUBSCRIPTION_BOT_URL,
        "is_active": status["status_key"] == "active",
        "channel_url": CHANNEL_URL,
        "support_url": SUPPORT_URL,
        "install_links": _public_install_links(),
        "devices_limit": slot_limit,
        "servers": [{"label": str(entry.get("label") or "").strip()} for entry in server_entries if str(entry.get("label") or "").strip()],
        "bound_devices": bound_devices,
        "bound_devices_count": len(bound_devices),
        "account_devices": account_devices,
        "account_devices_count": len(account_devices),
    }


async def get_public_subscription_feed_payload(
    token: str,
    *,
    slot_index: int | None = None,
) -> tuple[str, dict[str, str]] | None:
    if not is_valid_public_subscription_token(token):
        return None

    link = await get_public_subscription_link_by_token(token, active_only=True)
    if link is None:
        return None

    user = await get_user_by_id(int(link.user_id))
    if user is None:
        return None

    access_expires_at = _resolved_public_access_expires_at(user)
    if access_expires_at is None or getattr(user, "is_blocked", False):
        return None

    routes = await get_public_subscription_routes_for_user(int(user.id))
    slot_limit = _desired_public_slot_count_for_user(user)
    if not _has_ready_public_routes(routes, slot_limit=slot_limit, slot_index=slot_index):
        if slot_index is not None:
            await sync_public_subscription_slot_access(
                int(user.id),
                slot_index=int(slot_index),
                create_missing=True,
            )
        else:
            await sync_public_subscription_access(int(user.id), create_missing=True)
        routes = await get_public_subscription_routes_for_user(int(user.id))
    if slot_index is not None:
        routes = [route for route in routes if int(getattr(route, "slot_index", 0) or 0) == int(slot_index)]
    uris = _build_feed_uris(routes)
    if not uris:
        return None

    await touch_public_subscription_surface(token, feed_access=True)
    page_url = build_public_subscription_page_url(token)
    upload_bytes, download_bytes = _traffic_totals_from_routes(routes)
    return (
        "\n".join(uris).strip() + "\n",
        _build_feed_headers(
            page_url=page_url,
            display_name=_display_name_for_user(user),
            expires_at=access_expires_at,
            upload_bytes=upload_bytes,
            download_bytes=download_bytes,
        ),
    )
