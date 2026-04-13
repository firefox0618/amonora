from bot.config import config


def sbp_tariff_uses_platega() -> bool:
    return bool(config.enable_platega_sbp_user_flow)


def sbp_tariff_uses_manual() -> bool:
    return bool(config.enable_manual_sbp_user_flow)


def sbp_balance_topup_uses_platega() -> bool:
    return bool(config.enable_platega_sbp_user_flow)


def sbp_manual_emergency_fallback_active() -> bool:
    return bool(config.force_manual_sbp_user_flow and config.enable_manual_sbp_user_flow)
