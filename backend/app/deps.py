"""FastAPI dependencies: authentication and authorisation."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.db import get_db
from .core.security import decode_token
from .models import AuditLog, Trainee, User

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "يجب تسجيل الدخول أولاً") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _claims(creds: HTTPAuthorizationCredentials | None, kind: str) -> dict:
    if creds is None:
        raise _unauthorized()
    try:
        claims = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("انتهت الجلسة، سجّل الدخول مرة أخرى") from None
    except jwt.PyJWTError:
        raise _unauthorized("رمز الدخول غير صالح") from None
    if claims.get("typ") != kind:
        raise _unauthorized("رمز الدخول غير صالح")
    return claims


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    claims = _claims(creds, "user")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized("هذا الحساب موقوف")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "ليس لديك صلاحية لتنفيذ هذا الإجراء")
        return user

    return checker


admin_only = require_roles("admin")
staff_or_admin = require_roles("admin", "staff")
any_user = require_roles("admin", "staff", "trainer")


def get_current_trainee(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> Trainee:
    claims = _claims(creds, "trainee")
    trainee = db.get(Trainee, int(claims["sub"]))
    if trainee is None or not trainee.is_active:
        raise _unauthorized("هذا الباج موقوف")
    return trainee


def audit(
    db: Session,
    user: User | None,
    action: str,
    entity: str | None = None,
    entity_id: object | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Adds an audit row to the current transaction (caller commits)."""
    from .core.ratelimit import client_ip

    db.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
            ip=client_ip(request) if request else None,
        )
    )
