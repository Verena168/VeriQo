import uuid
from datetime import datetime, timezone

import pytest

from app.main import app as fastapi_app
from app.models import Application, Hackathon
from app.models.application import ApplicationStatus
from app.services.visibility import UNDER_REVIEW_MESSAGE, participant_state, participant_view

SCORE_FIELDS = {"score", "match_details", "team_fit_score", "ai_breakdown", "stage1_score"}
NOW = datetime.now(timezone.utc)


def application(status, published=False, score=72.5):
    return Application(id=uuid.uuid4(), hackathon_id=uuid.uuid4(), user_id=uuid.uuid4(), status=status, score=score,
                       match_details=[{"skill": "Python"}], resume_filename="cv.pdf", cv_file_id="a" * 24,
                       applied_at=NOW, decision_published_at=NOW if published else None)


@pytest.mark.parametrize("status,published,expected", [
    (ApplicationStatus.SHORTLISTED, False, "under_review"),  # AI/organizer decided, not published yet
    (ApplicationStatus.REJECTED, False, "under_review"),
    (ApplicationStatus.NEEDS_REVIEW, False, "under_review"),
    (ApplicationStatus.PENDING, False, "under_review"),
    (ApplicationStatus.SHORTLISTED, True, "shortlisted"),
    (ApplicationStatus.REJECTED, True, "rejected"),
    (ApplicationStatus.NEEDS_REVIEW, True, "under_review"),  # an undecided application never "publishes"
])
def test_participant_state(status, published, expected):
    assert participant_state(application(status, published)) == expected


def test_unpublished_view_reveals_nothing():
    view = participant_view(application(ApplicationStatus.SHORTLISTED), Hackathon(is_score_published=True))
    assert view.state == "under_review" and view.status_message == UNDER_REVIEW_MESSAGE
    assert view.published_at is None and view.feedback is None  # even with score sharing on
    assert not SCORE_FIELDS & set(view.model_dump())


def test_score_shared_only_when_opted_in_and_published():
    published = application(ApplicationStatus.REJECTED, published=True)
    assert participant_view(published, Hackathon(is_score_published=False)).feedback is None
    shared = participant_view(published, Hackathon(is_score_published=True)).feedback
    assert shared == {"score": 72.5, "breakdown": [{"skill": "Python"}]}


def _schema_fields(openapi: dict, schema: dict, seen=None) -> set[str]:
    """Every property name reachable from a response schema (follows $ref, arrays, unions)."""
    seen = seen if seen is not None else set()
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return set()
        seen.add(name)
        return _schema_fields(openapi, openapi["components"]["schemas"][name], seen)
    fields = set()
    for key, sub in schema.get("properties", {}).items():
        fields.add(key)
        fields |= _schema_fields(openapi, sub, seen)
    for k in ("items", "additionalProperties"):
        if isinstance(schema.get(k), dict):
            fields |= _schema_fields(openapi, schema[k], seen)
    for k in ("anyOf", "allOf", "oneOf"):
        for sub in schema.get(k, []):
            fields |= _schema_fields(openapi, sub, seen)
    return fields


PARTICIPANT_ROUTES = [
    ("post", "/api/v1/hackathons/{hackathon_id}/applications"),
    ("get", "/api/v1/applications/mine"),
    ("put", "/api/v1/applications/{application_id}/pitch-deck"),
]


@pytest.mark.parametrize("method,path", PARTICIPANT_ROUTES)
def test_participant_routes_cannot_return_scores(method, path):
    openapi = fastapi_app.openapi()
    responses = openapi["paths"][path][method]["responses"]
    ok = next(r for code, r in responses.items() if code.startswith("2"))
    schema = ok["content"]["application/json"]["schema"]
    leaked = (SCORE_FIELDS & _schema_fields(openapi, schema)) - {"feedback"}
    assert not leaked, f"{method.upper()} {path} can return {leaked}"
