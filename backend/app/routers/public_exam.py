"""Public exam reached by scanning the session QR. The same questions open before and after the lecture."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.ratelimit import SlidingWindowLimiter, client_ip
from ..services import exams

router = APIRouter(prefix="/public/exams", tags=["public-exam"])
_submit_limiter = SlidingWindowLimiter(limit=300, window_seconds=60)


class IdentifyIn(BaseModel):
    badge_id: str = Field(min_length=2, max_length=8)


class SubmitIn(BaseModel):
    badge_id: str = Field(min_length=2, max_length=8)
    answers: dict[int, bool]


@router.get("/{token}")
def get_exam(token: str, db: Session = Depends(get_db)) -> dict:
    return exams.public_exam(db, token)


@router.post("/{token}/identify")
def identify(token: str, body: IdentifyIn, db: Session = Depends(get_db)) -> dict:
    return exams.identify(db, token, body.badge_id)


@router.post("/{token}", status_code=201)
def post_exam(token: str, body: SubmitIn, request: Request, db: Session = Depends(get_db)) -> dict:
    if not _submit_limiter.hit(client_ip(request)):
        from fastapi import HTTPException

        raise HTTPException(429, "محاولات كثيرة. انتظر دقيقة ثم حاول مرة أخرى.")
    exams.submit(db, token, body.badge_id, dict(body.answers))
    return {"ok": True}
