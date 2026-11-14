"""Trainee name rules shared by registration and the public survey gate."""
from __future__ import annotations

from ..core.errors import ServiceError

TRIPLE_NAME_ERROR = "يرجى إدخال الاسم ثلاثي."


def require_triple_name(value: str) -> str:
    """Keep a name only when it is three words, and return it with single spaces."""
    parts = str(value or "").split()
    if len(parts) != 3:
        raise ServiceError(TRIPLE_NAME_ERROR, code="triple_name")
    return " ".join(parts)
