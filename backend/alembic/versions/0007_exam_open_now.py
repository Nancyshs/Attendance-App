"""exam sittings open from the moment they are started, for a chosen number of minutes

Revision ID: 0007
Revises: 0006
"""
from datetime import datetime, timedelta
from typing import Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAIRO = ZoneInfo("Africa/Cairo")
UTC = ZoneInfo("UTC")


def _as_time(value):
    if value is None:
        return None
    if isinstance(value, timedelta):
        return (datetime.min + value).time()
    return value


def _to_utc(day, clock):
    clock = _as_time(clock)
    if day is None or clock is None:
        return None
    local = datetime.combine(day, clock).replace(tzinfo=CAIRO)
    return local.astimezone(UTC).replace(tzinfo=None)


def upgrade() -> None:
    op.add_column("sessions", sa.Column("exam_before_opens_at", sa.DateTime(), nullable=True))
    op.add_column("sessions", sa.Column("exam_before_closes_at", sa.DateTime(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_opens_at", sa.DateTime(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_closes_at", sa.DateTime(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, day, exam_before_start, exam_before_end, exam_after_start, exam_after_end FROM sessions")
    ).fetchall()
    for sid, day, before_start, before_end, after_start, after_end in rows:
        conn.execute(
            sa.text(
                """
                UPDATE sessions
                SET exam_before_opens_at = :b0, exam_before_closes_at = :b1,
                    exam_after_opens_at = :a0, exam_after_closes_at = :a1
                WHERE id = :id
                """
            ),
            {
                "id": sid,
                "b0": _to_utc(day, before_start),
                "b1": _to_utc(day, before_end),
                "a0": _to_utc(day, after_start),
                "a1": _to_utc(day, after_end),
            },
        )
    op.drop_column("sessions", "exam_before_start")
    op.drop_column("sessions", "exam_before_end")
    op.drop_column("sessions", "exam_after_start")
    op.drop_column("sessions", "exam_after_end")


def downgrade() -> None:
    op.add_column("sessions", sa.Column("exam_before_start", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_before_end", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_start", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_end", sa.Time(), nullable=True))
    op.drop_column("sessions", "exam_after_closes_at")
    op.drop_column("sessions", "exam_after_opens_at")
    op.drop_column("sessions", "exam_before_closes_at")
    op.drop_column("sessions", "exam_before_opens_at")
