# Attendance & Feedback

QR-badge attendance (once-a-day check-in/out) and per-lecture anonymous feedback surveys.

- **Backend:** FastAPI + SQLAlchemy + MySQL (`backend/`)
- **Frontend:** React + Vite + Tailwind, English/Arabic with RTL (`frontend/`)
- **Scanning:** USB QR reader or phone camera, offline queue, duplicate-safe
- **Trainees:** scanning the badge with a phone opens a personal page with the lecture surveys

Dev quick start: see `DEPLOY.md` (use `ENVIRONMENT=development`), then
`cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload` and `cd frontend && npm run dev`.
Tests: `cd backend && .venv\Scripts\python -m pytest` (needs the `attendance_test` MySQL database from `tests/conftest.py`).
