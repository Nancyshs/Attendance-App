from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..core.db import get_db
from ..core.errors import Conflict, NotFound, ServiceError
from ..core.i18n import request_lang, translate
from ..core.timeutil import parse_hhmm
from ..deps import admin_only, any_user, audit, staff_or_admin
from ..models import AttendanceDay, LectureSession, SurveyResponse, Trainer, TrainingDay, User
from ..schemas import (
    ExamCloseIn,
    ExamOpenIn,
    ExamReopenIn,
    GenerateDaysIn,
    ImportResult,
    SessionIn,
    SessionOut,
    SurveyOpenIn,
    TrainerIn,
    TrainerOut,
    TrainingDayIn,
    TrainingDayOut,
    TrainingDayUpdate,
)
from ..services import exports
from ..services import settings as settings_service
from ..services.attendance import default_day_values
from ..services import badges
from ..services.exams import apply_windows, clock_on_day, close_for, exam_status, open_for, replace_questions
from ..services.surveys import close_survey_now, open_survey_now, survey_duration, survey_state, survey_window

router = APIRouter(tags=["schedule"])


# --------------------------------------------------------------------- trainers
@router.get("/trainers", response_model=list[TrainerOut])
def list_trainers(_: User = Depends(any_user), db: Session = Depends(get_db)) -> list[Trainer]:
    return list(db.scalars(select(Trainer).order_by(Trainer.name)))


