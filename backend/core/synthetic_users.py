from __future__ import annotations

from sqlalchemy import and_, func, or_

from backend.core.models import User


SYNTHETIC_USER_PREFIXES = ("manual_payment_", "smoke_", "test_", "debug_", "seed_", "bridge_")


def is_synthetic_username(username: str | None) -> bool:
    normalized = str(username or "").strip().lower()
    return any(normalized.startswith(prefix) for prefix in SYNTHETIC_USER_PREFIXES)


def is_synthetic_user(user: User | None) -> bool:
    if user is None:
        return False
    if bool(getattr(user, "is_synthetic", False)):
        return True
    return is_synthetic_username(getattr(user, "username", None))


def synthetic_username_sql_predicates(column) -> tuple:
    normalized = func.lower(func.coalesce(column, ""))
    return tuple(normalized.like(f"{prefix}%") for prefix in SYNTHETIC_USER_PREFIXES)


def real_user_sql_clause(model=User):
    username_clause = ~or_(*synthetic_username_sql_predicates(model.username))
    if hasattr(model, "is_synthetic"):
        return and_(func.coalesce(model.is_synthetic, False).is_(False), username_clause)
    return username_clause
