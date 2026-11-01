"""Team registration: the Team Lead creates the team, invites members (each confirms by email OTP),
collects every member's CV and GitHub profile, and submits (docs/STAGE1_DESIGN.md §3.2)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB, CurrentUser, Participant
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon, phase
from app.core.config import get_settings
from app.models import Hackathon, OtpCode, Team, TeamMember, TeamMemberArtifact, User
from app.models.hackathon import ParticipationMode
from app.models.team import ACTIVE_MEMBER_STATUSES, MemberStatus, TeamStatus
from app.models.user import UserRole
from app.mongo import files
from app.schemas import (
    GITHUB_PROFILE_RE,
    InvitationOut,
    InviteIn,
    MemberArtifactOut,
    OtpVerifyIn,
    RegistrationCreate,
    RegistrationMemberOut,
    RegistrationOut,
    UserBrief,
)
from app.services import email, otp
from app.services import registration as reg
from app.services.eligibility import person_violations, registration_problem
from app.services.intelligence_client import IntelligenceError
from app.services.teams import active_membership, load_team
from app.services.visibility import participant_view

router = APIRouter(tags=["registration"])
OTP_PURPOSE = "team_join"


# ------------------------------------------------------------------ helpers

def _artifact_out(a: TeamMemberArtifact | None) -> MemberArtifactOut | None:
    if a is None:
        return None
    out = MemberArtifactOut.model_validate(a)
    out.has_cv = bool(a.cv_file_id)
    return out


async def _registration_out(db, team: Team, hk: Hackathon, viewer: User) -> RegistrationOut:
    artifacts = {a.user_id: a for a in team.artifacts}
    live = [m for m in team.members if m.status in ACTIVE_MEMBER_STATUSES]
    live.sort(key=lambda m: (not m.is_lead, m.joined_at))
    return RegistrationOut(
        team_id=team.id, hackathon_id=hk.id, team_name=team.team_name, status=team.status.value,
        seeking_teammates=team.seeking_teammates, is_lead=team.lead_user_id == viewer.id,
        members=[RegistrationMemberOut(
            user=UserBrief.model_validate(m.user), is_lead=m.is_lead, status=m.status.value,
            invited_at=m.joined_at, confirmed_at=m.confirmed_at, artifact=_artifact_out(artifacts.get(m.user_id)),
        ) for m in live],
        checklist=reg.checklist(team, hk),
        application=participant_view(team.application, hk, team.team_name) if team.application else None,
    )


async def _lead_team(db, team_id: uuid.UUID, user: User, *, draft: bool = True) -> tuple[Team, Hackathon]:
    team = await load_team(db, team_id)
    if team is None or team.lead_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    if draft and team.status != TeamStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "This registration has already been submitted")
    return team, await get_hackathon(db, team.hackathon_id)


def _member(team: Team, user_id: uuid.UUID, statuses=ACTIVE_MEMBER_STATUSES) -> TeamMember | None:
    return next((m for m in team.members if m.user_id == user_id and m.status in statuses), None)


async def _send_invite(db, team: Team, hk: Hackathon, lead: User, invitee: User) -> None:
    try:
        code = await otp.issue(db, invitee.id, OTP_PURPOSE, team.id)
    except otp.OtpError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    email.enqueue(db, invitee.email, "team_invite_otp", {
        "name": invitee.name, "lead": lead.name, "team": team.team_name, "hackathon": hk.event_name,
        "ttl_minutes": get_settings().otp_ttl_minutes, "code": code,
    }, to_user_id=invitee.id)


# ------------------------------------------------------------------ lead: create / view / delete

@router.post("/hackathons/{hackathon_id}/registrations", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED)
async def start_registration(hackathon_id: uuid.UUID, body: RegistrationCreate, db: DB, user: Participant):
    """The caller becomes the Team Lead of a new draft team (a solo entrant is a team of one)."""
    hk = await get_hackathon(db, hackathon_id)
    if phase(hk) == "ended":
        raise HTTPException(status.HTTP_409_CONFLICT, "This hackathon has ended")
    if closed := registration_problem(hk):
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    if problems := person_violations(user, hk):
        raise HTTPException(status.HTTP_403_FORBIDDEN, " ".join(problems))
    if await active_membership(db, hk.id, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "You are already in, or invited to, a team for this hackathon. Check your invitations.")
    solo = hk.participation_mode == ParticipationMode.SOLO
    name = (body.team_name or "").strip() or (user.name if solo else "")
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a team name")
    if await db.scalar(select(Team.id).where(Team.hackathon_id == hk.id, Team.team_name == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That team name is taken in this hackathon")
    now = datetime.now(timezone.utc)
    team = Team(id=uuid.uuid4(), hackathon_id=hk.id, team_name=name, lead_user_id=user.id, status=TeamStatus.DRAFT,
                formed_by="self", seeking_teammates=body.seeking_teammates and not solo)
    db.add(team)
    db.add(TeamMember(team_id=team.id, user_id=user.id, hackathon_id=hk.id, is_lead=True,
                      status=MemberStatus.CONFIRMED, confirmed_at=now, ai_recommended=False))
    db.add(TeamMemberArtifact(team_id=team.id, user_id=user.id, github_url=user.github_url, uploaded_by=user.id))
    try:
        await db.commit()
    except IntegrityError:  # a concurrent request registered this person first
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already in a team for this hackathon")
    return await _registration_out(db, await load_team(db, team.id), hk, user)


@router.get("/hackathons/{hackathon_id}/registration", response_model=RegistrationOut | None)
async def my_registration(hackathon_id: uuid.UUID, db: DB, user: Participant):
    """The caller's team for this hackathon (as lead or confirmed member). Pending invitations are
    listed separately under /me/team-invitations."""
    hk = await get_hackathon(db, hackathon_id)
    member = await active_membership(db, hk.id, user.id)
    if member is None or member.status != MemberStatus.CONFIRMED:
        return None
    team = await load_team(db, member.team_id)
    if team.formed_by == "ai" and not (team.application and team.application.decision_published_at):
        return None  # an AI-formed team would reveal the (unpublished) shortlist
    return await _registration_out(db, team, hk, user)


@router.delete("/registrations/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_registration(team_id: uuid.UUID, db: DB, user: Participant):
    """The lead abandons a draft registration (e.g. to join someone else's team instead)."""
    team, _ = await _lead_team(db, team_id, user)
    await reg.delete_artifact_files(team)
    await db.delete(team)
    await db.commit()


# ------------------------------------------------------------------ lead: members

@router.post("/registrations/{team_id}/members", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED)
async def invite_member(team_id: uuid.UUID, body: InviteIn, db: DB, user: Participant):
    team, hk = await _lead_team(db, team_id, user)
    if hk.participation_mode == ParticipationMode.SOLO:
        raise HTTPException(status.HTTP_409_CONFLICT, "This is a solo hackathon")
    live = [m for m in team.members if m.status in ACTIVE_MEMBER_STATUSES]
    if len(live) >= hk.max_team_size:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Teams can have at most {hk.max_team_size} members")
    invitee = await db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if invitee is None or invitee.role != UserRole.PARTICIPANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No VERIQO participant account uses this email. Ask them to sign up first, then invite them.")
    if invitee.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already the team lead")
    if await active_membership(db, hk.id, invitee.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{invitee.name} is already in, or invited to, a team for this hackathon")
    existing = _member(team, invitee.id, statuses=(MemberStatus.DECLINED, MemberStatus.REMOVED))
    now = datetime.now(timezone.utc)
    if existing:  # re-inviting someone who declined or was removed earlier
        existing.status, existing.joined_at, existing.confirmed_at = MemberStatus.INVITED, now, None
    else:
        db.add(TeamMember(team_id=team.id, user_id=invitee.id, hackathon_id=hk.id, status=MemberStatus.INVITED,
                          joined_at=now, ai_recommended=False))
    if not any(a.user_id == invitee.id for a in team.artifacts):
        db.add(TeamMemberArtifact(team_id=team.id, user_id=invitee.id, github_url=invitee.github_url, uploaded_by=user.id))
    await _send_invite(db, team, hk, user, invitee)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"{invitee.name} was just added to another team")
    return await _registration_out(db, await load_team(db, team.id), hk, user)


@router.post("/registrations/{team_id}/members/{user_id}/resend", response_model=RegistrationOut)
async def resend_invite(team_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: Participant):
    team, hk = await _lead_team(db, team_id, user)
    member = _member(team, user_id, statuses=(MemberStatus.INVITED,))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending invitation for this member")
    await _send_invite(db, team, hk, user, member.user)
    await db.commit()
    return await _registration_out(db, await load_team(db, team.id), hk, user)


@router.delete("/registrations/{team_id}/members/{user_id}", response_model=RegistrationOut)
async def remove_member(team_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: Participant):
    team, hk = await _lead_team(db, team_id, user)
    member = _member(team, user_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this team")
    if member.is_lead:
        raise HTTPException(status.HTTP_409_CONFLICT, "The lead can't be removed; discard the registration instead")
    member.status, member.confirmed_at = MemberStatus.REMOVED, None
    artifact = next((a for a in team.artifacts if a.user_id == user_id), None)
    if artifact:
        await files.delete(artifact.cv_file_id)
        await db.delete(artifact)
    # Invalidate any outstanding code so it can't be used to rejoin.
    for code in await db.scalars(select(OtpCode).where(OtpCode.user_id == user_id, OtpCode.subject_id == team.id,
                                                       OtpCode.consumed_at.is_(None))):
        code.consumed_at = datetime.now(timezone.utc)
    await db.commit()
    return await _registration_out(db, await load_team(db, team.id), hk, user)


# ------------------------------------------------------------------ CVs and GitHub (lead or the member)

@router.put("/registrations/{team_id}/members/{user_id}/artifacts", response_model=RegistrationOut)
async def upload_member_artifacts(
    team_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: Participant,
    cv: UploadFile | None = File(default=None), github_url: str | None = Form(default=None),
):
    """Upload a member's CV (PDF/DOCX/TXT) and/or set their GitHub profile. The lead can do this for
    any member; a member can do it for themselves."""
    team = await load_team(db, team_id)
    me = _member(team, user.id) if team else None
    if team is None or me is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    if user.id != team.lead_user_id and user.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the team lead or the member themselves can do this")
    if team.status != TeamStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "This registration has already been submitted")
    target = _member(team, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this team")
    hk = await get_hackathon(db, team.hackathon_id)
    if cv is None and github_url is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a CV or provide a GitHub profile URL")
    if github_url is not None:
        github_url = github_url.strip()
        if not GITHUB_PROFILE_RE.match(github_url):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "GitHub URL must look like https://github.com/<username>")

    artifact = next((a for a in team.artifacts if a.user_id == user_id), None)
    if artifact is None:
        artifact = TeamMemberArtifact(team_id=team.id, user_id=user_id)
        db.add(artifact)
    data = stored = None
    if cv is not None:
        data = await cv.read(files.CV.max_bytes + 1)
        try:
            stored = await files.save(files.CV, cv.filename or "cv", data,
                                      {"user_id": str(user_id), "team_id": str(team.id), "hackathon_id": str(hk.id),
                                       "purpose": "member_cv"})
        except files.FileRejected as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    replaced = artifact.cv_file_id if stored else None
    if stored:
        artifact.cv_file_id, artifact.cv_filename = stored.file_id, stored.filename[:255]
    if github_url is not None:
        artifact.github_url = github_url
    artifact.uploaded_by = user.id
    try:
        await reg.analyse_member(artifact, stored.filename if stored else None, data)
    except IntelligenceError as exc:  # unexpected: keep the upload, flag for retry
        artifact.parse_status, artifact.parse_note = reg.PARSE_FAILED, str(exc)[:500]
    try:
        await db.commit()
    except Exception:
        if stored:
            await files.delete(stored.file_id)
        raise
    await files.delete(replaced)
    return await _registration_out(db, await load_team(db, team.id), hk, user)


# ------------------------------------------------------------------ submit

@router.post("/registrations/{team_id}/submit", response_model=RegistrationOut)
async def submit_registration(team_id: uuid.UUID, db: DB, user: Participant):
    team, hk = await _lead_team(db, team_id, user)
    if blockers := reg.checklist(team, hk):
        raise HTTPException(status.HTTP_409_CONFLICT, "Not ready to submit: " + " ".join(blockers))
    try:
        await reg.score_and_submit(db, team, hk, user)
    except IntelligenceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Scoring failed, please try again: {exc}")
    for m in team.members:
        if m.status == MemberStatus.CONFIRMED:
            email.enqueue(db, m.user.email, "application_received", {"name": m.user.name, "hackathon": hk.event_name},
                          to_user_id=m.user_id)
    await db.commit()
    return await _registration_out(db, await load_team(db, team.id), hk, user)


# ------------------------------------------------------------------ invitees

@router.get("/me/team-invitations", response_model=list[InvitationOut])
async def my_invitations(db: DB, user: Participant):
    rows = await db.execute(
        select(TeamMember, Team, Hackathon, User)
        .join(Team, Team.id == TeamMember.team_id)
        .join(Hackathon, Hackathon.id == Team.hackathon_id)
        .join(User, User.id == Team.lead_user_id)
        .where(TeamMember.user_id == user.id, TeamMember.status == MemberStatus.INVITED, Team.status == TeamStatus.DRAFT)
        .order_by(TeamMember.joined_at.desc())
    )
    return [InvitationOut(team_id=t.id, team_name=t.team_name, hackathon_id=h.id, hackathon_name=h.event_name,
                          lead_name=lead.name, invited_at=m.joined_at) for m, t, h, lead in rows.all()]


async def _my_invite(db, team_id: uuid.UUID, user: User) -> tuple[Team, TeamMember]:
    team = await load_team(db, team_id)
    member = _member(team, user.id, statuses=(MemberStatus.INVITED,)) if team else None
    if team is None or member is None or team.status != TeamStatus.DRAFT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found or no longer open")
    return team, member


@router.post("/team-invitations/{team_id}/verify", response_model=RegistrationOut)
async def accept_invitation(team_id: uuid.UUID, body: OtpVerifyIn, db: DB, user: Participant):
    """The invited member confirms with the code emailed to them, in their own logged-in session."""
    team, member = await _my_invite(db, team_id, user)
    hk = await get_hackathon(db, team.hackathon_id)
    try:
        await otp.verify(db, user.id, OTP_PURPOSE, body.code, team.id)
    except otp.OtpError as exc:
        await db.commit()  # record the failed attempt so the attempt limit holds
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    member.status, member.confirmed_at = MemberStatus.CONFIRMED, datetime.now(timezone.utc)
    await db.commit()
    return await _registration_out(db, await load_team(db, team.id), hk, user)


@router.post("/team-invitations/{team_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invitation(team_id: uuid.UUID, db: DB, user: Participant):
    team, member = await _my_invite(db, team_id, user)
    member.status = MemberStatus.DECLINED
    artifact = next((a for a in team.artifacts if a.user_id == user.id), None)
    if artifact:
        await files.delete(artifact.cv_file_id)
        await db.delete(artifact)
    await db.commit()


# ------------------------------------------------------------------ CV download (team members and staff)

@router.get("/teams/{team_id}/members/{user_id}/cv")
async def download_member_cv(team_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: CurrentUser):
    from app.api.v1.endpoints.applications import stream_file  # shared streaming helper

    team = await load_team(db, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    if user.role == UserRole.PARTICIPANT:
        if _member(team, user.id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    else:
        await get_owned_hackathon(db, team.hackathon_id, user)
    artifact = next((a for a in team.artifacts if a.user_id == user_id), None)
    return await stream_file(artifact.cv_file_id if artifact else None, "CV")
