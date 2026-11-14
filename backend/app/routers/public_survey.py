"""Public (no login) lecture survey, reached by scanning the session's QR code with any phone."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.db import get_db
from ..core.ratelimit import SlidingWindowLimiter, client_ip
from ..core.timeutil import utcnow
from ..models import LectureSession, Trainee
from ..services import settings as settings_service
from ..services.surveys import (
    active_questions,
    answers_payload,
    ensure_attended,
    public_response_for_trainee,
    submit_public_survey,
    survey_state,
    survey_window,
    template_for_session,
)

router = APIRouter(prefix="/public/surveys", tags=["public-survey"])

# A whole classroom may sit behind one NAT address, so the limit is generous; it only stops floods.
_submit_limiter = SlidingWindowLimiter(limit=300, window_seconds=60)


class PublicSubmitIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    answers: dict[int, int | str | None]
    badge_id: str | None = Field(default=None, max_length=8)


class IdentifyIn(BaseModel):
    badge_id: str = Field(min_length=2, max_length=8)


def _iso(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _load(db: Session, token: str) -> LectureSession:
    s = db.scalar(
        select(LectureSession).options(selectinload(LectureSession.trainer)).where(LectureSession.survey_token == token)
    )
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "رابط الاستبيان غير صحيح")
    return s


@router.get("/{token}")
def get_public_survey(token: str, db: Session = Depends(get_db)) -> dict:
    s = _load(db, token)
    cfg = settings_service.get_all(db)
    template = template_for_session(db, s)
    opens, closes = survey_window(s, cfg)
    return {
        "program_name": cfg["survey_program_name"],
        "session": {
            "id": s.id,
            "title": s.title,
            "axis": s.axis,
            "day": s.day.isoformat(),
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "trainer_name": s.trainer.name if s.trainer else None,
            "room": s.room,
        },
        "state": survey_state(s, cfg),
        "opens_at": _iso(opens),
        "closes_at": _iso(closes),
        "server_time": _iso(utcnow()),
        "questions": [
            {"id": q.id, "text": q.text, "type": q.type, "options": q.options, "required": q.required}
            for q in (active_questions(template) if template else [])
        ],
    }


@router.post("/{token}/identify")
def identify_for_survey(token: str, body: IdentifyIn, db: Session = Depends(get_db)) -> dict:
    """The survey QR asks for the trainee's code before the form opens."""
    s = _load(db, token)
    code = body.badge_id.strip().upper()
    trainee = db.scalar(select(Trainee).where(Trainee.badge_id == code))
    if trainee is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "الكود غير موجود")
    if not trainee.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "هذا الكود غير مفعّل")
    ensure_attended(db, trainee, s, "survey")
    previous = public_response_for_trainee(db, s.id, trainee.id)
    return {
        "full_name": trainee.full_name,
        "badge_id": trainee.badge_id,
        "submitted": previous is not None,
        "answers": answers_payload(previous) if previous is not None else {},
    }


@router.post("/{token}", status_code=201)
def post_public_survey(token: str, body: PublicSubmitIn, request: Request, db: Session = Depends(get_db)) -> dict:
    if not _submit_limiter.hit(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "محاولات كثيرة. انتظر دقيقة ثم حاول مرة أخرى.")
    s = _load(db, token)
    trainee = None
    if body.badge_id:
        code = body.badge_id.strip().upper()
        trainee = db.scalar(select(Trainee).where(Trainee.badge_id == code))
        if trainee is None or not trainee.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "الكود غير موجود")
    submit_public_survey(db, s, body.device_id, dict(body.answers), trainee)
    return {"ok": True}
