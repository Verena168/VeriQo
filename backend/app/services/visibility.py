"""What participants are allowed to see about their own application.

The organizer's decision (Application.status, first suggested by the AI) is a draft until results
are published. Before that, participants see only "under review", and nothing that would reveal
the decision indirectly (team assignment, submission access, telemetry). Scores are never shown,
unless the organizer opts in with Hackathon.is_score_published, and then only after publishing.
"""

from sqlalchemy import and_

from app.models import Application, Hackathon
from app.models.application import ApplicationStatus
from app.schemas import ParticipantApplicationOut

UNDER_REVIEW_MESSAGE = (
    "Successfully registered. Your application is under review, "
    "and you will be notified of your shortlisting status soon."
)
STATE_MESSAGES = {
    "shortlisted": "Congratulations! Your team has been shortlisted.",
    "rejected": "Thank you for registering. Your team was not shortlisted this time.",
}

# Use in queries wherever a participant's access depends on being shortlisted.
published_shortlisted = and_(
    Application.status == ApplicationStatus.SHORTLISTED,
    Application.decision_published_at.is_not(None),
)


def participant_state(app: Application) -> str:
    if app.decision_published_at is not None and app.status in (ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED):
        return app.status.value
    return "under_review"  # pending, needs_review, and every unpublished decision


def is_published_shortlisted(app: Application | None) -> bool:
    return app is not None and participant_state(app) == "shortlisted"


def participant_view(app: Application, hk: Hackathon, team_name: str) -> ParticipantApplicationOut:
    state = participant_state(app)
    feedback = None
    if hk.is_score_published and state != "under_review":
        feedback = {"score": app.score, "breakdown": app.match_details}
    return ParticipantApplicationOut(
        id=app.id,
        hackathon_id=app.hackathon_id,
        team_id=app.team_id,
        team_name=team_name,
        state=state,
        status_message=STATE_MESSAGES.get(state, UNDER_REVIEW_MESSAGE),
        has_pitch_deck=bool(app.pitch_deck_file_id),
        applied_at=app.applied_at,
        published_at=app.decision_published_at if state != "under_review" else None,
        feedback=feedback,
    )
