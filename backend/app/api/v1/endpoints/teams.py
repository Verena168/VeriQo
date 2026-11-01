"""Team creation/joining and AI-recommended team formation (Module A)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, Organizer, Participant, Staff
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon
from app.models import Application, Hackathon, Submission, Team, TeamMember, User
from app.models.application import ApplicationStatus
from app.schemas import MoveMemberIn, TeamOut, TeamUpdate
from app.services import intelligence_client as intel
from app.services.intelligence_client import IntelligenceError
from app.services.visibility import published_shortlisted

router = APIRouter(tags=["teams"])


class TeamCreate(BaseModel):
    team_name: str = Field(min_length=1, max_length=120)


def _skill_names(user: User) -> set[str]:
    return {s["name"].lower() for s in ((user.parsed_skills or {}).get("skills") or [])}


def _team_out(team: Team, hk: Hackathon) -> TeamOut:
    out = TeamOut.model_validate(team)
    have = set().union(*(_skill_names(m.user) for m in team.members)) if team.members else set()
    total = sum(r.priority for r in hk.requirements)
    covered = sum(r.priority for r in hk.requirements if r.skill.lower() in have)
    out.coverage = round(100 * covered / total, 1) if total else None
    out.missing_skills = [r.skill for r in hk.requirements if r.skill.lower() not in have]
    return out


async def _load_teams(db, hackathon_id: uuid.UUID, team_id: uuid.UUID | None = None) -> list[Team]:
    q = select(Team).where(Team.hackathon_id == hackathon_id).options(
        selectinload(Team.members).selectinload(TeamMember.user)
    ).order_by(Team.team_name)
    if team_id:
        q = q.where(Team.id == team_id)
    return list(await db.scalars(q))


async def _owned_team(db, team_id: uuid.UUID, user) -> tuple[Team, Hackathon]:
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    hk = await get_owned_hackathon(db, team.hackathon_id, user)
    return team, hk


async def _has_submissions(db, hackathon_id: uuid.UUID) -> bool:
    return bool(await db.scalar(select(Submission.id).where(Submission.hackathon_id == hackathon_id).limit(1)))


@router.post("/hackathons/{hackathon_id}/teams/form", response_model=list[TeamOut])
async def ai_form_teams(hackathon_id: uuid.UUID, db: DB, user: Organizer):
    """Replace all teams with AI-recommended, skill-balanced teams of shortlisted participants."""
    hk = await get_owned_hackathon(db, hackathon_id, user)
    if await _has_submissions(db, hk.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Teams are frozen once projects have been submitted")
    apps = list(await db.scalars(
        select(Application).where(Application.hackathon_id == hk.id, Application.status == ApplicationStatus.SHORTLISTED)
        .options(selectinload(Application.user))
    ))
    if not apps:
        raise HTTPException(status.HTTP_409_CONFLICT, "No shortlisted participants yet")
    participants = [{"id": str(a.user_id), "skills": [s["name"] for s in (a.user.parsed_skills or {}).get("skills", [])], "score": a.score} for a in apps]
    requirements = [{"skill": r.skill, "weight": r.priority} for r in hk.requirements]
    try:
        result = await intel.form_teams(participants, requirements, hk.max_team_size)
    except IntelligenceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    await db.execute(delete(TeamMember).where(TeamMember.hackathon_id == hk.id))
    await db.execute(delete(Team).where(Team.hackathon_id == hk.id))
    for t in result["teams"]:
        team = Team(hackathon_id=hk.id, team_name=t["name"], description=f"AI-recommended · {t['coverage']}% requirement coverage")
        db.add(team)
        await db.flush()
        for m in t["members"]:
            db.add(TeamMember(team_id=team.id, user_id=uuid.UUID(m["id"]), hackathon_id=hk.id, role=m["role"], ai_recommended=True))
    await db.commit()
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id)]


@router.get("/hackathons/{hackathon_id}/teams", response_model=list[TeamOut])
async def list_teams(hackathon_id: uuid.UUID, db: DB, user: Staff):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id)]


@router.post("/hackathons/{hackathon_id}/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(hackathon_id: uuid.UUID, body: TeamCreate, db: DB, user: Organizer):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    if await db.scalar(select(Team.id).where(Team.hackathon_id == hk.id, Team.team_name == body.team_name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A team with this name already exists")
    team = Team(hackathon_id=hk.id, team_name=body.team_name)
    db.add(team)
    await db.commit()
    return _team_out((await _load_teams(db, hk.id, team.id))[0], hk)


@router.get("/hackathons/{hackathon_id}/my-team", response_model=TeamOut | None)
async def my_team(hackathon_id: uuid.UUID, db: DB, user: Participant):
    hk = await get_hackathon(db, hackathon_id)
    # Organizers may form teams before publishing; a team assignment would reveal the decision.
    if not await db.scalar(select(Application.id).where(
        Application.hackathon_id == hk.id, Application.user_id == user.id, published_shortlisted
    )):
        return None
    team_id = await db.scalar(select(TeamMember.team_id).where(TeamMember.hackathon_id == hk.id, TeamMember.user_id == user.id))
    if team_id is None:
        return None
    return _team_out((await _load_teams(db, hk.id, team_id))[0], hk)


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(team_id: uuid.UUID, body: TeamUpdate, db: DB, user: Organizer):
    team, hk = await _owned_team(db, team_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    await db.commit()
    return _team_out((await _load_teams(db, hk.id, team.id))[0], hk)


@router.post("/teams/{team_id}/members", response_model=list[TeamOut])
async def move_member(team_id: uuid.UUID, body: MoveMemberIn, db: DB, user: Organizer):
    """Move a shortlisted participant into this team (from whichever team they were in)."""
    team, hk = await _owned_team(db, team_id, user)
    if await _has_submissions(db, hk.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Teams are frozen once projects have been submitted")
    shortlisted = await db.scalar(select(Application.id).where(
        Application.hackathon_id == hk.id, Application.user_id == body.user_id, Application.status == ApplicationStatus.SHORTLISTED
    ))
    if not shortlisted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only shortlisted participants can be placed in teams")
    size = await db.scalar(select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id != body.user_id))
    if size >= hk.max_team_size:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Team is full (max {hk.max_team_size})")
    await db.execute(delete(TeamMember).where(TeamMember.hackathon_id == hk.id, TeamMember.user_id == body.user_id))
    db.add(TeamMember(team_id=team.id, user_id=body.user_id, hackathon_id=hk.id, ai_recommended=False))
    await db.commit()
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id)]


@router.delete("/teams/{team_id}/members/{user_id}", response_model=list[TeamOut])
async def remove_member(team_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: Organizer):
    team, hk = await _owned_team(db, team_id, user)
    if await _has_submissions(db, hk.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Teams are frozen once projects have been submitted")
    await db.execute(delete(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user_id))
    await db.commit()
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id)]


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: uuid.UUID, db: DB, user: Organizer):
    team, hk = await _owned_team(db, team_id, user)
    if await db.scalar(select(Submission.id).where(Submission.team_id == team.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This team has a submission")
    await db.delete(team)
    await db.commit()
