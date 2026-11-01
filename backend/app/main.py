import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import engine
from app.mongo import code_store, telemetry
from app.mongo.client import close_client, get_mongo_db
from app.services import email
from app.services.intelligence_client import IntelligenceError

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Don't refuse to boot when a database is down; /health reports it instead.
    try:
        await telemetry.ensure_indexes(get_mongo_db())
        await code_store.ensure_indexes(get_mongo_db())
    except PyMongoError as exc:
        log.warning("MongoDB unreachable, telemetry indexes not created: %s", type(exc).__name__)
    stop = asyncio.Event()
    sender = asyncio.create_task(email.run_sender(stop), name="email-sender")
    yield
    stop.set()
    await sender
    await close_client()
    await engine.dispose()


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(IntelligenceError)
async def intelligence_error(_: Request, exc: IntelligenceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict:
    checks = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except (SQLAlchemyError, OSError):
        checks["postgres"] = "unreachable"
    try:
        await get_mongo_db().command("ping")
        checks["mongo"] = "ok"
    except PyMongoError:
        checks["mongo"] = "unreachable"
    return {"status": "ok" if all(v == "ok" for v in checks.values()) else "degraded", **checks}
