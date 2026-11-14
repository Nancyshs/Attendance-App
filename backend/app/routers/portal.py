"""Trainee portal: sign in by scanning the badge QR with a phone, then rate sessions."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.config import settings
from ..core.db import get_db
from ..core.errors import NotFound
from ..core.ratelimit import SlidingWindowLimiter, client_ip
from ..core.security import create_token
from ..core.timeutil import local_today, utcnow
from ..deps import get_current_trainee
from ..models import AttendanceDay, LectureSession, SurveySubmission, Trainee
from ..schemas import PortalAuthIn, SurveySubmitIn
from ..services import settings as settings_service
from ..services.attendance import extract_token
from ..services.surveys import (
    active_questions,
    has_checked_in,
    submit_survey,
    survey_state,
    survey_window,
    template_for_session,
)

router = APIRouter(prefix="/portal", tags=["portal"])

# Only FAILED token lookups are limited (a classroom behind one NAT must not lock itself out).
_fail_limiter = SlidingWindowLimiter(limit=25, window_seconds=60)


def _iso(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _trainee_json(t: Trainee) -> dict:
    return {
        "id": t.id,
        "badge_id": t.badge_id,
        "full_name": t.full_name,
        "photo_url": f"/media/{t.photo_path}" if t.photo_path else None,
    }


@router.post("/auth")
def portal_auth(body: PortalAuthIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request)
    if _fail_limiter.peek_blocked(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "محاولات غير صحيحة كثيرة. حاول بعد دقيقة.")
    token = extract_token(body.token)
    trainee = db.scalar(select(Trainee).where(Trainee.qr_token == token)) if token else None
    if trainee is None or not trainee.is_active:
        _fail_limiter.hit(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "هذا الباج غير صالح. من فضلك اسأل المنظمين.")
    access = create_token(str(trainee.id), kind="trainee", minutes=settings.trainee_token_minutes)
    return {"access_token": access, "trainee": _trainee_json(trainee)}


@router.get("/me")
def portal_me(trainee: Trainee = Depends(get_current_trainee), db: Session = Depends(get_db)) -> dict:
    cfg = settings_service.get_all(db)
    now = utcnow()
    today = local_today()
    first_day = today - timedelta(days=2)  # a couple of days to answer late, while the window is open

    sessions = list(
        db.scalars(
            select(LectureSession)
            .options(selectinload(LectureSession.trainer))
            .where(LectureSession.day >= first_day, LectureSession.day <= today)
            .order_by(LectureSession.day.desc(), LectureSession.start_time)
        )
    )
    attended_days = {
        r.day: r
        for r in db.scalars(
            select(AttendanceDay).where(AttendanceDay.trainee_id == trainee.id, AttendanceDay.day >= first_day)
        )
    }
    submitted = set(
        db.scalars(select(SurveySubmission.session_id).where(SurveySubmission.trainee_id == trainee.id))
    )

    items = []
    for s in sessions:
        row = attended_days.get(s.day)
        attended = bool(row and (row.check_in_at or row.excused))
        state = survey_state(s, cfg, now)
        if state != "cancelled":
            if s.id in submitted:
                state = "submitted"
            elif (cfg["require_attendance_for_survey"] or s.require_attendance) and not attended and state in ("open", "not_open"):
                state = "not_attended"
        opens, closes = survey_window(s, cfg)
        items.append(
            {
                "id": s.id,
                "title": s.title,
                "day": s.day.isoformat(),
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "trainer_name": s.trainer.name if s.trainer else None,
                "room": s.room,
                "state": state,
                "opens_at": _iso(opens),
                "closes_at": _iso(closes),
            }
        )

    today_row = attended_days.get(today)
    return {
        "trainee": _trainee_json(trainee),
        "program_name": cfg["program_name"],
        "today": {
            "date": today.isoformat(),
            "check_in_at": _iso(today_row.check_in_at) if today_row and today_row.check_in_at else None,
            "check_out_at": _iso(today_row.check_out_at) if today_row and today_row.check_out_at else None,
        },
        "sessions": items,
        "server_time": _iso(now),
    }


@router.get("/sessions/{session_id}/survey")
def get_survey(session_id: int, trainee: Trainee = Depends(get_current_trainee), db: Session = Depends(get_db)) -> dict:
    s = db.scalar(select(LectureSession).options(selectinload(LectureSession.trainer)).where(LectureSession.id == session_id))
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    cfg = settings_service.get_all(db)
    template = template_for_session(db, s)
    if template is None:
        raise NotFound("لا يوجد استبيان مُعدّ")
    already = bool(
        db.scalar(
            select(SurveySubmission.id).where(
                SurveySubmission.session_id == s.id, SurveySubmission.trainee_id == trainee.id
            )
        )
    )
    state = survey_state(s, cfg)
    if already:
        state = "submitted"
    elif (cfg["require_attendance_for_survey"] or s.require_attendance) and state in ("open", "not_open") and not has_checked_in(db, trainee.id, s):
        state = "not_attended"
    opens, closes = survey_window(s, cfg)
    return {
        "session": {
            "id": s.id,
            "title": s.title,
            "day": s.day.isoformat(),
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "trainer_name": s.trainer.name if s.trainer else None,
        },
        "state": state,
        "opens_at": _iso(opens),
        "closes_at": _iso(closes),
        "is_anonymous": template.is_anonymous,
        "questions": [
            {"id": q.id, "text": q.text, "type": q.type, "options": q.options, "required": q.required}
            for q in active_questions(template)
        ],
    }


@router.post("/sessions/{session_id}/survey", status_code=201)
def post_survey(
    session_id: int,
    body: SurveySubmitIn,
    trainee: Trainee = Depends(get_current_trainee),
    db: Session = Depends(get_db),
) -> dict:
    submit_survey(db, trainee, session_id, dict(body.answers))
    return {"ok": True}
