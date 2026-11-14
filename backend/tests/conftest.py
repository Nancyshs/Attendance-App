"""Test setup. Uses the MySQL database named in TEST_DATABASE_URL (default: attendance_test on 3307).

Concurrency behaviour (unique keys, row locks, deadlock retry) only exists on a real MySQL server, so the
tests deliberately do not use SQLite.
"""
from __future__ import annotations

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "mysql+pymysql://attendance:devpass123@127.0.0.1:3307/attendance_test?charset=utf8mb4"
)
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

from datetime import time  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password, new_qr_token  # noqa: E402
from app.core.timeutil import local_today  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, SurveyQuestion, SurveyTemplate, Trainee, TrainingDay, User  # noqa: E402
from app.services import settings as settings_service  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    settings_service.invalidate()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(db):
    u = User(username="admin", password_hash=hash_password("Admin-Pass-123"), full_name="Admin", role="admin")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def staff(db):
    u = User(username="gate", password_hash=hash_password("Gate-Pass-123"), full_name="Gate", role="staff")
    db.add(u)
    db.commit()
    return u


def login(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin_headers(client, admin):
    return login(client, "admin", "Admin-Pass-123")


@pytest.fixture
def staff_headers(client, staff):
    return login(client, "gate", "Gate-Pass-123")


@pytest.fixture
def today_day(db):
    """A training day for today whose late threshold is the very start of the day (everyone is late)
    unless a test overrides it."""
    d = TrainingDay(
        date=local_today(),
        start_time=time(0, 0),
        end_time=time(23, 59),
        late_after=time(23, 58),
        checkout_from=time(0, 1),
    )
    db.add(d)
    db.commit()
    return d


@pytest.fixture
def make_trainees(db):
    def _make(n: int) -> list[Trainee]:
        items = [
            Trainee(badge_id=f"A{i:02d}", qr_token=new_qr_token(), full_name=f"Trainee {i}") for i in range(1, n + 1)
        ]
        db.add_all(items)
        db.commit()
        return items

    return _make


@pytest.fixture
def template(db):
    t = SurveyTemplate(name="T", is_default=True, is_anonymous=True)
    t.questions = [
        SurveyQuestion(position=0, text="Content", type="rating", required=True),
        SurveyQuestion(position=1, text="Pace", type="choice", options=["Slow", "OK", "Fast"], required=True),
        SurveyQuestion(position=2, text="Comments", type="text", required=False),
    ]
    db.add(t)
    db.commit()
    return t
