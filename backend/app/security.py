"""Password hashing (stdlib scrypt) and JWT access tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from .config import settings

# scrypt parameters (n=2**14, r=8, p=1 ≈ 16 MiB, tens of ms per hash): the
# interactive-login profile recommended by the scrypt paper / OWASP.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_JWT_ALGORITHM = "HS256"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, _unb64(digest))


# Verifying against this when the user doesn't exist keeps login timing uniform,
# so response time doesn't reveal which emails have accounts.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> dict:
    """Decode and verify a token. Raises jwt.PyJWTError if invalid or expired."""
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM], options={"require": ["exp", "sub"]}
    )
