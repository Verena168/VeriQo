import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.application import ApplicationStatus
from app.models.reference import ReferenceKind
from app.models.report import ReportStatus, RiskLevel
from app.models.submission import SubmissionStatus
from app.models.user import UserRole

GITHUB_PROFILE_RE = re.compile(r"^https://github\.com/[A-Za-z0-9-]{1,39}/?$")
GITHUB_REPO_RE = re.compile(r"^https://github\.com/[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}?(?:\.git)?/?$")


def _validate_repo(v: str) -> str:
    v = v.strip()
    if not GITHUB_REPO_RE.match(v):
        raise ValueError("must be a public GitHub repository URL like https://github.com/owner/repo")
    return v.removesuffix("/").removesuffix(".git")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth / users

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt ignores bytes beyond 72
    role: UserRole = UserRole.PARTICIPANT
    github_url: str | None = None

    @field_validator("github_url")
    @classmethod
    def _gh(cls, v):
        if v and not GITHUB_PROFILE_RE.match(v):
            raise ValueError("must look like https://github.com/<username>")
        return v or None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    github_url: str | None
    parsed_skills: dict | None
    created_at: datetime


class UserBrief(ORM):
    id: uuid.UUID
    name: str
    email: str
    github_url: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    github_url: str | None = None

    @field_validator("github_url")
    @classmethod
    def _gh(cls, v):
        if v and not GITHUB_PROFILE_RE.match(v):
            raise ValueError("must look like https://github.com/<username>")
        return v


# ------------------------------------------------------------------ hackathons

class RequirementIn(BaseModel):
    skill: str = Field(min_length=1, max_length=80)
    priority: int = Field(default=1, ge=1, le=5)
    description: str | None = Field(default=None, max_length=500)


class RequirementOut(ORM, RequirementIn):
    id: uuid.UUID


class HackathonIn(BaseModel):
    event_name: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    theme: str | None = Field(default=None, max_length=120)
    start_date: datetime
    end_date: datetime
    shortlist_threshold: float = Field(default=60, ge=0, le=100)
    max_team_size: int = Field(default=4, ge=1, le=10)
    requirements: list[RequirementIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date.tzinfo is None or self.end_date.tzinfo is None:
            raise ValueError("dates must include a timezone")
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class HackathonUpdate(BaseModel):
    event_name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    theme: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    shortlist_threshold: float | None = Field(default=None, ge=0, le=100)
    max_team_size: int | None = Field(default=None, ge=1, le=10)
    requirements: list[RequirementIn] | None = None


class HackathonOut(ORM):
    id: uuid.UUID
    event_name: str
    description: str | None
    theme: str | None
    start_date: datetime
    end_date: datetime
    shortlist_threshold: float
    max_team_size: int
    organizer_id: uuid.UUID
    created_at: datetime
    requirements: list[RequirementOut] = []
    phase: str = "upcoming"  # upcoming / live / ended, computed by the endpoint


# ------------------------------------------------------------------ applications

class ApplicationOut(ORM):
    id: uuid.UUID
    hackathon_id: uuid.UUID
    status: ApplicationStatus
    score: float | None
    match_details: list | None
    resume_filename: str | None
    cv_file_id: str | None = None
    pitch_deck_file_id: str | None = None
    review_note: str | None
    applied_at: datetime


class ApplicationWithUser(ApplicationOut):
    user: UserOut


class ApplicationWithHackathon(ApplicationOut):
    hackathon: HackathonOut


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus


# ------------------------------------------------------------------ teams

class TeamMemberOut(ORM):
    user: UserBrief
    role: str | None
    ai_recommended: bool


class TeamOut(ORM):
    id: uuid.UUID
    hackathon_id: uuid.UUID
    team_name: str
    description: str | None
    members: list[TeamMemberOut] = []
    coverage: float | None = None
    missing_skills: list[str] = []


class TeamUpdate(BaseModel):
    team_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class MoveMemberIn(BaseModel):
    user_id: uuid.UUID


# ------------------------------------------------------------------ submissions / references

class SubmissionIn(BaseModel):
    project_title: str = Field(min_length=2, max_length=200)
    repository_url: str

    _repo = field_validator("repository_url")(_validate_repo)


class SubmissionOut(ORM):
    id: uuid.UUID
    hackathon_id: uuid.UUID
    team_id: uuid.UUID | None
    user_id: uuid.UUID
    project_title: str
    repository_url: str
    commit_sha: str | None
    status: SubmissionStatus
    submitted_at: datetime


class ReferenceIn(BaseModel):
    repo_url: str
    label: str = Field(min_length=1, max_length=200)
    kind: ReferenceKind = ReferenceKind.REFERENCE

    _repo = field_validator("repo_url")(_validate_repo)


class ReferenceOut(ORM):
    id: uuid.UUID
    repo_url: str
    label: str
    kind: ReferenceKind
    commit_sha: str | None
    status: str
    error: str | None
    created_at: datetime


# ------------------------------------------------------------------ reports

class ReportOut(ORM):
    id: uuid.UUID
    submission_id: uuid.UUID
    status: ReportStatus
    plagiarism_score: float | None
    ai_generated_prob: float | None
    paste_ratio: float | None
    active_minutes: int | None
    telemetry_coverage: float | None
    template_share: float | None
    pre_event_share: float | None
    telemetry_flag: str | None
    risk_level: RiskLevel | None
    judge_notes: str | None
    generated_at: datetime | None
    updated_at: datetime


class ReportDetail(ReportOut):
    matches: list | None
    details: dict | None


class ReportRow(BaseModel):
    """One row of the organizer evaluation grid."""

    submission: SubmissionOut
    team_name: str | None
    members: list[UserBrief]
    report: ReportOut | None


class ReportUpdate(BaseModel):
    judge_notes: str | None = Field(default=None, max_length=5000)
    status: ReportStatus | None = None
