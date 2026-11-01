"""Teams: the organizer's view of registered teams, and AI team formation for solo registrants (Module A).

Teams are formed by their lead at registration (registrations.py). AI formation is for solo
registrants in a team event who asked to be matched ("looking for teammates"): after
shortlisting, the organizer merges them into skill-balanced teams.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, Organizer, Participant, Staff
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon
from app.models import (
    Application,
    Hackathon,
    Submission,
    Team,
    TeamMember,
    TeamMemberArtifact,
)
from app.models.application import ApplicationStatus
from app.models.team import MemberStatus, TeamStatus
from app.schemas import TeamOut, TeamUpdate
from app.services import intelligence_client as intel
from app.services.intelligence_client import IntelligenceError
from app.services.registration import member_skills
from app.services.teams import member_has_published_shortlist

router = APIRouter(tags=["teams"])


def _team_out(team: Team, hk: Hackathon) -> TeamOut:
    confirmed = sorted((m for m in team.members if m.status == MemberStatus.CONFIRMED), key=lambda m: (not m.is_lead, m.joined_at))
    out = TeamOut.model_validate(team)
    out.members = [m for m in out.members if any(c.user_id == m.user.id for c in confirmed)]
    out.members.sort(key=lambda m: not m.is_lead)
    artifacts = {a.user_id: a for a in team.artifacts}
    have = {s["name"].lower() for m in confirmed for s in member_skills(artifacts.get(m.user_id))}
    total = sum(r.priority for r in hk.requirements)
    covered = sum(r.priority for r in hk.requirements if r.skill.lower() in have)
    out.coverage = round(100 * covered / total, 1) if total else None
    out.missing_skills = [r.skill for r in hk.requirements if r.skill.lower() not in have]
    return out


async def _load_teams(db, hackathon_id: uuid.UUID, team_id: uuid.UUID | None = None) -> list[Team]:
    q = (select(Team).where(Team.hackathon_id == hackathon_id, Team.status == TeamStatus.SUBMITTED)
         .options(selectinload(Team.members).selectinload(TeamMember.user), selectinload(Team.artifacts))
         .order_by(Team.team_name).execution_options(populate_existing=True))
    if team_id:
        q = q.where(Team.id == team_id)
    return list(await db.scalars(q))


@router.get("/hackathons/{hackathon_id}/teams", response_model=list[TeamOut])
async def list_teams(hackathon_id: uuid.UUID, db: DB, user: Staff):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id)]


@router.get("/hackathons/{hackathon_id}/my-team", response_model=TeamOut | None)
async def my_team(hackathon_id: uuid.UUID, db: DB, user: Participant):
    """The caller's competition team, once their shortlisting is published (it would otherwise
    reveal the decision, e.g. for AI-formed teams)."""
    hk = await get_hackathon(db, hackathon_id)
    if not await db.scalar(select(member_has_published_shortlist(user.id, hk.id))):
        return None
    team_id = await db.scalar(select(TeamMember.team_id).where(
        TeamMember.hackathon_id == hk.id, TeamMember.user_id == user.id, TeamMember.status == MemberStatus.CONFIRMED))
    teams = await _load_teams(db, hk.id, team_id) if team_id else []
    return _team_out(teams[0], hk) if teams else None


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(team_id: uuid.UUID, body: TeamUpdate, db: DB, user: Organizer):
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    hk = await get_owned_hackathon(db, team.hackathon_id, user)
    data = body.model_dump(exclude_unset=True)
    if "team_name" in data and await db.scalar(select(Team.id).where(
            Team.hackathon_id == hk.id, Team.team_name == data["team_name"], Team.id != team.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That team name is taken in this hackathon")
    for field, value in data.items():
        setattr(team, field, value)
    await db.commit()
    return _team_out((await _load_teams(db, hk.id, team.id))[0], hk)


@router.post("/hackathons/{hackathon_id}/teams/form", response_model=list[TeamOut])
async def ai_form_teams(hackathon_id: uuid.UUID, db: DB, user: Organizer):
    """Merge shortlisted solo registrants who asked for teammates into skill-balanced AI teams.

    Each new team gets a fresh application, scored on its members' pooled skills and shortlisted
    (its members already were); it stays unpublished until the organizer publishes results, which
    is also how members learn their new team.
    """
    hk = await get_owned_hackathon(db, hackathon_id, user)
    candidates = list(await db.scalars(
        select(Application).join(Team, Team.id == Application.team_id)
        .where(Application.hackathon_id == hk.id, Application.status == ApplicationStatus.SHORTLISTED,
               Team.status == TeamStatus.SUBMITTED, Team.formed_by == "self", Team.seeking_teammates.is_(True))
        .options(selectinload(Application.team).options(
            selectinload(Team.members).selectinload(TeamMember.user), selectinload(Team.artifacts)))
    ))
    solos = [a for a in candidates if sum(m.status == MemberStatus.CONFIRMED for m in a.team.members) == 1]
    if len(solos) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "AI formation needs at least two shortlisted solo registrants who are looking for teammates")
    if await db.scalar(select(Submission.id).where(Submission.team_id.in_([a.team_id for a in solos])).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Some of these registrants have already submitted a project")

    by_user = {}
    for a in solos:
        member = next(m for m in a.team.members if m.status == MemberStatus.CONFIRMED)
        artifact = next((x for x in a.team.artifacts if x.user_id == member.user_id), None)
        by_user[str(member.user_id)] = (a, member, artifact)
    participants = [{"id": uid, "skills": [s["name"] for s in member_skills(art)], "score": app.score}
                    for uid, (app, _, art) in by_user.items()]
    requirements = [{"skill": r.skill, "weight": r.priority} for r in hk.requirements]
    try:
        formed = await intel.form_teams(participants, requirements, hk.max_team_size)
    except IntelligenceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    now = datetime.now(timezone.utc)
    existing_names = set(await db.scalars(select(Team.team_name).where(Team.hackathon_id == hk.id)))
    new_ids = []
    counter = 1
    for t in formed["teams"]:
        if len(t["members"]) < 2:
            continue  # a leftover single registrant keeps their solo registration
        while f"AI Team {counter}" in existing_names:
            counter += 1
        name = f"AI Team {counter}"
        existing_names.add(name)
        lead_uid = uuid.UUID(t["members"][0]["id"])  # the AI seeds each team with its strongest member
        team = Team(id=uuid.uuid4(), hackathon_id=hk.id, team_name=name, lead_user_id=lead_uid, status=TeamStatus.SUBMITTED,
                    formed_by="ai", submitted_at=now, description=f"AI-formed · {t['coverage']}% requirement coverage")
        db.add(team)
        await db.flush()
        pooled = set()
        for m in t["members"]:
            app, old_member, artifact = by_user[m["id"]]
            old_team = app.team
            old_team.status, old_team.merged_into_id = TeamStatus.MERGED, team.id
            old_member.status = MemberStatus.REMOVED
            await db.flush()  # free the person's single live-team slot before adding the new membership
            db.add(TeamMember(team_id=team.id, user_id=old_member.user_id, hackathon_id=hk.id, role=m["role"],
                              ai_recommended=True, is_lead=old_member.user_id == lead_uid,
                              status=MemberStatus.CONFIRMED, confirmed_at=now))
            if artifact:
                db.add(TeamMemberArtifact(team_id=team.id, user_id=artifact.user_id, cv_file_id=artifact.cv_file_id,
                                          cv_filename=artifact.cv_filename, github_url=artifact.github_url,
                                          uploaded_by=artifact.uploaded_by, parse_status=artifact.parse_status,
                                          parse_note=artifact.parse_note, parsed_profile=artifact.parsed_profile))
                pooled |= {s["name"] for s in member_skills(artifact)}
        score, details = None, None
        if requirements:
            try:
                result = await intel.match(sorted(pooled), requirements)
                score, details = result["score"], result["breakdown"]
            except IntelligenceError:
                pass
        db.add(Application(id=uuid.uuid4(), hackathon_id=hk.id, team_id=team.id, submitted_by=lead_uid,
                           status=ApplicationStatus.SHORTLISTED, score=score, match_details=details,
                           review_note="Formed by AI from shortlisted solo registrants", applied_at=now))
        new_ids.append(team.id)
    if not new_ids:
        raise HTTPException(status.HTTP_409_CONFLICT, "Not enough compatible registrants to form a team")
    await db.commit()
    return [_team_out(t, hk) for t in await _load_teams(db, hk.id) if t.id in new_ids]
