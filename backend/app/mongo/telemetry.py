"""TELEMETRY_LOG collection (MongoDB).

The VS Code extension buffers events locally and flushes one *batch* every ~30 s. Each batch
becomes one document, which keeps write volume low with hundreds of concurrent participants
and makes retries safe: the client-generated ``batch_id`` has a unique index, so a re-sent
batch is rejected as a duplicate instead of being double-counted.

Privacy: only counts, sizes and timestamps are stored, never the text that was typed or pasted.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

COLLECTION = "telemetry_logs"

# A single insertion at least this large is recorded as an individual paste event.
LARGE_PASTE_CHARS = 200
_EXT_RE = re.compile(r"^[a-z0-9]{1,10}$")


class PasteEvent(BaseModel):
    ts: datetime
    chars: int = Field(ge=0)
    lines: int = Field(ge=0)
    file_ext: str | None = Field(default=None, max_length=16, pattern=r"^\.?[A-Za-z0-9]{1,10}$")  # never the full path
    # "clipboard": the extension's paste command fired; "bulk_insert": a large insertion
    # with no paste command (likely an inline AI completion or a refactor).
    source: Literal["clipboard", "bulk_insert"] = "clipboard"


class TelemetryMetrics(BaseModel):
    typed_chars: int = Field(default=0, ge=0)
    pasted_chars: int = Field(default=0, ge=0)
    paste_count: int = Field(default=0, ge=0)
    deleted_chars: int = Field(default=0, ge=0)
    active_seconds: int = Field(default=0, ge=0, le=3600)  # editor focused and edited within idle timeout
    # Large insertions with no paste command: usually inline AI completions or generated code.
    bulk_insert_chars: int = Field(default=0, ge=0)
    ai_completion_accepts: int = Field(default=0, ge=0)  # best-effort, see PasteEvent.source
    # Typed characters per file extension without the dot ({"py": 1200, "tsx": 300}) for language stats.
    chars_by_ext: dict[str, int] = Field(default_factory=dict, max_length=50)

    @field_validator("chars_by_ext")
    @classmethod
    def _ext_keys(cls, v: dict[str, int]) -> dict[str, int]:
        if any(not _EXT_RE.match(k) or n < 0 for k, n in v.items()):
            raise ValueError("chars_by_ext keys must be short lowercase extensions without a dot")
        return v


class TelemetryBatchIn(BaseModel):
    """Request body the extension POSTs to /api/v1/telemetry."""

    batch_id: uuid.UUID
    session_id: uuid.UUID  # one per VS Code window session
    hackathon_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    metrics: TelemetryMetrics
    paste_events: list[PasteEvent] = Field(default_factory=list, max_length=500)
    extension_version: str = Field(max_length=32)

    @model_validator(mode="after")
    def _window_is_ordered(self):
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        return self


class TelemetryLogDocument(TelemetryBatchIn):
    """What is stored. user_id comes from the auth token, never from the request body."""

    user_id: uuid.UUID
    submission_id: uuid.UUID | None = None  # back-filled when the team submits
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


INDEXES = [
    IndexModel([("batch_id", ASCENDING)], unique=True),
    # Serves the suspicion-scoring query: one user's logs within one hackathon, by time.
    IndexModel([("hackathon_id", ASCENDING), ("user_id", ASCENDING), ("window_end", ASCENDING)]),
    IndexModel([("submission_id", ASCENDING)], sparse=True),
]


async def ensure_indexes(db: AsyncDatabase) -> None:
    await db[COLLECTION].create_indexes(INDEXES)


async def insert_batch(db: AsyncDatabase, doc: TelemetryLogDocument) -> bool:
    """Store a batch. Returns False if this batch_id was already stored (client retry)."""
    try:
        await db[COLLECTION].insert_one(doc.model_dump())
    except DuplicateKeyError:
        return False
    return True


async def summarize_user(
    db: AsyncDatabase, hackathon_id: uuid.UUID, user_id: uuid.UUID,
    start: datetime, end: datetime,
) -> dict:
    """Totals for whitebook Algorithm 2 (Telemetry Suspicion Scoring) over the event window."""
    pipeline = [
        {"$match": {
            "hackathon_id": hackathon_id,
            "user_id": user_id,
            "window_end": {"$gte": start, "$lte": end},
        }},
        {"$group": {
            "_id": None,
            "typed_chars": {"$sum": "$metrics.typed_chars"},
            "pasted_chars": {"$sum": "$metrics.pasted_chars"},
            "paste_count": {"$sum": "$metrics.paste_count"},
            "bulk_insert_chars": {"$sum": "$metrics.bulk_insert_chars"},
            "active_seconds": {"$sum": "$metrics.active_seconds"},
            "batches": {"$sum": 1},
        }},
    ]
    rows = await (await db[COLLECTION].aggregate(pipeline)).to_list(1)
    totals = rows[0] if rows else {
        "typed_chars": 0, "pasted_chars": 0, "paste_count": 0, "bulk_insert_chars": 0, "active_seconds": 0, "batches": 0,
    }
    totals.pop("_id", None)
    # Bulk inserts (likely AI completions) count as "not typed" alongside pastes.
    written = totals["typed_chars"] + totals["pasted_chars"] + totals["bulk_insert_chars"]
    totals["paste_ratio"] = (totals["pasted_chars"] + totals["bulk_insert_chars"]) / written if written else None
    return totals


async def member_timeline(
    db: AsyncDatabase, hackathon_id: uuid.UUID, user_id: uuid.UUID, start: datetime, end: datetime, bucket_minutes: int = 30,
) -> dict:
    """Typed vs pasted characters per time bucket, plus the individual large paste events."""
    match = {"hackathon_id": hackathon_id, "user_id": user_id, "window_end": {"$gte": start, "$lte": end}}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$window_end", "unit": "minute", "binSize": bucket_minutes}},
            "typed": {"$sum": "$metrics.typed_chars"},
            "pasted": {"$sum": "$metrics.pasted_chars"},
            "bulk": {"$sum": "$metrics.bulk_insert_chars"},
            "active_seconds": {"$sum": "$metrics.active_seconds"},
        }},
        {"$sort": {"_id": 1}},
    ]
    buckets = [
        {"t": r["_id"], "typed": r["typed"], "pasted": r["pasted"], "bulk": r["bulk"], "active_minutes": round(r["active_seconds"] / 60, 1)}
        async for r in await db[COLLECTION].aggregate(pipeline)
    ]
    events = []
    async for d in db[COLLECTION].find(match, {"paste_events": 1}).sort("window_end", 1):
        events.extend(d.get("paste_events", []))
    events.sort(key=lambda e: e["ts"])
    return {"buckets": buckets, "paste_events": events[-500:]}


async def user_activity(db: AsyncDatabase, user_id: uuid.UUID, start: datetime, end: datetime, tz: str) -> dict:
    """Per-day activity and per-language typing for the Year in Code profile."""
    match = {"$match": {"user_id": user_id, "window_end": {"$gte": start, "$lt": end}}}
    daily = [
        {"date": r["_id"], "active_minutes": round(r["active"] / 60), "typed": r["typed"], "pasted": r["pasted"], "bulk": r["bulk"]}
        async for r in await db[COLLECTION].aggregate([
            match,
            {"$group": {
                "_id": {"$dateToString": {"date": "$window_end", "format": "%Y-%m-%d", "timezone": tz}},
                "active": {"$sum": "$metrics.active_seconds"},
                "typed": {"$sum": "$metrics.typed_chars"},
                "pasted": {"$sum": "$metrics.pasted_chars"},
                "bulk": {"$sum": "$metrics.bulk_insert_chars"},
            }},
            {"$sort": {"_id": 1}},
        ])
    ]
    langs = [
        {"ext": r["_id"], "chars": r["chars"]}
        async for r in await db[COLLECTION].aggregate([
            match,
            {"$project": {"kv": {"$objectToArray": {"$ifNull": ["$metrics.chars_by_ext", {}]}}}},
            {"$unwind": "$kv"},
            {"$group": {"_id": "$kv.k", "chars": {"$sum": "$kv.v"}}},
            {"$sort": {"chars": -1}},
        ])
    ]
    hours = [
        {"hour": r["_id"], "active_minutes": round(r["active"] / 60)}
        async for r in await db[COLLECTION].aggregate([
            match,
            {"$group": {"_id": {"$hour": {"date": "$window_end", "timezone": tz}}, "active": {"$sum": "$metrics.active_seconds"}}},
            {"$sort": {"_id": 1}},
        ])
    ]
    sessions = len(await db[COLLECTION].distinct("session_id", match["$match"]))
    return {"daily": daily, "languages": langs, "hours": hours, "sessions": sessions}
