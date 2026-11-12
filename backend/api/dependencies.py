from datetime import datetime, timezone
from typing import Optional, Dict, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config.settings import settings
from database.database import get_db
from database import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        role: Optional[str] = payload.get("role")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    if role == "admin":
        result = await db.execute(select(models.Admin).where(models.Admin.username == username))
        admin = result.scalars().first()
        if admin and admin.is_active:
            return {"username": admin.username, "role": "admin", "id": admin.id, "obj": admin}
        raise credentials_exception
    if role == "client":
        result = await db.execute(select(models.Client).where(models.Client.username == username))
        client = result.scalars().first()
        if client and client.is_active:
            expires = client.subscription_expires
            if expires is not None:
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= datetime.now(timezone.utc):
                    raise HTTPException(status_code=403, detail="انتهت فترة اشتراكك، يرجى التواصل مع الإدارة للتجديد")
            return {"username": client.username, "role": "client", "id": client.id, "obj": client}
        raise credentials_exception
    raise credentials_exception


async def get_current_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> models.Admin:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user.get("obj") or current_user


async def get_current_cards_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Only admins and semi-annual/annual subscribers can manage Hotspot cards."""
    if current_user.get("role") == "admin":
        return current_user
    plan = getattr(current_user.get("obj"), "plan", "monthly") or "monthly"
    if plan not in {"annual", "semi_annual"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية توليد وإدارة الكروت مخصصة لمشتركي الباقة السنوية والنصف سنوية أو إدارة النظام.")
    return current_user
