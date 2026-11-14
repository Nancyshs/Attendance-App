"""Idempotent first-run setup.

    python -m scripts.seed --username admin            # prompts for a password
    python -m scripts.seed --username admin --password "S0me-long-pass"
    python -m scripts.seed --demo                      # adds 50 fake trainees + a week of sessions (testing only)

Safe to run repeatedly: existing data is never overwritten.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from datetime import timedelta

from sqlalchemy import func, select, update

from app.core.db import SessionLocal
from app.core.security import hash_password, new_qr_token
from app.core.timeutil import local_today, parse_hhmm
from app.models import (
    LectureSession,
    SurveyQuestion,
    SurveyTemplate,
    Trainee,
    Trainer,
    TrainingDay,
    User,
)
from app.routers.trainees import next_badge_id
from app.services import settings as settings_service
from app.services.attendance import default_day_values

OLD_TEMPLATE_NAME = "تقييم المحاضرة القياسي"
STANDARD_TEMPLATE_NAME = "استبيان تقييم جودة الجلسة التدريبية"

# (text, type, options, required) -- the programme's official session-quality form
STANDARD_QUESTIONS = [
    ("وضوح عناصر الجلسة التدريبية", "rating", None, True),
    ("جودة المحتوى العلمي ودقة المعلومات المقدمة", "rating", None, True),
    ("ارتباط موضوع الجلسة بطبيعة عملي واحتياجاتي المهنية", "rating", None, True),
    ("وضوح شرح المدرب وقدرته على توصيل المعلومات", "rating", None, True),
    ("جودة الأمثلة والتطبيقات العملية المقدمة", "rating", None, True),
    ("مناسبة الوقت المخصص للمحتوى التدريبي", "rating", None, True),
    ("مدى إمكانية تطبيق ما تعلمته في مجال عملي", "rating", None, True),
    ("التقييم العام لجودة الجلسة التدريبية", "rating", None, True),
    ("ما أكثر معلومة أو مهارة استفدت منها خلال الجلسة؟", "text", None, True),
    ("ما أهم مقترح لديك لتحسين هذه الجلسة؟", "text", None, True),
]


def ensure_template(db) -> None:
    """Creates the standard session survey. It becomes the default only when nothing else was chosen yet
    (or the default is still the old stock template), so an admin's own default is never replaced."""
    if db.scalar(select(SurveyTemplate).where(SurveyTemplate.name == STANDARD_TEMPLATE_NAME)):
        return
    current_default = db.scalar(select(SurveyTemplate).where(SurveyTemplate.is_default.is_(True)))
    make_default = current_default is None or current_default.name == OLD_TEMPLATE_NAME
    tpl = SurveyTemplate(
        name=STANDARD_TEMPLATE_NAME,
        description="8 معايير تقييم من 1 إلى 5 + سؤالان مفتوحان",
        is_default=False,
        is_anonymous=True,
    )
    for pos, (text, qtype, options, required) in enumerate(STANDARD_QUESTIONS):
        tpl.questions.append(SurveyQuestion(position=pos, text=text, type=qtype, options=options, required=required))
    db.add(tpl)
    db.flush()
    if make_default:
        db.execute(update(SurveyTemplate).values(is_default=False))
        tpl.is_default = True
    print("  + standard session survey created" + (" (default)" if make_default else ""))

def ensure_admin(db, username: str, password: str | None) -> None:
    if db.scalar(select(User).where(User.username == username)):
        print(f"  = user '{username}' already exists")
        return
    generated = False
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass(f"Password for '{username}' (min 8 chars): ")
        if not password:
            password, generated = secrets.token_urlsafe(12), True
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters")
    db.add(User(username=username, password_hash=hash_password(password), full_name="مدير النظام", role="admin"))
    print(f"  + admin '{username}' created" + (f" with generated password: {password}" if generated else ""))


def demo(db) -> None:
    if db.scalar(select(func.count()).select_from(Trainee)):
        print("  = trainees exist, skipping demo data")
        return
    names = [f"متدرب {i:02d}" for i in range(1, 51)]
    for name in names:
        db.add(Trainee(badge_id=next_badge_id(db), qr_token=new_qr_token(), full_name=name, group_name="المجموعة 1"))
        db.flush()
    trainers = [Trainer(name=n) for n in ("د. سارة", "م. عمر", "أ. ليلى")]
    db.add_all(trainers)
    db.flush()
    cfg = settings_service.get_all(db)
    values = default_day_values(cfg)
    slots = [("09:30", "10:30"), ("10:45", "11:45"), ("12:00", "13:00"), ("14:00", "15:00"), ("15:15", "16:15")]
    today = local_today()
    for offset in range(0, 5):
        day = today + timedelta(days=offset)
        if day.weekday() not in cfg["working_weekdays"]:
            continue
        if not db.scalar(select(TrainingDay).where(TrainingDay.date == day)):
            db.add(TrainingDay(date=day, **values))
        for i, (start, end) in enumerate(slots):
            db.add(
                LectureSession(
                    day=day,
                    start_time=parse_hhmm(start),
                    end_time=parse_hhmm(end),
                    title=f"المحاضرة {i + 1}",
                    trainer_id=trainers[i % 3].id,
                    room="قاعة أ",
                )
            )
    print("  + demo trainees, trainers and sessions created")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=None)
    parser.add_argument("--demo", action="store_true", help="add demo data (do NOT use in production)")
    args = parser.parse_args()

    with SessionLocal() as db:
        print("Seeding...")
        ensure_template(db)
        ensure_admin(db, args.username, args.password)
        if args.demo:
            demo(db)
        db.commit()
    print("Done.")


if __name__ == "__main__":
    main()
