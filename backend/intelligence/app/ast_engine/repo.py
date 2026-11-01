"""Clone a submitted GitHub repository and fingerprint it (Module C)."""

import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from app.ast_engine.fingerprint import FileFingerprint, fingerprint_source
from app.ast_engine.languages import language_for
from app.core.config import get_settings

# Only public GitHub over HTTPS: rejects file://, ssh, ext:: and other git transports.
REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", "venv", ".venv", "env",
    "__pycache__", "vendor", "third_party", "site-packages", "coverage", ".idea", ".vscode", "target", "bin", "obj",
}
MAX_FILE_BYTES = 300_000


class RepoError(ValueError):
    pass


def parse_repo_url(url: str) -> tuple[str, str]:
    m = REPO_RE.match(url.strip())
    if not m:
        raise RepoError("repository must be a public GitHub URL like https://github.com/owner/repo")
    return m.group(1), m.group(2)


def _git(args: list[str], cwd: Path | None = None, timeout: int = 60, binary: bool = False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    res = subprocess.run(
        ["git", "-c", "core.symlinks=false", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always", *args],
        cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False,
    )
    if res.returncode != 0:
        raise RepoError(f"git {args[0]} failed: {res.stderr.decode(errors='replace').strip()[:300]}")
    return res.stdout if binary else res.stdout.decode(errors="replace")


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):  # .git objects are read-only on Windows
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onexc=onerror)


def _looks_generated(code: str) -> bool:
    lines = code.splitlines() or [""]
    return len(code) / len(lines) > 300  # minified bundles


def iter_source_files(files: dict[str, str]) -> list[FileFingerprint]:
    out = []
    for path, code in sorted(files.items()):
        if _looks_generated(code):
            continue
        fp = fingerprint_source(path, code)
        if fp:
            out.append(fp)
    return out


def read_tree(root: Path, limit: int) -> dict[str, str]:
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink() or not language_for(rel) or p.stat().st_size > MAX_FILE_BYTES:
                continue
            files[rel] = p.read_text(encoding="utf-8", errors="replace")
            if len(files) >= limit:
                return files
    return files


def _read_snapshot(repo: Path, sha: str, limit: int) -> dict[str, str]:
    data = _git(["archive", "--format=tar", sha], cwd=repo, timeout=120, binary=True)
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            parts = Path(m.name).parts
            if not m.isfile() or m.size > MAX_FILE_BYTES or not language_for(m.name) or any(x in SKIP_DIRS for x in parts):
                continue
            files[m.name] = tar.extractfile(m).read().decode("utf-8", errors="replace")
            if len(files) >= limit:
                break
    return files


def analyze_repo(
    url: str, commit_sha: str | None = None, event_start: datetime | None = None, deadline: datetime | None = None
) -> dict:
    """Fingerprint the repo at commit_sha, or else at the last commit made before the deadline."""
    owner, name = parse_repo_url(url)
    if commit_sha and not SHA_RE.match(commit_sha):
        raise RepoError("commit_sha must be a hex SHA")
    settings = get_settings()
    workdir = Path(tempfile.mkdtemp(prefix="veriqo-"))
    repo = workdir / "repo"
    try:
        _git(["clone", "--quiet", "--no-tags", f"https://github.com/{owner}/{name}.git", str(repo)],
             timeout=settings.clone_timeout_s)
        def log(ref: str) -> list[dict]:
            out = []
            for line in _git(["log", "--format=%H%x1f%cI%x1f%aI%x1f%an", ref], cwd=repo).splitlines():
                sha, committed, authored, author = line.split("\x1f")
                out.append({"sha": sha, "committed_at": committed, "authored_at": authored, "author": author})
            return out

        commits_after_deadline = 0
        if commit_sha:
            _git(["checkout", "--quiet", commit_sha], cwd=repo)
        elif deadline is not None:
            all_commits = log("HEAD")
            on_time = [c for c in all_commits if datetime.fromisoformat(c["committed_at"]) <= deadline]
            if not on_time:
                raise RepoError("repository has no commits made before the submission deadline")
            commits_after_deadline = len(all_commits) - len(on_time)
            _git(["checkout", "--quiet", on_time[0]["sha"]], cwd=repo)
        head = _git(["rev-parse", "HEAD"], cwd=repo).strip()
        commits = log("HEAD")

        files = iter_source_files(read_tree(repo, settings.max_repo_files))

        pre_event = None
        if event_start is not None and commits:
            before = [c for c in commits if datetime.fromisoformat(c["committed_at"]) < event_start]
            pre_event = {"commits_before_start": len(before), "total_commits": len(commits), "code_share": 0.0, "snapshot_sha": None}
            if before:
                snap = iter_source_files(_read_snapshot(repo, before[0]["sha"], settings.max_repo_files))
                pre_hashes = {h for f in snap for h, _ in f.fps}
                final = [h for f in files for h, _ in f.fps]
                pre_event.update(
                    snapshot_sha=before[0]["sha"],
                    code_share=round(100 * sum(h in pre_hashes for h in final) / (len(final) or 1), 1),
                )
    finally:
        _rmtree(workdir)

    languages: dict[str, int] = {}
    for f in files:
        languages[f.family] = languages.get(f.family, 0) + f.n_tokens
    return {
        "repo": f"{owner}/{name}",
        "commit_sha": head,
        "commits": commits[:500],
        "files": [f.to_dict() for f in files],
        "languages": languages,
        "pre_event": pre_event,
        "commits_after_deadline": commits_after_deadline,
    }