@router.post("/trainers", response_model=TrainerOut, status_code=201)
def create_trainer(
    body: TrainerIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> Trainer:
    t = Trainer(**body.model_dump())
    db.add(t)
    db.flush()
    audit(db, user, "trainer_created", "trainer", t.id, {"name": t.name}, request)
    db.commit()
    return t


@router.put("/trainers/{trainer_id}", response_model=TrainerOut)
def update_trainer(
    trainer_id: int, body: TrainerIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> Trainer:
    t = db.get(Trainer, trainer_id)
    if t is None:
        raise NotFound("المحاضر غير موجود")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    audit(db, user, "trainer_updated", "trainer", t.id, request=request)
    db.commit()
    return t


# ---------------------------------------------------------------- training days
@router.get("/training-days", response_model=list[TrainingDayOut])
def list_days(
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> list[TrainingDay]:
    stmt = select(TrainingDay).order_by(TrainingDay.date)
    if date_from:
        stmt = stmt.where(TrainingDay.date >= date_from)
    if date_to:
        stmt = stmt.where(TrainingDay.date <= date_to)
    return list(db.scalars(stmt.limit(500)))


@router.post("/training-days", response_model=TrainingDayOut, status_code=201)
def create_day(
    body: TrainingDayIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TrainingDay:
    if db.scalar(select(TrainingDay.id).where(TrainingDay.date == body.date)):
        raise Conflict("يوجد يوم تدريب بالفعل في هذا التاريخ")
    d = TrainingDay(
        date=body.date,
        start_time=parse_hhmm(body.start_time),
        end_time=parse_hhmm(body.end_time),
        late_after=parse_hhmm(body.late_after),
        checkout_from=parse_hhmm(body.checkout_from),
        note=body.note,
    )
    db.add(d)
    db.flush()
    audit(db, user, "training_day_created", "training_day", d.id, {"date": body.date.isoformat()}, request)
    db.commit()
    return d


@router.post("/training-days/generate", response_model=list[TrainingDayOut])
def generate_days(
    body: GenerateDaysIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> list[TrainingDay]:
    """Creates a training day for every working weekday in the range (existing days are kept)."""
    if body.date_to < body.date_from or (body.date_to - body.date_from).days > 366:
        raise ServiceError("نطاق التاريخ غير صالح (الحد الأقصى سنة)")
    cfg = settings_service.get_all(db)
    values = default_day_values(cfg)
    existing = set(
        db.scalars(select(TrainingDay.date).where(TrainingDay.date >= body.date_from, TrainingDay.date <= body.date_to))
    )
    created: list[TrainingDay] = []
    cur = body.date_from
    while cur <= body.date_to:
        if cur.weekday() in cfg["working_weekdays"] and cur not in existing:
            d = TrainingDay(date=cur, **values)
            db.add(d)
            created.append(d)
        cur += timedelta(days=1)
    audit(db, user, "training_days_generated", "training_day", None, {"count": len(created)}, request)
    db.commit()
    return created


@router.patch("/training-days/{day_id}", response_model=TrainingDayOut)
def update_day(
    day_id: int, body: TrainingDayUpdate, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> TrainingDay:
    d = db.get(TrainingDay, day_id)
    if d is None:
        raise NotFound("يوم التدريب غير موجود")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, parse_hhmm(v) if k != "note" and v else v)
    d.is_auto = False
    audit(db, user, "training_day_updated", "training_day", d.id, data, request)
    db.commit()
    return d


@router.delete("/training-days/{day_id}", status_code=204)
def delete_day(day_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)) -> None:
    d = db.get(TrainingDay, day_id)
    if d is None:
        raise NotFound("يوم التدريب غير موجود")
    if db.scalar(select(func.count()).select_from(AttendanceDay).where(AttendanceDay.day == d.date)):
        raise Conflict("هذا اليوم عليه سجلات حضور ولا يمكن حذفه", "has_records")
    audit(db, user, "training_day_deleted", "training_day", d.id, {"date": d.date.isoformat()}, request)
    db.delete(d)
    db.commit()


# --------------------------------------------------------------------- sessions
def _session_out(s: LectureSession, cfg: dict, submissions: int = 0, request: Request | None = None) -> SessionOut:
    opens, closes = survey_window(s, cfg)
    return SessionOut(
        id=s.id,
        day=s.day,
        start_time=s.start_time.strftime("%H:%M"),
        end_time=s.end_time.strftime("%H:%M"),
        title=s.title,
        description=s.description,
        trainer_id=s.trainer_id,
        trainer_name=s.trainer.name if s.trainer else None,
        room=s.room,
        template_id=s.template_id,
        axis=s.axis,
        survey_token=s.survey_token,
        survey_url=badges.survey_url(s.survey_token, request),
        survey_duration_minutes=s.survey_duration_minutes,
        effective_duration_minutes=survey_duration(s, cfg),
        survey_opens_at=s.survey_opens_at,
        survey_closes_at=s.survey_closes_at,
        survey_until_end_of_day=s.survey_until_end_of_day,
        require_attendance=s.require_attendance,
        survey_state=survey_state(s, cfg),
        effective_opens_at=opens,
        effective_closes_at=closes,
        is_cancelled=s.is_cancelled,
        submissions=submissions,
        exam_token=s.exam_token,
        exam_url=badges.exam_url(s.exam_token, request),
        exam_before_opens_at=s.exam_before_opens_at,
        exam_before_closes_at=s.exam_before_closes_at,
        exam_after_opens_at=s.exam_after_opens_at,
        exam_after_closes_at=s.exam_after_closes_at,
        exam_phase=exam_status(s)[0],
        exam_state=exam_status(s)[1],
        exam_questions=[{"id": q.id, "text": q.text, "correct": q.correct} for q in s.exam_questions],
    )


def _validate_times(body: SessionIn) -> None:
    if parse_hhmm(body.end_time) <= parse_hhmm(body.start_time):
        raise ServiceError("وقت النهاية يجب أن يكون بعد وقت البداية", code="invalid_time")
    if body.survey_until_end_of_day and body.survey_duration_minutes:
        raise ServiceError("اختار إما فتح الاستبيان لآخر اليوم أو لمدة محددة بالدقائق", code="survey_window")


def _ensure_training_day(db: Session, day: date) -> None:
    """A session on a day without a training day creates it, so attendance and survey stay consistent."""
    if db.scalar(select(TrainingDay.id).where(TrainingDay.date == day)):
        return
    cfg = settings_service.get_all(db)
    db.add(TrainingDay(date=day, is_auto=True, **default_day_values(cfg)))
    db.flush()


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    trainer_id: int | None = None,
    _: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    stmt = (
        select(LectureSession)
        .options(selectinload(LectureSession.trainer), selectinload(LectureSession.exam_questions))
        .order_by(LectureSession.day, LectureSession.start_time)
    )
    if date_from:
        stmt = stmt.where(LectureSession.day >= date_from)
    if date_to:
        stmt = stmt.where(LectureSession.day <= date_to)
    if trainer_id:
        stmt = stmt.where(LectureSession.trainer_id == trainer_id)
    sessions = list(db.scalars(stmt.limit(2000)))
    cfg = settings_service.get_all(db)
    counts: dict[int, int] = {}
    if sessions:
        counts = dict(
            db.execute(
                select(SurveyResponse.session_id, func.count())
                .where(SurveyResponse.session_id.in_([s.id for s in sessions]))
                .group_by(SurveyResponse.session_id)
            ).all()
        )
    return [_session_out(s, cfg, int(counts.get(s.id, 0)), request) for s in sessions]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> SessionOut:
    _validate_times(body)
    _ensure_training_day(db, body.day)
    data = body.model_dump(exclude={"open_now", "exam_questions", "exam_before_start", "exam_before_end", "exam_after_start", "exam_after_end"})
    data["start_time"], data["end_time"] = parse_hhmm(body.start_time), parse_hhmm(body.end_time)
    data["axis"] = (body.axis or "").strip() or None
    s = LectureSession(**data)
    apply_windows(s, body.exam_before_start, body.exam_before_end, body.exam_after_start, body.exam_after_end)
    db.add(s)
    db.flush()
    replace_questions(db, s, body.exam_questions)
    if body.open_now:
        open_survey_now(s, settings_service.get_all(db))
    audit(db, user, "session_created", "session", s.id, {"title": s.title, "day": body.day.isoformat()}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), request=request)


@router.put("/sessions/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int, body: SessionIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> SessionOut:
    s = db.scalar(
        select(LectureSession)
        .options(selectinload(LectureSession.exam_questions))
        .where(LectureSession.id == session_id)
    )
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    _validate_times(body)
    _ensure_training_day(db, body.day)
    # survey_opens_at / survey_closes_at are managed by the open/close actions: only touch them when sent
    data = body.model_dump(
        exclude={"open_now", "exam_questions", "exam_before_start", "exam_before_end", "exam_after_start", "exam_after_end"},
        exclude_unset=True,
    )
    data["start_time"], data["end_time"] = parse_hhmm(body.start_time), parse_hhmm(body.end_time)
    if "axis" in data:
        data["axis"] = (body.axis or "").strip() or None
    # The lecture form chooses one close rule. A manual open/close is cleared so that choice applies.
    choosing = "survey_until_end_of_day" in body.model_fields_set or "survey_duration_minutes" in body.model_fields_set
    if body.survey_until_end_of_day:
        data["survey_duration_minutes"] = None
    for k, v in data.items():
        setattr(s, k, v)
    if choosing:
        s.survey_opens_at = None
        s.survey_closes_at = None
    if any(name in body.model_fields_set for name in ("exam_before_start", "exam_before_end", "exam_after_start", "exam_after_end")):
        apply_windows(s, body.exam_before_start, body.exam_before_end, body.exam_after_start, body.exam_after_end)
    if "exam_questions" in body.model_fields_set:
        replace_questions(db, s, body.exam_questions)
    if body.open_now:
        open_survey_now(s, settings_service.get_all(db))
    audit(db, user, "session_updated", "session", s.id, {"title": s.title}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), request=request)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> None:
    s = db.get(LectureSession, session_id)
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    if db.scalar(select(func.count()).select_from(SurveyResponse).where(SurveyResponse.session_id == s.id)):
        raise Conflict("هذه المحاضرة عليها إجابات استبيان. اجعلها «ملغاة» بدلاً من حذفها.", "has_records")
    audit(db, user, "session_deleted", "session", s.id, {"title": s.title}, request)
    db.delete(s)
    db.commit()


@router.post("/sessions/{session_id}/survey/open", response_model=SessionOut)
def open_session_survey(
    session_id: int,
    request: Request,
    body: SurveyOpenIn | None = None,
    user: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> SessionOut:
    """Opens (or re-opens) the survey now; it closes by itself after the chosen number of minutes."""
    s = db.get(LectureSession, session_id)
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    if s.is_cancelled:
        raise ServiceError("تم إلغاء هذه المحاضرة", code="session_cancelled")
    cfg = settings_service.get_all(db)
    open_survey_now(s, cfg, body.duration_minutes if body else None)
    audit(db, user, "survey_opened", "session", s.id, {"minutes": survey_duration(s, cfg)}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, cfg, _response_count(db, s.id), request)


@router.post("/sessions/{session_id}/survey/close", response_model=SessionOut)
def close_session_survey(
    session_id: int, request: Request, user: User = Depends(staff_or_admin), db: Session = Depends(get_db)
) -> SessionOut:
    s = db.get(LectureSession, session_id)
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    close_survey_now(s)
    audit(db, user, "survey_closed", "session", s.id, None, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), _response_count(db, s.id), request)


def _response_count(db: Session, session_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(SurveyResponse).where(SurveyResponse.session_id == session_id)) or 0)


def _load_session(db: Session, session_id: int) -> LectureSession:
    s = db.scalar(select(LectureSession).options(selectinload(LectureSession.trainer)).where(LectureSession.id == session_id))
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    return s


@router.get("/sessions/{session_id}/survey-qr.svg")
def session_survey_qr(session_id: int, request: Request, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> Response:
    s = _load_session(db, session_id)
    return Response(badges.survey_qr_svg(s.survey_token, request), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/survey-qr.pdf")
def session_survey_poster(
    session_id: int, request: Request, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)
) -> Response:
    """Printable A4 poster: the trainer's name above the session title, then a large QR code."""
    s = _load_session(db, session_id)
    cfg = settings_service.get_all(db)
    lang = request_lang(request)
    when = badges.poster_when(s.day, s.start_time, s.end_time, lang)
    pdf = badges.render_survey_poster(
        cfg["survey_program_name"], s.title, s.survey_token, s.trainer.name if s.trainer else None, when, s.axis, lang, request
    )
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="survey_qr_{s.id}.pdf"'})


@router.get("/sessions/{session_id}/exam-qr.svg")
def session_exam_qr(session_id: int, request: Request, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> Response:
    s = _load_session(db, session_id)
    return Response(badges.exam_qr_svg(s.exam_token, request), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/exam-qr.pdf")
def session_exam_poster(
    session_id: int, request: Request, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)
) -> Response:
    s = _load_session(db, session_id)
    cfg = settings_service.get_all(db)
    lang = request_lang(request)
    en = lang == "en"
    when = badges.poster_when(s.day, s.start_time, s.end_time, lang)
    pdf = badges.render_survey_poster(
        cfg["survey_program_name"],
        s.title,
        s.exam_token,
        s.trainer.name if s.trainer else None,
        when,
        s.axis,
        lang,
        request,
        headline="Session exam" if en else "امتحان الجلسة التدريبية",
        caption="Please scan the code to open the exam" if en else "يرجى مسح الرمز لفتح الامتحان",
        link=badges.exam_url(s.exam_token, request),
    )
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="exam_qr_{s.id}.pdf"'})


@router.post("/sessions/{session_id}/exam/reopen", response_model=SessionOut)
def reopen_exam(
    session_id: int, body: ExamReopenIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)
) -> SessionOut:
    """Set a new from-to window, on the lecture's own date, for the before or after sitting."""
    s = db.scalar(
        select(LectureSession).options(selectinload(LectureSession.exam_questions), selectinload(LectureSession.trainer)).where(LectureSession.id == session_id)
    )
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    before = clock_on_day(s, "before")
    after = clock_on_day(s, "after")
    if body.phase == "before":
        apply_windows(s, body.start_time, body.end_time, after[0], after[1])
    else:
        apply_windows(s, before[0], before[1], body.start_time, body.end_time)
    audit(db, user, "exam_reopened", "session", s.id, {"phase": body.phase, "start": body.start_time, "end": body.end_time}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), _response_count(db, s.id), request)


@router.post("/sessions/{session_id}/exam/open", response_model=SessionOut)
def open_exam_now(
    session_id: int, body: ExamOpenIn, request: Request, user: User = Depends(staff_or_admin), db: Session = Depends(get_db)
) -> SessionOut:
    """Open the chosen sitting from this moment, for the given number of minutes."""
    s = db.scalar(
        select(LectureSession).options(selectinload(LectureSession.exam_questions), selectinload(LectureSession.trainer)).where(LectureSession.id == session_id)
    )
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    if not s.exam_questions:
        raise ServiceError("أضف أسئلة الامتحان أولاً", code="no_questions")
    open_for(s, body.phase, body.minutes)
    audit(db, user, "exam_opened", "session", s.id, {"phase": body.phase, "minutes": body.minutes}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), _response_count(db, s.id), request)


@router.post("/sessions/{session_id}/exam/close", response_model=SessionOut)
def close_exam_now(
    session_id: int, body: ExamCloseIn, request: Request, user: User = Depends(staff_or_admin), db: Session = Depends(get_db)
) -> SessionOut:
    s = db.scalar(
        select(LectureSession).options(selectinload(LectureSession.exam_questions), selectinload(LectureSession.trainer)).where(LectureSession.id == session_id)
    )
    if s is None:
        raise NotFound("المحاضرة غير موجودة")
    close_for(s, body.phase)
    audit(db, user, "exam_closed", "session", s.id, {"phase": body.phase}, request)
    db.commit()
    db.refresh(s)
    return _session_out(s, settings_service.get_all(db), _response_count(db, s.id), request)


@router.get("/sessions/{session_id}/exam-report")
def exam_report(session_id: int, _: User = Depends(staff_or_admin), db: Session = Depends(get_db)) -> dict:
    from ..services.exams import report_rows

    return report_rows(db, session_id)


@router.get("/sessions/{session_id}/exam.xlsx")
def exam_xlsx(
    session_id: int,
    part: str = Query("before"),
    _: User = Depends(staff_or_admin),
    db: Session = Depends(get_db),
) -> Response:
    from ..services.exams import report_rows

    if part not in {"before", "after", "compare"}:
        raise HTTPException(400, "part must be before, after, or compare")
    data = exports.exam_workbook(report_rows(db, session_id), part)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="exam_{session_id}_{part}.xlsx"'},
    )


