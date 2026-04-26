from dataclasses import dataclass

from bot.config import config


@dataclass(frozen=True)
class Region:
    code: str
    name_ru: str
    flag: str
    import_name: str
    provider_type: str = "xui"
    runtime_type: str | None = None
    runtime_service_name: str | None = None
    anti_sharing_scope_label: str = "3x-ui limitIp"
    anti_sharing_policy_summary: str = "Жёсткий panel-side лимит по активным IP на ключ."
    user_selectable: bool = True
    admin_visible: bool = True
    reserve_only: bool = False
    retired: bool = False


@dataclass(frozen=True)
class RegionLimitRule:
    max_active_devices: int | None = None
    cpu_percent_soft_limit: float | None = None
    memory_percent_soft_limit: float | None = None
    disk_percent_soft_limit: float | None = None
    load_average_soft_limit: float | None = None


_REGIONS = {
    "de": Region(
        code="de",
        name_ru="Германия",
        flag="🇩🇪",
        import_name="🇩🇪 AMONORA-GERMANY",
        provider_type="xui",
        runtime_type="xui",
        runtime_service_name="3x-ui",
        anti_sharing_scope_label="3x-ui limitIp",
        anti_sharing_policy_summary="Жёсткий panel-side лимит по активным IP на ключ через 3x-ui.",
        user_selectable=True,
    ),
    "ee": Region(
        code="ee",
        name_ru="Эстония",
        flag="🇪🇪",
        import_name="🇪🇪 AMONORA-ESTONIA",
        provider_type="xui",
        runtime_type="retired",
        runtime_service_name="retired",
        anti_sharing_scope_label="3x-ui limitIp",
        anti_sharing_policy_summary="Жёсткий panel-side лимит по активным IP на ключ через x-ui.",
        user_selectable=False,
        admin_visible=True,
        reserve_only=True,
        retired=False,
    ),
    "dk": Region(
        code="dk",
        name_ru="Дания",
        flag="🇩🇰",
        import_name="🇩🇰 AMONORA-DENMARK",
        provider_type="xray_core",
        runtime_type="xray_core",
        runtime_service_name="xray",
        anti_sharing_scope_label="Xray access-log lease",
        anti_sharing_policy_summary="Lease-based anti-sharing по активным IP через Xray access-log worker.",
        user_selectable=True,
    ),
    "se": Region(
        code="se",
        name_ru="Швеция",
        flag="🇸🇪",
        import_name="🇸🇪 AMONORA-SWEDEN",
        provider_type="xui",
        runtime_type="xui",
        runtime_service_name="3x-ui",
        anti_sharing_scope_label="3x-ui limitIp",
        anti_sharing_policy_summary="Жёсткий panel-side лимит по активным IP на ключ через 3x-ui.",
        user_selectable=False,
        reserve_only=True,
    ),
}

_LEGACY_ALIASES = {
    "nl": "de",
    "нидерланды": "de",
    "дания": "dk",
}

_REGION_LIMIT_RULES = {
    "de": RegionLimitRule(),
    # Эстония — слабая резервная нода, поэтому ориентируемся на реальные ресурсы, а не на грубый лимит устройств.
    "ee": RegionLimitRule(
        cpu_percent_soft_limit=85.0,
        memory_percent_soft_limit=82.0,
        disk_percent_soft_limit=80.0,
        load_average_soft_limit=1.2,
    ),
    "dk": RegionLimitRule(),
    "se": RegionLimitRule(),
}


def normalize_country_code(country_code: str | None) -> str:
    code = (country_code or "de").strip().lower()
    code = _LEGACY_ALIASES.get(code, code)
    if code in _REGIONS:
        return code
    return "de"


def is_cross_region_change(current_country_code: str | None, target_country_code: str | None) -> bool:
    return normalize_country_code(current_country_code) != normalize_country_code(target_country_code)


def get_region(country_code: str | None) -> Region:
    return _REGIONS[normalize_country_code(country_code)]


def get_country_name(country_code: str | None) -> str:
    return get_region(country_code).name_ru


def get_country_flag(country_code: str | None) -> str:
    return get_region(country_code).flag


def get_country_import_name(country_code: str | None) -> str:
    return get_region(country_code).import_name


def build_region_snapshot(country_code: str | None) -> dict[str, str]:
    region = get_region(country_code)
    runtime_type = get_country_runtime_type(region.code)
    return {
        "country_code": region.code,
        "country_name": region.name_ru,
        "country_flag": region.flag,
        "import_name": region.import_name,
        "provider_type": runtime_type,
        "runtime_type": runtime_type,
        "runtime_service_name": get_country_runtime_service_name(region.code),
        "anti_sharing_scope_label": get_region_anti_sharing_scope_label(region.code, provider_type=runtime_type),
        "anti_sharing_policy_summary": get_region_anti_sharing_policy_summary(region.code, provider_type=runtime_type),
        "user_selectable": region.user_selectable,
        "admin_visible": region.admin_visible,
        "reserve_only": region.reserve_only,
        "retired": runtime_type == "retired" or region.retired,
        "vpn_host": get_country_vpn_host(region.code),
        "panel_url": get_country_panel_url(region.code),
    }


def get_supported_region_codes() -> list[str]:
    return [region.code for region in _REGIONS.values() if not region.retired]


def get_country_provider_type(country_code: str | None) -> str:
    return get_region(country_code).provider_type


