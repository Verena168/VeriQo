"""Derive language/framework signals from a public GitHub profile via the REST API (Module A)."""

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.nlp.taxonomy import SKILLS, canonicalize

_PROFILE_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/?$", re.I)


class GitHubError(ValueError):
    pass


def username_from_url(url: str) -> str:
    m = _PROFILE_RE.match(url.strip())
    if not m:
        raise GitHubError("expected a profile URL like https://github.com/<username>")
    return m.group(1)


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = get_settings().github_token
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def fetch_profile(url: str) -> dict:
    username = username_from_url(url)
    async with httpx.AsyncClient(base_url="https://api.github.com", headers=_headers(), timeout=20) as gh:
        user = await gh.get(f"/users/{username}")
        if user.status_code == 404:
            raise GitHubError(f"GitHub user '{username}' not found")
        if user.status_code == 403:
            raise GitHubError("GitHub API rate limit reached; set GITHUB_TOKEN for the intelligence service")
        user.raise_for_status()
        repos = await gh.get(f"/users/{username}/repos", params={"per_page": 100, "sort": "pushed", "type": "owner"})
        repos.raise_for_status()

    owned = [r for r in repos.json() if not r.get("fork")]
    languages = Counter(r["language"] for r in owned if r.get("language"))
    topics = Counter(t for r in owned for t in r.get("topics") or [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    recent = sum(1 for r in owned if r.get("pushed_at") and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) > cutoff)

    skills: Counter = Counter()
    for name, n in (languages + topics).items():
        canon = canonicalize(name) or canonicalize(name.replace("-", " "))
        if canon:
            skills[canon] += n
    created = datetime.fromisoformat(user.json()["created_at"].replace("Z", "+00:00"))
    return {
        "username": username,
        "public_repos": len(owned),
        "followers": user.json().get("followers", 0),
        "account_age_years": round((datetime.now(timezone.utc) - created).days / 365.25, 1),
        "recently_active_repos": recent,
        "languages": dict(languages.most_common()),
        "skills": [
            {"name": s, "category": SKILLS[s][0], "mentions": n, "source": "github"}
            for s, n in skills.most_common()
        ],
    }
