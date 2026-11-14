from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.ratelimit import SlidingWindowLimiter, client_ip
from ..core.security import create_token, hash_password, verify_password
from ..core.config import settings
from ..core.timeutil import utcnow
from ..deps import admin_only, any_user, audit
from ..models import User
from ..schemas import ChangePasswordIn, LoginIn, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(tags=["auth"])

_ip_limiter = SlidingWindowLimiter(limit=30, window_seconds=60)
_fail_limiter = SlidingWindowLimiter(limit=8, window_seconds=300)  # failed attempts per user+ip

# Constant-time-ish defence against user enumeration: always run a bcrypt verify.
_DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    ip = client_ip(request)
    _ip_limiter.check(ip)
    key = f"{body.username.lower()}|{ip}"
    if _fail_limiter.peek_blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "محاولات دخول فاشلة كثيرة. حاول بعد دقائق.")

    user = db.scalar(select(User).where(User.username == body.username))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid or not user.is_active:
        _fail_limiter.hit(key)
        audit(db, None, "login_failed", "user", body.username[:64], request=request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "اسم المستخدم أو كلمة المرور غير صحيحة")

    user.last_login_at = utcnow()
    audit(db, user, "login", "user", user.id, request=request)
    db.commit()
    token = create_token(str(user.id), kind="user", minutes=settings.access_token_minutes, extra={"role": user.role})
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(any_user)) -> User:
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(
    body: ChangePasswordIn, request: Request, user: User = Depends(any_user), db: Session = Depends(get_db)
) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "كلمة المرور الحالية غير صحيحة")
    user.password_hash = hash_password(body.new_password)
    audit(db, user, "password_changed", "user", user.id, request=request)
    db.commit()


# ------------------------------------------------------------------ user management
@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)
) -> User:
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "اسم المستخدم موجود بالفعل")
    if body.role == "trainer" and not body.trainer_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "حساب المحاضر يجب ربطه ببيانات محاضر")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        trainer_id=body.trainer_id,
    )
    db.add(user)
    db.flush()
    audit(db, admin, "user_created", "user", user.id, {"username": user.username, "role": user.role}, request)
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "المستخدم غير موجود")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("is_active") is False or data.get("role", "admin") != "admin"):
        raise HTTPException(400, "لا يمكنك تقليل صلاحياتك أو إيقاف حسابك")
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    audit(db, admin, "user_updated", "user", user.id, {k: v for k, v in data.items()}, request)
    db.commit()
    return user
