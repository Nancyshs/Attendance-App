"""True/false exam: two sittings on the lecture day, one QR, and a three-sheet workbook."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook

from app.core.timeutil import to_local, utcnow


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def test_exam_is_sat_before_and_after_and_exports_three_sheets(client, db, admin_headers, make_trainees):
    (trainee,) = make_trainees(1)
    now = to_local(utcnow())
    start = max(0, now.hour * 60 + now.minute - 5)
    end = min(23 * 60 + 59, now.hour * 60 + now.minute + 5)
    if end <= start:
        end = min(23 * 60 + 59, start + 1)
    body = {
        "day": str(now.date()),
        "start_time": "09:00",
        "end_time": "10:00",
        "title": "امتحان الجلسة",
        "exam_before_start": _hhmm(start),
        "exam_before_end": _hhmm(end),
        "exam_questions": [
            {"text": "السماء زرقاء", "correct": True},
            {"text": "الثلج ساخن", "correct": False},
        ],
    }
    created = client.post("/api/sessions", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["exam_state"] == "open"
    assert session["exam_phase"] == "before"
    assert session["exam_url"].endswith(f"/x/{session['exam_token']}")
    assert "correct" not in client.get(f"/api/public/exams/{session['exam_token']}").json()["questions"][0]

    token = session["exam_token"]
    who = client.post(f"/api/public/exams/{token}/identify", json={"badge_id": trainee.badge_id.lower()})
    assert who.status_code == 200 and who.json()["submitted"] is False
    qids = [q["id"] for q in session["exam_questions"]]
    sent = client.post(f"/api/public/exams/{token}", json={"badge_id": trainee.badge_id, "answers": {str(qids[0]): True, str(qids[1]): False}})
    assert sent.status_code == 201, sent.text
    assert client.post(f"/api/public/exams/{token}", json={"badge_id": trainee.badge_id, "answers": {str(qids[0]): True, str(qids[1]): False}}).status_code == 409

    locked = client.put("/api/sessions/" + str(session["id"]), json={**body, "exam_questions": [{"text": "سؤال جديد", "correct": True}]}, headers=admin_headers)
    assert locked.status_code == 409 and locked.json()["code"] == "exam_started"

    overlap = client.post(
        "/api/sessions/" + str(session["id"]) + "/exam/reopen",
        json={"phase": "after", "start_time": _hhmm(start), "end_time": _hhmm(end)},
        headers=admin_headers,
    )
    assert overlap.status_code == 400 and overlap.json()["code"] == "exam_window"

    minute = now.hour * 60 + now.minute
    if minute >= 3:
        opened = client.post(
            f"/api/sessions/{session['id']}/exam/reopen",
            json={"phase": "before", "start_time": "00:00", "end_time": "00:01"},
            headers=admin_headers,
        )
        assert opened.status_code == 200, opened.text
        opened = client.post(
            f"/api/sessions/{session['id']}/exam/reopen",
            json={"phase": "after", "start_time": "00:02", "end_time": "23:59"},
            headers=admin_headers,
        )
        assert opened.status_code == 200 and opened.json()["exam_phase"] == "after"
        again = client.post(
            f"/api/public/exams/{token}",
            json={"badge_id": trainee.badge_id, "answers": {str(qids[0]): False, str(qids[1]): False}},
        )
        assert again.status_code == 201, again.text

    before_book = load_workbook(BytesIO(client.get(f"/api/sessions/{session['id']}/exam.xlsx?part=before", headers=admin_headers).content))
    after_book = load_workbook(BytesIO(client.get(f"/api/sessions/{session['id']}/exam.xlsx?part=after", headers=admin_headers).content))
    compare_book = load_workbook(BytesIO(client.get(f"/api/sessions/{session['id']}/exam.xlsx?part=compare", headers=admin_headers).content))
    assert before_book.sheetnames == ["قبل المحاضرة"]
    assert after_book.sheetnames == ["بعد المحاضرة"]
    assert compare_book.sheetnames == ["المقارنة"]
    before = list(before_book["قبل المحاضرة"].iter_rows(min_row=3, values_only=True))
    assert before[0][0] == trainee.badge_id
    assert before[0][2] == "صح" and before[0][3] == "خطأ"
    poster = client.get(f"/api/sessions/{session['id']}/exam-qr.svg", headers=admin_headers)
    assert poster.status_code == 200 and b"<svg" in poster.content

    # a window that has not started yet is reported as not open, with its own phase
    tomorrow = now.date() + timedelta(days=1)
    future = client.post(
        "/api/sessions",
        json={"day": str(tomorrow), "start_time": "09:00", "end_time": "10:00", "title": "غداً", "exam_before_start": "09:00", "exam_before_end": "09:10"},
        headers=admin_headers,
    )
    assert future.status_code == 201 and future.json()["exam_state"] == "not_open" and future.json()["exam_phase"] == "before"


def test_lecture_can_limit_survey_and_exam_to_checked_in_trainees(client, db, admin_headers, staff, today_day, make_trainees):
    from app.services.attendance import process_scan

    (trainee,) = make_trainees(1)
    now = to_local(utcnow())
    start = max(0, now.hour * 60 + now.minute - 5)
    end = min(23 * 60 + 59, now.hour * 60 + now.minute + 5)
    if end <= start:
        end = min(23 * 60 + 59, start + 1)
    created = client.post(
        "/api/sessions",
        json={
            "day": str(now.date()),
            "start_time": "09:00",
            "end_time": "10:00",
            "title": "حضور إجباري",
            "require_attendance": True,
            "exam_before_start": _hhmm(start),
            "exam_before_end": _hhmm(end),
            "exam_questions": [{"text": "سؤال", "correct": True}],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["require_attendance"] is True
    blocked_exam = client.post(f"/api/public/exams/{session['exam_token']}/identify", json={"badge_id": trainee.badge_id})
    blocked_survey = client.post(f"/api/public/surveys/{session['survey_token']}/identify", json={"badge_id": trainee.badge_id})
    assert blocked_exam.status_code == 403 and blocked_exam.json()["code"] == "not_attended"
    assert blocked_survey.status_code == 403 and blocked_survey.json()["code"] == "not_attended"

    process_scan(db, raw=trainee.qr_token, mode="auto", source="usb", user=staff)
    assert client.post(f"/api/public/exams/{session['exam_token']}/identify", json={"badge_id": trainee.badge_id}).status_code == 200
    qid = session["exam_questions"][0]["id"]
    sent = client.post(
        f"/api/public/exams/{session['exam_token']}",
        json={"badge_id": trainee.badge_id, "answers": {str(qid): True}},
    )
    assert sent.status_code == 201, sent.text
    assert client.post(f"/api/public/surveys/{session['survey_token']}/identify", json={"badge_id": trainee.badge_id}).status_code == 200
