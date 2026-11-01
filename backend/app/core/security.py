import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
