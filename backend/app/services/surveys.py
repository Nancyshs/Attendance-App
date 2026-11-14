"""Survey logic: availability windows, validation and (anonymous) submission."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..core.errors import Conflict, Forbidden, NotFound, ServiceError
from ..core.timeutil import UTC, as_utc, local_datetime_to_utc, local_day_bounds, round_to_hour, utcnow
from ..models import (
    AttendanceDay,
    LectureSession,
    SurveyAnswer,
    SurveyQuestion,
    SurveyResponse,
    SurveySubmission,
    SurveyTemplate,
    Trainee,
)
from . import settings as settings_service

QUESTION_TYPES = ("rating", "nps", "choice", "text")


def session_end_utc(s: LectureSession) -> datetime:
    return local_datetime_to_utc(s.day, s.end_time)


def session_start_utc(s: LectureSession) -> datetime:
    return local_datetime_to_utc(s.day, s.start_time)


def survey_duration(s: LectureSession, cfg: dict[str, Any]) -> int:
    return int(s.survey_duration_minutes or cfg["survey_duration_minutes"])


# Far enough that a survey with no close time never flips to "closed" on its own.
NEVER_CLOSES = datetime(9999, 1, 1, tzinfo=UTC)


def survey_window(s: LectureSession, cfg: dict[str, Any]) -> tuple[datetime, datetime]:
    """When the survey accepts answers.

    Opens at the end of the session unless the admin opened it by hand.
    Closes at a manual time if one was set, otherwise at the end of the session's
    local day when that option is on, otherwise it stays open.
    """
    end = session_end_utc(s)
    opens = as_utc(s.survey_opens_at) if s.survey_opens_at else end - timedelta(minutes=int(cfg["survey_opens_minutes_before_end"]))
    if s.survey_closes_at:
        closes = as_utc(s.survey_closes_at)
    elif s.survey_until_end_of_day:
        closes = local_day_bounds(s.day)[1]
    elif s.survey_duration_minutes:
        closes = opens + timedelta(minutes=int(s.survey_duration_minutes))
    else:
        closes = NEVER_CLOSES
    return opens, closes


def survey_state(s: LectureSession, cfg: dict[str, Any], now: datetime | None = None) -> str:
    now = now or utcnow()
    if s.is_cancelled:
        return "cancelled"
    opens, closes = survey_window(s, cfg)
    if now >= closes:
        return "closed"
    if now < opens:
        return "not_open"
    return "open"


def open_survey_now(s: LectureSession, cfg: dict[str, Any], minutes: int | None = None) -> None:
    """Opens (or re-opens) the survey right now for `minutes` (default: the session/programme duration)."""
    if minutes is not None:
        s.survey_duration_minutes = minutes
    now = utcnow().replace(microsecond=0)  # MySQL DATETIME rounds fractions up; never store a moment in the future
    s.survey_opens_at = now
    s.survey_closes_at = now + timedelta(minutes=survey_duration(s, cfg))


def close_survey_now(s: LectureSession) -> None:
    s.survey_closes_at = utcnow().replace(microsecond=0)

def get_default_template(db: Session) -> SurveyTemplate | None:
    return db.scalar(
        select(SurveyTemplate)
        .options(selectinload(SurveyTemplate.questions))
        .where(SurveyTemplate.is_default.is_(True), SurveyTemplate.is_active.is_(True))
        .limit(1)
    )


def template_for_session(db: Session, s: LectureSession) -> SurveyTemplate | None:
    if s.template_id:
        t = db.scalar(
            select(SurveyTemplate).options(selectinload(SurveyTemplate.questions)).where(SurveyTemplate.id == s.template_id)
        )
        if t:
            return t
    return get_default_template(db)


def active_questions(t: SurveyTemplate) -> list[SurveyQuestion]:
    return [q for q in t.questions if q.is_active]


def has_checked_in(db: Session, trainee_id: int, s: LectureSession) -> bool:
    row = db.scalar(
        select(AttendanceDay).where(AttendanceDay.trainee_id == trainee_id, AttendanceDay.day == s.day)
    )
    return bool(row and (row.check_in_at is not None or row.excused))


def survey_requires_attendance(s: LectureSession, cfg: dict[str, Any]) -> bool:
    return bool(s.require_attendance) or bool(cfg["require_attendance_for_survey"])


def ensure_attended(db: Session, trainee: Trainee | None, s: LectureSession, kind: str) -> None:
    """The lecture checkbox limits the survey and the exam to people who checked in."""
    if not s.require_attendance:
        return
    if trainee is not None and has_checked_in(db, trainee.id, s):
        return
    message = "الامتحان متاح فقط لمن سجّل حضوره" if kind == "exam" else "الاستبيان متاح فقط لمن سجّل حضوره"
    raise Forbidden(message, code="not_attended")


def _validate_answers(questions: list[SurveyQuestion], answers: dict[int, Any]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    known = {q.id for q in questions}
    for qid in answers:
        if qid not in known:
            raise ServiceError(f"سؤال غير معروف {qid}", code="invalid_answer")
    for q in questions:
        value = answers.get(q.id)
        empty = value is None or (isinstance(value, str) and not value.strip())
        if empty:
            raise ServiceError(f"يرجى الإجابة عن جميع الأسئلة قبل الإرسال: {q.text}", code="missing_answer")
        if q.type == "rating":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise ServiceError("التقييم يجب أن يكون من 1 إلى 5", code="invalid_answer")
            clean.append({"question_id": q.id, "rating": value})
        elif q.type == "nps":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10:
                raise ServiceError("الدرجة يجب أن تكون من 0 إلى 10", code="invalid_answer")
            clean.append({"question_id": q.id, "rating": value})
        elif q.type == "choice":
            options = q.options or []
            if not isinstance(value, str) or value not in options:
                raise ServiceError("اختيار غير صالح", code="invalid_answer")
            clean.append({"question_id": q.id, "choice": value})
        else:  # text
            if not isinstance(value, str):
                raise ServiceError("إجابة نصية غير صالحة", code="invalid_answer")
            clean.append({"question_id": q.id, "text": value.strip()[:2000]})
    return clean


def submit_survey(db: Session, trainee: Trainee, session_id: int, answers: dict[int, Any]) -> None:
    s = db.get(LectureSession, session_id)
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    cfg = settings_service.get_all(db)

    state = survey_state(s, cfg)
    if state == "cancelled":
        raise ServiceError("تم إلغاء هذه المحاضرة", code="session_cancelled")
    if state == "not_open":
        raise ServiceError("استبيان هذه المحاضرة لم يُفتح بعد", code="survey_not_open")
    if state == "closed":
        raise ServiceError("استبيان هذه المحاضرة مغلق", code="survey_closed")
    if survey_requires_attendance(s, cfg) and not has_checked_in(db, trainee.id, s):
        raise Forbidden("يمكن فقط للمتدربين الذين حضروا هذا اليوم تقييم محاضراته", code="not_attended")

    template = template_for_session(db, s)
    if template is None:
        raise ServiceError("لا يوجد قالب استبيان مُعدّ", code="no_template")
    clean = _validate_answers(active_questions(template), answers)
    if not clean:
        raise ServiceError("من فضلك أجب عن سؤال واحد على الأقل", code="missing_answer")

    now = utcnow()
    try:
        # One transaction: the unique (session, trainee) submission row is the duplicate guard,
        # so double taps / two devices can never create two responses.
        db.add(SurveySubmission(session_id=s.id, trainee_id=trainee.id, submitted_at=now))
        db.flush()
        response = SurveyResponse(
            session_id=s.id,
            template_id=template.id,
            trainee_id=None if template.is_anonymous else trainee.id,
            submitted_at=round_to_hour(now) if template.is_anonymous else now,
        )
        response.answers = [SurveyAnswer(**a) for a in clean]
        db.add(response)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("لقد أرسلت هذا الاستبيان من قبل", code="already_submitted") from None

def public_person_hash(session_id: int, trainee_id: int) -> str:
    """Stable key for one trainee on one session. Older rows used only this hash."""
    return hashlib.sha256(f"{session_id}:trainee:{trainee_id}".encode()).hexdigest()


def public_response_for_trainee(db: Session, session_id: int, trainee_id: int) -> SurveyResponse | None:
    linked = db.scalar(
        select(SurveyResponse)
        .options(selectinload(SurveyResponse.answers))
        .where(SurveyResponse.session_id == session_id, SurveyResponse.trainee_id == trainee_id)
    )
    if linked is not None:
        return linked
    return db.scalar(
        select(SurveyResponse)
        .options(selectinload(SurveyResponse.answers))
        .where(SurveyResponse.session_id == session_id, SurveyResponse.device_hash == public_person_hash(session_id, trainee_id))
    )


def answers_payload(response: SurveyResponse) -> dict[int, int | str]:
    out: dict[int, int | str] = {}
    for answer in response.answers:
        if answer.text is not None:
            out[answer.question_id] = answer.text
        elif answer.choice is not None:
            out[answer.question_id] = answer.choice
        elif answer.rating is not None:
            out[answer.question_id] = answer.rating
    return out


def submit_public_survey(db: Session, s: LectureSession, device_id: str, answers: dict[int, Any], trainee: Trainee | None = None) -> None:
    """QR survey. A known trainee updates their own previous answers; a bare device still answers once."""
    cfg = settings_service.get_all(db)
    state = survey_state(s, cfg)
    if state == "cancelled":
        raise ServiceError("تم إلغاء هذه المحاضرة", code="session_cancelled")
    if state == "not_open":
        raise ServiceError("استبيان هذه المحاضرة لم يُفتح بعد", code="survey_not_open")
    if state == "closed":
        raise ServiceError("استبيان هذه المحاضرة مغلق", code="survey_closed")
    ensure_attended(db, trainee, s, "survey")

    template = template_for_session(db, s)
    if template is None:
        raise ServiceError("لا يوجد قالب استبيان مُعدّ", code="no_template")
    clean = _validate_answers(active_questions(template), answers)
    if not clean:
        raise ServiceError("من فضلك أجب عن سؤال واحد على الأقل", code="missing_answer")

    if trainee is not None:
        existing = public_response_for_trainee(db, s.id, trainee.id)
        if existing is not None:
            existing.answers.clear()
            db.flush()
            existing.answers = [SurveyAnswer(**a) for a in clean]
            existing.submitted_at = round_to_hour(utcnow())
            existing.template_id = template.id
            existing.trainee_id = trainee.id
            db.commit()
            return

    device_hash = public_person_hash(s.id, trainee.id) if trainee is not None else hashlib.sha256(f"{s.id}:{device_id}".encode()).hexdigest()
    try:
        response = SurveyResponse(
            session_id=s.id,
            template_id=template.id,
            trainee_id=trainee.id if trainee is not None else None,
            device_hash=device_hash,
            submitted_at=round_to_hour(utcnow()),
        )
        response.answers = [SurveyAnswer(**a) for a in clean]
        db.add(response)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("لقد أرسلت هذا الاستبيان من قبل", code="already_submitted") from None