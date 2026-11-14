from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.errors import NotFound, ServiceError
from ..core.i18n import request_lang, translate
from ..core.timeutil import as_utc, local_today, utcnow
from ..deps import admin_only, audit, staff_or_admin
from ..models import AttendanceDay, ScanLog, Trainee, User
from ..schemas import ManualAttendanceIn, ScanIn
from ..services.attendance import (
    classify,
    get_or_create_training_day,
    local_time_to_utc,
    process_scan,
)
from ..services.reports import _iso

router = APIRouter(tags=["attendance"])


@router.post("/scan")
def scan(request: Request, body: ScanIn, user: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> dict:
    """Records a check-in / check-out. Business rejections are returned with ok=false (HTTP 200)
    so scanner screens can show the reason without treating it as a network failure."""
    result = process_scan(
        db,
        raw=body.code,
        mode=body.mode,
        source=body.source,
        user=user,
        scanned_at=body.scanned_at,
        client_id=body.client_id,
        device=body.device,
    )
    result = dict(result)
    result["message"] = translate(result.get("message"), request_lang(request))
    return result


@router.get("/attendance")
def attendance_for_day(
    day: date | None = None,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    day = day or local_today()
    now = utcnow()
    td = get_or_create_training_day(db, day, auto=(day == local_today()))
    trainees = list(db.scalars(select(Trainee).where(Trainee.is_active.is_(True)).order_by(Trainee.badge_id)))
    rows = {r.trainee_id: r for r in db.scalars(select(AttendanceDay).where(AttendanceDay.day == day))}
    out = []
    for t in trainees:
        r = rows.get(t.id)
        c = classify(r, td, now) if td else None
        out.append(
            {
                "trainee": {
                    "id": t.id,
                    "badge_id": t.badge_id,
                    "full_name": t.full_name,
                    "group_name": t.group_name,
                    "photo_url": f"/media/{t.photo_path}" if t.photo_path else None,
                },
                "status": c.status if c else "no_training",
                "early_leave": c.early_leave if c else False,
                "incomplete": c.incomplete if c else False,
                "worked_minutes": c.worked_minutes if c else None,
                "check_in_at": _iso(r.check_in_at) if r else None,
                "check_out_at": _iso(r.check_out_at) if r else None,
                "check_in_source": r.check_in_source if r else None,
                "excused": bool(r and r.excused),
                "is_manual": bool(r and r.is_manual),
                "note": r.note if r else None,
            }
        )
    return {
        "date": day.isoformat(),
        "training_day": (
            {
                "start_time": td.start_time.strftime("%H:%M"),
                "end_time": td.end_time.strftime("%H:%M"),
                "late_after": td.late_after.strftime("%H:%M"),
                "checkout_from": td.checkout_from.strftime("%H:%M"),
            }
            if td
            else None
        ),
        "rows": out,
    }


@router.put("/attendance/{trainee_id}/{day}")
def manual_attendance(
    trainee_id: int,
    day: date,
    body: ManualAttendanceIn,
    request: Request,
    user: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Manual correction (forgot badge, excused absence, fixed check-out). Always audited."""
    trainee = db.get(Trainee, trainee_id)
    if trainee is None:
        raise NotFound("المتدرب غير موجود")
    td = get_or_create_training_day(db, day)
    if td is None:
        raise ServiceError("لا يوجد يوم تدريب في هذا التاريخ. أنشئ اليوم أولاً.", code="no_training_day")
    check_in = local_time_to_utc(day, body.check_in_time)
    check_out = local_time_to_utc(day, body.check_out_time)
    if check_out and not check_in:
        raise ServiceError("الانصراف يحتاج وقت حضور", code="invalid_time")
    if check_in and check_out and as_utc(check_out) <= as_utc(check_in):
        raise ServiceError("وقت الانصراف يجب أن يكون بعد الحضور", code="invalid_time")

    row = db.scalar(select(AttendanceDay).where(AttendanceDay.trainee_id == trainee_id, AttendanceDay.day == day))
    if row is None:
        try:
            with db.begin_nested():
                row = AttendanceDay(trainee_id=trainee_id, day=day)
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.scalar(
                select(AttendanceDay).where(AttendanceDay.trainee_id == trainee_id, AttendanceDay.day == day)
            )
    before = {
        "check_in": _iso(row.check_in_at),
        "check_out": _iso(row.check_out_at),
        "excused": row.excused,
    }
    row.check_in_at = check_in
    row.check_out_at = check_out
    row.check_in_source = "manual" if check_in else None
    row.check_out_source = "manual" if check_out else None
    row.check_in_by = user.id if check_in else None
    row.check_out_by = user.id if check_out else None
    row.excused = body.excused
    row.note = body.note
    row.is_manual = True
    audit(
        db,
        user,
        "attendance_manual_edit",
        "attendance",
        f"{trainee_id}:{day.isoformat()}",
        {"before": before, "after": body.model_dump(), "trainee": trainee.badge_id},
        request,
    )
    db.commit()
    c = classify(row, td, utcnow())
    return {"status": c.status, "check_in_at": _iso(row.check_in_at), "check_out_at": _iso(row.check_out_at)}


@router.delete("/attendance/{trainee_id}/{day}", status_code=204)
def clear_attendance(
    trainee_id: int, day: date, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> None:
    row = db.scalar(select(AttendanceDay).where(AttendanceDay.trainee_id == trainee_id, AttendanceDay.day == day))
    if row is None:
        raise NotFound("لا يوجد سجل لهذا اليوم")
    audit(db, user, "attendance_cleared", "attendance", f"{trainee_id}:{day.isoformat()}", request=request)
    db.delete(row)
    db.commit()


@router.get("/scan-logs")
def scan_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    only_problems: bool = False,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(ScanLog, Trainee).outerjoin(Trainee, Trainee.id == ScanLog.trainee_id).order_by(ScanLog.id.desc())
    if only_problems:
        stmt = stmt.where(ScanLog.ok.is_(False))
    lang = request_lang(request)
    out = []
    for log, t in db.execute(stmt.limit(limit)).all():
        out.append(
            {
                "id": log.id,
                "at": _iso(log.scanned_at),
                "received_at": _iso(log.created_at),
                "action": log.action,
                "ok": log.ok,
                "code": log.code,
                "message": translate(log.message, lang),
                "source": log.source,
                "device": log.device,
                "trainee_name": t.full_name if t else None,
                "badge_id": t.badge_id if t else None,
            }
        )
    return out
