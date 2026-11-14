"""Time helpers.

Rule of the house: every timestamp is stored in UTC and handled as a timezone
aware ``datetime`` in Python. Business concepts that are inherently local
("the training day", "09:00 start") are stored as plain date/time values and
interpreted in the configured timezone (default: Africa/Cairo).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from .config import settings

UTC = timezone.utc


@lru_cache
def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(local_tz())


def local_today() -> date:
    return to_local(utcnow()).date()


def local_datetime_to_utc(day: date, at: time) -> datetime:
    """Interpret ``day`` + ``at`` as Cairo wall-clock time and convert to UTC."""
    naive = datetime.combine(day, at.replace(tzinfo=None))
    return naive.replace(tzinfo=local_tz()).astimezone(UTC)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = local_datetime_to_utc(day, time(0, 0))
    end = local_datetime_to_utc(day + timedelta(days=1), time(0, 0))
    return start, end


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")[:2]
    return time(int(hh), int(mm))


def round_to_hour(dt: datetime) -> datetime:
    """Used to blur timestamps of anonymous survey responses."""
    return as_utc(dt).replace(minute=0, second=0, microsecond=0)
