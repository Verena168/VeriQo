"""Project submission, reference repos, and triggering integrity scans (Module C)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, Organizer, Participant, Staff
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon, phase
from app.models import Application, ReferenceRepo, Submission, TeamMember
from app.models.application import ApplicationStatus
from app.models.submission import SubmissionStatus
from app.mongo import code_store
from app.mongo.client import get_mongo_db
from app.schemas import ReferenceIn, ReferenceOut, SubmissionIn, SubmissionOut
from app.services import scan

router = APIRouter(tags=["submissions"])


@router.post("/hackathons/{hackathon_id}/submissions", response_model=SubmissionOut)
async def submit_project(hackathon_id: uuid.UUID, body: SubmissionIn, db: DB, user: Participant):
    """Create or update the caller's team submission (solo if not in a team)."""
    hk = await get_hackathon(db, hackathon_id)
    if phase(hk) != "live":
        raise HTTPException(status.HTTP_409_CONFLICT, "Submissions are only accepted while the hackathon is live")
    if not await db.scalar(select(Application.id).where(
        Application.hackathon_id == hk.id, Application.user_id == user.id, Application.status == ApplicationStatus.SHORTLISTED
    )):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only shortlisted participants can submit")
    team_id = await db.scalar(select(TeamMember.team_id).where(TeamMember.hackathon_id == hk.id, TeamMember.user_id == user.id))
    q = select(Submission).where(Submission.hackathon_id == hk.id)
    q = q.where(Submission.team_id == team_id) if team_id else q.where(Submission.team_id.is_(None), Submission.user_id == user.id)
    sub = await db.scalar(q)
    if sub and sub.status == SubmissionStatus.SCANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This submission is being scanned; try again shortly")
    if sub is None:
        sub = Submission(hackathon_id=hk.id, team_id=team_id)
        db.add(sub)
    sub.user_id, sub.project_title, sub.repository_url = user.id, body.project_title, body.repository_url
    sub.status, sub.commit_sha = SubmissionStatus.SUBMITTED, None
    await db.commit()
    await db.refresh(sub)
    return sub


@router.get("/hackathons/{hackathon_id}/my-submission", response_model=SubmissionOut | None)
async def my_submission(hackathon_id: uuid.UUID, db: DB, user: Participant):
    team_id = await db.scalar(select(TeamMember.team_id).where(TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == user.id))
    q = select(Submission).where(Submission.hackathon_id == hackathon_id)
    q = q.where(Submission.team_id == team_id) if team_id else q.where(Submission.team_id.is_(None), Submission.user_id == user.id)
    return await db.scalar(q)


@router.get("/hackathons/{hackathon_id}/submissions", response_model=list[SubmissionOut])
async def list_submissions(hackathon_id: uuid.UUID, db: DB, user: Staff):
    await get_owned_hackathon(db, hackathon_id, user)
    return list(await db.scalars(select(Submission).where(Submission.hackathon_id == hackathon_id).order_by(Submission.submitted_at)))


@router.post("/hackathons/{hackathon_id}/scan", status_code=status.HTTP_202_ACCEPTED)
async def scan_all(hackathon_id: uuid.UUID, db: DB, user: Organizer, background: BackgroundTasks):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    subs = list(await db.scalars(select(Submission).where(Submission.hackathon_id == hk.id)))
    if not subs:
        raise HTTPException(status.HTTP_409_CONFLICT, "No submissions to scan")
    if any(s.status == SubmissionStatus.SCANNING for s in subs):
        raise HTTPException(status.HTTP_409_CONFLICT, "A scan is already running")
    pending_refs = await db.scalar(select(ReferenceRepo.id).where(ReferenceRepo.hackathon_id == hk.id, ReferenceRepo.status == "pending"))
    for s in subs:
        s.status = SubmissionStatus.SCANNING
    await db.commit()
    background.add_task(scan.scan_hackathon, hk.id)
    return {"queued": len(subs), "warning": "Some reference repos are still being analysed" if pending_refs else None}


@router.post("/submissions/{submission_id}/scan", status_code=status.HTTP_202_ACCEPTED)
async def scan_one(submission_id: uuid.UUID, db: DB, user: Organizer, background: BackgroundTasks):
    sub = await db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    await get_owned_hackathon(db, sub.hackathon_id, user)
    if sub.status == SubmissionStatus.SCANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already scanning")
    sub.status = SubmissionStatus.SCANNING
    await db.commit()
    background.add_task(scan.scan_submission, sub.id)
    return {"queued": 1}


# ------------------------------------------------------------------ reference corpus

@router.get("/hackathons/{hackathon_id}/references", response_model=list[ReferenceOut])
async def list_references(hackathon_id: uuid.UUID, db: DB, user: Staff):
    await get_owned_hackathon(db, hackathon_id, user)
    return list(await db.scalars(select(ReferenceRepo).where(ReferenceRepo.hackathon_id == hackathon_id).order_by(ReferenceRepo.created_at)))


@router.post("/hackathons/{hackathon_id}/references", response_model=ReferenceOut, status_code=status.HTTP_201_CREATED)
async def add_reference(hackathon_id: uuid.UUID, body: ReferenceIn, db: DB, user: Organizer, background: BackgroundTasks):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    ref = ReferenceRepo(hackathon_id=hk.id, repo_url=body.repo_url, label=body.label, kind=body.kind, status="pending")
    db.add(ref)
    await db.commit()
    await db.refresh(ref)
    background.add_task(scan.analyze_reference, ref.id)
    return ref


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference(reference_id: uuid.UUID, db: DB, user: Organizer):
    ref = await db.get(ReferenceRepo, reference_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reference not found")
    await get_owned_hackathon(db, ref.hackathon_id, user)
    await code_store.delete_source(get_mongo_db(), ref.id)
    await db.delete(ref)
    await db.commit()
