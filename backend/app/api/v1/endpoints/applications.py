"""Team applications: the organizer's review grid, decisions, publishing, and pitch decks (Module A).

Registration itself (creating a team, inviting members, uploading CVs, submitting) lives in
registrations.py; an application is created when a team lead submits.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, Organizer, Participant, Staff
from app.api.v1.endpoints.hackathons import (
    get_hackathon,
    get_owned_hackathon,
    phase,
    to_out,
)
from app.models import Application, Team, TeamMember
from app.models.application import ApplicationStatus
from app.models.team import MemberStatus, TeamStatus
from app.models.user import UserRole
from app.mongo import files
from app.schemas import (
    ApplicationOut,
    ApplicationUpdate,
    ApplicationWithTeam,
    MemberArtifactOut,
    ParticipantApplicationOut,
    ParticipantApplicationWithHackathon,
    PublishResultsIn,
    StaffMemberOut,
    UserOut,
)
from app.services import email
from app.services.registration import member_skills
from app.services.teams import confirmed_team_id
from app.services.visibility import participant_view

router = APIRouter(tags=["applications"])


# ------------------------------------------------------------------ shared helpers

async def stream_file(file_id: str | None, what: str) -> StreamingResponse:
    """Stream a GridFS file with safe headers (used for CVs and pitch decks)."""
    if not file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {what} uploaded")
    try:
        info, chunks = await files.open_stream(file_id)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what.capitalize()} file is missing")
    safe = "".join(c for c in info["filename"] if c.isalnum() or c in "._- ")[:100] or "file"
    return StreamingResponse(chunks, media_type=info["content_type"], headers={
        "Content-Disposition": f'inline; filename="{safe}"',
        "Content-Length": str(info["size"]),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


def _staff_row(app: Application) -> ApplicationWithTeam:
    team = app.team
    artifacts = {a.user_id: a for a in team.artifacts}
    members = sorted((m for m in team.members if m.status == MemberStatus.CONFIRMED), key=lambda m: (not m.is_lead, m.joined_at))
    out = []
    for m in members:
        a = artifacts.get(m.user_id)
        art = MemberArtifactOut.model_validate(a) if a else None
        if art:
            art.has_cv = bool(a.cv_file_id)
        skills = list(dict.fromkeys(s["name"] for s in member_skills(a)))  # de-duplicated, resume first
        profile = (a.parsed_profile or {}) if a else {}
        level = (profile.get("resume") or {}).get("experience_level") or profile.get("experience_level")
        out.append(StaffMemberOut(user=UserOut.model_validate(m.user), is_lead=m.is_lead, role=m.role, artifact=art,
                                  skills=skills, experience_level=level))
    return ApplicationWithTeam(**ApplicationOut.model_validate(app).model_dump(), team_name=team.team_name,
                               formed_by=team.formed_by, seeking_teammates=team.seeking_teammates, members=out)


def _with_team_loaded():
    return selectinload(Application.team).options(
        selectinload(Team.members).selectinload(TeamMember.user), selectinload(Team.artifacts)
    )


async def _application_with_access(db, application_id: uuid.UUID, user) -> Application:
    """Team members (any confirmed member) or the hackathon's staff may access an application."""
    app = await db.scalar(select(Application).where(Application.id == application_id).options(_with_team_loaded()))
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if user.role == UserRole.PARTICIPANT:
        if await confirmed_team_id(db, app.hackathon_id, user.id) != app.team_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    else:
        await get_owned_hackathon(db, app.hackathon_id, user)
    return app


# ------------------------------------------------------------------ participants

@router.get("/applications/mine", response_model=list[ParticipantApplicationWithHackathon])
async def my_applications(db: DB, user: Participant):
    """Applications of every team the caller is a confirmed member of (participant-safe view)."""
    rows = (await db.execute(
        select(Application, Team).join(Team, Team.id == Application.team_id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id, TeamMember.status == MemberStatus.CONFIRMED)
        .order_by(Application.applied_at.desc())
    )).all()
    out = []
    for app, team in rows:
        hk = await get_hackathon(db, app.hackathon_id)
        if team.formed_by == "ai" and app.decision_published_at is None:
            continue  # an unpublished AI-formed team would reveal the shortlist
        out.append(ParticipantApplicationWithHackathon(**participant_view(app, hk, team.team_name).model_dump(),
                                                       hackathon=to_out(hk)))
    return out


