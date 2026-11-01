from fastapi import APIRouter, File, HTTPException, UploadFile

from app.ast_engine import classifier
from app.ast_engine.compare import compare
from app.ast_engine.fingerprint import FileFingerprint
from app.ast_engine.repo import RepoError, analyze_repo
from app.nlp.github_profile import GitHubError, fetch_profile
from app.nlp.resume_parser import MAX_FILE_BYTES, UnreadableResume, parse_resume
from app.nlp.skill_matcher import match
from app.nlp.taxonomy import CATEGORIES, SKILLS
from app.nlp.team_builder import form_teams
from app.schemas import AnalyzeIn, CompareIn, GitHubIn, MatchIn, TeamsIn

router = APIRouter()


@router.get("/skills")
def list_skills() -> dict:
    return {"categories": CATEGORIES, "skills": [{"name": n, "category": c} for n, (c, _) in SKILLS.items()]}


@router.post("/resume/parse")
def resume_parse(file: UploadFile = File(...)) -> dict:
    data = file.file.read(MAX_FILE_BYTES + 1)
    try:
        return parse_resume(file.filename or "", data)
    except UnreadableResume as exc:
        raise HTTPException(422, detail={"code": "unreadable_resume", "message": str(exc)})


@router.post("/github/profile")
async def github_profile(body: GitHubIn) -> dict:
    try:
        return await fetch_profile(body.url)
    except GitHubError as exc:
        raise HTTPException(422, detail={"code": "github_error", "message": str(exc)})


@router.post("/match")
def skill_match(body: MatchIn) -> dict:
    return match(body.candidate_skills, [r.model_dump() for r in body.requirements], body.threshold)


@router.post("/teams/form")
def teams_form(body: TeamsIn) -> dict:
    return form_teams([p.model_dump() for p in body.participants], [r.model_dump() for r in body.requirements], body.team_size)


@router.post("/code/analyze")
def code_analyze(body: AnalyzeIn) -> dict:
    try:
        return analyze_repo(body.repo_url, body.commit_sha, body.event_start, body.deadline)
    except RepoError as exc:
        raise HTTPException(422, detail={"code": "repo_error", "message": str(exc)})


@router.post("/code/compare")
def code_compare(body: CompareIn) -> dict:
    files = [FileFingerprint.from_dict(f.model_dump()) for f in body.files]
    corpus = [
        {**s.model_dump(exclude={"files"}), "files": [FileFingerprint.from_dict(f.model_dump()) for f in s.files]}
        for s in body.corpus
    ]
    return compare(files, corpus)


@router.get("/models/clone-classifier")
def clone_model_info() -> dict:
    return classifier.model_info()
