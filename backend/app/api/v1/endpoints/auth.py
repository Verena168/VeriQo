"""Register, login (JWT), and profile. The VS Code extension uses the same login."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginIn, ProfileUpdate, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: DB):
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(name=body.name, email=email, hashed_password=hash_password(body.password), role=body.role, github_url=body.github_url)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id, user.role.value), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: DB):
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return TokenOut(access_token=create_access_token(user.id, user.role.value), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: ProfileUpdate, user: CurrentUser, db: DB):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
