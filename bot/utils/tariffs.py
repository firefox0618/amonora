from dataclasses import dataclass
from datetime import datetime

from bot.config import config


PROMO_DATE_RANGE_LABEL = ""


@dataclass(frozen=True)
class Tariff:
    code: str
    title: str
    duration_days: int
    rub_price: int
    stars_price: int


BASE_TARIFF_SPECS = {
    "1m": {"title": "1 месяц", "duration_days": 30},
    "3m": {"title": "3 месяца", "duration_days": 90},
    "6m": {"title": "6 месяцев", "duration_days": 180},
    "12m": {"title": "12 месяцев", "duration_days": 365},
}

BASE_MONTHS_BY_CODE = {
    "1m": 1,
    "3m": 3,
    "6m": 6,
    "12m": 12,
}

BASE_MONTHS_BY_TITLE = {
    "1 месяц": 1,
    "3 месяца": 3,
    "6 месяцев": 6,
    "12 месяцев": 12,
}


def current_promo_now() -> datetime:
    return datetime.now()


def promo_active(now: datetime | None = None) -> bool:
    return False


def gifted_months_for_tariff(value: str | None, *, now: datetime | None = None) -> int:
    return 0


def total_months_for_tariff(value: str | None, *, now: datetime | None = None) -> int | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in BASE_MONTHS_BY_CODE:
        return BASE_MONTHS_BY_CODE[normalized]
    for title, months in BASE_MONTHS_BY_TITLE.items():
        if normalized == title.lower():
            return months
    return None


def gift_duration_days(base_days: int, value: str | None, *, now: datetime | None = None) -> int:
    return int(base_days)


def _month_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "месяц"
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return "месяца"
    return "месяцев"


def promo_tariff_offer_lines(
    *,
    now: datetime | None = None,
    bullets: bool = False,
    html: bool = False,
    include_gift_wording: bool = True,
) -> list[str]:
    return []


def promo_tariff_offer_block(
    *,
    now: datetime | None = None,
    bullets: bool = False,
    html: bool = False,
    include_gift_wording: bool = True,
) -> str:
    return "\n".join(
        promo_tariff_offer_lines(
            now=now,
            bullets=bullets,
            html=html,
            include_gift_wording=include_gift_wording,
        )
    )


def marketing_tariff_title(title: str, code: str | None = None, *, now: datetime | None = None) -> str:
    return title


def tariff_duration_badge(title: str, code: str | None = None, *, now: datetime | None = None) -> str | None:
    return None


def get_tariff(code: str) -> Tariff | None:
    normalized = str(code or "").strip().lower()
    spec = BASE_TARIFF_SPECS.get(normalized)
    if spec is None:
        return None
    return Tariff(
        code=normalized,
        title=str(spec["title"]),
        duration_days=gift_duration_days(int(spec["duration_days"]), normalized),
        rub_price=getattr(config, f"tariff_{normalized}_rub"),
        stars_price=getattr(config, f"tariff_{normalized}_stars"),
    )


def get_tariffs_list() -> list[Tariff]:
    rows: list[Tariff] = []
    for code in ("1m", "3m", "6m", "12m"):
        tariff = get_tariff(code)
        if tariff is not None:
            rows.append(tariff)
    return rows
