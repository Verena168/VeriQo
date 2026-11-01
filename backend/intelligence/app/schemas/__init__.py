from datetime import datetime

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    skill: str = Field(min_length=1, max_length=80)
    weight: int = Field(default=1, ge=1, le=5)


class MatchIn(BaseModel):
    candidate_skills: list[str] = Field(max_length=500)
    requirements: list[Requirement] = Field(max_length=100)
    threshold: float | None = Field(default=None, ge=0, le=1)


class GitHubIn(BaseModel):
    url: str = Field(max_length=200)


class Participant(BaseModel):
    id: str
    skills: list[str] = Field(default_factory=list)
    score: float | None = None


class TeamsIn(BaseModel):
    participants: list[Participant] = Field(max_length=5000)
    requirements: list[Requirement] = Field(max_length=100)
    team_size: int = Field(ge=1, le=10)


class AnalyzeIn(BaseModel):
    repo_url: str = Field(max_length=300)
    commit_sha: str | None = None
    event_start: datetime | None = None
    deadline: datetime | None = None


class FileFP(BaseModel):
    path: str
    family: str
    n_tokens: int
    n_lines: int
    fps: list[tuple[int, int]]
    ast: list[int] = Field(default_factory=list)


class CorpusSource(BaseModel):
    source_id: str
    label: str
    kind: str = Field(pattern="^(submission|reference|template)$")
    files: list[FileFP]


class CompareIn(BaseModel):
    files: list[FileFP]
    corpus: list[CorpusSource]
