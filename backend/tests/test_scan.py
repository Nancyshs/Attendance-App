from __future__ import annotations

import threading
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.timeutil import utcnow
from app.models import AttendanceDay, ScanLog
from app.services.attendance import extract_token, process_scan


def scan(client, headers, code, **kw):
    r = client.post("/api/scan", json={"code": code, **kw}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_extract_token_variants():
    assert extract_token("https://host/t/abcd2345wxyz") == "ABCD2345WXYZ"
    assert extract_token("  a07\r\n") == "A07"
    assert extract_token("http://h/t/TOKEN?x=1") == "TOKEN"
    assert extract_token("") == ""


def test_scan_requires_authentication(client):
    assert client.post("/api/scan", json={"code": "x"}).status_code == 401


def test_check_in_then_duplicate_then_check_out(client, staff_headers, today_day, make_trainees, db):
    (t,) = make_trainees(1)
    first = scan(client, staff_headers, f"http://localhost/t/{t.qr_token}")
    assert first["ok"] and first["action"] == "check_in"

    again = scan(client, staff_headers, t.qr_token)  # accidental double scan
    assert again["action"] == "duplicate" and again["code"] == "already_checked_in"

    # explicit check-out is allowed immediately; auto mode would wait for the guard window
    out = scan(client, staff_headers, t.qr_token, mode="out")
    assert out["action"] == "check_out"

    final = scan(client, staff_headers, t.qr_token, mode="out")
    assert final["action"] == "duplicate" and final["code"] == "already_checked_out"
    assert db.scalar(select(func.count()).select_from(AttendanceDay)) == 1


def test_auto_mode_checks_out_after_guard_window(client, staff_headers, today_day, make_trainees, db):
    (t,) = make_trainees(1)
    earlier = (utcnow() - timedelta(hours=3)).isoformat()
    assert scan(client, staff_headers, t.qr_token, scanned_at=earlier)["action"] == "check_in"
    assert scan(client, staff_headers, t.qr_token)["action"] == "check_out"


def test_checkout_without_checkin_is_rejected(client, staff_headers, today_day, make_trainees):
    (t,) = make_trainees(1)
    res = scan(client, staff_headers, t.qr_token, mode="out")
    assert not res["ok"] and res["code"] == "no_check_in"


def test_unknown_and_inactive_badges_are_rejected_and_logged(client, staff_headers, today_day, make_trainees, db):
    (t,) = make_trainees(1)
    assert scan(client, staff_headers, "NOPE1234NOPE")["code"] == "unknown_badge"
    t.is_active = False
    db.commit()
    assert scan(client, staff_headers, t.qr_token)["code"] == "inactive"
    assert db.scalar(select(func.count()).select_from(ScanLog).where(ScanLog.ok.is_(False))) == 2


def test_badge_id_can_be_typed_manually(client, staff_headers, today_day, make_trainees):
    make_trainees(1)
    res = scan(client, staff_headers, "a01", source="usb")
    assert res["ok"] and res["action"] == "check_in"


def test_late_status(client, staff_headers, today_day, make_trainees, db):
    (t,) = make_trainees(1)
    res = scan(client, staff_headers, t.qr_token)
    # fixture sets late_after=23:58, so unless the suite runs at 23:59 this is on time
    assert res["status"] in ("present", "late")


def test_client_id_makes_retries_idempotent(client, staff_headers, today_day, make_trainees, db):
    (t,) = make_trainees(1)
    cid = uuid.uuid4().hex
    a = scan(client, staff_headers, t.qr_token, client_id=cid)
    b = scan(client, staff_headers, t.qr_token, client_id=cid)
    assert a["action"] == "check_in"
    assert b["action"] == "check_in" and b["replayed"] is True
    assert db.scalar(select(func.count()).select_from(ScanLog)) == 1


def test_no_training_day_on_non_working_day(client, staff_headers, make_trainees, db):
    from app.services import settings as settings_service

    (t,) = make_trainees(1)
    settings_service.update(db, {"working_weekdays": []})
    assert scan(client, staff_headers, t.qr_token)["code"] == "no_training_day"


def test_training_day_is_auto_created_on_working_day(client, staff_headers, make_trainees, db):
    from app.core.timeutil import local_today
    from app.services import settings as settings_service

    (t,) = make_trainees(1)
    settings_service.update(db, {"working_weekdays": [0, 1, 2, 3, 4, 5, 6]})
    assert scan(client, staff_headers, t.qr_token)["ok"]
    from app.models import TrainingDay

    assert db.scalar(select(TrainingDay).where(TrainingDay.date == local_today())).is_auto


# ------------------------------------------------------------------ concurrency
def _run_threads(target_args: list[tuple], fn) -> list:
    results: list = [None] * len(target_args)
    errors: list = []

    start = threading.Barrier(len(target_args))

    def worker(i: int, args: tuple):
        try:
            start.wait()
            with SessionLocal() as session:
                results[i] = fn(session, *args)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i, a)) for i, a in enumerate(target_args)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    return results


def test_fifty_people_scan_at_the_same_instant(today_day, make_trainees, staff, db):
    trainees = make_trainees(50)

    def go(session, token):
        return process_scan(session, raw=token, mode="auto", source="usb", user=staff)

    results = _run_threads([(t.qr_token,) for t in trainees], go)
    assert all(r["ok"] and r["action"] == "check_in" for r in results)
    assert db.scalar(select(func.count()).select_from(AttendanceDay)) == 50


def test_same_badge_hammered_concurrently_yields_exactly_one_check_in(today_day, make_trainees, staff, db):
    (t,) = make_trainees(1)

    def go(session, _):
        return process_scan(session, raw=t.qr_token, mode="auto", source="camera", user=staff)

    results = _run_threads([(i,) for i in range(40)], go)
    assert sum(r["action"] == "check_in" for r in results) == 1
    assert all(r["ok"] for r in results)
    assert db.scalar(select(func.count()).select_from(AttendanceDay)) == 1


def test_concurrent_checkout_race_has_one_winner(today_day, make_trainees, staff, db):
    (t,) = make_trainees(1)
    with SessionLocal() as s:
        process_scan(s, raw=t.qr_token, mode="auto", source="usb", user=staff,
                     scanned_at=utcnow() - timedelta(hours=3))

    def go(session, _):
        return process_scan(session, raw=t.qr_token, mode="out", source="usb", user=staff)

    results = _run_threads([(i,) for i in range(25)], go)
    assert sum(r["action"] == "check_out" for r in results) == 1


def test_concurrent_retries_with_same_client_id(today_day, make_trainees, staff, db):
    (t,) = make_trainees(1)
    cid = uuid.uuid4().hex

    def go(session, _):
        return process_scan(session, raw=t.qr_token, mode="auto", source="usb", user=staff, client_id=cid)

    results = _run_threads([(i,) for i in range(20)], go)
    assert all(r["action"] == "check_in" for r in results)
    assert db.scalar(select(func.count()).select_from(ScanLog)) == 1