def get_country_runtime_type(country_code: str | None) -> str:
    region = get_region(country_code)
    return str(region.runtime_type or region.provider_type).strip().lower() or region.provider_type


def get_country_runtime_service_name(country_code: str | None) -> str:
    region = get_region(country_code)
    if region.runtime_service_name:
        return region.runtime_service_name
    runtime_type = get_country_runtime_type(country_code)
    if runtime_type == "xray_core":
        return "xray"
    if runtime_type == "amneziawg":
        return "awg-quick@awg0"
    if runtime_type == "retired":
        return "retired"
    return "3x-ui"


def get_region_anti_sharing_scope_label(country_code: str | None, provider_type: str | None = None) -> str:
    normalized_provider = str(provider_type or "").strip().lower()
    if normalized_provider == "xray_core":
        return "Xray access-log lease"
    if normalized_provider == "amneziawg":
        return "AmneziaWG device binding"
    if normalized_provider == "retired":
        return "Retired region"
    if normalized_provider == "xui":
        return "3x-ui limitIp"
    return get_region(country_code).anti_sharing_scope_label


def get_region_anti_sharing_policy_summary(country_code: str | None, provider_type: str | None = None) -> str:
    normalized_provider = str(provider_type or "").strip().lower()
    if normalized_provider == "xray_core":
        return "Lease-based anti-sharing по активным IP через Xray access-log worker."
    if normalized_provider == "amneziawg":
        return "App/device activation binding без 3x-ui limitIp как общего enforcement surface."
    if normalized_provider == "retired":
        return "Регион выведен из продуктового контура и используется только как infra-host."
    if normalized_provider == "xui":
        return "Жёсткий panel-side лимит по активным IP на ключ через 3x-ui."
    return get_region(country_code).anti_sharing_policy_summary


def is_retired_region(country_code: str | None) -> bool:
    return bool(get_region(country_code).retired)


def is_region_user_selectable(country_code: str | None, *, telegram_id: int | None = None) -> bool:
    region = get_region(country_code)
    if region.user_selectable:
        return True
    if region.code == "dk" and config.enable_dk_test_flow and telegram_id in set(config.dk_test_telegram_ids):
        return True
    return False


def get_user_selectable_region_codes(*, telegram_id: int | None = None) -> list[str]:
    return [region.code for region in _REGIONS.values() if is_region_user_selectable(region.code, telegram_id=telegram_id)]


def is_legacy_country_code(country_code: str | None) -> bool:
    code = (country_code or "").strip().lower()
    return code in _LEGACY_ALIASES


def get_country_panel_url(country_code: str | None) -> str | None:
    code = normalize_country_code(country_code)
    if get_country_provider_type(code) != "xui":
        return None
    if code == "de" and config.xui_url_de:
        return config.xui_url_de
    if code == "ee" and config.xui_url_ee:
        legacy_ee_panel_url = str(config.xui_url_ee).strip()
        if legacy_ee_panel_url == "http://est.amonoraconnect.com:2053/dashboard":
            return "http://127.0.0.1:12054"
        return legacy_ee_panel_url
    return config.xui_url


def get_country_vpn_host(country_code: str | None) -> str:
    code = normalize_country_code(country_code)
    if code == "ee" and config.vpn_host_ee:
        return config.vpn_host_ee
    if code == "ee":
        return "est.amonoraconnect.com"
    if code == "dk" and config.vpn_host_dk:
        return config.vpn_host_dk
    if code == "dk":
        return "dk.amonoraconnect.com"
    if code == "de" and config.vpn_host_de:
        return config.vpn_host_de
    return config.vpn_host
def get_region_limit_rule(country_code: str | None) -> RegionLimitRule:
    return _REGION_LIMIT_RULES.get(normalize_country_code(country_code), RegionLimitRule())


def parse_load_average(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    first = raw.split("/", 1)[0].strip().replace(",", ".")
    try:
        return float(first)
    except ValueError:
        return None


def region_soft_limit_reasons(
    rule: RegionLimitRule,
    *,
    active_devices: int | None = None,
    cpu_used_percent: float | None = None,
    memory_used_percent: float | None = None,
    disk_used_percent: float | None = None,
    load_average: float | None = None,
) -> list[str]:
    reasons: list[str] = []

    if rule.max_active_devices is not None and active_devices is not None and active_devices >= rule.max_active_devices:
        reasons.append(f"активных устройств {active_devices}/{rule.max_active_devices}")
    if rule.cpu_percent_soft_limit is not None and cpu_used_percent is not None and cpu_used_percent >= rule.cpu_percent_soft_limit:
        reasons.append(f"CPU {cpu_used_percent:.1f}%")
    if rule.memory_percent_soft_limit is not None and memory_used_percent is not None and memory_used_percent >= rule.memory_percent_soft_limit:
        reasons.append(f"RAM {memory_used_percent:.1f}%")
    if rule.disk_percent_soft_limit is not None and disk_used_percent is not None and disk_used_percent >= rule.disk_percent_soft_limit:
        reasons.append(f"disk {disk_used_percent:.1f}%")
    if rule.load_average_soft_limit is not None and load_average is not None and load_average >= rule.load_average_soft_limit:
        reasons.append(f"load {load_average:.2f}/{rule.load_average_soft_limit:.2f}")

    return reasons
