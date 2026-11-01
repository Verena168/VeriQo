"""Organizer CRUD for hackathons and their skill requirements."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, Organizer
from app.models import Application, Hackathon, HackathonRequirement
from app.models.user import UserRole
from app.schemas import (
    HackathonIn,
    HackathonOut,
    HackathonUpdate,
    ShortlistConfig,
    event_rule_errors,
)
from app.services.visibility import published_shortlisted

router = APIRouter(prefix="/hackathons", tags=["hackathons"])


RULE_FIELDS = (
    "start_date", "end_date", "registration_opens_at", "registration_closes_at",
    "participation_mode", "min_team_size", "max_team_size", "age_min", "age_max",
)
JSON_FIELDS = {"prizes", "shortlist_config"}  # stored in JSONB columns: must be plain JSON (no Decimal)


def _column_values(body, exclude_unset: bool) -> dict:
    """Request body -> column values; JSONB fields are serialized to JSON-safe types."""
    data = body.model_dump(exclude={"requirements"}, exclude_unset=exclude_unset)
    as_json = body.model_dump(mode="json", include=JSON_FIELDS & set(data), exclude_unset=exclude_unset)
    return data | as_json


def phase(h: Hackathon) -> str:
    now = datetime.now(timezone.utc)
    return "upcoming" if now < h.start_date else "live" if now <= h.end_date else "ended"


def to_out(h: Hackathon) -> HackathonOut:
    out = HackathonOut.model_validate(h)
    out.phase = phase(h)
    # Older events store {}: always return the full validated pipeline, defaults filled in.
    out.shortlist_config = ShortlistConfig.model_validate(h.shortlist_config or {}).model_dump(mode="json")
    return out


async def get_hackathon(db, hackathon_id: uuid.UUID) -> Hackathon:
    h = await db.scalar(
        select(Hackathon).where(Hackathon.id == hackathon_id).options(selectinload(Hackathon.requirements))
    )
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hackathon not found")
    return h


async def get_owned_hackathon(db, hackathon_id: uuid.UUID, user) -> Hackathon:
    h = await get_hackathon(db, hackathon_id)
    if user.role == UserRole.ORGANIZER and h.organizer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not organize this hackathon")
    return h


@router.get("", response_model=list[HackathonOut])
async def list_hackathons(db: DB, user: CurrentUser):
    rows = await db.scalars(select(Hackathon).options(selectinload(Hackathon.requirements)).order_by(Hackathon.start_date.desc()))
    return [to_out(h) for h in rows]


@router.get("/mine", response_model=list[HackathonOut])
async def my_hackathons(db: DB, user: CurrentUser):
    """Organizer: hackathons they run. Participant: hackathons they are shortlisted for (used by the extension)."""
    q = select(Hackathon).options(selectinload(Hackathon.requirements)).order_by(Hackathon.start_date.desc())
    if user.role == UserRole.ORGANIZER:
        q = q.where(Hackathon.organizer_id == user.id)
    elif user.role == UserRole.PARTICIPANT:
        q = q.join(Application, Application.hackathon_id == Hackathon.id).where(
            Application.user_id == user.id, published_shortlisted
        )
    return [to_out(h) for h in await db.scalars(q)]


@router.post("", response_model=HackathonOut, status_code=status.HTTP_201_CREATED)
async def create_hackathon(body: HackathonIn, db: DB, user: Organizer):
    h = Hackathon(**_column_values(body, exclude_unset=False), organizer_id=user.id)
    h.requirements = [HackathonRequirement(**r.model_dump()) for r in body.requirements]
    db.add(h)
    await db.commit()
    return to_out(await get_hackathon(db, h.id))


@router.get("/{hackathon_id}", response_model=HackathonOut)
async def read_hackathon(hackathon_id: uuid.UUID, db: DB, user: CurrentUser):
    return to_out(await get_hackathon(db, hackathon_id))


@router.patch("/{hackathon_id}", response_model=HackathonOut)
async def update_hackathon(hackathon_id: uuid.UUID, body: HackathonUpdate, db: DB, user: Organizer):
    h = await get_owned_hackathon(db, hackathon_id, user)
    data = _column_values(body, exclude_unset=True)
    reqs = body.model_dump(exclude_unset=True).get("requirements")

    # Cross-field rules must hold for the merged result, not just the fields being changed.
    merged = {field: getattr(h, field) for field in RULE_FIELDS} | {k: v for k, v in data.items() if k in RULE_FIELDS}
    if errors := event_rule_errors(merged):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(errors))

    # Rounds can't be switched on or off once people have applied (weights may still change).
    if "shortlist_config" in data and await db.scalar(select(Application.id).where(Application.hackathon_id == h.id).limit(1)):
        before = ShortlistConfig.model_validate(h.shortlist_config or {}).enabled_keys()
        if body.shortlist_config.enabled_keys() != before:
            raise HTTPException(status.HTTP_409_CONFLICT, "Rounds can't be enabled or disabled after the first application")

    for field, value in data.items():
        setattr(h, field, value)
    if reqs is not None:
        h.requirements = [HackathonRequirement(**r) for r in reqs]
    hackathon_id = h.id  # read before expiring: touching an expired attribute would trigger sync IO
    await db.commit()
    db.expire_all()  # reload the replaced requirements collection fresh
    return to_out(await get_hackathon(db, hackathon_id))


@router.delete("/{hackathon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hackathon(hackathon_id: uuid.UUID, db: DB, user: Organizer):
    h = await get_owned_hackathon(db, hackathon_id, user)
    if await db.scalar(select(Application.id).where(Application.hackathon_id == h.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete a hackathon that already has applications")
    await db.delete(h)
    await db.commit()
