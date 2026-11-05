from typing import Optional
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from config.settings import settings
from services.auth_service import (
    verify_password,
    hash_password,
    create_access_token,
    verify_token,
)
from database.db_core import AsyncSessionLocal
from database.models import Admin, AuditLog
from sqlalchemy import select

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Login ─────────────────────────────────────────────────────────────────────

async def login(username: str, password: str) -> dict:
    # First check env-configured dashboard credentials
    if (
        username == settings.DASHBOARD_USERNAME
        and password == settings.DASHBOARD_PASSWORD
    ):
        token = create_access_token(
            {"sub": username, "role": "admin", "source": "env"}
        )
        async with AsyncSessionLocal() as session:
            log = AuditLog(
                action="login",
                performed_by=username,
                details="Login via env credentials",
            )
            session.add(log)
            await session.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {"username": username, "role": "admin"},
        }

    # Check database admins
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Admin).where(Admin.username == username, Admin.is_active == True)  # noqa: E712
        )
        admin = result.scalar_one_or_none()

    if admin and verify_password(password, admin.hashed_password):
        token = create_access_token(
            {"sub": admin.username, "role": "admin", "source": "db", "id": admin.id}
        )
        async with AsyncSessionLocal() as session:
            log = AuditLog(
                action="login",
                performed_by=admin.username,
                details="Login via DB credentials",
            )
            session.add(log)
            await session.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {"username": admin.username, "role": "admin"},
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="اسم المستخدم أو كلمة المرور غير صحيحة",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── Token dependency ──────────────────────────────────────────────────────────

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="رمز الوصول غير صالح أو منتهي الصلاحية",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    if token is None:
        return None
    return verify_token(token)
