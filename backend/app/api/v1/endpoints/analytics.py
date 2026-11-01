"""Participant "Year in Code" statistics and organizer overviews (Module D)."""

import uuid
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, Participant, Staff
from app.api.v1.endpoints.hackathons import get_owned_hackathon
from app.core.config import get_settings
from app.models import Application, Submission, Team, TeamMember
from app.models.report import ReportStatus
from app.models.team import MemberStatus, TeamStatus
from app.mongo import telemetry
from app.mongo.client import get_mongo_db
from app.services import intelligence_client as intel
from app.services.intelligence_client import IntelligenceError
from app.services.visibility import participant_state

router = APIRouter(prefix="/analytics", tags=["analytics"])
EXT_LANGUAGE = {
    "py": "Python", "js": "JavaScript", "jsx": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript", "java": "Java",
    "kt": "Kotlin", "c": "C", "h": "C", "cpp": "C++", "cc": "C++", "hpp": "C++", "cs": "C#", "go": "Go", "rs": "Rust",
    "rb": "Ruby", "php": "PHP", "swift": "Swift", "dart": "Dart", "html": "HTML", "css": "CSS", "scss": "CSS",
    "sql": "SQL", "sol": "Solidity", "ipynb": "Python", "md": "Markdown", "json": "JSON", "yml": "YAML", "yaml": "YAML",
}


@router.get("/year-in-code")
async def year_in_code(db: DB, user: Participant, year: int | None = Query(default=None, ge=2020, le=2100)):
    tz = get_settings().display_timezone
    year = year or datetime.now(ZoneInfo(tz)).year
    start = datetime(year, 1, 1, tzinfo=ZoneInfo(tz))
    end = datetime(year + 1, 1, 1, tzinfo=ZoneInfo(tz))
    act = await telemetry.user_activity(get_mongo_db(), user.id, start, end, tz)

    langs: Counter = Counter()
    for row in act["languages"]:
        langs[EXT_LANGUAGE.get(row["ext"], row["ext"].upper())] += row["chars"]

    # The applications of the teams the person is a confirmed member of, in this year.
    rows = (await db.execute(
        select(Application, Team).join(Team, Team.id == Application.team_id)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id, TeamMember.status == MemberStatus.CONFIRMED)
        .options(selectinload(Application.hackathon))
    )).all()
    rows = [(a, t) for a, t in rows if start <= a.applied_at < end]
    apps = [a for a, _ in rows]
    hackathons = []
    for a, team in rows:
        state = participant_state(a)
        # An AI-formed team assigned before results are published would reveal the decision.
        show_team = team.formed_by == "self" or state == "shortlisted"
        sub = await db.scalar(select(Submission).where(Submission.hackathon_id == a.hackathon_id, Submission.team_id == team.id)
                              .options(selectinload(Submission.report))) if state == "shortlisted" else None
        rep = sub.report if sub and sub.report and sub.report.status in (ReportStatus.COMPLETE, ReportStatus.REVIEWED) else None
        hackathons.append({
            "hackathon_id": str(a.hackathon_id), "event_name": a.hackathon.event_name, "start_date": a.hackathon.start_date,
            # Participant view: published state only, never the AI score.
            "application_status": state, "team_name": team.team_name if show_team else None,
            "project_title": sub.project_title if sub else None,
            "risk_level": rep.risk_level.value if rep and rep.risk_level else None,
            # "Verified" = the integrity scan found no concerns, so the stats can be trusted on a portfolio.
            "verified": bool(rep and rep.risk_level and rep.risk_level.value == "green"),
        })

    total_active = sum(d["active_minutes"] for d in act["daily"])
    typed = sum(d["typed"] for d in act["daily"])
    pasted = sum(d["pasted"] + d["bulk"] for d in act["daily"])
    monthly = Counter()
    for d in act["daily"]:
        monthly[d["date"][:7]] += d["active_minutes"]
    streak = best = 0
    prev = None
    for d in act["daily"]:
        day = datetime.fromisoformat(d["date"]).date()
        streak = streak + 1 if prev and (day - prev).days == 1 else 1
        best, prev = max(best, streak), day
    skills = (user.parsed_skills or {}).get("skills") or []
    cat_counts = Counter(s["category"] for s in skills)

    return {
        "year": year,
        "user": {"name": user.name, "github_url": user.github_url},
        "totals": {
            "active_hours": round(total_active / 60, 1),
            "active_days": len(act["daily"]),
            "longest_streak_days": best,
            "sessions": act["sessions"],
            "typed_chars": typed,
            "pasted_or_inserted_chars": pasted,
            "typed_share": round(typed / (typed + pasted), 3) if typed + pasted else None,
            "hackathons": len(apps),
            "shortlisted": sum(participant_state(a) == "shortlisted" for a in apps),
            "submissions": sum(h["project_title"] is not None for h in hackathons),
            "verified_projects": sum(h["verified"] for h in hackathons),
        },
        "daily": act["daily"],
        "monthly": [{"month": m, "active_hours": round(v / 60, 1)} for m, v in sorted(monthly.items())],
        "hours": act["hours"],
        "languages": [{"language": k, "chars": v} for k, v in langs.most_common(8)],
        "skills": skills[:20],
        "skill_categories": [{"category": k, "count": v} for k, v in cat_counts.most_common()],
        "hackathons": sorted(hackathons, key=lambda h: h["start_date"], reverse=True),
    }


@router.get("/hackathons/{hackathon_id}")
async def hackathon_overview(hackathon_id: uuid.UUID, db: DB, user: Staff):
    hk = await get_owned_hackathon(db, hackathon_id, user)
    # Only live registrations: merged (AI) and draft teams are not separate entries.
    apps = list(await db.scalars(select(Application).join(Team, Team.id == Application.team_id)
                                 .where(Application.hackathon_id == hk.id, Team.status == TeamStatus.SUBMITTED)))
    subs = list(await db.scalars(select(Submission).where(Submission.hackathon_id == hk.id).options(selectinload(Submission.report))))
    teams = len(apps)
    drafts = len(list(await db.scalars(select(Team.id).where(Team.hackathon_id == hk.id, Team.status == TeamStatus.DRAFT))))
    buckets = Counter(min(int(a.score // 10) * 10, 90) for a in apps if a.score is not None)
    risk = Counter(s.report.risk_level.value for s in subs if s.report and s.report.risk_level)
    return {
        "applications": len(apps),
        "by_status": dict(Counter(a.status.value for a in apps)),
        "score_histogram": [{"bucket": f"{b}-{b + 10}", "count": buckets.get(b, 0)} for b in range(0, 100, 10)],
        "teams": teams,
        "draft_registrations": drafts,
        "submissions": len(subs),
        "scanned": sum(1 for s in subs if s.report and s.report.status in (ReportStatus.COMPLETE, ReportStatus.REVIEWED)),
        "risk": {k: risk.get(k, 0) for k in ("green", "amber", "red")},
    }


@router.get("/meta/skills")
async def skills_catalog(user: CurrentUser):
    try:
        return await intel.skills_catalog()
    except IntelligenceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/meta/clone-model")
async def clone_model(user: CurrentUser):
    try:
        return await intel.clone_model_info()
    except IntelligenceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
