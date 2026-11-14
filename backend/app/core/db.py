"""Database engine / session management.

Tuned for bursts: a bounded connection pool, ``pool_pre_ping`` so stale
connections never surface as errors, READ COMMITTED to keep row locks short
and avoid gap-lock contention when ~50 people scan at the same second.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in the database, always returns tz-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: D401
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def _build_engine():
    url = settings.database_url
    kwargs: dict = {
        "pool_pre_ping": True,
        "pool_recycle": settings.db_pool_recycle,
        "isolation_level": "READ COMMITTED",
        "future": True,
    }
    if url.startswith("mysql"):
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            connect_args={
                "connect_timeout": 10,
                "read_timeout": 30,
                "write_timeout": 30,
                "init_command": "SET time_zone = '+00:00'",
            },
        )
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
