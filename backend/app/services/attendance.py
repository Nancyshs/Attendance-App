"""Attendance core: scanning (check-in / check-out once per day) and status derivation.

Concurrency design (the whole point of this module):

* A scan is ONE short transaction. No network calls, no heavy work inside it.
* ``UNIQUE(trainee_id, day)`` is the arbiter. We try to INSERT the check-in and, if the
  unique key says somebody (another worker / a double scan) got there first, we fall back
  to the "second scan" logic. There is no read-then-write race.
* Check-out is a conditional ``UPDATE ... WHERE check_out_at IS NULL`` so two simultaneous
  check-out scans can never both "win".
* ``client_id`` makes retries idempotent (flaky Wi-Fi, offline queue replays).
* Deadlocks / lock timeouts (MySQL 1213 / 1205) are retried transparently.
"""
from __future__ import annotations

import random
import re
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..core.timeutil import (
    as_utc,
    local_datetime_to_utc,
    parse_hhmm,
    to_local,
    utcnow,
)
from ..models import AttendanceDay, ScanLog, Trainee, TrainingDay, User
from . import settings as settings_service

BADGE_ID_RE = re.compile(r"^[A-Z]\d{2,3}$")
RETRYABLE_MYSQL_CODES = {1213, 1205}  # deadlock, lock wait timeout
MAX_ATTEMPTS = 4


# ------------------------------------------------------------------ input handling
def extract_token(raw: str) -> str:
    """Accepts a bare token, a badge id, or the full badge URL (https://host/t/<TOKEN>)."""
    value = (raw or "").strip().strip("\r\n\t ")
    if not value:
        return ""
    if "/" in value:
        value = value.split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[-1]
    return value.strip().upper()[:64]


# ------------------------------------------------------------------- training days
def default_day_values(cfg: dict[str, Any]) -> dict[str, time]:
    start = parse_hhmm(cfg["day_start_time"])
    late_dt = datetime.combine(date.today(), start) + timedelta(minutes=int(cfg["late_after_minutes"]))
    return {
        "start_time": start,
        "end_time": parse_hhmm(cfg["day_end_time"]),
        "late_after": late_dt.time(),
        "checkout_from": parse_hhmm(cfg["checkout_from_time"]),
    }


def get_or_create_training_day(db: Session, day: date, *, auto: bool = True) -> TrainingDay | None:
    """Returns the training day, auto-creating it on working weekdays.

    Auto-creation means a forgotten schedule entry never blocks the door scanner.
    """
    existing = db.scalar(select(TrainingDay).where(TrainingDay.date == day))
    if existing or not auto:
        return existing
    cfg = settings_service.get_all(db)
    if day.weekday() not in cfg["working_weekdays"]:
        return None
    values = default_day_values(cfg)
    try:
        with db.begin_nested():
            td = TrainingDay(date=day, is_auto=True, **values)
            db.add(td)
            db.flush()
        return td
    except IntegrityError:  # another request created it first
        return db.scalar(select(TrainingDay).where(TrainingDay.date == day))


# --------------------------------------------------------------------- classification
@dataclass
class Classification:
    status: str  # present|late|absent|excused|not_arrived|upcoming
    early_leave: bool = False
    incomplete: bool = False
    worked_minutes: int | None = None


def day_is_over(day: TrainingDay, now: datetime) -> bool:
    local_now = to_local(now)
    if local_now.date() > day.date:
        return True
    return local_now.date() == day.date and local_now.time() > day.end_time


