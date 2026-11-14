"""True/false exam sat twice: once before the lecture and once after it."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.errors import Conflict, NotFound, ServiceError
from ..core.timeutil import local_datetime_to_utc, parse_hhmm, to_local, utcnow
from ..models import ExamAnswer, ExamAttempt, ExamQuestion, LectureSession, Trainee
from . import settings as settings_service
from .surveys import ensure_attended

PHASES = ("before", "after")


def _clock(value: str | None) -> time | None:
    text = (value or "").strip()
    return parse_hhmm(text) if text else None


def apply_windows(session: LectureSession, before_start: str | None, before_end: str | None, after_start: str | None, after_end: str | None) -> None:
    """Store the two sittings. Each sitting needs both ends, and the two must not overlap."""
    parsed: dict[str, tuple[time | None, time | None]] = {}
    labels = {"before": "قبل المحاضرة", "after": "بعد المحاضرة"}
    for phase, start, end in (("before", before_start, before_end), ("after", after_start, after_end)):
        a, b = _clock(start), _clock(end)
        if (a is None) != (b is None):
            raise ServiceError(f"حددي بداية ونهاية امتحان {labels[phase]} معاً", code="exam_window")
        if a is not None and b is not None and b <= a:
            raise ServiceError(f"نهاية امتحان {labels[phase]} يجب أن تكون بعد بدايته", code="exam_window")
        parsed[phase] = (a, b)
    before, after = parsed["before"], parsed["after"]
    if before[0] and after[0] and before[0] < after[1] and after[0] < before[1]:
        raise ServiceError("وقتا الامتحان قبل المحاضرة وبعدها متداخلان، اجعلي كل فترة في وقت مختلف", code="exam_window")
    session.exam_before_opens_at = local_datetime_to_utc(session.day, before[0]) if before[0] else None
    session.exam_before_closes_at = local_datetime_to_utc(session.day, before[1]) if before[1] else None
    session.exam_after_opens_at = local_datetime_to_utc(session.day, after[0]) if after[0] else None
    session.exam_after_closes_at = local_datetime_to_utc(session.day, after[1]) if after[1] else None


def open_for(session: LectureSession, phase: str, minutes: int) -> None:
    """Open one sitting from this moment, for the number of minutes chosen."""
    if phase not in PHASES:
        raise ServiceError("اختاري قبل المحاضرة أو بعدها", code="exam_window")
    if minutes < 1 or minutes > 1440:
        raise ServiceError("المدة من دقيقة إلى 1440 دقيقة", code="exam_window")
    now = utcnow().replace(microsecond=0)
    other = "after" if phase == "before" else "before"
    other_span = _span(session, other)
    if other_span and other_span[0] <= now < other_span[1]:
        _assign(session, other, other_span[0], now)
    _assign(session, phase, now, now + timedelta(minutes=minutes))


def close_for(session: LectureSession, phase: str) -> None:
    """Close one sitting immediately, the same way a survey is closed."""
    if phase not in PHASES:
        raise ServiceError("اختاري قبل المحاضرة أو بعدها", code="exam_window")
    now = utcnow().replace(microsecond=0)
    span = _span(session, phase)
    opens = span[0] if span and span[0] <= now else now
    _assign(session, phase, opens, now)


def _assign(session: LectureSession, phase: str, opens: datetime, closes: datetime) -> None:
    if phase == "before":
        session.exam_before_opens_at = opens
        session.exam_before_closes_at = closes
    else:
        session.exam_after_opens_at = opens
        session.exam_after_closes_at = closes


def replace_questions(db: Session, session: LectureSession, questions: list[Any]) -> None:
    """Replace the written questions. Refused once anyone has already sat the exam."""
    incoming = [(q.text.strip(), bool(q.correct)) for q in questions if q.text.strip()]
    if any(not q.text.strip() for q in questions):
        raise ServiceError("اكتبي نص كل سؤال", code="exam_question")
    current = [(q.text, q.correct) for q in session.exam_questions]
    if incoming == current:
        return
    taken = db.scalar(select(ExamAttempt.id).where(ExamAttempt.session_id == session.id))
    if taken is not None:
        raise Conflict("لا يمكن تعديل أسئلة الامتحان بعد بدء الإجابات", "exam_started")
    session.exam_questions.clear()
    db.flush()
    for position, (text, correct) in enumerate(incoming):
        session.exam_questions.append(ExamQuestion(position=position, text=text, correct=correct))


def clock_on_day(session: LectureSession, phase: str) -> tuple[str | None, str | None]:
    """The sitting as HH:MM on the lecture date, when it still falls on that date."""
    span = _span(session, phase)
    if span is None:
        return None, None
    start, end = to_local(span[0]), to_local(span[1])
    if start.date() != session.day or end.date() != session.day:
        return None, None
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def _span(session: LectureSession, phase: str) -> tuple[datetime, datetime] | None:
    opens = session.exam_before_opens_at if phase == "before" else session.exam_after_opens_at
    closes = session.exam_before_closes_at if phase == "before" else session.exam_after_closes_at
    if opens is None or closes is None:
        return None
    return opens, closes


def exam_status(session: LectureSession, now: datetime | None = None) -> tuple[str | None, str, datetime | None, datetime | None]:
    """Return (phase, state, opens_at, closes_at).

    state is cancelled, open, not_open, or closed. phase is the sitting that
    state refers to, when one is scheduled.
    """
    now = now or utcnow()
    if session.is_cancelled:
        return None, "cancelled", None, None
    upcoming: tuple[datetime, str, datetime] | None = None
    last_closed: tuple[str, datetime, datetime] | None = None
    for phase in PHASES:
        span = _span(session, phase)
        if span is None:
            continue
        opens, closes = span
        if opens <= now < closes:
            return phase, "open", opens, closes
        if now < opens and (upcoming is None or opens < upcoming[0]):
            upcoming = (opens, phase, closes)
        elif now >= closes:
            last_closed = (phase, opens, closes)
    if upcoming is not None:
        _, phase, closes = upcoming
        return phase, "not_open", upcoming[0], closes
    if last_closed is not None:
        phase, opens, closes = last_closed
        return phase, "closed", opens, closes
    return None, "not_open", None, None


def _load(db: Session, token: str) -> LectureSession:
    session = db.scalar(
        select(LectureSession)
        .options(selectinload(LectureSession.trainer), selectinload(LectureSession.exam_questions))
        .where(LectureSession.exam_token == token)
    )
    if session is None:
        raise NotFound("رابط الامتحان غير صحيح")
    return session


def public_exam(db: Session, token: str) -> dict:
    session = _load(db, token)
    phase, state, opens, closes = exam_status(session)
    cfg = settings_service.get_all(db)
    return {
        "program_name": cfg["survey_program_name"],
        "title": session.title,
        "axis": session.axis,
        "day": session.day.isoformat(),
        "trainer_name": session.trainer.name if session.trainer else None,
        "state": state,
        "phase": phase,
        "opens_at": opens.isoformat().replace("+00:00", "Z") if opens else None,
        "closes_at": closes.isoformat().replace("+00:00", "Z") if closes else None,
        "questions": [{"id": q.id, "text": q.text} for q in session.exam_questions],
    }


def _attempt(db: Session, session_id: int, trainee_id: int, phase: str) -> ExamAttempt | None:
    return db.scalar(
        select(ExamAttempt)
        .options(selectinload(ExamAttempt.answers))
        .where(ExamAttempt.session_id == session_id, ExamAttempt.trainee_id == trainee_id, ExamAttempt.phase == phase)
    )


def identify(db: Session, token: str, badge_id: str) -> dict:
    session = _load(db, token)
    code = badge_id.strip().upper()
    trainee = db.scalar(select(Trainee).where(Trainee.badge_id == code))
    if trainee is None or not trainee.is_active:
        raise ServiceError("الكود غير موجود", code="unknown_code", status_code=401)
    ensure_attended(db, trainee, session, "exam")
    phase, state, _, _ = exam_status(session)
    previous = _attempt(db, session.id, trainee.id, phase) if phase else None
    return {
        "full_name": trainee.full_name,
        "badge_id": trainee.badge_id,
        "state": state,
        "phase": phase,
        "submitted": previous is not None,
    }


def submit(db: Session, token: str, badge_id: str, answers: dict[int, Any]) -> None:
    session = _load(db, token)
    answers = {int(key): value for key, value in answers.items()}
    phase, state, _, _ = exam_status(session)
    if state == "cancelled":
        raise ServiceError("تم إلغاء هذه المحاضرة", code="session_cancelled")
    if state != "open" or phase is None:
        raise ServiceError("الامتحان غير مفتوح الآن", code="exam_not_open")
    if not session.exam_questions:
        raise ServiceError("لا توجد أسئلة لهذا الامتحان", code="no_questions")
    code = badge_id.strip().upper()
    trainee = db.scalar(select(Trainee).where(Trainee.badge_id == code))
    if trainee is None or not trainee.is_active:
        raise ServiceError("الكود غير موجود", code="unknown_code", status_code=401)
    ensure_attended(db, trainee, session, "exam")
    if _attempt(db, session.id, trainee.id, phase) is not None:
        raise Conflict("لقد أجبت على هذا الامتحان", "already_submitted")
    clean: list[ExamAnswer] = []
    for question in session.exam_questions:
        value = answers.get(question.id)
        if not isinstance(value, bool):
            raise ServiceError("يرجى الإجابة عن جميع الأسئلة بصح أو خطأ قبل الإرسال", code="missing_answer")
        clean.append(ExamAnswer(question_id=question.id, value=value))
    attempt = ExamAttempt(session_id=session.id, trainee_id=trainee.id, phase=phase, submitted_at=utcnow())
    attempt.answers = clean
    db.add(attempt)
    db.commit()


def report_rows(db: Session, session_id: int) -> dict:
    session = db.scalar(
        select(LectureSession)
        .options(
            selectinload(LectureSession.exam_questions),
            selectinload(LectureSession.exam_attempts).selectinload(ExamAttempt.answers),
            selectinload(LectureSession.exam_attempts).selectinload(ExamAttempt.trainee),
        )
        .where(LectureSession.id == session_id)
    )
    if session is None:
        raise NotFound("المحاضرة غير موجودة")
    questions = list(session.exam_questions)
    by_phase: dict[str, dict[int, ExamAttempt]] = {"before": {}, "after": {}}
    for attempt in session.exam_attempts:
        by_phase.setdefault(attempt.phase, {})[attempt.trainee_id] = attempt
    trainee_ids = sorted(set(by_phase["before"]) | set(by_phase["after"]))
    trainees = {t.id: t for t in db.scalars(select(Trainee).where(Trainee.id.in_(trainee_ids)))} if trainee_ids else {}

    def pack(attempt: ExamAttempt | None) -> dict | None:
        if attempt is None:
            return None
        given = {a.question_id: a.value for a in attempt.answers}
        marks = [given.get(q.id) == q.correct for q in questions]
        return {"answers": [given.get(q.id) for q in questions], "score": sum(1 for ok in marks if ok)}

    rows = []
    for trainee_id in trainee_ids:
        trainee = trainees.get(trainee_id) or by_phase["before"].get(trainee_id, by_phase["after"].get(trainee_id)).trainee
        rows.append({
            "badge_id": trainee.badge_id,
            "full_name": trainee.full_name,
            "before": pack(by_phase["before"].get(trainee_id)),
            "after": pack(by_phase["after"].get(trainee_id)),
        })
    rows.sort(key=lambda r: r["badge_id"])
    return {
        "title": session.title,
        "day": session.day.isoformat(),
        "questions": [q.text for q in questions],
        "total": len(questions),
        "rows": rows,
    }
