"""Business settings stored in the database with a small in-process cache.

Scanning happens in bursts, so settings are cached for a few seconds instead of
being re-read on every request.
"""
from __future__ import annotations

import threading
import time as _time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Setting

DEFAULTS: dict[str, Any] = {
    "program_name": "برنامج التدريب",
    "day_start_time": "09:00",
    "day_end_time": "17:00",
    "late_after_minutes": 15,
    "checkout_from_time": "16:00",
    "min_checkout_gap_minutes": 20,
    # Python weekday numbers: Mon=0 ... Sun=6.  Default working week: Sun-Thu
    "working_weekdays": [6, 0, 1, 2, 3],
    "survey_program_name": "البرنامج التدريبي المتكامل لتنمية القدرات الفنية والإدارية في مجالات إدارة المخلفات الصلبة والتغيرات المناخية والاقتصاد الدائري",
    "survey_duration_minutes": 30,
    "survey_opens_minutes_before_end": 0,
    "survey_close_hours_after_end": 24,
    "require_attendance_for_survey": True,
    "absence_alert_threshold": 3,
    "low_rating_threshold": 3.5,
}

_CACHE_TTL = 15.0
_lock = threading.Lock()
_cache: dict[str, Any] = {}
_cache_at: float = 0.0


def _load(db: Session) -> dict[str, Any]:
    values = dict(DEFAULTS)
    for row in db.scalars(select(Setting)):
        if row.key in DEFAULTS:
            values[row.key] = row.value
    return values


def get_all(db: Session) -> dict[str, Any]:
    global _cache, _cache_at
    now = _time.monotonic()
    with _lock:
        if _cache and now - _cache_at < _CACHE_TTL:
            return dict(_cache)
    values = _load(db)
    with _lock:
        _cache, _cache_at = values, now
    return dict(values)


def get(db: Session, key: str) -> Any:
    return get_all(db)[key]


def update(db: Session, changes: dict[str, Any]) -> dict[str, Any]:
    global _cache_at
    for key, value in changes.items():
        if key not in DEFAULTS:
            continue
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    with _lock:
        _cache_at = 0.0  # invalidate
    return get_all(db)


def invalidate() -> None:
    global _cache_at
    with _lock:
        _cache_at = 0.0
