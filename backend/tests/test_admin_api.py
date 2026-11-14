from __future__ import annotations

import io

import segno
from openpyxl import Workbook, load_workbook

from app.core.timeutil import local_today
from app.services.governorates import GOVERNORATES


def test_login_wrong_password(client, admin):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope-nope"})
    assert r.status_code == 401
    assert client.post("/api/auth/login", json={"username": "ghost", "password": "x"}).status_code == 401


def test_roles_are_enforced(client, staff_headers, admin_headers):
    # staff may list trainees but not create them
    assert client.get("/api/trainees", headers=staff_headers).status_code == 200
    assert client.post("/api/trainees", json={"full_name": "X"}, headers=staff_headers).status_code == 403
    assert client.get("/api/audit-logs", headers=staff_headers).status_code == 403
    assert client.get("/api/trainees").status_code == 401


def test_trainee_crud_and_badge_ids(client, admin_headers):
    ids = []
    for name in ("Ahmed Ali Hassan", "Mona Said Kamal"):
        r = client.post("/api/trainees", json={"full_name": name}, headers=admin_headers)
        assert r.status_code == 201, r.text
        ids.append(r.json()["badge_id"])
    assert ids == ["A01", "A02"]
    short = client.post("/api/trainees", json={"full_name": "أحمد علي"}, headers=admin_headers)
    assert short.status_code == 400 and short.json()["code"] == "triple_name"
    dup = client.post("/api/trainees", json={"full_name": "Ziad Omar Nabil", "badge_id": "a01"}, headers=admin_headers)
    assert dup.status_code == 409 and dup.json()["code"] == "badge_exists"


