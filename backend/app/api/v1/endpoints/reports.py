"""Originality reports for the organizer evaluation grid (Module D)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, Participant, Staff
from app.api.v1.endpoints.hackathons import get_hackathon, get_owned_hackathon
from app.models import OriginalityReport, Submission, Team, TeamMember, User
from app.models.report import ReportStatus
from app.mongo import telemetry
from app.mongo.client import get_mongo_db
from app.schemas import (
    ReportDetail,
    ReportOut,
    ReportRow,
    ReportUpdate,
    SubmissionOut,
    UserBrief,
)

router = APIRouter(tags=["reports"])


async def _members(db, sub: Submission) -> list[User]:
    if sub.team_id is None:
        return [await db.get(User, sub.user_id)]
    return list(await db.scalars(select(User).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == sub.team_id)))


async def _team_name(db, sub: Submission) -> str | None:
    return await db.scalar(select(Team.team_name).where(Team.id == sub.team_id)) if sub.team_id else None


@router.get("/hackathons/{hackathon_id}/reports", response_model=list[ReportRow])
async def evaluation_grid(hackathon_id: uuid.UUID, db: DB, user: Staff):
    await get_owned_hackathon(db, hackathon_id, user)
    subs = list(await db.scalars(
        select(Submission).where(Submission.hackathon_id == hackathon_id).options(selectinload(Submission.report)).order_by(Submission.submitted_at)
    ))
    return [
        ReportRow(
            submission=SubmissionOut.model_validate(s),
            team_name=await _team_name(db, s),
            members=[UserBrief.model_validate(m) for m in await _members(db, s)],
            report=ReportOut.model_validate(s.report) if s.report else None,
        )
        for s in subs
    ]


async def _report_with_access(db, report_id: uuid.UUID, user) -> tuple[OriginalityReport, Submission]:
    report = await db.get(OriginalityReport, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    sub = await db.get(Submission, report.submission_id)
    await get_owned_hackathon(db, sub.hackathon_id, user)
    return report, sub


@router.get("/reports/{report_id}")
async def report_detail(report_id: uuid.UUID, db: DB, user: Staff):
    report, sub = await _report_with_access(db, report_id, user)
    return {
        "report": ReportDetail.model_validate(report),
        "submission": SubmissionOut.model_validate(sub),
        "team_name": await _team_name(db, sub),
        "members": [UserBrief.model_validate(m) for m in await _members(db, sub)],
    }


@router.patch("/reports/{report_id}", response_model=ReportDetail)
async def review_report(report_id: uuid.UUID, body: ReportUpdate, db: DB, user: Staff):
    report, _ = await _report_with_access(db, report_id, user)
    if body.judge_notes is not None:
        report.judge_notes = body.judge_notes
    if body.status is not None:
        if body.status not in (ReportStatus.REVIEWED, ReportStatus.COMPLETE) or report.status == ReportStatus.FAILED:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only completed reports can be marked reviewed")
        report.status = body.status
    await db.commit()
    await db.refresh(report)
    return report


@router.get("/reports/{report_id}/telemetry/{user_id}")
async def member_telemetry(report_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: Staff):
    _, sub = await _report_with_access(db, report_id, user)
    if user_id not in {m.id for m in await _members(db, sub)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this submission")
    hk = await get_hackathon(db, sub.hackathon_id)
    return await telemetry.member_timeline(get_mongo_db(), hk.id, user_id, hk.start_date, hk.end_date)


@router.get("/hackathons/{hackathon_id}/my-report", response_model=ReportDetail | None)
async def my_report(hackathon_id: uuid.UUID, db: DB, user: Participant):
    """Participants see their own team's report (whitebook DFD: 'Originality Report (Own Submissions)')."""
    team_id = await db.scalar(select(TeamMember.team_id).where(TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == user.id))
    q = select(Submission).where(Submission.hackathon_id == hackathon_id)
    q = q.where(Submission.team_id == team_id) if team_id else q.where(Submission.team_id.is_(None), Submission.user_id == user.id)
    sub = await db.scalar(q.options(selectinload(Submission.report)))
    if sub is None or sub.report is None or sub.report.status not in (ReportStatus.COMPLETE, ReportStatus.REVIEWED):
        return None
    out = ReportDetail.model_validate(sub.report)
    out.judge_notes = None  # judges' notes are internal
    return out
