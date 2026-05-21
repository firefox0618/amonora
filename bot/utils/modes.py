from dataclasses import dataclass

from bot.utils.access import is_admin_telegram_id
from bot.utils.regions import (
    get_country_provider_type,
    get_supported_region_codes,
    get_user_selectable_region_codes,
    normalize_country_code,
)


DEFAULT_MODE = "stable"
MODE_ORDER = ("stable", "mobile", "reserve")
LEGACY_MODE_ALIASES = {
    "auto": "stable",
    "автовыбор": "stable",
    "nova": "stable",
    "нова": "stable",
    "core": "stable",
    "ядро": "stable",
    "origin": "stable",
    "base": "stable",
    "основа": "stable",
    "white": "mobile",
    "white mode": "mobile",
    "стабильный": "stable",
    "мобильный": "mobile",
    "резерв": "reserve",
}


@dataclass(frozen=True)
class ModeDefinition:
    key: str
    label: str
    title: str
    description: str
    admin_description: str | None
    protocol: str


MODES: dict[str, ModeDefinition] = {
    "stable": ModeDefinition(
        key="stable",
        label="🛡 Стабильный",
        title="Стабильный",
        description="основной режим на каждый день",
        admin_description="основной режим на каждый день",
        protocol="vless",
    ),
    "mobile": ModeDefinition(
        key="mobile",
        label="📱 Мобильный",
        title="Мобильный",
        description="маршрут для сетей, где доступна только часть направлений",
        admin_description="маршрут для сетей с ограниченным набором доступных направлений",
        protocol="vless",
    ),
    "reserve": ModeDefinition(
        key="reserve",
        label="🧰 Резерв",
        title="Резерв",
        description="запасной режим, если основной не подошёл",
        admin_description="запасной режим, если основной не подошёл",
        protocol="vless",
    ),
}


def normalize_mode(mode: str | None, default: str = DEFAULT_MODE) -> str:
    value = (mode or "").strip().lower()
    value = LEGACY_MODE_ALIASES.get(value, value)
    if value in MODES:
        return value
    return default


def get_auto_mode() -> str:
    return DEFAULT_MODE


def is_mode_key(mode: str | None) -> bool:
    value = (mode or "").strip().lower()
    return value in MODES or value in LEGACY_MODE_ALIASES


def get_mode_keys(*, telegram_id: int | None = None, country_code: str | None = None) -> tuple[str, ...]:
    items: list[str] = []
    for mode in MODE_ORDER:
        if country_code is not None and not mode_supported_in_region(mode, country_code, telegram_id=telegram_id):
            continue
        items.append(mode)
    return tuple(items)


def resolve_auto_mode(country_code: str | None = None) -> str:
    del country_code
    return DEFAULT_MODE


def resolve_effective_mode(
    mode: str | None,
    country_code: str | None = None,
    *,
    protocol: str | None = None,
    metadata: dict | None = None,
) -> str:
    del country_code, protocol, metadata
    return normalize_mode(mode)


def _mode_label_icon(mode: str, country_code: str | None = None) -> str:
    normalized_country = normalize_country_code(country_code)
    if mode == "mobile" and normalized_country in {"de", "dk"}:
        return "☁"
    return MODES[mode].label.split(" ", 1)[0]


def format_mode(mode: str | None, *, with_recommended: bool = False, country_code: str | None = None) -> str:
    del with_recommended
    normalized = normalize_mode(mode)
    definition = MODES[normalized]
    icon = _mode_label_icon(normalized, country_code)
    return f"{icon} {definition.title}"


def get_mode_description(mode: str | None, *, telegram_id: int | None = None) -> str:
    normalized = normalize_mode(mode)
    definition = MODES[normalized]
    if definition.admin_description and is_admin_telegram_id(telegram_id):
        return definition.admin_description
    return definition.description


def get_mode_protocol(mode: str | None, country_code: str | None = None) -> str:
    effective_mode = resolve_effective_mode(mode, country_code)
    provider_type = get_country_provider_type(country_code)
    normalized_country = normalize_country_code(country_code)
    if effective_mode == "reserve" and provider_type == "xui" and normalized_country != "de":
        return "trojan"
    base_protocol = MODES[effective_mode].protocol
    if base_protocol == "trojan" and provider_type != "xui":
        return "vless"
    return base_protocol


def infer_mode_from_protocol(protocol: str | None, metadata: dict | None = None) -> str:
    payload = metadata or {}
    explicit_mode = normalize_mode(payload.get("mode"), default="")
    if explicit_mode in MODES:
        return explicit_mode

    explicit_resolved = normalize_mode(payload.get("resolved_mode"), default="")
    if explicit_resolved in MODES:
        return explicit_resolved

    connection_profile = str(payload.get("connection_profile") or payload.get("active_profile") or "").strip().lower()
    if connection_profile == "reserve":
        return "reserve"

    normalized_protocol = (protocol or "").strip().lower()
    if normalized_protocol == "trojan":
        return "reserve"

    stream_network = str(payload.get("stream_network") or "").strip().lower()
    if stream_network == "xhttp":
        return "stable"

    country_code = normalize_country_code(payload.get("country_code"))
    if get_country_provider_type(country_code) == "xray_core":
        return "stable"

    return "stable"


def mode_requires_admin_experimental_access(mode: str | None) -> bool:
    return normalize_mode(mode) == "mobile"


def mode_available_for_user(mode: str | None, *, telegram_id: int | None = None) -> bool:
    del telegram_id
    return normalize_mode(mode) in MODES


def get_mode_connection_profile(mode: str | None, country_code: str | None = None) -> str | None:
    if get_country_provider_type(country_code) != "xray_core":
        return None
    normalized_mode = resolve_effective_mode(mode, country_code)
    if normalized_mode in {"mobile", "reserve"}:
        return "reserve"
    return "primary"


def mode_supported_in_region(mode: str | None, country_code: str | None, *, telegram_id: int | None = None) -> bool:
    del telegram_id
    normalized_country = normalize_country_code(country_code)
    normalized_mode = normalize_mode(mode)
    if normalized_mode == "mobile" and normalized_country == "ee":
        return False
    return normalized_country in set(get_supported_region_codes())


def get_mode_region_codes(*, telegram_id: int | None = None, mode: str | None = None) -> list[str]:
    del mode
    return list(get_user_selectable_region_codes(telegram_id=telegram_id))
