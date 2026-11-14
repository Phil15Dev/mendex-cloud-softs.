import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

SESSION_MAX = timedelta(hours=24)     # maximum session lifetime
IDLE_TIMEOUT = timedelta(minutes=30)  # sign out after 30 minutes without activity
RESET_TTL = timedelta(minutes=15)     # password-reset link lifetime
MIN_PASSWORD = 10

_ph = PasswordHasher()  # Argon2id
DUMMY_HASH = _ph.hash("not-a-real-password")  # verified when the username is unknown (equal timing)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token_for(session_token: str) -> str:
    """CSRF token derived from the session token with the server secret (not stored)."""
    return hmac.new(settings.secret_key.encode(), f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def password_problem(password: str):
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > 200:
        return "That password is too long."
    return None