def classify(row: AttendanceDay | None, day: TrainingDay, now: datetime | None = None) -> Classification:
    now = now or utcnow()
    local_now = to_local(now)
    over = day_is_over(day, now)

    if row is None or row.check_in_at is None:
        if row is not None and row.excused:
            return Classification("excused")
        if local_now.date() < day.date:
            return Classification("upcoming")
        return Classification("absent" if over else "not_arrived")

    check_in_local = to_local(row.check_in_at).time()
    late = check_in_local > day.late_after
    status = "late" if late else "present"
    if row.excused and late:
        status = "excused"

    early_leave = False
    incomplete = False
    worked = None
    if row.check_out_at is not None:
        early_leave = to_local(row.check_out_at).time() < day.checkout_from
        worked = max(0, int((as_utc(row.check_out_at) - as_utc(row.check_in_at)).total_seconds() // 60))
    elif over:
        incomplete = True
    return Classification(status, early_leave, incomplete, worked)


# ------------------------------------------------------------------------ scanning
def _trainee_payload(t: Trainee | None) -> dict[str, Any] | None:
    if t is None:
        return None
    return {
        "id": t.id,
        "badge_id": t.badge_id,
        "full_name": t.full_name,
        "group_name": t.group_name,
        "photo_url": f"/media/{t.photo_path}" if t.photo_path else None,
    }


def _iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat().replace("+00:00", "Z") if dt else None


def _payload(
    *,
    ok: bool,
    action: str,
    code: str,
    message: str,
    trainee: Trainee | None = None,
    row: AttendanceDay | None = None,
    status: str | None = None,
    early_leave: bool = False,
    scanned_at: datetime | None = None,
) -> dict[str, Any]:
    worked = None
    if row is not None and row.check_in_at and row.check_out_at:
        worked = max(0, int((as_utc(row.check_out_at) - as_utc(row.check_in_at)).total_seconds() // 60))
    return {
        "ok": ok,
        "action": action,
        "code": code,
        "message": message,
        "status": status,
        "early_leave": early_leave,
        "trainee": _trainee_payload(trainee),
        "check_in_at": _iso(row.check_in_at) if row else None,
        "check_out_at": _iso(row.check_out_at) if row else None,
        "worked_minutes": worked,
        "scanned_at": _iso(scanned_at),
        "replayed": False,
    }


def _hhmm(dt: datetime | None) -> str:
    return to_local(dt).strftime("%H:%M") if dt else "--:--"


def _is_retryable(exc: OperationalError) -> bool:
    orig = getattr(exc, "orig", None)
    code = orig.args[0] if orig is not None and getattr(orig, "args", None) else None
    return code in RETRYABLE_MYSQL_CODES


def process_scan(
    db: Session,
    *,
    raw: str,
    mode: str,
    source: str,
    user: User | None,
    scanned_at: datetime | None = None,
    client_id: str | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Public entry point with transparent retry on deadlocks."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _process_scan_once(
                db,
                raw=raw,
                mode=mode,
                source=source,
                user=user,
                scanned_at=scanned_at,
                client_id=client_id,
                device=device,
            )
        except OperationalError as exc:
            db.rollback()
            if _is_retryable(exc) and attempt < MAX_ATTEMPTS:
                _time.sleep(0.03 * attempt + random.random() * 0.05)
                continue
            raise
    raise RuntimeError("unreachable")  # pragma: no cover


def _log(
    db: Session,
    *,
    payload: dict[str, Any],
    raw: str,
    trainee: Trainee | None,
    source: str,
    device: str | None,
    user: User | None,
    scanned_at: datetime,
    client_id: str | None,
) -> None:
    db.add(
        ScanLog(
            client_id=client_id,
            trainee_id=trainee.id if trainee else None,
            raw_input=(raw or "")[:190],
            action=payload["action"],
            ok=payload["ok"],
            code=payload["code"],
            message=payload["message"][:255],
            source=source,
            device=(device or "")[:64] or None,
            scanned_by=user.id if user else None,
            scanned_at=scanned_at,
            result=payload,
        )
    )


def _process_scan_once(
    db: Session,
    *,
    raw: str,
    mode: str,
    source: str,
    user: User | None,
    scanned_at: datetime | None,
    client_id: str | None,
    device: str | None,
) -> dict[str, Any]:
    server_now = utcnow()

    # Idempotency: a retried request returns the original answer instead of acting twice.
    if client_id:
        previous = db.scalar(select(ScanLog).where(ScanLog.client_id == client_id))
        if previous is not None and previous.result:
            return {**previous.result, "replayed": True}

    # Offline-queue replays carry their original time; refuse anything absurd.
    now = server_now
    if scanned_at is not None:
        candidate = as_utc(scanned_at)
        if server_now - timedelta(hours=48) <= candidate <= server_now + timedelta(seconds=90):
            now = candidate

    token = extract_token(raw)
    trainee: Trainee | None = None
    if token:
        trainee = db.scalar(select(Trainee).where(Trainee.qr_token == token))
        if trainee is None and BADGE_ID_RE.match(token):
            trainee = db.scalar(select(Trainee).where(Trainee.badge_id == token))
            if trainee is not None:
                source = "manual"

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        _log(
            db,
            payload=payload,
            raw=raw,
            trainee=trainee,
            source=source,
            device=device,
            user=user,
            scanned_at=now,
            client_id=client_id,
        )
        try:
            db.commit()
        except IntegrityError:
            # same client_id arrived twice at the same instant: serve the first result
            db.rollback()
            if client_id:
                first = db.scalar(select(ScanLog).where(ScanLog.client_id == client_id))
                if first is not None and first.result:
                    return {**first.result, "replayed": True}
            raise
        return payload

    if trainee is None:
        return finish(
            _payload(ok=False, action="rejected", code="unknown_badge", message="الباج غير معروف", scanned_at=now)
        )
    if not trainee.is_active:
        return finish(
            _payload(
                ok=False,
                action="rejected",
                code="inactive",
                message="هذا المتدرب موقوف",
                trainee=trainee,
                scanned_at=now,
            )
        )

    day_date = to_local(now).date()
    training_day = get_or_create_training_day(db, day_date)
    if training_day is None:
        return finish(
            _payload(
                ok=False,
                action="rejected",
                code="no_training_day",
                message="لا يوجد تدريب مجدول اليوم",
                trainee=trainee,
                scanned_at=now,
            )
        )

    cfg = settings_service.get_all(db)
    min_gap = timedelta(minutes=int(cfg["min_checkout_gap_minutes"]))

    row = db.scalar(select(AttendanceDay).where(AttendanceDay.trainee_id == trainee.id, AttendanceDay.day == day_date))

    # ---- first scan of the day -> check-in (the unique key arbitrates races)
    if (row is None or row.check_in_at is None) and mode != "out":
        if row is None:
            try:
                with db.begin_nested():
                    row = AttendanceDay(
                        trainee_id=trainee.id,
                        day=day_date,
                        check_in_at=now,
                        check_in_source=source,
                        check_in_by=user.id if user else None,
                    )
                    db.add(row)
                    db.flush()
                created = True
            except IntegrityError:
                created = False
                row = db.scalar(
                    select(AttendanceDay).where(AttendanceDay.trainee_id == trainee.id, AttendanceDay.day == day_date)
                )
        else:  # excused placeholder row without a check-in: promote it atomically
            res = db.execute(
                update(AttendanceDay)
                .where(AttendanceDay.id == row.id, AttendanceDay.check_in_at.is_(None))
                .values(check_in_at=now, check_in_source=source, check_in_by=user.id if user else None)
            )
            created = res.rowcount == 1
            db.refresh(row)

        if created:
            cls = classify(row, training_day, now)
            msg = f"تم تسجيل الحضور الساعة {_hhmm(now)}" + (" (متأخر)" if cls.status in ("late", "excused") else "")
            return finish(
                _payload(
                    ok=True,
                    action="check_in",
                    code="checked_in",
                    message=msg,
                    trainee=trainee,
                    row=row,
                    status=cls.status,
                    scanned_at=now,
                )
            )
        # lost the race: continue as a repeat scan with the winner's row

    if row is None or row.check_in_at is None:
        return finish(
            _payload(
                ok=False,
                action="rejected",
                code="no_check_in",
                message="لا يوجد حضور مسجل اليوم، لا يمكن تسجيل الانصراف",
                trainee=trainee,
                scanned_at=now,
            )
        )

    # ---- already checked out
    if row.check_out_at is not None:
        return finish(
            _payload(
                ok=True,
                action="duplicate",
                code="already_checked_out",
                message=f"تم تسجيل الانصراف من قبل الساعة {_hhmm(row.check_out_at)}",
                trainee=trainee,
                row=row,
                status=classify(row, training_day, now).status,
                scanned_at=now,
            )
        )

    # ---- second scan inside the guard window = accidental double scan, not a check-out
    elapsed = now - as_utc(row.check_in_at)
    if mode == "in" or (mode != "out" and elapsed < min_gap):
        return finish(
            _payload(
                ok=True,
                action="duplicate",
                code="already_checked_in",
                message=f"تم تسجيل الحضور من قبل الساعة {_hhmm(row.check_in_at)}",
                trainee=trainee,
                row=row,
                status=classify(row, training_day, now).status,
                scanned_at=now,
            )
        )

    # ---- check-out (atomic: only one concurrent scan can set it)
    res = db.execute(
        update(AttendanceDay)
        .where(AttendanceDay.id == row.id, AttendanceDay.check_out_at.is_(None))
        .values(check_out_at=now, check_out_source=source, check_out_by=user.id if user else None)
    )
    db.refresh(row)
    if res.rowcount != 1:
        return finish(
            _payload(
                ok=True,
                action="duplicate",
                code="already_checked_out",
                message=f"تم تسجيل الانصراف من قبل الساعة {_hhmm(row.check_out_at)}",
                trainee=trainee,
                row=row,
                scanned_at=now,
            )
        )
    cls = classify(row, training_day, now)
    msg = f"تم تسجيل الانصراف الساعة {_hhmm(now)}" + (" (مبكر)" if cls.early_leave else "")
    return finish(
        _payload(
            ok=True,
            action="check_out",
            code="checked_out",
            message=msg,
            trainee=trainee,
            row=row,
            status=cls.status,
            early_leave=cls.early_leave,
            scanned_at=now,
        )
    )


# --------------------------------------------------------------------- manual edits
def local_time_to_utc(day: date, hhmm: str | None) -> datetime | None:
    if not hhmm:
        return None
    return local_datetime_to_utc(day, parse_hhmm(hhmm))
