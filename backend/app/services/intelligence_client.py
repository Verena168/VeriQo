"""HTTP client for the Intelligence Layer.

The API never imports NLP/AST code directly. Heavy work runs in the separate service so a
slow resume parse or repository scan cannot block web requests.
"""

from datetime import datetime

import httpx

from app.core.config import get_settings


class IntelligenceError(RuntimeError):
    def __init__(self, message: str, code: str = "intelligence_error", status: int = 502):
        super().__init__(message)
        self.code, self.status = code, status


def intelligence_client(timeout: float = 300.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=get_settings().intelligence_url, timeout=timeout)


async def _call(method: str, path: str, timeout: float = 300.0, **kwargs) -> dict:
    try:
        async with intelligence_client(timeout) as c:
            r = await c.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise IntelligenceError(f"intelligence service unreachable: {type(exc).__name__}") from exc
    if r.status_code == 422 and isinstance(r.json().get("detail"), dict):
        d = r.json()["detail"]
        raise IntelligenceError(d.get("message", "invalid input"), d.get("code", "invalid"), 422)
    if r.status_code >= 400:
        raise IntelligenceError(f"intelligence service error {r.status_code}: {r.text[:200]}")
    return r.json()


async def parse_resume(filename: str, data: bytes, content_type: str | None) -> dict:
    return await _call("POST", "/resume/parse", timeout=60, files={"file": (filename, data, content_type or "application/octet-stream")})


async def github_profile(url: str) -> dict:
    return await _call("POST", "/github/profile", timeout=30, json={"url": url})


async def match(candidate_skills: list[str], requirements: list[dict]) -> dict:
    return await _call("POST", "/match", timeout=120, json={"candidate_skills": candidate_skills, "requirements": requirements})


async def form_teams(participants: list[dict], requirements: list[dict], team_size: int) -> dict:
    return await _call("POST", "/teams/form", timeout=60, json={"participants": participants, "requirements": requirements, "team_size": team_size})


async def analyze_repo(repo_url: str, commit_sha: str | None, event_start: datetime | None, deadline: datetime | None) -> dict:
    body = {
        "repo_url": repo_url, "commit_sha": commit_sha,
        "event_start": event_start.isoformat() if event_start else None,
        "deadline": deadline.isoformat() if deadline else None,
    }
    return await _call("POST", "/code/analyze", timeout=600, json=body)


async def compare(files: list[dict], corpus: list[dict]) -> dict:
    return await _call("POST", "/code/compare", timeout=600, json={"files": files, "corpus": corpus})


async def skills_catalog() -> dict:
    return await _call("GET", "/skills", timeout=10)


async def clone_model_info() -> dict:
    return await _call("GET", "/models/clone-classifier", timeout=10)
