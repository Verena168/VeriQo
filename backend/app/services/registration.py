"""Team registration rules and team scoring (docs/STAGE1_DESIGN.md §3.2, §3.6)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Hackathon, Team, TeamMemberArtifact, User
from app.models.application import ApplicationStatus
from app.models.hackathon import ParticipationMode
from app.models.team import MemberStatus, TeamStatus
from app.mongo import files
from app.services import intelligence_client as intel
from app.services.eligibility import person_violations, registration_problem
from app.services.intelligence_client import IntelligenceError

PARSE_OK = "ok"
PARSE_UNREADABLE = "unreadable"  # CV has no extractable text: allowed, but the team goes to manual review
PARSE_FAILED = "failed"          # analysis service error: the member must re-upload


def checklist(team: Team, hk: Hackathon, now: datetime | None = None) -> list[str]:
    """Everything that still blocks submitting this registration (empty list = ready).

    `team` must have members (with users) and artifacts loaded.
    """
    if team.status != TeamStatus.DRAFT:
        return []
    items = []
    if closed := registration_problem(hk, now):
        items.append(closed)
    confirmed = [m for m in team.members if m.status == MemberStatus.CONFIRMED]
    pending = [m for m in team.members if m.status == MemberStatus.INVITED]
    for m in pending:
        items.append(f"{m.user.name} hasn't confirmed the invitation yet (or remove them).")
    size = len(confirmed)
    solo_seeker = team.seeking_teammates and size == 1 and hk.participation_mode == ParticipationMode.TEAM
    if size > hk.max_team_size:
        items.append(f"Too many members: the maximum is {hk.max_team_size}.")
    elif size < hk.min_team_size and not solo_seeker:
        items.append(f"Add members: teams need at least {hk.min_team_size} confirmed members (you have {size}).")
    artifacts = {a.user_id: a for a in team.artifacts}
    for m in confirmed:
        a = artifacts.get(m.user_id)
        who = "Your" if m.is_lead else f"{m.user.name}'s"
        if a is None or not a.cv_file_id:
            items.append(f"{who} CV is missing.")
        elif a.parse_status == PARSE_FAILED:
            items.append(f"{who} CV couldn't be analysed; please upload it again.")
        if a is None or not a.github_url:
            items.append(f"{who} GitHub profile link is missing.")
        for problem in person_violations(m.user, hk):
            items.append(f"{m.user.name}: {problem}")
    return items


async def analyse_member(artifact: TeamMemberArtifact, cv_name: str | None, cv_data: bytes | None) -> None:
    """Parse a newly uploaded CV (if any) and re-read the GitHub profile; record the outcome.

    cv_data=None means only the GitHub link changed: the earlier CV analysis is kept.
    """
    previous = artifact.parsed_profile or {}
    resume, notes = previous.get("resume"), []
    if cv_data is not None:
        resume = None
        try:
            resume = await intel.parse_resume(cv_name or "cv.pdf", cv_data, None)
            artifact.parse_status = PARSE_OK
        except IntelligenceError as exc:
            if exc.code != "unreadable_resume":  # service down/timeout: ask for a retry, keep nothing stale
                artifact.parse_status = PARSE_FAILED
                artifact.parse_note = f"Analysis service unavailable: {exc}"[:500]
                artifact.parsed_profile = {"resume": None, "github": previous.get("github")}
                return
            artifact.parse_status = PARSE_UNREADABLE
            notes.append(f"CV could not be read: {exc}")
    elif artifact.parse_status == PARSE_UNREADABLE:
        notes.append("CV could not be read")
    github = None
    if artifact.github_url:
        try:
            github = await intel.github_profile(artifact.github_url)
        except IntelligenceError as exc:
            notes.append(f"GitHub: {exc}")
    artifact.parse_note = "; ".join(notes)[:500] or None
    artifact.parsed_profile = {"resume": resume, "github": github}


def member_skills(artifact: TeamMemberArtifact | None) -> list[dict]:
    if not artifact or not artifact.parsed_profile:
        return []
    p = artifact.parsed_profile
    if "skills" in p:  # migrated from the per-person flow: merged resume + GitHub skills
        return p.get("skills") or []
    return [*((p.get("resume") or {}).get("skills") or []), *((p.get("github") or {}).get("skills") or [])]


async def score_and_submit(db: AsyncSession, team: Team, hk: Hackathon, lead: User) -> Application:
    """Pool every confirmed member's skills, score the TEAM against the requirements, and
    create its application. The AI decision is only a suggestion until the organizer publishes."""
    confirmed = [m for m in team.members if m.status == MemberStatus.CONFIRMED]
    artifacts = {a.user_id: a for a in team.artifacts}
    pooled = sorted({s["name"] for m in confirmed for s in member_skills(artifacts.get(m.user_id))})
    requirements = [{"skill": r.skill, "weight": r.priority} for r in hk.requirements]
    unreadable = [m.user.name for m in confirmed if artifacts[m.user_id].parse_status == PARSE_UNREADABLE]

    score, breakdown = None, None
    if requirements:
        result = await intel.match(pooled, requirements)
        score, breakdown = result["score"], result["breakdown"]
    if unreadable:
        status, note = ApplicationStatus.NEEDS_REVIEW, f"Unreadable CV(s): {', '.join(unreadable)}"
    elif not requirements:
        status, note = ApplicationStatus.SHORTLISTED, None
    else:
        status, note = (ApplicationStatus.SHORTLISTED if score >= hk.shortlist_threshold else ApplicationStatus.REJECTED), None

    now = datetime.now(timezone.utc)
    app = Application(id=uuid.uuid4(), hackathon_id=hk.id, team_id=team.id, submitted_by=lead.id, status=status,
                      score=score, match_details=breakdown, review_note=note, applied_at=now)
    db.add(app)
    team.status, team.submitted_at = TeamStatus.SUBMITTED, now
    return app


async def delete_artifact_files(team: Team) -> None:
    for a in team.artifacts:
        await files.delete(a.cv_file_id)
