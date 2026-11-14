from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.i18n import request_lang, translate
from ..core.timeutil import local_today
from ..deps import admin_only, any_user, staff_or_admin
from ..models import AuditLog, User
from ..services import exports, reports
from ..services import settings as settings_service

router = APIRouter(tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    end = date_to or local_today()
    start = date_from or end - timedelta(days=60)
    if end < start:
        raise HTTPException(400, "تاريخ النهاية يجب ألا يسبق تاريخ البداية")
    if (end - start).days > 400:
        raise HTTPException(400, "المدة طويلة جداً (الحد الأقصى 400 يوم)")
    return start, end


@router.get("/reports/dashboard")
def dashboard(request: Request, day: date | None = None, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> dict:
    data = reports.dashboard(db, day)
    lang = request_lang(request)
    if lang == "en":
        for s in data.get("recent_scans", []):
            s["message"] = translate(s.get("message"), lang)
    return data


@router.get("/reports/attendance")
def attendance(
    date_from: date | None = None,
    date_to: date | None = None,
    include_inactive: bool = False,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    start, end = _range(date_from, date_to)
    return reports.attendance_report(db, start, end, include_inactive=include_inactive)


@router.get("/reports/attendance.xlsx")
def attendance_xlsx(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> Response:
    start, end = _range(date_from, date_to)
    data = exports.attendance_workbook(reports.attendance_report(db, start, end), request_lang(request))
    return Response(
        data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="attendance_{start}_{end}.xlsx"'}
    )


def _survey_args(user: User, trainer_id: int | None) -> int | None:
    """Trainers can only ever see their own results."""
    if user.role == "trainer":
        if not user.trainer_id:
            raise HTTPException(403, "حسابك غير مرتبط ببيانات محاضر")
        return user.trainer_id
    return trainer_id


@router.get("/reports/surveys")
def surveys(
    date_from: date | None = None,
    date_to: date | None = None,
    trainer_id: int | None = None,
    session_id: int | None = None,
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict:
    start, end = _range(date_from, date_to)
    return reports.survey_report(db, start, end, trainer_id=_survey_args(user, trainer_id), session_id=session_id)


@router.get("/reports/survey-respondents")
def survey_respondents(
    date_from: date | None = None,
    date_to: date | None = None,
    trainer_id: int | None = None,
    session_id: int | None = None,
    user: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    start, end = _range(date_from, date_to)
    return reports.survey_respondents(db, start, end, trainer_id=_survey_args(user, trainer_id), session_id=session_id)


@router.get("/reports/surveys.xlsx")
def surveys_xlsx(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    trainer_id: int | None = None,
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> Response:
    start, end = _range(date_from, date_to)
    data = exports.survey_workbook(reports.survey_report(db, start, end, trainer_id=_survey_args(user, trainer_id)), request_lang(request))
    return Response(
        data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="feedback_{start}_{end}.xlsx"'}
    )


# ------------------------------------------------------------ settings & audit log
@router.get("/settings")
def get_settings(_: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> dict:
    return settings_service.get_all(db)


@router.put("/settings")
def put_settings(body: dict, user: User = Depends(admin_only), db: Session = Depends(get_db)) -> dict:
    from ..deps import audit

    errors = _validate_settings(body)
    if errors:
        raise HTTPException(422, "; ".join(errors))
    result = settings_service.update(db, body)
    audit(db, user, "settings_updated", "settings", None, body)
    db.commit()
    return result


def _validate_settings(body: dict) -> list[str]:
    errors: list[str] = []
    for key in ("day_start_time", "day_end_time", "checkout_from_time"):
        if key in body:
            try:
                hh, mm = str(body[key]).split(":")
                assert 0 <= int(hh) < 24 and 0 <= int(mm) < 60
            except Exception:
                errors.append(f"{key}: الوقت يجب أن يكون بصيغة HH:MM")
    for key in ("late_after_minutes", "min_checkout_gap_minutes", "survey_close_hours_after_end", "survey_duration_minutes",
                "survey_opens_minutes_before_end", "absence_alert_threshold"):
        if key in body and (not isinstance(body[key], int) or isinstance(body[key], bool) or body[key] < 0):
            errors.append(f"{key}: يجب أن يكون رقماً صحيحاً غير سالب")
    if "working_weekdays" in body:
        v = body["working_weekdays"]
        if not (isinstance(v, list) and all(isinstance(i, int) and 0 <= i <= 6 for i in v)):
            errors.append("أيام العمل يجب أن تكون قائمة أرقام من 0 إلى 6")
    if "low_rating_threshold" in body and not isinstance(body["low_rating_threshold"], (int, float)):
        errors.append("حد التقييم المنخفض يجب أن يكون رقماً")
    if isinstance(body.get("survey_duration_minutes"), int) and body["survey_duration_minutes"] < 1:
        errors.append("survey_duration_minutes: يجب ألا تقل المدة عن دقيقة")
    if "survey_program_name" in body and not isinstance(body["survey_program_name"], str):
        errors.append("اسم البرنامج في الاستبيان غير صالح")
    if "program_name" in body and (not isinstance(body["program_name"], str) or not body["program_name"].strip()):
        errors.append("اسم البرنامج مطلوب")
    if "require_attendance_for_survey" in body and not isinstance(body["require_attendance_for_survey"], bool):
        errors.append("خيار اشتراط الحضور للاستبيان يجب أن يكون نعم/لا")
    return errors


@router.get("/audit-logs")
def audit_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    _: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [
        {
            "id": r.id,
            "at": r.created_at.isoformat().replace("+00:00", "Z"),
            "username": r.username,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "details": r.details,
            "ip": r.ip,
        }
        for r in rows
    ]
