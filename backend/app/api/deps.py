from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.user import UserRole

DB = Annotated[AsyncSession, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    user_id = decode_access_token(creds.credentials) if creds else None
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(r.value for r in roles)}")
        return user

    return Depends(checker)


Organizer = Annotated[User, require_roles(UserRole.ORGANIZER)]
Staff = Annotated[User, require_roles(UserRole.ORGANIZER, UserRole.JUDGE)]
Participant = Annotated[User, require_roles(UserRole.PARTICIPANT)]
