import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise ValueError(f"Environment variable {name} is not set")
    return value


def get_optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value == "":
        return ""
    return value


def parse_int_list(value: str | None, default: list[int] | None = None) -> list[int]:
    if value is None or value.strip() == "":
        return list(default or [])
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_str_list(value: str | None, default: list[str] | None = None) -> list[str]:
    if value is None or value.strip() == "":
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    bot_token: str
    admin_ids: list[int]
    test_bot_token: str | None
    test_bot_allowed_telegram_ids: list[int]
    support_bot_token: str | None
    support_admin_ids: list[int]
    control_bot_token: str | None
    control_allowed_telegram_ids: list[int]
    control_owner_ids: list[int]
    control_admin_ids: list[int]
    control_operator_ids: list[int]
    control_support_view_only_ids: list[int]
    control_chat_ids: list[int]
    control_enable_payments: bool
    control_enable_nodes: bool
    control_enable_users: bool
    control_enable_access: bool
    control_enable_panel_auth: bool
    control_enable_errors: bool
    control_enable_system: bool
    control_default_cooldown_seconds: int
    control_infra_cooldown_seconds: int
    control_night_critical_only: bool
    control_night_hours: str
    control_daily_summary_enabled: bool
    control_daily_summary_hour: int
    dashboard_public_base_url: str | None
    openai_api_key: str | None
    openai_channel_model: str
    amonora_internal_channel_webhook_secret: str | None
    channel_default_post_hour: int

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_pass: str

    xui_url: str
    xui_url_de: str | None
    xui_url_ee: str | None
    xui_username: str
    xui_password: str
    xui_username_ee: str | None
    xui_password_ee: str | None

    channel_id: str
    trial_days: int
    ref_bonus_days: int
    default_mode: str
    default_protocol: str
    vpn_host: str
    vpn_host_de: str | None
    vpn_host_ee: str | None
    vpn_host_dk: str | None
    mobile_mode_override_link_de: str | None
    mobile_mode_override_link_dk: str | None
    enable_dk_test_flow: bool
    dk_test_telegram_ids: list[int]
    xray_core_dk_ssh_host: str | None
    xray_core_dk_ssh_port: int
    xray_core_dk_ssh_user: str
    xray_core_dk_ssh_key_path: str | None
    xray_core_dk_ssh_known_hosts: str | None
    xray_core_dk_ssh_timeout: float
    xray_core_dk_config_path: str
    xray_core_dk_meta_path: str
    vpn_max_devices_per_key: int
    vpn_antisharing_lease_seconds: int
    vpn_antisharing_soft_limit_enabled: bool

    stars_provider_token: str | None
    stars_currency: str
    platega_merchant_id: str | None
    platega_secret_key: str | None
    platega_base_url: str
    platega_webhook_secret: str | None
    platega_callback_max_age_seconds: int
    enable_platega_sbp_user_flow: bool
    enable_platega_crypto_user_flow: bool
    enable_manual_sbp_user_flow: bool
    enable_manual_crypto_user_flow: bool
    force_manual_sbp_user_flow: bool
    crypto_pay_api_token: str | None
    enable_crypto_pay_user_flow: bool
    enable_legacy_crypto_pay_webhook: bool
    crypto_pay_base_url: str
    crypto_pay_webhook_secret: str | None
    crypto_pay_accepted_assets: str
    crypto_pay_swap_to: str | None
    crypto_pay_invoice_expires_seconds: int
    crypto_pay_webhook_max_age_seconds: int
    manual_sbp_details: str | None
    manual_crypto_details: str | None
    manual_payment_review_hours: int
    tariff_1m_rub: int
    tariff_3m_rub: int
    tariff_6m_rub: int
    tariff_12m_rub: int
    device_slot_unit_price_rub: int
    device_slot_max_extra_slots: int
    tariff_1m_stars: int
    tariff_3m_stars: int
    tariff_6m_stars: int
    tariff_12m_stars: int
    referral_share_text: str
    referral_reward_invited_text: str
    referral_reward_referrer_template: str
    referral_push_webhook_url: str | None
    referral_push_webhook_token: str | None
    referral_push_timeout_seconds: float

    @property
    def database_url(self) -> str:
        db_host = "127.0.0.1" if self.db_host.strip().lower() == "localhost" else self.db_host
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_pass}"
            f"@{db_host}:{self.db_port}/{self.db_name}"
        )

