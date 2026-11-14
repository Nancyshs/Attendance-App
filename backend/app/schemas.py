"""Pydantic request/response models."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
Role = Literal["admin", "staff", "trainer"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: Role
    trainer_id: int | None = None
    is_active: bool
    last_login_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=120)
    role: Role = "staff"
    trainer_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    trainer_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


# --------------------------------------------------------------------- trainees
class TraineeIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    governorate: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)
    national_id: str | None = Field(default=None, max_length=14)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=11)
    group_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    badge_id: str | None = Field(default=None, pattern=r"^[A-Za-z]\d{2,3}$")

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())


class TraineeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    governorate: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)
    national_id: str | None = Field(default=None, max_length=14)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=11)
    group_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class TraineeOut(ORM):
    id: int
    badge_id: str
    full_name: str
    governorate: str | None = None
    job_title: str | None = None
    organization: str | None = None
    national_id: str | None = None
    email: str | None = None
    phone: str | None = None
    group_name: str | None = None
    notes: str | None = None
    is_active: bool
    photo_url: str | None = None
    qr_token: str | None = None
    created_at: datetime


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[dict[str, Any]]


# ---------------------------------------------------------------------- schedule
class TrainerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    is_active: bool = True


class TrainerOut(ORM):
    id: int
    name: str
    email: str | None = None
    is_active: bool


def _check_hhmm(v: str | None) -> str | None:
    if v is None:
        return v
    if not HHMM.match(v):
        raise ValueError("الوقت يجب أن يكون بصيغة HH:MM")
    return v


class TrainingDayIn(BaseModel):
    date: date
    start_time: str = "09:00"
    end_time: str = "17:00"
    late_after: str = "09:15"
    checkout_from: str = "16:00"
    note: str | None = Field(default=None, max_length=255)

    _v = field_validator("start_time", "end_time", "late_after", "checkout_from")(_check_hhmm)


class TrainingDayUpdate(BaseModel):
    start_time: str | None = None
    end_time: str | None = None
    late_after: str | None = None
    checkout_from: str | None = None
    note: str | None = Field(default=None, max_length=255)

    _v = field_validator("start_time", "end_time", "late_after", "checkout_from")(_check_hhmm)


class TrainingDayOut(ORM):
    id: int
    date: date
    start_time: time
    end_time: time
    late_after: time
    checkout_from: time
    note: str | None = None
    is_auto: bool


class GenerateDaysIn(BaseModel):
    date_from: date
    date_to: date


class ExamQuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    correct: bool = True


class ExamQuestionOut(BaseModel):
    id: int
    text: str
    correct: bool


class ExamReopenIn(BaseModel):
    phase: Literal["before", "after"]
    start_time: str
    end_time: str

    _v = field_validator("start_time", "end_time")(_check_hhmm)


class ExamOpenIn(BaseModel):
    phase: Literal["before", "after"]
    minutes: int = Field(ge=1, le=1440)


class ExamCloseIn(BaseModel):
    phase: Literal["before", "after"]


class SessionIn(BaseModel):
    day: date
    start_time: str
    end_time: str
    title: str = Field(min_length=1, max_length=190)
    description: str | None = Field(default=None, max_length=500)
    trainer_id: int | None = None
    room: str | None = Field(default=None, max_length=80)
    template_id: int | None = None
    axis: str | None = Field(default=None, max_length=190)
    survey_duration_minutes: int | None = Field(default=None, ge=1, le=10080)
    survey_opens_at: datetime | None = None
    survey_closes_at: datetime | None = None
    survey_until_end_of_day: bool = False  # close at local midnight of the session day; otherwise it stays open
    require_attendance: bool = False  # survey and exam only for trainees who checked in
    open_now: bool = False  # action flag: open (or re-open) the survey immediately
    is_cancelled: bool = False
    exam_before_start: str | None = None
    exam_before_end: str | None = None
    exam_after_start: str | None = None
    exam_after_end: str | None = None
    exam_questions: list[ExamQuestionIn] = []

    _v = field_validator("start_time", "end_time")(_check_hhmm)


class SessionOut(BaseModel):
    id: int
    day: date
    start_time: str
    end_time: str
    title: str
    description: str | None
    trainer_id: int | None
    trainer_name: str | None
    room: str | None
    template_id: int | None
    axis: str | None = None
    survey_token: str = ""
    survey_url: str = ""
    survey_duration_minutes: int | None = None
    effective_duration_minutes: int = 30
    survey_opens_at: datetime | None
    survey_closes_at: datetime | None
    survey_until_end_of_day: bool = False
    require_attendance: bool = False
    survey_state: str
    effective_opens_at: datetime
    effective_closes_at: datetime
    is_cancelled: bool
    submissions: int = 0
    exam_token: str = ""
    exam_url: str = ""
    exam_before_opens_at: datetime | None = None
    exam_before_closes_at: datetime | None = None
    exam_after_opens_at: datetime | None = None
    exam_after_closes_at: datetime | None = None
    exam_state: str = "not_open"
    exam_phase: str | None = None
    exam_questions: list[ExamQuestionOut] = []


# --------------------------------------------------------------------- attendance
class ScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=300)
    mode: Literal["auto", "in", "out"] = "auto"
    source: Literal["usb", "camera", "manual"] = "camera"
    client_id: str | None = Field(default=None, min_length=8, max_length=64)
    scanned_at: datetime | None = None
    device: str | None = Field(default=None, max_length=64)


class ManualAttendanceIn(BaseModel):
    check_in_time: str | None = None  # HH:MM local; null = no check-in
    check_out_time: str | None = None
    excused: bool = False
    note: str | None = Field(default=None, max_length=500)

    _v = field_validator("check_in_time", "check_out_time")(_check_hhmm)


# ------------------------------------------------------------------------ surveys
class QuestionIn(BaseModel):
    id: int | None = None
    text: str = Field(min_length=1, max_length=500)
    type: Literal["rating", "nps", "choice", "text"]
    options: list[str] | None = None
    required: bool = True

    @field_validator("options")
    @classmethod
    def _opts(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [o.strip() for o in v if o and o.strip()]
        return cleaned or None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_anonymous: bool = True
    is_default: bool = False
    is_active: bool = True
    questions: list[QuestionIn] = Field(min_length=1, max_length=30)


class QuestionOut(ORM):
    id: int
    position: int
    text: str
    type: str
    options: list[str] | None = None
    required: bool
    is_active: bool


class TemplateOut(ORM):
    id: int
    name: str
    description: str | None = None
    is_anonymous: bool
    is_default: bool
    is_active: bool
    questions: list[QuestionOut]


# ------------------------------------------------------------------------- portal
class PortalAuthIn(BaseModel):
    token: str = Field(min_length=4, max_length=300)


class SurveySubmitIn(BaseModel):
    answers: dict[int, int | str | None]


class SurveyOpenIn(BaseModel):
    duration_minutes: int | None = Field(default=None, ge=1, le=10080)
