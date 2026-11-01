"""Batch ingestion from the VS Code extension (Module B)."""

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import DB, Participant
from app.api.v1.endpoints.hackathons import get_hackathon
from app.models import Application
from app.models.application import ApplicationStatus
from app.mongo import telemetry
from app.mongo.client import get_mongo_db
from app.services.telemetry_scoring import suspicion

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest(body: telemetry.TelemetryBatchIn, db: DB, user: Participant, response: Response):
    allowed = await db.scalar(select(Application.id).where(
        Application.hackathon_id == body.hackathon_id, Application.user_id == user.id,
        Application.status == ApplicationStatus.SHORTLISTED,
    ))
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a shortlisted participant of this hackathon")
    doc = telemetry.TelemetryLogDocument(**body.model_dump(), user_id=user.id)
    if not await telemetry.insert_batch(get_mongo_db(), doc):
        response.status_code = status.HTTP_200_OK  # duplicate batch from a client retry: already stored
        return {"stored": False, "duplicate": True}
    return {"stored": True}


@router.get("/summary")
async def my_summary(hackathon_id: uuid.UUID, db: DB, user: Participant):
    """What the extension's status view shows: the participant's own totals for this event."""
    hk = await get_hackathon(db, hackathon_id)
    s = await telemetry.summarize_user(get_mongo_db(), hk.id, user.id, hk.start_date, hk.end_date)
    return {**s, "flag": suspicion(s)}