_admin_ids = parse_int_list(get_env("ADMIN_IDS"))
_control_owner_ids = parse_int_list(get_optional_env("AMONORA_CONTROL_OWNER_IDS"))
_control_admin_ids = parse_int_list(get_optional_env("AMONORA_CONTROL_ADMIN_IDS"))
_control_operator_ids = parse_int_list(get_optional_env("AMONORA_CONTROL_OPERATOR_IDS"))
_control_support_view_only_ids = parse_int_list(get_optional_env("AMONORA_CONTROL_SUPPORT_VIEW_ONLY_IDS"))
_control_default_allowed_ids = list(
    dict.fromkeys(
        [
            *_control_owner_ids,
            *_control_admin_ids,
            *_control_operator_ids,
            *_control_support_view_only_ids,
        ]
    )
)


config = Config(
    bot_token=get_env("BOT_TOKEN"),
    admin_ids=_admin_ids,
    test_bot_token=get_optional_env("AMONORA_TEST_BOT_TOKEN"),
    test_bot_allowed_telegram_ids=parse_int_list(get_optional_env("AMONORA_TEST_BOT_ALLOWED_TELEGRAM_IDS"), _admin_ids),
    support_bot_token=get_optional_env("SUPPORT_BOT_TOKEN"),
    support_admin_ids=parse_int_list(get_optional_env("SUPPORT_ADMIN_IDS"), _admin_ids),
    control_bot_token=get_optional_env("AMONORA_CONTROL_BOT_TOKEN"),
    control_allowed_telegram_ids=parse_int_list(
        get_optional_env("AMONORA_CONTROL_ALLOWED_TELEGRAM_IDS"),
        _control_default_allowed_ids,
    ),
    control_owner_ids=_control_owner_ids,
    control_admin_ids=_control_admin_ids,
    control_operator_ids=_control_operator_ids,
    control_support_view_only_ids=_control_support_view_only_ids,
    control_chat_ids=parse_int_list(get_optional_env("AMONORA_CONTROL_CHAT_IDS")),
    control_enable_payments=get_optional_env("AMONORA_CONTROL_ENABLE_PAYMENTS", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_nodes=get_optional_env("AMONORA_CONTROL_ENABLE_NODES", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_users=get_optional_env("AMONORA_CONTROL_ENABLE_USERS", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_access=get_optional_env("AMONORA_CONTROL_ENABLE_ACCESS", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_panel_auth=get_optional_env("AMONORA_CONTROL_ENABLE_PANEL_AUTH", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_errors=get_optional_env("AMONORA_CONTROL_ENABLE_ERRORS", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_enable_system=get_optional_env("AMONORA_CONTROL_ENABLE_SYSTEM", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    control_default_cooldown_seconds=int(get_env("AMONORA_CONTROL_DEFAULT_COOLDOWN_SECONDS", "300")),
    control_infra_cooldown_seconds=int(get_env("AMONORA_CONTROL_INFRA_COOLDOWN_SECONDS", "900")),
    control_night_critical_only=get_optional_env("AMONORA_CONTROL_NIGHT_CRITICAL_ONLY", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    control_night_hours=get_env("AMONORA_CONTROL_NIGHT_HOURS", "00-07"),
    control_daily_summary_enabled=get_optional_env("AMONORA_CONTROL_DAILY_SUMMARY_ENABLED", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    control_daily_summary_hour=int(get_env("AMONORA_CONTROL_DAILY_SUMMARY_HOUR", "9")),
    dashboard_public_base_url=get_optional_env("DASHBOARD_PUBLIC_BASE_URL"),
    openai_api_key=get_optional_env("OPENAI_API_KEY", ""),
    openai_channel_model=get_env("OPENAI_CHANNEL_MODEL", "gpt-4.1-mini"),
    amonora_internal_channel_webhook_secret=get_optional_env("AMONORA_INTERNAL_CHANNEL_WEBHOOK_SECRET", ""),
    channel_default_post_hour=int(get_env("AMONORA_CHANNEL_DEFAULT_POST_HOUR", "12")),
    db_host=get_env("DB_HOST"),
    db_port=int(get_env("DB_PORT")),
    db_name=get_env("DB_NAME"),
    db_user=get_env("DB_USER"),
    db_pass=get_env("DB_PASS"),
    xui_url=get_env("XUI_URL"),
    xui_url_de=get_optional_env("XUI_URL_DE"),
    xui_url_ee=get_optional_env("XUI_URL_EE"),
    xui_username=get_env("XUI_USERNAME"),
    xui_password=get_env("XUI_PASSWORD"),
    xui_username_ee=get_optional_env("XUI_USERNAME_EE"),
    xui_password_ee=get_optional_env("XUI_PASSWORD_EE"),
    channel_id=get_env("CHANNEL_ID"),
    trial_days=int(get_env("TRIAL_DAYS", "3")),
    ref_bonus_days=int(get_env("REF_BONUS_DAYS", "3")),
    default_mode=get_env("DEFAULT_MODE", "stable"),
    default_protocol=get_env("DEFAULT_PROTOCOL", "vless"),
    vpn_host=get_env("VPN_HOST"),
    vpn_host_de=get_optional_env("VPN_HOST_DE"),
    vpn_host_ee=get_optional_env("VPN_HOST_EE"),
    vpn_host_dk=get_optional_env("VPN_HOST_DK"),
    mobile_mode_override_link_de=get_optional_env("MOBILE_MODE_OVERRIDE_LINK_DE"),
    mobile_mode_override_link_dk=get_optional_env("MOBILE_MODE_OVERRIDE_LINK_DK"),
    enable_dk_test_flow=get_optional_env("ENABLE_DK_TEST_FLOW", "0").strip().lower() in {"1", "true", "yes", "on"},
    dk_test_telegram_ids=parse_int_list(get_optional_env("DK_TEST_TELEGRAM_IDS")),
    xray_core_dk_ssh_host=get_optional_env("XRAY_CORE_DK_SSH_HOST", ""),
    xray_core_dk_ssh_port=int(get_env("XRAY_CORE_DK_SSH_PORT", "22")),
    xray_core_dk_ssh_user=get_env("XRAY_CORE_DK_SSH_USER", "root"),
    xray_core_dk_ssh_key_path=get_optional_env("XRAY_CORE_DK_SSH_KEY_PATH", ""),
    xray_core_dk_ssh_known_hosts=get_optional_env("XRAY_CORE_DK_SSH_KNOWN_HOSTS", ""),
    xray_core_dk_ssh_timeout=float(get_env("XRAY_CORE_DK_SSH_TIMEOUT", "8")),
    xray_core_dk_config_path=get_env("XRAY_CORE_DK_CONFIG_PATH", "/usr/local/etc/xray/config.json"),
    xray_core_dk_meta_path=get_env("XRAY_CORE_DK_META_PATH", "/usr/local/etc/xray/amonora_dk_meta.json"),
    vpn_max_devices_per_key=max(int(get_env("VPN_MAX_DEVICES_PER_KEY", "1")), 1),
    vpn_antisharing_lease_seconds=max(int(get_env("VPN_ANTISHARING_LEASE_SECONDS", "180")), 30),
    vpn_antisharing_soft_limit_enabled=get_optional_env("VPN_ANTISHARING_SOFT_LIMIT_ENABLED", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    stars_provider_token=get_optional_env("STARS_PROVIDER_TOKEN", ""),
    stars_currency=get_env("STARS_CURRENCY", "XTR"),
    platega_merchant_id=get_optional_env("PLATEGA_MERCHANT_ID", ""),
    platega_secret_key=get_optional_env("PLATEGA_SECRET_KEY", ""),
    platega_base_url=get_env("PLATEGA_BASE_URL", "https://app.platega.io"),
    platega_webhook_secret=get_optional_env("PLATEGA_WEBHOOK_SECRET", ""),
    platega_callback_max_age_seconds=int(get_env("PLATEGA_CALLBACK_MAX_AGE_SECONDS", "1800")),
    enable_platega_sbp_user_flow=get_optional_env("ENABLE_PLATEGA_SBP_USER_FLOW", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    enable_platega_crypto_user_flow=get_optional_env("ENABLE_PLATEGA_CRYPTO_USER_FLOW", "1").strip().lower()
    in {"1", "true", "yes", "on"},
    enable_manual_sbp_user_flow=get_optional_env("ENABLE_MANUAL_SBP_USER_FLOW", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    enable_manual_crypto_user_flow=get_optional_env("ENABLE_MANUAL_CRYPTO_USER_FLOW", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    force_manual_sbp_user_flow=get_optional_env("FORCE_MANUAL_SBP_USER_FLOW", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    crypto_pay_api_token=get_optional_env("CRYPTO_PAY_API_TOKEN", ""),
    enable_crypto_pay_user_flow=get_optional_env("ENABLE_CRYPTO_PAY_USER_FLOW", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    enable_legacy_crypto_pay_webhook=get_optional_env("ENABLE_LEGACY_CRYPTO_PAY_WEBHOOK", "0").strip().lower()
    in {"1", "true", "yes", "on"},
    crypto_pay_base_url=get_env("CRYPTO_PAY_BASE_URL", "https://pay.crypt.bot/api"),
    crypto_pay_webhook_secret=get_optional_env("CRYPTO_PAY_WEBHOOK_SECRET", ""),
    crypto_pay_accepted_assets=get_env("CRYPTO_PAY_ACCEPTED_ASSETS", "USDT,TON"),
    crypto_pay_swap_to=get_optional_env("CRYPTO_PAY_SWAP_TO", ""),
    crypto_pay_invoice_expires_seconds=int(get_env("CRYPTO_PAY_INVOICE_EXPIRES_SECONDS", "3600")),
    crypto_pay_webhook_max_age_seconds=int(get_env("CRYPTO_PAY_WEBHOOK_MAX_AGE_SECONDS", "900")),
    manual_sbp_details=get_optional_env("MANUAL_SBP_DETAILS", ""),
    manual_crypto_details=get_optional_env("MANUAL_CRYPTO_DETAILS", ""),
    manual_payment_review_hours=int(get_env("MANUAL_PAYMENT_REVIEW_HOURS", "12")),
    tariff_1m_rub=int(get_env("TARIFF_1M_RUB", "149")),
    tariff_3m_rub=int(get_env("TARIFF_3M_RUB", "399")),
    tariff_6m_rub=int(get_env("TARIFF_6M_RUB", "749")),
    tariff_12m_rub=int(get_env("TARIFF_12M_RUB", "1390")),
    device_slot_unit_price_rub=max(int(get_env("DEVICE_SLOT_UNIT_PRICE_RUB", "49")), 1),
    device_slot_max_extra_slots=max(int(get_env("DEVICE_SLOT_MAX_EXTRA_SLOTS", "5")), 0),
    tariff_1m_stars=int(get_env("TARIFF_1M_STARS", "299")),
    tariff_3m_stars=int(get_env("TARIFF_3M_STARS", "799")),
    tariff_6m_stars=int(get_env("TARIFF_6M_STARS", "1499")),
    tariff_12m_stars=int(get_env("TARIFF_12M_STARS", "2799")),
    referral_share_text=get_optional_env(
        "REFERRAL_SHARE_TEXT",
        "Лучший сервис для доступа\nПереходи и получай бонусные рубли 👇",
    )
    or "",
    referral_reward_invited_text=get_optional_env(
        "REFERRAL_REWARD_INVITED_TEXT",
        "Вам начислены бонусные рубли",
    )
    or "",
    referral_reward_referrer_template=get_optional_env(
        "REFERRAL_REWARD_REFERRER_TEMPLATE",
        "Ваш друг оплатил, вам начислено {bonus_rub} бонусных рублей",
    )
    or "",
    referral_push_webhook_url=get_optional_env("REFERRAL_PUSH_WEBHOOK_URL", ""),
    referral_push_webhook_token=get_optional_env("REFERRAL_PUSH_WEBHOOK_TOKEN", ""),
    referral_push_timeout_seconds=float(get_env("REFERRAL_PUSH_TIMEOUT_SECONDS", "5")),
)
