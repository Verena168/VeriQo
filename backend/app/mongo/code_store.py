"""Code fingerprints in MongoDB.

code_sources: one doc per analysed repo (a submission or a reference repo), keyed by its Postgres id.
code_files:   one doc per source file with its winnowed fingerprints; split out of code_sources so
              a large repository can never hit MongoDB's 16 MB document limit.
"""

import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

SOURCES, FILES = "code_sources", "code_files"


async def ensure_indexes(db: AsyncDatabase) -> None:
    await db[SOURCES].create_indexes([IndexModel([("hackathon_id", ASCENDING), ("kind", ASCENDING)])])
    await db[FILES].create_indexes([IndexModel([("source_id", ASCENDING)])])


async def save_analysis(db: AsyncDatabase, source_id: uuid.UUID, hackathon_id: uuid.UUID, kind: str, label: str, analysis: dict) -> None:
    await db[FILES].delete_many({"source_id": source_id})
    files = analysis["files"]
    if files:
        await db[FILES].insert_many([{"source_id": source_id, **f} for f in files])
    meta = {k: v for k, v in analysis.items() if k != "files"}
    await db[SOURCES].replace_one(
        {"_id": source_id},
        {"_id": source_id, "hackathon_id": hackathon_id, "kind": kind, "label": label,
         "n_files": len(files), "analyzed_at": datetime.now(timezone.utc), **meta},
        upsert=True,
    )


async def get_source(db: AsyncDatabase, source_id: uuid.UUID) -> dict | None:
    return await db[SOURCES].find_one({"_id": source_id})


async def load_files(db: AsyncDatabase, source_id: uuid.UUID) -> list[dict]:
    return [
        {k: d[k] for k in ("path", "family", "n_tokens", "n_lines", "fps", "ast")}
        async for d in db[FILES].find({"source_id": source_id})
    ]


async def load_corpus(db: AsyncDatabase, hackathon_id: uuid.UUID, exclude: uuid.UUID) -> list[dict]:
    corpus = []
    async for src in db[SOURCES].find({"hackathon_id": hackathon_id, "_id": {"$ne": exclude}}):
        corpus.append({
            "source_id": str(src["_id"]), "label": src["label"], "kind": src["kind"],
            "files": await load_files(db, src["_id"]),
        })
    return corpus


async def delete_source(db: AsyncDatabase, source_id: uuid.UUID) -> None:
    await db[FILES].delete_many({"source_id": source_id})
    await db[SOURCES].delete_one({"_id": source_id})