@router.get("/sessions/import-template.xlsx")
def sessions_template(request: Request, _: User = Depends(admin_only)) -> Response:
    en = request_lang(request) == "en"
    data = exports.template_workbook(
        (["Date", "Start", "End", "Title", "Trainer", "Room"] if en else ["التاريخ", "من", "إلى", "العنوان", "المحاضر", "القاعة"]),
        [["2026-11-15", "09:30", "11:00", "Introduction to Python" if en else "مقدمة في البرمجة", "Dr. Sara" if en else "د. سارة", "Hall A" if en else "قاعة أ"]],
        "Sessions" if en else "المحاضرات",
    )
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sessions_template.xlsx"'},
    )


@router.post("/sessions/import", response_model=ImportResult)
async def import_sessions(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(admin_only),
    db: Session = Depends(get_db),
) -> ImportResult:
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "الملف كبير جداً")
    try:
        rows = exports.read_table(file.filename or "upload.xlsx", data)
    except Exception:
        raise HTTPException(400, "تعذّرت قراءة الملف. استخدم قالب .xlsx أو ملف .csv بترميز UTF-8") from None

    trainers = {t.name.lower(): t for t in db.scalars(select(Trainer))}
    created = 0
    errors: list[dict] = []
    for row in rows:
        try:
            raw_day = row.get("date")
            day = raw_day.date() if isinstance(raw_day, datetime) else date.fromisoformat(str(raw_day).strip()[:10])
            start = exports.cell_time(row.get("start") or row.get("start_time"))
            end = exports.cell_time(row.get("end") or row.get("end_time"))
            title = " ".join(str(row.get("title") or "").split())
            if not (start and end and title):
                raise ValueError("التاريخ والبداية والنهاية والعنوان مطلوبة")
            if parse_hhmm(end) <= parse_hhmm(start):
                raise ValueError("النهاية يجب أن تكون بعد البداية")
            trainer = None
            tname = " ".join(str(row.get("trainer") or "").split())
            if tname:
                trainer = trainers.get(tname.lower())
                if trainer is None:
                    trainer = Trainer(name=tname)
                    db.add(trainer)
                    db.flush()
                    trainers[tname.lower()] = trainer
            _ensure_training_day(db, day)
            db.add(
                LectureSession(
                    day=day,
                    start_time=parse_hhmm(start),
                    end_time=parse_hhmm(end),
                    title=title[:190],
                    trainer_id=trainer.id if trainer else None,
                    room=(str(row["room"]).strip()[:80] if row.get("room") else None),
                )
            )
            created += 1
        except Exception as exc:
            errors.append({"row": row["_row"], "error": str(exc)})
    audit(db, user, "sessions_imported", "session", None, {"created": created}, request)
    db.commit()
    lang = request_lang(request)
    for e in errors:
        e["error"] = translate(e["error"], lang)
    return ImportResult(created=created, skipped=len(errors), errors=errors)
