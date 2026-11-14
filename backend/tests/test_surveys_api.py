from __future__ import annotations

import threading
from datetime import time, timedelta

from sqlalchemy import func, select

from app.core.timeutil import local_today
from app.models import LectureSession, SurveyAnswer, SurveyResponse, SurveySubmission, Trainer
from app.services.attendance import process_scan


def portal_login(client, trainee):
    r = client.post("/api/portal/auth", json={"token": f"http://x/t/{trainee.qr_token}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_session(db, template=None, **kw):
    trainer = Trainer(name="Dr. Sara")
    db.add(trainer)
    db.flush()
    s = LectureSession(
        day=local_today(),
        start_time=time(0, 0),
        end_time=time(0, 1),  # already finished -> survey open (window closes 24h after the end)
        title="Intro",
        trainer_id=trainer.id,
        template_id=template.id if template else None,
        survey_duration_minutes=1440,
        **kw,
    )
    db.add(s)
    db.commit()
    return s


def attend(db, staff, trainee):
    process_scan(db, raw=trainee.qr_token, mode="auto", source="usb", user=staff)


def test_portal_rejects_bad_token(client):
    assert client.post("/api/portal/auth", json={"token": "WRONGWRONGWR"}).status_code == 401


def test_survey_flow_is_anonymous_and_single_submission(client, db, staff, today_day, make_trainees, template):
    (t,) = make_trainees(1)
    s = make_session(db, template)
    attend(db, staff, t)
    h = portal_login(client, t)

    me = client.get("/api/portal/me", headers=h).json()
    assert me["sessions"][0]["state"] == "open"

    form = client.get(f"/api/portal/sessions/{s.id}/survey", headers=h).json()
    qids = {q["text"]: q["id"] for q in form["questions"]}
    answers = {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}
    r = client.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": answers}, headers=h)
    assert r.status_code == 201, r.text

    # duplicate is refused
    r2 = client.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": answers}, headers=h)
    assert r2.status_code == 409 and r2.json()["code"] == "already_submitted"

    # the stored response carries no trainee id (anonymous) and a blurred timestamp
    resp = db.scalar(select(SurveyResponse))
    assert resp.trainee_id is None
    assert resp.submitted_at.minute == 0 and resp.submitted_at.second == 0
    assert db.scalar(select(func.count()).select_from(SurveySubmission)) == 1
    assert client.get("/api/portal/me", headers=h).json()["sessions"][0]["state"] == "submitted"
    headers = _admin(client, db)
    params = {"date_from": local_today(), "date_to": local_today()}
    report = client.get("/api/reports/surveys", headers=headers, params=params).json()
    content = next(q for q in report["sessions"][0]["questions"] if q["text"] == "Content")
    assert content["percent"] == 100.0
    assert report["sessions"][0]["percent"] == 100.0
    from io import BytesIO

    from openpyxl import load_workbook

    book = load_workbook(BytesIO(client.get("/api/reports/surveys.xlsx", headers=headers, params=params).content))
    sheet = book["التقييمات"]
    assert [cell.value for cell in sheet[1]] == ["المحاضرة", "التاريخ", "المدرب", "نسبة الجلسة", "السؤال", "نسبة السؤال", "الإجابات"]
    assert sheet.cell(2, 4).value == "100%"
    assert any(row[4] == "Content" and row[5] == "100%" for row in sheet.iter_rows(min_row=2, values_only=True))


def test_survey_requires_attendance(client, db, today_day, make_trainees, template):
    (t,) = make_trainees(1)
    s = make_session(db, template)
    h = portal_login(client, t)
    r = client.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": {"1": 5}}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "not_attended"


def test_survey_validation(client, db, staff, today_day, make_trainees, template):
    (t,) = make_trainees(1)
    s = make_session(db, template)
    attend(db, staff, t)
    h = portal_login(client, t)
    qids = {q["text"]: q["id"] for q in client.get(f"/api/portal/sessions/{s.id}/survey", headers=h).json()["questions"]}
    # missing required
    r = client.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": {str(qids["Content"]): 4}}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "missing_answer"
    # out-of-range rating
    r = client.post(
        f"/api/portal/sessions/{s.id}/survey",
        json={"answers": {str(qids["Content"]): 9, str(qids["Pace"]): "OK"}},
        headers=h,
    )
    assert r.status_code == 400 and r.json()["code"] == "invalid_answer"
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 0


def test_survey_not_open_before_session_ends(client, db, staff, today_day, make_trainees, template):
    (t,) = make_trainees(1)
    s = make_session(db, template)
    s.end_time = time(23, 59)
    s.start_time = time(23, 58)
    db.commit()
    attend(db, staff, t)
    h = portal_login(client, t)
    r = client.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": {"1": 5}}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "survey_not_open"


def test_fifty_trainees_submit_simultaneously_and_double_taps_are_safe(client, db, staff, today_day, make_trainees, template):
    trainees = make_trainees(50)
    s = make_session(db, template)
    for t in trainees:
        attend(db, staff, t)
    headers = [portal_login(client, t) for t in trainees]
    form = client.get(f"/api/portal/sessions/{s.id}/survey", headers=headers[0]).json()
    qids = {q["text"]: q["id"] for q in form["questions"]}
    answers = {str(qids["Content"]): 4, str(qids["Pace"]): "OK", str(qids["Comments"]): "note"}

    from fastapi.testclient import TestClient

    from app.main import app

    statuses: list[int] = []
    lock = threading.Lock()
    gate = threading.Barrier(100)

    def submit(h):
        with TestClient(app) as c:
            gate.wait()
            code = c.post(f"/api/portal/sessions/{s.id}/survey", json={"answers": answers}, headers=h).status_code
        with lock:
            statuses.append(code)

    threads = [threading.Thread(target=submit, args=(h,)) for h in headers for _ in range(2)]  # every trainee double-taps
    [x.start() for x in threads]
    [x.join() for x in threads]

    assert sorted(set(statuses)) == [201, 409]
    assert statuses.count(201) == 50
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 50
    assert db.scalar(select(func.count()).select_from(SurveyAnswer)) == 150

    report = client.get(
        "/api/reports/surveys", headers=_admin(client, db), params={"date_from": local_today(), "date_to": local_today()}
    ).json()
    assert report["sessions"][0]["responses"] == 50
    assert report["sessions"][0]["avg_rating"] == 4.0
    content = next(q for q in report["sessions"][0]["questions"] if q["text"] == "Content")
    assert content["percent"] == 80.0


def _admin(client, db):
    from app.core.security import hash_password
    from app.models import User

    db.add(User(username="boss", password_hash=hash_password("Boss-Pass-123"), full_name="Boss", role="admin"))
    db.commit()
    r = client.post("/api/auth/login", json={"username": "boss", "password": "Boss-Pass-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

# ------------------------------------------------------------- public QR survey
def _admin_h(client, db):
    from app.core.security import hash_password
    from app.models import User

    if not db.scalar(select(User).where(User.username == "boss")):
        db.add(User(username="boss", password_hash=hash_password("S0me-long-pass"), full_name="Boss", role="admin"))
        db.commit()
    r = client.post("/api/auth/login", json={"username": "boss", "password": "S0me-long-pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_survey_qr_requires_a_registered_code(client, db, template, make_trainees):
    (t,) = make_trainees(1)
    t.full_name = "محمد أحمد علي"
    db.commit()
    s = make_session(db, template)
    url = f"/api/public/surveys/{s.survey_token}/identify"
    ok = client.post(url, json={"badge_id": "a01"})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"full_name": "محمد أحمد علي", "badge_id": "A01", "submitted": False, "answers": {}}
    missing = client.post(url, json={"badge_id": "Z99"})
    assert missing.status_code == 401
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 0


def test_public_survey_same_person_can_edit_answers(client, db, template, make_trainees):
    (t,) = make_trainees(1)
    t.full_name = "محمد أحمد علي"
    db.commit()
    s = make_session(db, template)
    token = s.survey_token
    form = client.get(f"/api/public/surveys/{token}").json()
    qids = {q["text"]: q["id"] for q in form["questions"]}
    body = {
        "device_id": "device-aaaaaaaa",
        "badge_id": "A01",
        "answers": {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "أول مرة"},
    }
    assert client.post(f"/api/public/surveys/{token}", json=body).status_code == 201
    edited = {
        **body,
        "device_id": "device-bbbbbbbb",
        "answers": {str(qids["Content"]): 2, str(qids["Pace"]): "Slow", str(qids["Comments"]): "بعد التعديل"},
    }
    assert client.post(f"/api/public/surveys/{token}", json=edited).status_code == 201
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 1
    db.expire_all()
    saved = db.scalar(select(SurveyResponse))
    assert saved.trainee_id == t.id
    by_q = {a.question_id: a for a in saved.answers}
    assert by_q[qids["Content"]].rating == 2
    assert by_q[qids["Pace"]].choice == "Slow"
    assert by_q[qids["Comments"]].text == "بعد التعديل"
    who = client.post(f"/api/public/surveys/{token}/identify", json={"badge_id": "A01"})
    assert who.status_code == 200
    payload = who.json()
    assert payload["submitted"] is True
    assert payload["answers"][str(qids["Content"])] == 2
    h = _admin_h(client, db)
    report = client.get("/api/reports/survey-respondents", headers=h)
    assert report.status_code == 200, report.text
    row = next(r for r in report.json()["rows"] if r["trainee"]["badge_id"] == "A01" and r["session"]["id"] == s.id)
    assert row["trainee"]["full_name"] == "محمد أحمد علي"
    content = next(a for a in row["answers"] if a["question_id"] == qids["Content"])
    assert content["value"] == 2 and content["text"] == "Content"


def test_public_survey_one_answer_per_device_and_admin_window_control(client, db, template):
    s = make_session(db, template, axis="Axis X")
    token = s.survey_token
    form = client.get(f"/api/public/surveys/{token}").json()
    assert form["state"] == "open" and form["session"]["axis"] == "Axis X"
    qids = {q["text"]: q["id"] for q in form["questions"]}
    body = {"device_id": "device-aaaaaaaa", "answers": {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "note"}}

    assert client.post(f"/api/public/surveys/{token}", json=body).status_code == 201
    dup = client.post(f"/api/public/surveys/{token}", json=body)
    assert dup.status_code == 409 and dup.json()["code"] == "already_submitted"
    other = {**body, "device_id": "device-bbbbbbbb"}
    assert client.post(f"/api/public/surveys/{token}", json=other).status_code == 201
    resp = db.scalars(select(SurveyResponse).order_by(SurveyResponse.id)).all()
    assert len(resp) == 2 and all(r.trainee_id is None and r.device_hash for r in resp)

    # admin closes it -> trainees can no longer answer
    h = _admin_h(client, db)
    closed = client.post(f"/api/sessions/{s.id}/survey/close", headers=h).json()
    assert closed["survey_state"] == "closed" and closed["submissions"] == 2
    third = {**body, "device_id": "device-cccccccc"}
    r = client.post(f"/api/public/surveys/{token}", json=third)
    assert r.status_code == 400 and r.json()["code"] == "survey_closed"

    # ... and re-opens it for 10 minutes
    reopened = client.post(f"/api/sessions/{s.id}/survey/open", json={"duration_minutes": 10}, headers=h).json()
    assert reopened["survey_state"] == "open" and reopened["effective_duration_minutes"] == 10
    assert client.post(f"/api/public/surveys/{token}", json=third).status_code == 201

    # editing the session must not wipe the manual window
    edit = client.put(
        f"/api/sessions/{s.id}",
        json={"day": str(local_today()), "start_time": "00:00", "end_time": "00:01", "title": "Renamed"},
        headers=h,
    )
    assert edit.status_code == 200 and edit.json()["survey_state"] == "open"

    assert client.get(f"/api/sessions/{s.id}/survey-qr.svg", headers=h).text.startswith("<svg")
    pdf = client.get(f"/api/sessions/{s.id}/survey-qr.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_public_survey_unknown_token_and_not_open_yet(client, db, template):
    assert client.get("/api/public/surveys/nope").status_code == 404
    s = make_session(db, template)
    s.start_time, s.end_time = time(23, 58), time(23, 59)
    db.commit()
    form = client.get(f"/api/public/surveys/{s.survey_token}").json()
    assert form["state"] == "not_open"
    r = client.post(
        f"/api/public/surveys/{s.survey_token}",
        json={"device_id": "device-aaaaaaaa", "answers": {str(form["questions"][0]["id"]): 5}},
    )
    assert r.status_code == 400 and r.json()["code"] == "survey_not_open"
    # the admin can open it right away
    h = _admin_h(client, db)
    assert client.post(f"/api/sessions/{s.id}/survey/open", json={}, headers=h).json()["survey_state"] == "open"


def test_fifty_devices_submit_publicly_at_once(client, db, template):
    s = make_session(db, template)
    form = client.get(f"/api/public/surveys/{s.survey_token}").json()
    qid = next(q["id"] for q in form["questions"] if q["text"] == "Content")
    pace = next(q["id"] for q in form["questions"] if q["text"] == "Pace")
    from fastapi.testclient import TestClient

    from app.main import app

    statuses: list[int] = []
    lock = threading.Lock()
    gate = threading.Barrier(100)

    def submit(i):
        with TestClient(app) as c:
            gate.wait()
            code = c.post(
                f"/api/public/surveys/{s.survey_token}",
                json={"device_id": f"device-{i:04d}-xxxx", "answers": {str(qid): 4, str(pace): "OK", str(next(q["id"] for q in form["questions"] if q["text"] == "Comments")): "note"}},
            ).status_code
        with lock:
            statuses.append(code)

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(50) for _ in range(2)]  # double taps
    [x.start() for x in threads]
    [x.join() for x in threads]
    assert statuses.count(201) == 50 and statuses.count(409) == 50
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 50


def test_unchecked_survey_stays_open_and_end_of_day_closes(client, db):
    h = _admin_h(client, db)
    today = {"day": str(local_today()), "start_time": "00:00", "end_time": "00:01", "title": "مفتوحة"}
    created = client.post("/api/sessions", json=today, headers=h)
    assert created.status_code == 201, created.text
    open_row = created.json()
    assert open_row["survey_state"] == "open"
    assert open_row["survey_until_end_of_day"] is False
    assert open_row["effective_closes_at"].startswith("9999")

    flagged = client.put(f"/api/sessions/{open_row['id']}", json={**today, "survey_until_end_of_day": True}, headers=h)
    assert flagged.status_code == 200
    assert flagged.json()["survey_state"] == "open"
    assert not flagged.json()["effective_closes_at"].startswith("9999")

    yesterday = str(local_today() - timedelta(days=1))
    past = client.post(
        "/api/sessions",
        json={"day": yesterday, "start_time": "09:00", "end_time": "10:00", "title": "أمس", "survey_until_end_of_day": True},
        headers=h,
    )
    assert past.status_code == 201 and past.json()["survey_state"] == "closed"
    still = client.post(
        "/api/sessions",
        json={"day": yesterday, "start_time": "09:00", "end_time": "10:00", "title": "أمس مفتوحة"},
        headers=h,
    )
    assert still.status_code == 201 and still.json()["survey_state"] == "open"

# ------------------------------------------------------------- see / edit own answers
def test_portal_trainee_sees_own_answers_and_can_edit_while_open(client, db, staff, today_day, make_trainees, template):
    (t,) = make_trainees(1)
    s = make_session(db, template)
    attend(db, staff, t)
    h = portal_login(client, t)
    url = f"/api/portal/sessions/{s.id}/survey"
    form = client.get(url, headers=h).json()
    assert form["my_answers"] is None and form["can_edit"] is False
    qids = {q["text"]: q["id"] for q in form["questions"]}
    first = {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}
    assert client.post(url, json={"answers": first}, headers=h).status_code == 201
    assert client.post(url, json={"answers": first}, headers=h).status_code == 409  # still only once

    again = client.get(url, headers=h).json()
    assert again["state"] == "submitted" and again["can_edit"] is True
    assert again["my_answers"] == {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}

    changed = {str(qids["Content"]): 2, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}
    assert client.put(url, json={"answers": changed}, headers=h).status_code == 200
    after = client.get(url, headers=h).json()
    assert after["my_answers"] == {str(qids["Content"]): 2, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 1
    assert db.scalar(select(func.count()).select_from(SurveySubmission)) == 1
    assert db.scalar(select(SurveyResponse)).trainee_id is None  # still anonymous

    # invalid edits are refused and keep the previous answers
    bad = client.put(url, json={"answers": {str(qids["Content"]): 9, str(qids["Pace"]): "OK", str(qids["Comments"]): "Great"}}, headers=h)
    assert bad.status_code == 400
    assert client.get(url, headers=h).json()["my_answers"][str(qids["Content"])] == 2

    # nobody can edit someone else's answers, and editing without having answered is refused
    (other,) = make_trainees(1)
    attend(db, staff, other)
    h2 = portal_login(client, other)
    assert client.get(url, headers=h2).json()["my_answers"] is None
    assert client.put(url, json={"answers": changed}, headers=h2).json()["code"] == "not_submitted"

    # once the survey is closed the answers are still visible but can no longer be edited
    s.survey_closes_at = s.survey_opens_at = None
    s.survey_until_end_of_day = False
    s.survey_duration_minutes = 1
    s.end_time, s.start_time = time(0, 1), time(0, 0)
    s.day = local_today() - timedelta(days=3)
    db.commit()
    closed = client.get(url, headers=h).json()
    assert closed["my_answers"] is not None and closed["can_edit"] is False
    assert client.put(url, json={"answers": changed}, headers=h).json()["code"] == "survey_closed"


def test_public_device_sees_own_answers_and_can_edit(client, db, template):
    s = make_session(db, template)
    url = f"/api/public/surveys/{s.survey_token}"
    form = client.get(url, params={"device_id": "device-aaaaaaaa"}).json()
    assert form["my_answers"] is None and form["can_edit"] is False
    qids = {q["text"]: q["id"] for q in form["questions"]}
    body = {"device_id": "device-aaaaaaaa", "answers": {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "note"}}
    assert client.post(url, json=body).status_code == 201

    mine = client.get(url, params={"device_id": "device-aaaaaaaa"}).json()
    assert mine["my_answers"] == {str(qids["Content"]): 5, str(qids["Pace"]): "OK", str(qids["Comments"]): "note"} and mine["can_edit"] is True
    # another device sees nothing of it
    assert client.get(url, params={"device_id": "device-bbbbbbbb"}).json()["my_answers"] is None
    assert client.get(url).json()["my_answers"] is None

    edited = {**body, "answers": {str(qids["Content"]): 1, str(qids["Pace"]): "OK", str(qids["Comments"]): "Slow"}}
    assert client.put(url, json=edited).status_code == 200
    assert client.get(url, params={"device_id": "device-aaaaaaaa"}).json()["my_answers"][str(qids["Content"])] == 1
    assert db.scalar(select(func.count()).select_from(SurveyResponse)) == 1

    # a device that never answered cannot "edit"
    r = client.put(url, json={**edited, "device_id": "device-bbbbbbbb"})
    assert r.status_code == 400 and r.json()["code"] == "not_submitted"

    # closed -> still readable, not editable
    h = _admin_h(client, db)
    client.post(f"/api/sessions/{s.id}/survey/close", headers=h)
    closed = client.get(url, params={"device_id": "device-aaaaaaaa"}).json()
    assert closed["my_answers"] is not None and closed["can_edit"] is False
    assert client.put(url, json=edited).json()["code"] == "survey_closed"
