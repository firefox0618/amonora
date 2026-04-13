from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4


_CURRENT_TRACE_ID: ContextVar[str | None] = ContextVar("amonora_trace_id", default=None)


def normalize_trace_id(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, bytes):
        try:
            value = raw_value.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
    else:
        value = str(raw_value or "").strip()
    if not value:
        return None
    return value[:64]


def new_trace_id(prefix: str = "req") -> str:
    normalized_prefix = str(prefix or "req").strip().lower() or "req"
    return f"{normalized_prefix}:{uuid4().hex}"[:64]


def set_current_trace_id(trace_id: str | None) -> Token:
    return _CURRENT_TRACE_ID.set(normalize_trace_id(trace_id))


def reset_current_trace_id(token: Token) -> None:
    _CURRENT_TRACE_ID.reset(token)


def get_current_trace_id() -> str | None:
    return normalize_trace_id(_CURRENT_TRACE_ID.get())


def current_or_new_trace_id(raw_value: object = None, *, prefix: str = "req") -> str:
    return normalize_trace_id(raw_value) or get_current_trace_id() or new_trace_id(prefix)
