from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt
from passlib.context import CryptContext

from config.settings import settings

# PBKDF2 is the primary scheme for predictable operation across supported
# platforms. Existing bcrypt hashes remain readable for migration.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


class AuthService:
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except (TypeError, ValueError):
            return False

    def get_password_hash(self, password: str) -> str:
        if not isinstance(password, str) or len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        return pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        now = datetime.now(timezone.utc)
        expires = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        payload = {**data, "iat": now, "exp": expires}
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except jwt.InvalidTokenError:
            return None


auth_service = AuthService()
verify_password = auth_service.verify_password
get_password_hash = auth_service.get_password_hash
hash_password = auth_service.get_password_hash
create_access_token = auth_service.create_access_token
verify_token = auth_service.verify_token
