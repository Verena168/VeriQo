"""Integrity scan pipeline: analyse repos -> compare -> join telemetry -> Originality Report.

Runs as a FastAPI background task, so it opens its own DB session. Hackathon-wide scans are two
phases (analyse everything, then compare everything) because each submission is compared
against all the others.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import Hackathon, OriginalityReport, ReferenceRepo, Submission, TeamMember, User
from app.models.report import ReportStatus
from app.models.submission import SubmissionStatus
from app.mongo import code_store, telemetry
from app.mongo.client import get_mongo_db
from app.services import intelligence_client as intel
from app.services.risk import assess
from app.services.telemetry_scoring import suspicion, team_flag

log = logging.getLogger("uvicorn.error")
MAX_STORED_MATCHES = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _analyze_submission(db: AsyncSession, sub: Submission, hk: Hackathon) -> None:
    mdb = get_mongo_db()
    existing = await code_store.get_source(mdb, sub.id)
    # After the deadline the pinned commit can't change, so a finished analysis can be reused.
    if sub.commit_sha and _now() > hk.end_date and existing and existing.get("commit_sha") == sub.commit_sha:
        return
    pinned = sub.commit_sha if _now() > hk.end_date else None
    analysis = await intel.analyze_repo(sub.repository_url, pinned, hk.start_date, hk.end_date)
    label = sub.project_title
    await code_store.save_analysis(mdb, sub.id, hk.id, "submission", label, analysis)
    sub.commit_sha = analysis["commit_sha"]
    await db.commit()


async def _members(db: AsyncSession, sub: Submission) -> list[User]:
    if sub.team_id is None:
        return [await db.get(User, sub.user_id)]
    rows = await db.execute(select(User).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == sub.team_id))
    return list(rows.scalars())


async def _build_report(db: AsyncSession, sub: Submission, hk: Hackathon) -> OriginalityReport:
    mdb = get_mongo_db()
    source = await code_store.get_source(mdb, sub.id)
    files = await code_store.load_files(mdb, sub.id)
    corpus = await code_store.load_corpus(mdb, hk.id, exclude=sub.id)
    cmp = await intel.compare(files, corpus)

    member_rows, flags = [], []
    typed = pasted = bulk = active = 0
    with_data = 0
    for user in await _members(db, sub):
        s = await telemetry.summarize_user(mdb, hk.id, user.id, hk.start_date, hk.end_date)
        flag = suspicion(s)
        flags.append(flag)
        if s["batches"]:
            with_data += 1
        typed += s["typed_chars"]
        pasted += s["pasted_chars"]
        bulk += s["bulk_insert_chars"]
        active += s["active_seconds"]
        member_rows.append({
            "user_id": str(user.id), "name": user.name, "flag": flag, "batches": s["batches"],
            "typed_chars": s["typed_chars"], "pasted_chars": s["pasted_chars"], "bulk_insert_chars": s["bulk_insert_chars"],
            "paste_count": s["paste_count"], "paste_ratio": s["paste_ratio"], "active_minutes": round(s["active_seconds"] / 60),
        })
    written = typed + pasted + bulk
    coverage = with_data / len(member_rows) if member_rows else None
    t_flag = team_flag(flags)
    pre_event = (source.get("pre_event") or {}) if source else {}
    pre_share = pre_event.get("code_share")
    after_deadline = (source or {}).get("commits_after_deadline", 0)
    risk, reasons = assess(cmp["plagiarism_score"], pre_share, t_flag, coverage, after_deadline)

    commits = (source or {}).get("commits", [])
    report = (await db.execute(select(OriginalityReport).where(OriginalityReport.submission_id == sub.id))).scalar_one_or_none()
    if report is None:
        report = OriginalityReport(submission_id=sub.id)
        db.add(report)
    report.status = ReportStatus.COMPLETE
    report.plagiarism_score = cmp["plagiarism_score"]
    report.ai_generated_prob = None  # no reliable detector for code; telemetry is used instead
    report.paste_ratio = round((pasted + bulk) / written, 4) if written else None
    report.active_minutes = round(active / 60)
    report.telemetry_coverage = round(coverage, 3) if coverage is not None else None
    report.template_share = cmp["template_share"]
    report.pre_event_share = pre_share
    report.telemetry_flag = t_flag
    report.risk_level = risk
    report.matches = [f for f in cmp["files"] if f["best_match"]][:MAX_STORED_MATCHES]
    report.details = {
        "risk_reasons": reasons,
        "top_sources": cmp["top_sources"],
        "files_compared": cmp["files_compared"],
        "files_flagged": cmp["files_flagged"],
        "decision_threshold": cmp["decision_threshold"],
        "members": member_rows,
        "commits": {
            "analysed_sha": sub.commit_sha,
            "total": len(commits),
            "before_start": pre_event.get("commits_before_start"),
            "after_deadline": after_deadline,
            "pre_event_snapshot": pre_event.get("snapshot_sha"),
            "authors": sorted({c["author"] for c in commits}),
            "first_commit_at": commits[-1]["committed_at"] if commits else None,
            "last_commit_at": commits[0]["committed_at"] if commits else None,
        },
        "languages": (source or {}).get("languages", {}),
    }
    report.generated_at = _now()
    sub.status = SubmissionStatus.SCANNED
    await db.commit()
    return report


async def _fail(db: AsyncSession, sub: Submission, message: str) -> None:
    await db.rollback()
    sub = await db.get(Submission, sub.id)
    sub.status = SubmissionStatus.SCAN_FAILED
    report = (await db.execute(select(OriginalityReport).where(OriginalityReport.submission_id == sub.id))).scalar_one_or_none()
    if report is None:
        report = OriginalityReport(submission_id=sub.id)
        db.add(report)
    report.status = ReportStatus.FAILED
    report.details = {"error": message}
    await db.commit()


async def scan_hackathon(hackathon_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        hk = await db.get(Hackathon, hackathon_id)
        subs = list((await db.execute(select(Submission).where(Submission.hackathon_id == hackathon_id))).scalars())
        for sub in subs:
            sub.status = SubmissionStatus.SCANNING
        await db.commit()

        analysed = []
        for sub in subs:
            try:
                await _analyze_submission(db, sub, hk)
                analysed.append(sub)
            except Exception as exc:  # one broken repo must not stop the whole scan
                log.warning("analysis failed for submission %s: %s", sub.id, exc)
                await _fail(db, sub, str(exc))
        for sub in analysed:
            try:
                await _build_report(db, sub, hk)
            except Exception as exc:
                log.warning("report failed for submission %s: %s", sub.id, exc)
                await _fail(db, sub, str(exc))


async def scan_submission(submission_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        sub = await db.get(Submission, submission_id)
        hk = await db.get(Hackathon, sub.hackathon_id)
        sub.status = SubmissionStatus.SCANNING
        await db.commit()
        try:
            await _analyze_submission(db, sub, hk)
            await _build_report(db, sub, hk)
        except Exception as exc:
            log.warning("scan failed for submission %s: %s", sub.id, exc)
            await _fail(db, sub, str(exc))


async def analyze_reference(reference_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        ref = await db.get(ReferenceRepo, reference_id)
        try:
            analysis = await intel.analyze_repo(ref.repo_url, None, None, None)
            await code_store.save_analysis(get_mongo_db(), ref.id, ref.hackathon_id, ref.kind.value, ref.label, analysis)
            ref.commit_sha, ref.status, ref.error = analysis["commit_sha"], "ready", None
        except Exception as exc:
            ref.status, ref.error = "failed", str(exc)[:500]
        await db.commit()
