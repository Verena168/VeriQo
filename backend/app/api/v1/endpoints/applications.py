"""Participant applications: resume upload, AI shortlisting results (Module A)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, Organizer, Participant, Staff
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon, phase, to_out
from app.models import Application, TeamMember
from app.models.application import ApplicationStatus
from app.models.user import UserRole
from app.mongo import files
from app.schemas import GITHUB_PROFILE_RE, ApplicationOut, ApplicationUpdate, ApplicationWithHackathon, ApplicationWithUser
from app.services import email
from app.services import intelligence_client as intel
from app.services.intelligence_client import IntelligenceError

router = APIRouter(tags=["applications"])
MAX_RESUME_BYTES = 5 * 1024 * 1024


def _with_hackathon(app: Application, hk) -> ApplicationWithHackathon:
    return ApplicationWithHackathon(**ApplicationOut.model_validate(app).model_dump(), hackathon=to_out(hk))


def _merge_skills(*lists: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for skills in lists:
        for s in skills:
            m = merged.setdefault(s["name"], {"name": s["name"], "category": s["category"], "mentions": 0, "sources": []})
            m["mentions"] += s.get("mentions", 1)
            if s.get("source") and s["source"] not in m["sources"]:
                m["sources"].append(s["source"])
    return sorted(merged.values(), key=lambda s: -s["mentions"])


@router.post("/hackathons/{hackathon_id}/applications", response_model=ApplicationWithHackathon, status_code=status.HTTP_201_CREATED)
async def apply(
    hackathon_id: uuid.UUID,
    db: DB,
    user: Participant,
    resume: UploadFile = File(...),
    github_url: str | None = Form(default=None),
):
    hk = await get_hackathon(db, hackathon_id)
    if phase(hk) == "ended":
        raise HTTPException(status.HTTP_409_CONFLICT, "This hackathon has ended")
    if await db.scalar(select(TeamMember.team_id).where(TeamMember.hackathon_id == hk.id, TeamMember.user_id == user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already in a team for this hackathon")
    github_url = (github_url or "").strip() or user.github_url
    if github_url and not GITHUB_PROFILE_RE.match(github_url):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "GitHub URL must look like https://github.com/<username>")

    data = await resume.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Resume must be 5 MB or smaller")
    try:
        files.validate(files.CV, resume.filename or "", data)  # by content, before any AI work
    except files.FileRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    review_note, parsed = None, None
    try:
        parsed = await intel.parse_resume(resume.filename or "resume", data, resume.content_type)
    except IntelligenceError as exc:
        if exc.code != "unreadable_resume":
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
        review_note = f"Resume could not be parsed: {exc}"

    github = None
    github_url = github_url or (parsed or {}).get("github_url")
    if github_url:
        try:
            github = await intel.github_profile(github_url)
            user.github_url = github_url
        except IntelligenceError as exc:
            review_note = (review_note + "; " if review_note else "") + f"GitHub: {exc}"

    skills = _merge_skills((parsed or {}).get("skills", []), (github or {}).get("skills", []))
    user.parsed_skills = {
        "skills": skills,
        "experience_years": (parsed or {}).get("experience_years"),
        "experience_level": (parsed or {}).get("experience_level"),
        "github": {k: v for k, v in (github or {}).items() if k != "skills"} or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    requirements = [{"skill": r.skill, "weight": r.priority} for r in hk.requirements]
    score, breakdown = None, None
    if parsed is not None:
        try:
            result = await intel.match([s["name"] for s in skills], requirements)
        except IntelligenceError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
        score, breakdown = result["score"], result["breakdown"]

    if parsed is None:
        new_status = ApplicationStatus.NEEDS_REVIEW  # whitebook Use Case 1 exception path
    elif not requirements:
        new_status = ApplicationStatus.SHORTLISTED
    else:
        new_status = ApplicationStatus.SHORTLISTED if score >= hk.shortlist_threshold else ApplicationStatus.REJECTED

    app = await db.scalar(select(Application).where(Application.hackathon_id == hk.id, Application.user_id == user.id))
    if app is None:
        app = Application(hackathon_id=hk.id, user_id=user.id)
        db.add(app)
    stored = await files.save(files.CV, resume.filename or "resume", data,
                              {"user_id": str(user.id), "hackathon_id": str(hk.id), "purpose": "application_cv"})
    replaced_file_id = app.cv_file_id
    app.status, app.score, app.match_details = new_status, score, breakdown
    app.resume_filename = stored.filename[:255]
    app.cv_file_id = stored.file_id
    app.review_note = review_note[:500] if review_note else None
    app.applied_at = datetime.now(timezone.utc)
    email.enqueue(db, user.email, "application_received", {"name": user.name, "hackathon": hk.event_name}, to_user_id=user.id)
    try:
        await db.commit()
    except Exception:
        await files.delete(stored.file_id)  # don't leave an orphaned upload behind
        raise
    await files.delete(replaced_file_id)  # previous CV, only once the new one is safely recorded
    await db.refresh(app)
    return _with_hackathon(app, hk)


async def _application_for_file(db, application_id: uuid.UUID, user) -> Application:
    """The applicant themselves, or staff of the hackathon, may access an application's files."""
    app = await db.get(Application, application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if user.role == UserRole.PARTICIPANT:
        if app.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    else:
        await get_owned_hackathon(db, app.hackathon_id, user)
    return app


async def _stream(file_id: str | None, what: str) -> StreamingResponse:
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


@router.get("/applications/{application_id}/cv")
async def download_cv(application_id: uuid.UUID, db: DB, user: CurrentUser):
    app = await _application_for_file(db, application_id, user)
    return await _stream(app.cv_file_id, "CV")


@router.put("/applications/{application_id}/pitch-deck", response_model=ApplicationOut)
async def upload_pitch_deck(application_id: uuid.UUID, db: DB, user: Participant, deck: UploadFile = File(...)):
    app = await _application_for_file(db, application_id, user)
    hk = await get_hackathon(db, app.hackathon_id)
    if phase(hk) == "ended":
        raise HTTPException(status.HTTP_409_CONFLICT, "This hackathon has ended")
    data = await deck.read(files.PITCH_DECK.max_bytes + 1)
    try:
        stored = await files.save(files.PITCH_DECK, deck.filename or "pitch", data,
                                  {"user_id": str(user.id), "hackathon_id": str(app.hackathon_id), "purpose": "pitch_deck"})
    except files.FileRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    replaced_file_id, app.pitch_deck_file_id = app.pitch_deck_file_id, stored.file_id
    try:
        await db.commit()
    except Exception:
        await files.delete(stored.file_id)
        raise
    await files.delete(replaced_file_id)
    await db.refresh(app)
    return app


@router.get("/applications/{application_id}/pitch-deck")
async def download_pitch_deck(application_id: uuid.UUID, db: DB, user: CurrentUser):
    app = await _application_for_file(db, application_id, user)
    return await _stream(app.pitch_deck_file_id, "pitch deck")


@router.get("/applications/mine", response_model=list[ApplicationWithHackathon])
async def my_applications(db: DB, user: Participant):
    rows = list(await db.scalars(
        select(Application).where(Application.user_id == user.id).order_by(Application.applied_at.desc())
    ))
    return [_with_hackathon(a, await get_hackathon(db, a.hackathon_id)) for a in rows]


@router.get("/hackathons/{hackathon_id}/applications", response_model=list[ApplicationWithUser])
async def list_applications(hackathon_id: uuid.UUID, db: DB, user: Staff):
    await get_owned_hackathon(db, hackathon_id, user)
    rows = await db.scalars(
        select(Application).where(Application.hackathon_id == hackathon_id)
        .options(selectinload(Application.user))
        .order_by(Application.score.desc().nulls_last())
    )
    return list(rows)


@router.patch("/applications/{application_id}", response_model=ApplicationWithUser)
async def override_status(application_id: uuid.UUID, body: ApplicationUpdate, db: DB, user: Organizer):
    app = await db.get(Application, application_id, options=[selectinload(Application.user)])
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    await get_owned_hackathon(db, app.hackathon_id, user)
    if body.status != ApplicationStatus.SHORTLISTED and await db.scalar(
        select(TeamMember.team_id).where(TeamMember.hackathon_id == app.hackathon_id, TeamMember.user_id == app.user_id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Remove this participant from their team first")
    app.status = body.status
    await db.commit()
    await db.refresh(app)
    return app