@router.put("/applications/{application_id}/pitch-deck", response_model=ParticipantApplicationOut)
async def upload_pitch_deck(application_id: uuid.UUID, db: DB, user: Participant, deck: UploadFile = File(...)):
    app = await _application_with_access(db, application_id, user)
    if app.team.lead_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team lead can upload the pitch deck")
    hk = await get_hackathon(db, app.hackathon_id)
    if phase(hk) == "ended":
        raise HTTPException(status.HTTP_409_CONFLICT, "This hackathon has ended")
    data = await deck.read(files.PITCH_DECK.max_bytes + 1)
    try:
        stored = await files.save(files.PITCH_DECK, deck.filename or "pitch", data,
                                  {"team_id": str(app.team_id), "hackathon_id": str(app.hackathon_id), "purpose": "pitch_deck"})
    except files.FileRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    replaced_file_id, app.pitch_deck_file_id = app.pitch_deck_file_id, stored.file_id
    try:
        await db.commit()
    except Exception:
        await files.delete(stored.file_id)
        raise
    await files.delete(replaced_file_id)
    return participant_view(app, hk, app.team.team_name)


@router.get("/applications/{application_id}/pitch-deck")
async def download_pitch_deck(application_id: uuid.UUID, db: DB, user: CurrentUser):
    app = await _application_with_access(db, application_id, user)
    return await stream_file(app.pitch_deck_file_id, "pitch deck")


# ------------------------------------------------------------------ organizer / judges

@router.get("/hackathons/{hackathon_id}/applications", response_model=list[ApplicationWithTeam])
async def list_applications(hackathon_id: uuid.UUID, db: DB, user: Staff):
    """One row per registered team, ranked by the AI team score."""
    await get_owned_hackathon(db, hackathon_id, user)
    rows = await db.scalars(
        select(Application).join(Team, Team.id == Application.team_id)
        .where(Application.hackathon_id == hackathon_id, Team.status == TeamStatus.SUBMITTED)
        .options(_with_team_loaded())
        .order_by(Application.score.desc().nulls_last())
    )
    return [_staff_row(a) for a in rows]


@router.patch("/applications/{application_id}", response_model=ApplicationWithTeam)
async def override_status(application_id: uuid.UUID, body: ApplicationUpdate, db: DB, user: Organizer):
    app = await _application_with_access(db, application_id, user)
    if body.status != app.status:
        app.status = body.status
        # A changed decision is unpublished again; the next "Publish results" notifies this team.
        app.decision_published_at = None
    await db.commit()
    app = await _application_with_access(db, application_id, user)
    return _staff_row(app)


RESULT_TEMPLATES = {ApplicationStatus.SHORTLISTED: "result_shortlisted", ApplicationStatus.REJECTED: "result_rejected"}


@router.post("/hackathons/{hackathon_id}/results/publish")
async def publish_results(hackathon_id: uuid.UUID, body: PublishResultsIn, db: DB, user: Organizer):
    """Reveal decided results to teams and (optionally) email every confirmed member.

    Idempotent: only decisions not yet published are included, so publishing again after a
    late change notifies just the affected teams. Status changes and queued emails are
    committed together, so nobody's status can change without their email being queued.
    """
    hk = await get_owned_hackathon(db, hackathon_id, user)
    apps = list(await db.scalars(
        select(Application).join(Team, Team.id == Application.team_id)
        .where(Application.hackathon_id == hk.id, Team.status == TeamStatus.SUBMITTED).options(_with_team_loaded())
    ))
    undecided = [a for a in apps if a.status in (ApplicationStatus.PENDING, ApplicationStatus.NEEDS_REVIEW)]
    if undecided and not body.allow_undecided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{len(undecided)} team(s) still need a decision (pending or needs review). "
            "Decide them first, or publish anyway to leave them under review.",
        )
    to_publish = [a for a in apps if a.status in RESULT_TEMPLATES and a.decision_published_at is None]
    now = datetime.now(timezone.utc)
    emails = 0
    for a in to_publish:
        a.decision_published_at = now
        if body.notify:
            for m in a.team.members:
                if m.status == MemberStatus.CONFIRMED:
                    email.enqueue(db, m.user.email, RESULT_TEMPLATES[a.status],
                                  {"name": m.user.name, "hackathon": hk.event_name}, to_user_id=m.user_id)
                    emails += 1
    if to_publish:
        hk.results_published_at = now
    await db.commit()
    return {
        "published": len(to_publish),
        "shortlisted": sum(a.status == ApplicationStatus.SHORTLISTED for a in to_publish),
        "rejected": sum(a.status == ApplicationStatus.REJECTED for a in to_publish),
        "still_under_review": len(undecided),
        "emails_queued": emails,
    }
