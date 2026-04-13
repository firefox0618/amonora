import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    # Keep the existing naive-UTC behavior for the current SQLAlchemy/session code
    # while sourcing time from a timezone-aware clock.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str, salt: str | None = None) -> str:
    effective_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        effective_salt.encode("utf-8"),
        200_000,
    )
    return f"{effective_salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected = password_hash.split("$", 1)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def generate_code(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def session_expiry(hours: int = 24) -> datetime:
    return utcnow() + timedelta(hours=hours)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
