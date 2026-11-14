"""Password hashing, JWT tokens and random token helpers."""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from .config import settings
from .timeutil import utcnow

ALGORITHM = "HS256"
# Crockford-style alphabet: no 0/O/1/I/L to avoid look-alike confusion when typed by hand
_TOKEN_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _prehash(password: str) -> bytes:
    # bcrypt only looks at the first 72 bytes; pre-hash so long passphrases work fully
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def new_qr_token(length: int = 12) -> str:
    """Random, unguessable badge token (12 chars from a 31 symbol alphabet ~ 59 bits)."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


def create_token(subject: str, *, kind: str, minutes: int, extra: dict[str, Any] | None = None) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
