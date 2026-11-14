"""Aggregations for the dashboard, attendance report and survey report."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..core.timeutil import as_utc, local_today, to_local, utcnow
from ..models import (
    AttendanceDay,
    LectureSession,
    ScanLog,
    SurveyAnswer,
    SurveyQuestion,
    SurveyResponse,
    Trainee,
    Trainer,
    TrainingDay,
)
from . import settings as settings_service
from .attendance import classify, day_is_over, get_or_create_training_day
from .surveys import survey_state, survey_window


def _iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat().replace("+00:00", "Z") if dt else None


def _photo(t: Trainee) -> str | None:
    return f"/media/{t.photo_path}" if t.photo_path else None


def survey_respondents(
    db: Session, date_from: date, date_to: date, *, trainer_id: int | None = None, session_id: int | None = None
) -> dict[str, Any]:
    """Named trainees who submitted a survey, with their profile and each answer."""
    from .surveys import public_person_hash

    stmt = (
        select(SurveyResponse)
        .join(LectureSession, LectureSession.id == SurveyResponse.session_id)
        .where(LectureSession.day >= date_from, LectureSession.day <= date_to)
        .options(selectinload(SurveyResponse.answers))
        .order_by(LectureSession.day, SurveyResponse.id)
    )
    if trainer_id is not None:
        stmt = stmt.where(LectureSession.trainer_id == trainer_id)
    if session_id is not None:
        stmt = stmt.where(SurveyResponse.session_id == session_id)
    responses = list(db.scalars(stmt).unique())
    if not responses:
        return {"rows": []}

    session_ids = {r.session_id for r in responses}
    sessions = list(
        db.scalars(select(LectureSession).options(selectinload(LectureSession.trainer)).where(LectureSession.id.in_(session_ids)))
    )
    session_by_id = {s.id: s for s in sessions}
    question_ids = {a.question_id for r in responses for a in r.answers}
    questions = {q.id: q for q in db.scalars(select(SurveyQuestion).where(SurveyQuestion.id.in_(question_ids)))} if question_ids else {}
    trainees = list(db.scalars(select(Trainee)))
    by_id = {t.id: t for t in trainees}
    hash_lookup: dict[tuple[int, str], Trainee] = {}
    if any(r.trainee_id is None and r.device_hash for r in responses):
        for s in sessions:
            for t in trainees:
                hash_lookup[(s.id, public_person_hash(s.id, t.id))] = t

    rows: list[dict[str, Any]] = []
    for response in responses:
        trainee = by_id.get(response.trainee_id) if response.trainee_id else None
        if trainee is None and response.device_hash:
            trainee = hash_lookup.get((response.session_id, response.device_hash))
        if trainee is None:
            continue
        session = session_by_id[response.session_id]
        answers = []
        for answer in response.answers:
            question = questions.get(answer.question_id)
            if answer.text is not None:
                value: int | str | None = answer.text
            elif answer.choice is not None:
                value = answer.choice
            else:
                value = answer.rating
            answers.append(
                {
                    "question_id": answer.question_id,
                    "text": question.text if question else "",
                    "type": question.type if question else "text",
                    "position": question.position if question else 0,
                    "value": value,
                }
            )
        answers.sort(key=lambda item: (item["position"], item["question_id"]))
        rows.append(
            {
                "response_id": response.id,
                "submitted_at": _iso(response.submitted_at),
                "trainee": {
                    "id": trainee.id,
                    "full_name": trainee.full_name,
                    "badge_id": trainee.badge_id,
                    "governorate": trainee.governorate,
                    "job_title": trainee.job_title,
                    "organization": trainee.organization,
                    "national_id": trainee.national_id,
                    "phone": trainee.phone,
                    "email": trainee.email,
                    "group_name": trainee.group_name,
                },
                "session": {
                    "id": session.id,
                    "title": session.title,
                    "axis": session.axis,
                    "day": session.day.isoformat(),
                    "trainer_name": session.trainer.name if session.trainer else None,
                },
                "answers": answers,
            }
        )
    rows.sort(key=lambda item: (item["session"]["day"], item["session"]["title"], item["trainee"]["full_name"]))
    return {"rows": rows}


# ------------------------------------------------------------------- attendance
def attendance_report(
    db: Session, date_from: date, date_to: date, *, include_inactive: bool = False
) -> dict[str, Any]:
    now = utcnow()
    days = list(
        db.scalars(
            select(TrainingDay).where(TrainingDay.date >= date_from, TrainingDay.date <= date_to).order_by(TrainingDay.date)
        )
    )
    q = select(Trainee).order_by(Trainee.badge_id)
    if not include_inactive:
        q = q.where(Trainee.is_active.is_(True))
    trainees = list(db.scalars(q))

    rows = db.scalars(
        select(AttendanceDay).where(AttendanceDay.day >= date_from, AttendanceDay.day <= date_to)
    )
    by_key = {(r.trainee_id, r.day): r for r in rows}

    out_trainees = []
    for t in trainees:
        cells = []
        counts = defaultdict(int)
        worked_total = 0
        worked_n = 0
        for d in days:
            row = by_key.get((t.id, d.date))
            c = classify(row, d, now)
            counts[c.status] += 1
            if c.early_leave:
                counts["early_leave"] += 1
            if c.incomplete:
                counts["incomplete"] += 1
            if c.worked_minutes is not None:
                worked_total += c.worked_minutes
                worked_n += 1
            cells.append(
                {
                    "date": d.date.isoformat(),
                    "status": c.status,
                    "early_leave": c.early_leave,
                    "incomplete": c.incomplete,
                    "check_in_at": _iso(row.check_in_at) if row else None,
                    "check_out_at": _iso(row.check_out_at) if row else None,
                    "worked_minutes": c.worked_minutes,
                    "excused": bool(row and row.excused),
                    "note": row.note if row else None,
                    "is_manual": bool(row and row.is_manual),
                }
            )
        attended = counts["present"] + counts["late"]
        denominator = attended + counts["absent"]  # excused days are neither for nor against
        out_trainees.append(
            {
                "trainee": {
                    "id": t.id,
                    "badge_id": t.badge_id,
                    "full_name": t.full_name,
                    "group_name": t.group_name,
                    "photo_url": _photo(t),
                    "is_active": t.is_active,
                },
                "summary": {
                    "present": counts["present"],
                    "late": counts["late"],
                    "absent": counts["absent"],
                    "excused": counts["excused"],
                    "early_leave": counts["early_leave"],
                    "incomplete": counts["incomplete"],
                    "attendance_pct": round(attended / denominator * 100, 1) if denominator else None,
                    "avg_hours": round(worked_total / worked_n / 60, 2) if worked_n else None,
                },
                "cells": cells,
            }
        )
    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        "days": [
            {
                "date": d.date.isoformat(),
                "start_time": d.start_time.strftime("%H:%M"),
                "end_time": d.end_time.strftime("%H:%M"),
                "is_over": day_is_over(d, now),
            }
            for d in days
        ],
        "trainees": out_trainees,
    }


# ------------------------------------------------------------------------ surveys
def _session_label(s: LectureSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "day": s.day.isoformat(),
        "start_time": s.start_time.strftime("%H:%M"),
        "end_time": s.end_time.strftime("%H:%M"),
        "trainer_id": s.trainer_id,
        "trainer_name": s.trainer.name if s.trainer else None,
        "room": s.room,
    }


def survey_report(
    db: Session, date_from: date, date_to: date, *, trainer_id: int | None = None, session_id: int | None = None
) -> dict[str, Any]:
    sq = select(LectureSession).where(
        LectureSession.day >= date_from, LectureSession.day <= date_to, LectureSession.is_cancelled.is_(False)
    )
    if trainer_id:
        sq = sq.where(LectureSession.trainer_id == trainer_id)
    if session_id:
        sq = sq.where(LectureSession.id == session_id)
    sessions = list(db.scalars(sq.order_by(LectureSession.day, LectureSession.start_time)))
    ids = [s.id for s in sessions]
    if not ids:
        return {"sessions": [], "trainers": [], "trend": [], "comments": [], "overall": _empty_overall()}

    # per session/question aggregates
    agg = db.execute(
        select(
            SurveyResponse.session_id,
            SurveyAnswer.question_id,
            func.avg(SurveyAnswer.rating),
            func.count(SurveyAnswer.rating),
        )
        .join(SurveyResponse, SurveyResponse.id == SurveyAnswer.response_id)
        .where(SurveyResponse.session_id.in_(ids), SurveyAnswer.rating.is_not(None))
        .group_by(SurveyResponse.session_id, SurveyAnswer.question_id)
    ).all()
    dist = db.execute(
        select(SurveyResponse.session_id, SurveyAnswer.question_id, SurveyAnswer.rating, func.count())
        .join(SurveyResponse, SurveyResponse.id == SurveyAnswer.response_id)
        .where(SurveyResponse.session_id.in_(ids), SurveyAnswer.rating.is_not(None))
        .group_by(SurveyResponse.session_id, SurveyAnswer.question_id, SurveyAnswer.rating)
    ).all()
    choices = db.execute(
        select(SurveyResponse.session_id, SurveyAnswer.question_id, SurveyAnswer.choice, func.count())
        .join(SurveyResponse, SurveyResponse.id == SurveyAnswer.response_id)
        .where(SurveyResponse.session_id.in_(ids), SurveyAnswer.choice.is_not(None))
        .group_by(SurveyResponse.session_id, SurveyAnswer.question_id, SurveyAnswer.choice)
    ).all()
    comments_rows = db.execute(
        select(SurveyResponse.session_id, SurveyAnswer.question_id, SurveyAnswer.text, SurveyResponse.submitted_at)
        .join(SurveyResponse, SurveyResponse.id == SurveyAnswer.response_id)
        .where(SurveyResponse.session_id.in_(ids), SurveyAnswer.text.is_not(None), SurveyAnswer.text != "")
        .order_by(SurveyResponse.submitted_at.desc())
    ).all()
    responses_count = dict(
        db.execute(
            select(SurveyResponse.session_id, func.count())
            .where(SurveyResponse.session_id.in_(ids))
            .group_by(SurveyResponse.session_id)
        ).all()
    )
    submissions_count = dict(
        db.execute(
            select(SurveyResponse.session_id, func.count())
            .where(SurveyResponse.session_id.in_(ids))
            .group_by(SurveyResponse.session_id)
        ).all()
    )
    eligible_by_day = dict(
        db.execute(
            select(AttendanceDay.day, func.count())
            .where(
                AttendanceDay.day >= date_from,
                AttendanceDay.day <= date_to,
                AttendanceDay.check_in_at.is_not(None),
            )
            .group_by(AttendanceDay.day)
        ).all()
    )
    q_ids = {row[1] for row in agg} | {row[1] for row in choices} | {row[1] for row in comments_rows}
    questions = {q.id: q for q in db.scalars(select(SurveyQuestion).where(SurveyQuestion.id.in_(q_ids)))} if q_ids else {}

    dist_map: dict[tuple[int, int], dict[int, int]] = defaultdict(dict)
    for sid, qid, rating, n in dist:
        dist_map[(sid, qid)][int(rating)] = int(n)
    choice_map: dict[tuple[int, int], dict[str, int]] = defaultdict(dict)
    for sid, qid, choice, n in choices:
        choice_map[(sid, qid)][choice] = int(n)
    comment_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for sid, qid, text, at in comments_rows:
        comment_map[sid].append(
            {
                "session_id": sid,
                "question": questions[qid].text if qid in questions else "",
                "text": text,
                "submitted_at": _iso(at),
            }
        )

    session_out = []
    all_comments: list[dict[str, Any]] = []
    for s in sessions:
        qstats = []
        rating_sum = 0.0
        rating_n = 0
        promoters = detractors = nps_n = 0
        for sid, qid, avg, n in agg:
            if sid != s.id or qid not in questions:
                continue
            q = questions[qid]
            d = dist_map[(sid, qid)]
            qstats.append(
                {
                    "question_id": qid,
                    "text": q.text,
                    "type": q.type,
                    "avg": round(float(avg), 2),
                    "percent": round(float(avg) / (10 if q.type == "nps" else 5) * 100, 1),
                    "count": int(n),
                    "distribution": d,
                }
            )
            if q.type == "rating":
                rating_sum += float(avg) * int(n)
                rating_n += int(n)
            elif q.type == "nps":
                nps_n += int(n)
                promoters += sum(c for score, c in d.items() if score >= 9)
                detractors += sum(c for score, c in d.items() if score <= 6)
        for (sid, qid), opts in choice_map.items():
            if sid == s.id and qid in questions:
                qstats.append(
                    {
                        "question_id": qid,
                        "text": questions[qid].text,
                        "type": "choice",
                        "avg": None,
                        "percent": None,
                        "count": sum(opts.values()),
                        "choices": opts,
                    }
                )
        responses = int(responses_count.get(s.id, 0))
        submissions = int(submissions_count.get(s.id, 0))
        eligible = int(eligible_by_day.get(s.day, 0))
        avg_rating = round(rating_sum / rating_n, 2) if rating_n else None
        item = {
            **_session_label(s),
            "avg_rating": avg_rating,
            "percent": round(avg_rating / 5 * 100, 1) if avg_rating is not None else None,
            "responses": responses,
            "eligible": eligible,
            "response_rate": round(submissions / eligible * 100, 1) if eligible else None,
            "nps": round((promoters - detractors) / nps_n * 100) if nps_n else None,
            "questions": sorted(qstats, key=lambda x: x["question_id"]),
            "comments": comment_map.get(s.id, []),
        }
        all_comments.extend(
            {**c, "session_title": s.title, "day": s.day.isoformat(), "trainer_name": item["trainer_name"]}
            for c in comment_map.get(s.id, [])
        )
        session_out.append(item)

    # trainer aggregation (weighted by number of ratings)
    trainer_acc: dict[int | None, dict[str, Any]] = {}
    for s_item in session_out:
        if s_item["avg_rating"] is None:
            continue
        key = s_item["trainer_id"]
        acc = trainer_acc.setdefault(
            key, {"trainer_id": key, "trainer_name": s_item["trainer_name"] or "—", "sum": 0.0, "n": 0, "sessions": 0}
        )
        weight = max(1, s_item["responses"])
        acc["sum"] += s_item["avg_rating"] * weight
        acc["n"] += weight
        acc["sessions"] += 1
    trainers = sorted(
        (
            {
                "trainer_id": a["trainer_id"],
                "trainer_name": a["trainer_name"],
                "avg_rating": round(a["sum"] / a["n"], 2),
                "responses": a["n"],
                "sessions": a["sessions"],
            }
            for a in trainer_acc.values()
        ),
        key=lambda x: -x["avg_rating"],
    )

    trend_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for s_item in session_out:
        if s_item["avg_rating"] is None:
            continue
        w = max(1, s_item["responses"])
        trend_acc[s_item["day"]][0] += s_item["avg_rating"] * w
        trend_acc[s_item["day"]][1] += w
    trend = [{"day": d, "avg_rating": round(v[0] / v[1], 2)} for d, v in sorted(trend_acc.items())]

    rated = [s for s in session_out if s["avg_rating"] is not None]
    total_w = sum(max(1, s["responses"]) for s in rated)
    overall = {
        "sessions": len(session_out),
        "responses": sum(s["responses"] for s in session_out),
        "avg_rating": round(sum(s["avg_rating"] * max(1, s["responses"]) for s in rated) / total_w, 2) if total_w else None,
    }
    all_comments.sort(key=lambda c: c["submitted_at"] or "", reverse=True)
    return {"sessions": session_out, "trainers": trainers, "trend": trend, "comments": all_comments[:500], "overall": overall}


def _empty_overall() -> dict[str, Any]:
    return {"sessions": 0, "responses": 0, "avg_rating": None}


# ---------------------------------------------------------------------- dashboard
def dashboard(db: Session, day: date | None = None) -> dict[str, Any]:
    now = utcnow()
    today = day or local_today()
    cfg = settings_service.get_all(db)
    training_day = get_or_create_training_day(db, today, auto=(today == local_today()))

    active_total = db.scalar(select(func.count()).select_from(Trainee).where(Trainee.is_active.is_(True))) or 0
    rows = list(
        db.execute(
            select(AttendanceDay, Trainee)
            .join(Trainee, Trainee.id == AttendanceDay.trainee_id)
            .where(AttendanceDay.day == today)
        ).all()
    )
    present = late = checked_out = excused = early = arrived = 0
    if training_day:
        for row, t in rows:
            if not t.is_active:
                continue
            c = classify(row, training_day, now)
            if row.check_in_at:
                arrived += 1
            if c.status == "present":
                present += 1
            elif c.status == "late":
                late += 1
            elif c.status == "excused":
                excused += 1
            if row.check_out_at:
                checked_out += 1
            if c.early_leave:
                early += 1
    accounted = sum(1 for row, t in rows if t.is_active and (row.check_in_at or row.excused))
    waiting = max(0, active_total - accounted)
    over = bool(training_day and day_is_over(training_day, now))

    recent = db.execute(
        select(ScanLog, Trainee)
        .outerjoin(Trainee, Trainee.id == ScanLog.trainee_id)
        .order_by(ScanLog.id.desc())
        .limit(20)
    ).all()
    recent_out = [
        {
            "id": log.id,
            "at": _iso(log.scanned_at),
            "action": log.action,
            "ok": log.ok,
            "message": log.message,
            "source": log.source,
            "trainee_name": t.full_name if t else None,
            "badge_id": t.badge_id if t else None,
        }
        for log, t in recent
    ]

    sessions = list(
        db.scalars(select(LectureSession).where(LectureSession.day == today).order_by(LectureSession.start_time))
    )
    sess_out = []
    if sessions:
        ids = [s.id for s in sessions]
        subs = dict(
            db.execute(
                select(SurveyResponse.session_id, func.count())
                .where(SurveyResponse.session_id.in_(ids))
                .group_by(SurveyResponse.session_id)
            ).all()
        )
        for s in sessions:
            opens, closes = survey_window(s, cfg)
            sess_out.append(
                {
                    **_session_label(s),
                    "survey_state": survey_state(s, cfg, now),
                    "survey_opens_at": _iso(opens),
                    "survey_closes_at": _iso(closes),
                    "submissions": int(subs.get(s.id, 0)),
                    "is_cancelled": s.is_cancelled,
                }
            )

    # alerts ---------------------------------------------------------------------
    alerts: list[dict[str, Any]] = []
    past_days = [
        d
        for d in db.scalars(select(TrainingDay).where(TrainingDay.date <= today))
        if day_is_over(d, now)
    ]
    threshold = int(cfg["absence_alert_threshold"])
    if past_days and threshold > 0:
        past_dates = [d.date for d in past_days]
        attended = dict(
            db.execute(
                select(AttendanceDay.trainee_id, func.count())
                .where(AttendanceDay.day.in_(past_dates), AttendanceDay.check_in_at.is_not(None))
                .group_by(AttendanceDay.trainee_id)
            ).all()
        )
        excused_ct = dict(
            db.execute(
                select(AttendanceDay.trainee_id, func.count())
                .where(
                    AttendanceDay.day.in_(past_dates),
                    AttendanceDay.check_in_at.is_(None),
                    AttendanceDay.excused.is_(True),
                )
                .group_by(AttendanceDay.trainee_id)
            ).all()
        )
        for t in db.scalars(select(Trainee).where(Trainee.is_active.is_(True))):
            absences = len(past_dates) - int(attended.get(t.id, 0)) - int(excused_ct.get(t.id, 0))
            if absences >= threshold:
                alerts.append(
                    {
                        "type": "absences",
                        "severity": "high" if absences >= threshold * 2 else "medium",
                        "trainee_id": t.id,
                        "title": t.full_name,
                        "badge_id": t.badge_id,
                        "value": absences,
                    }
                )
    low = float(cfg["low_rating_threshold"])
    recent_survey = survey_report(db, today - timedelta(days=14), today)
    for s in recent_survey["sessions"]:
        if s["avg_rating"] is not None and s["responses"] >= 3 and s["avg_rating"] < low:
            alerts.append(
                {
                    "type": "low_rating",
                    "severity": "high" if s["avg_rating"] < low - 0.5 else "medium",
                    "session_id": s["id"],
                    "title": s["title"],
                    "trainer_name": s["trainer_name"],
                    "day": s["day"],
                    "value": s["avg_rating"],
                }
            )
    alerts.sort(key=lambda a: (a["severity"] != "high", a["type"]))

    return {
        "date": today.isoformat(),
        "program_name": cfg["program_name"],
        "has_training_day": training_day is not None,
        "day": (
            {
                "start_time": training_day.start_time.strftime("%H:%M"),
                "end_time": training_day.end_time.strftime("%H:%M"),
                "late_after": training_day.late_after.strftime("%H:%M"),
                "is_over": over,
            }
            if training_day
            else None
        ),
        "totals": {
            "active": active_total,
            "arrived": arrived,
            "on_time": present,
            "late": late,
            "checked_out": checked_out,
            "excused": excused,
            "not_arrived": waiting,
            "early_leave": early,
            "present_now": max(0, arrived - checked_out),
        },
        "recent_scans": recent_out,
        "sessions": sess_out,
        "alerts": alerts[:30],
        "server_time": _iso(now),
        "local_time": to_local(now).strftime("%H:%M"),
    }
