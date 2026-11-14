"""SQLAlchemy models."""
from __future__ import annotations

import secrets
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .core.db import UTCDateTime
from .core.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------- users
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="staff")  # admin|staff|trainer
    trainer_id: Mapped[int | None] = mapped_column(ForeignKey("trainers.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Trainer(TimestampMixin, Base):
    __tablename__ = "trainers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(190))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ------------------------------------------------------------------------ trainees
class Trainee(TimestampMixin, Base):
    __tablename__ = "trainees"

    id: Mapped[int] = mapped_column(primary_key=True)
    badge_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)  # e.g. A07
    qr_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    governorate: Mapped[str | None] = mapped_column(String(80))
    job_title: Mapped[str | None] = mapped_column(String(120))
    organization: Mapped[str | None] = mapped_column(String(160))  # الجهة
    national_id: Mapped[str | None] = mapped_column(String(14), unique=True)  # رقم البطاقة، 14 رقماً
    email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(11))
    group_name: Mapped[str | None] = mapped_column(String(120))
    photo_path: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ------------------------------------------------------------------------ schedule
class TrainingDay(TimestampMixin, Base):
    __tablename__ = "training_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    late_after: Mapped[time] = mapped_column(Time, nullable=False)  # check-in after this = Late
    checkout_from: Mapped[time] = mapped_column(Time, nullable=False)  # check-out before this = Early leave
    note: Mapped[str | None] = mapped_column(String(255))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SurveyTemplate(TimestampMixin, Base):
    __tablename__ = "survey_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    questions: Mapped[list[SurveyQuestion]] = relationship(
        back_populates="template", order_by="SurveyQuestion.position", cascade="all, delete-orphan"
    )


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("survey_templates.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # rating|nps|choice|text
    options: Mapped[list | None] = mapped_column(JSON)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    template: Mapped[SurveyTemplate] = relationship(back_populates="questions")


class LectureSession(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_day_start", "day", "start_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    title: Mapped[str] = mapped_column(String(190), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    trainer_id: Mapped[int | None] = mapped_column(ForeignKey("trainers.id", ondelete="SET NULL"))
    room: Mapped[str | None] = mapped_column(String(80))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("survey_templates.id", ondelete="SET NULL"))
    axis: Mapped[str | None] = mapped_column(String(190))  # "المحور التدريبي" printed on the survey
    # Public (anonymous) survey link: /s/<survey_token>. The QR code of the session points here.
    survey_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16)
    )
    survey_duration_minutes: Mapped[int | None] = mapped_column(Integer)  # set only by a manual open; NULL = no timed close
    survey_opens_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # NULL = opens when the session ends
    survey_closes_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # NULL = end of day, or never, per the flag below
    survey_until_end_of_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # When set, the survey and the exam accept only trainees who checked in that day.
    require_attendance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Public exam link: /x/<exam_token>. The same questions are sat before and after the lecture.
    exam_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16)
    )
    exam_before_opens_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    exam_before_closes_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    exam_after_opens_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    exam_after_closes_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    trainer: Mapped[Trainer | None] = relationship()
    template: Mapped[SurveyTemplate | None] = relationship()
    exam_questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="session", order_by="ExamQuestion.position", cascade="all, delete-orphan"
    )
    exam_attempts: Mapped[list["ExamAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------- attendance
class AttendanceDay(TimestampMixin, Base):
    __tablename__ = "attendance_days"
    __table_args__ = (
        UniqueConstraint("trainee_id", "day", name="uq_attendance_trainee_day"),
        Index("ix_attendance_day", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    check_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    check_in_source: Mapped[str | None] = mapped_column(String(16))  # usb|camera|manual
    check_out_source: Mapped[str | None] = mapped_column(String(16))
    check_in_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    check_out_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    excused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    trainee: Mapped[Trainee] = relationship()


class ScanLog(TimestampMixin, Base):
    """Every scan attempt, accepted or rejected. Also provides idempotency via client_id."""

    __tablename__ = "scan_logs"
    __table_args__ = (Index("ix_scan_logs_scanned_at", "scanned_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    trainee_id: Mapped[int | None] = mapped_column(ForeignKey("trainees.id", ondelete="SET NULL"))
    raw_input: Mapped[str | None] = mapped_column(String(190))
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # check_in|check_out|duplicate|rejected
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    device: Mapped[str | None] = mapped_column(String(64))
    scanned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    scanned_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)  # the response payload, replayed for duplicate client_ids

    trainee: Mapped[Trainee | None] = relationship()


# -------------------------------------------------------------------------- survey
class SurveySubmission(Base):
    """Who has answered which session. Contains NO answers, which keeps responses anonymous."""

    __tablename__ = "survey_submissions"
    __table_args__ = (UniqueConstraint("session_id", "trainee_id", name="uq_submission_session_trainee"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        Index("ix_responses_session", "session_id"),
        # one answer per device for the public (QR) survey; NULL for badge-portal responses
        UniqueConstraint("session_id", "device_hash", name="uq_response_session_device"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_hash: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("survey_templates.id", ondelete="SET NULL"))
    trainee_id: Mapped[int | None] = mapped_column(ForeignKey("trainees.id", ondelete="SET NULL"))  # NULL if anonymous
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)  # blurred to the hour if anonymous

    answers: Mapped[list[SurveyAnswer]] = relationship(back_populates="response", cascade="all, delete-orphan")


class SurveyAnswer(Base):
    __tablename__ = "survey_answers"
    __table_args__ = (Index("ix_answers_question", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("survey_responses.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)  # rating (1-5) or nps (0-10)
    choice: Mapped[str | None] = mapped_column(String(190))
    text: Mapped[str | None] = mapped_column(Text)

    response: Mapped[SurveyResponse] = relationship(back_populates="answers")


# ---------------------------------------------------------------------------- exam
class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (Index("ix_exam_questions_session", "session_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)  # True = صح

    session: Mapped[LectureSession] = relationship(back_populates="exam_questions")


class ExamAttempt(Base):
    """One trainee's answers for one sitting: before the lecture or after it."""

    __tablename__ = "exam_attempts"
    __table_args__ = (UniqueConstraint("session_id", "trainee_id", "phase", name="uq_exam_attempt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    trainee_id: Mapped[int] = mapped_column(ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[str] = mapped_column(String(8), nullable=False)  # before|after
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    session: Mapped[LectureSession] = relationship(back_populates="exam_attempts")
    trainee: Mapped[Trainee] = relationship()
    answers: Mapped[list["ExamAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class ExamAnswer(Base):
    __tablename__ = "exam_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("exam_questions.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)  # True = the trainee answered صح

    attempt: Mapped[ExamAttempt] = relationship(back_populates="answers")
    question: Mapped[ExamQuestion] = relationship()


# ---------------------------------------------------------------------------- misc
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
