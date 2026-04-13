from __future__ import annotations

from dataclasses import dataclass
from secrets import choice
from string import ascii_lowercase, digits


REFERRAL_LINK_PREFIX = "https://t.me/amonora_bot?start=ref_"
REFERRAL_CODE_ALPHABET = ascii_lowercase + digits
REFERRAL_CODE_LENGTH = 10
REFERRAL_BONUS_BY_TARIFF = {
    "1m": 50,
    "3m": 50,
    "6m": 50,
    "12m": 100,
}
REFERRAL_LEVELS = [
    ("Без уровня", 0, 0),
    ("Новичок", 1, 3),
    ("Продвинутый", 4, 10),
    ("Партнер", 11, None),
]


@dataclass(frozen=True)
class ReferralDashboard:
    ref_link: str
    balance_rub: int
    earned_total_rub: int
    invited_count: int
    paid_count: int
    current_level_name: str
    next_level_name: str | None
    left_to_next_level: int
    progress_percent: int
    progress_bar: str


@dataclass(frozen=True)
class ReferralRewardOutcome:
    applied: bool
    referrer_user_id: int | None
    invited_user_id: int | None
    referrer_telegram_id: int | None
    invited_telegram_id: int | None
    bonus_referrer_rub: int
    bonus_invited_rub: int
    referrer_balance_rub: int
    invited_balance_rub: int
    tariff_code: str | None
    tariff_title: str | None


def generate_ref_code(length: int = REFERRAL_CODE_LENGTH) -> str:
    return "".join(choice(REFERRAL_CODE_ALPHABET) for _ in range(max(int(length), 6)))


def referral_bonus_for_tariff(tariff_code: str | None) -> int:
    return int(REFERRAL_BONUS_BY_TARIFF.get(str(tariff_code or "").strip().lower(), 0))


def build_referral_link(ref_code: str) -> str:
    return f"{REFERRAL_LINK_PREFIX}{ref_code}"


def render_progress_bar(percent: int, size: int = 10) -> str:
    safe_percent = max(min(int(percent), 100), 0)
    filled = round(size * safe_percent / 100)
    return "[" + "█" * filled + "░" * (size - filled) + "]"


def calc_level(paid_count: int) -> tuple[str, str | None, int, int]:
    paid_total = max(int(paid_count), 0)
    if paid_total <= 0:
        return "Без уровня", "Новичок", 1, 0

    if 1 <= paid_total <= 3:
        left = max(4 - paid_total, 0)
        percent = min(int((paid_total / 3) * 100), 100)
        return "Новичок", "Продвинутый", left, percent

    if 4 <= paid_total <= 10:
        left = max(11 - paid_total, 0)
        percent = min(int(((paid_total - 4) / 6) * 100), 100)
        return "Продвинутый", "Партнер", left, percent

    return "Партнер", None, 0, 100
