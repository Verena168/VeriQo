import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veriqo.intelligence")


def _warm_up() -> None:
    """Load the heavy models once in the background, so the first real request is fast.

    Without this, the first resume match after a restart paid for the PyTorch import and the
    MiniLM load (well over a minute on this machine) and the API's call timed out.
    """
    t = time.perf_counter()
    from app.nlp import resume_parser, skill_matcher

    resume_parser.extract_skills("Python React Docker")
    skill_matcher.match(["Python"], [{"skill": "Machine Learning", "weight": 1}])
    log.info("Models warmed up in %.1fs (embedding model loaded: %s)", time.perf_counter() - t, skill_matcher.model_ready())


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_up, name="model-warmup", daemon=True).start()
    yield


app = FastAPI(title="VERIQO Intelligence Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    from app.nlp.skill_matcher import model_ready

    return {"status": "ok", "embedding_model_loaded": model_ready()}