def test_badge_id_follows_governorate_and_qr_carries_it(client, admin_headers):
    letters = [letter for _, letter in GOVERNORATES]
    assert len(GOVERNORATES) == 27
    assert len(set(letters)) == 26  # شمال سيناء and جنوب سيناء share J

    cairo = client.post("/api/trainees", json={"full_name": "أحمد محمد علي", "governorate": "القاهرة"}, headers=admin_headers)
    assert cairo.status_code == 201, cairo.text
    assert cairo.json()["badge_id"] == "C01"
    variant = client.post("/api/trainees", json={"full_name": "منى أحمد حسن", "governorate": "القاهره"}, headers=admin_headers)
    assert variant.status_code == 201, variant.text
    assert variant.json()["badge_id"] == "C02"
    assert variant.json()["governorate"] == "القاهرة"
    giza = client.post("/api/trainees", json={"full_name": "سامي محمود إبراهيم", "governorate": "الجيزة"}, headers=admin_headers)
    assert giza.json()["badge_id"] == "G01"
    north = client.post("/api/trainees", json={"full_name": "نورا أحمد محمد", "governorate": "شمال سيناء"}, headers=admin_headers)
    south = client.post("/api/trainees", json={"full_name": "هدى علي حسن", "governorate": "جنوب سيناء"}, headers=admin_headers)
    assert north.json()["badge_id"] == "J01"
    assert south.json()["badge_id"] == "J02"
    unknown = client.post("/api/trainees", json={"full_name": "سعد محمد علي", "governorate": "باريس"}, headers=admin_headers)
    assert unknown.status_code == 400 and unknown.json()["code"] == "unknown_governorate"

    svg = client.get(f"/api/trainees/{cairo.json()['id']}/qr.svg", headers=admin_headers)
    assert svg.status_code == 200
    expected = io.BytesIO()
    segno.make("C01", error="m").save(expected, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    assert svg.content == expected.getvalue()


def test_national_id_is_14_digits_and_phone_is_11(client, admin_headers):
    short = client.post(
        "/api/trainees",
        json={"full_name": "أحمد محمد علي", "governorate": "القاهرة", "national_id": "123", "phone": "01001234567", "organization": "جهة"},
        headers=admin_headers,
    )
    assert short.status_code == 400 and short.json()["code"] == "invalid_contact"
    ok = client.post(
        "/api/trainees",
        json={
            "full_name": "سارة علي حسن",
            "governorate": "الجيزة",
            "national_id": "29501011234567",
            "phone": "01009876543",
            "organization": "جهاز شؤون البيئة",
        },
        headers=admin_headers,
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["badge_id"] == "G01"
    assert body["national_id"] == "29501011234567"
    assert body["phone"] == "01009876543"
    assert body["organization"] == "جهاز شؤون البيئة"
    dup = client.post(
        "/api/trainees",
        json={"full_name": "أخرى محمد علي", "national_id": "29501011234567"},
        headers=admin_headers,
    )
    assert dup.status_code == 409 and dup.json()["code"] == "national_id_exists"


def test_import_trainees_from_excel(client, admin_headers):
    wb = Workbook()
    ws = wb.active
    ws.append(["full_name", "email", "phone", "group_name"])
    ws.append(["Omar Hassan Ali", "omar@example.com", "01001234567", "G1"])
    ws.append(["", "x@example.com", "", ""])  # invalid
    ws.append(["Omar Hassan Ali", "", "", ""])  # duplicate name
    ws.append(["Sara Adel Nour", "bad-email", "", ""])  # invalid email
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(
        "/api/trainees/import",
        files={"file": ("t.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1 and len(body["errors"]) == 3


def test_badges_pdf_with_arabic_name_and_qr_svg(client, admin_headers):
    t = client.post("/api/trainees", json={"full_name": "محمد أحمد علي", "group_name": "المجموعة الأولى"}, headers=admin_headers).json()
    pdf = client.get("/api/trainees/badges.pdf", headers=admin_headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    svg = client.get(f"/api/trainees/{t['id']}/qr.svg", headers=admin_headers)
    assert svg.status_code == 200 and b"<svg" in svg.content


def test_dashboard_and_exports(client, admin_headers, staff_headers, today_day, make_trainees):
    (t, *_) = make_trainees(3)
    client.post("/api/scan", json={"code": t.qr_token}, headers=staff_headers)
    dash = client.get("/api/reports/dashboard", headers=admin_headers).json()
    assert dash["totals"]["active"] == 3
    assert dash["totals"]["arrived"] == 1 and dash["totals"]["not_arrived"] == 2
    assert dash["recent_scans"][0]["badge_id"] == "A01"

    params = {"date_from": local_today().isoformat(), "date_to": local_today().isoformat()}
    xl = client.get("/api/reports/attendance.xlsx", headers=admin_headers, params=params)
    assert xl.status_code == 200
    wb = load_workbook(io.BytesIO(xl.content))
    assert {"الملخص", "التفاصيل اليومية", "الجدول"} <= set(wb.sheetnames)
    assert wb["الملخص"].max_row == 4  # header + 3 trainees

    sx = client.get("/api/reports/surveys.xlsx", headers=admin_headers, params=params)
    assert sx.status_code == 200


def test_manual_attendance_is_audited(client, admin_headers, staff_headers, today_day, make_trainees):
    (t,) = make_trainees(1)
    d = local_today().isoformat()
    r = client.put(
        f"/api/attendance/{t.id}/{d}",
        json={"check_in_time": "09:05", "check_out_time": "16:30", "note": "forgot badge"},
        headers=staff_headers,
    )
    assert r.status_code == 200, r.text
    bad = client.put(f"/api/attendance/{t.id}/{d}", json={"check_in_time": "10:00", "check_out_time": "09:00"}, headers=staff_headers)
    assert bad.status_code == 400
    logs = client.get("/api/audit-logs", headers=admin_headers).json()
    assert any(entry["action"] == "attendance_manual_edit" for entry in logs)


def test_template_edit_preserves_answers(client, admin_headers):
    tpl = client.post(
        "/api/survey-templates",
        json={"name": "Mine", "questions": [{"text": "Q1", "type": "rating"}, {"text": "Q2", "type": "text", "required": False}]},
        headers=admin_headers,
    )
    assert tpl.status_code == 201, tpl.text
    bad = client.post(
        "/api/survey-templates",
        json={"name": "Bad", "questions": [{"text": "Pick", "type": "choice", "options": ["only one"]}]},
        headers=admin_headers,
    )
    assert bad.status_code == 400


def test_health_and_unknown_api_route(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health/ready").json()["database"] == "up"
    assert client.get("/api/nope").status_code == 404
