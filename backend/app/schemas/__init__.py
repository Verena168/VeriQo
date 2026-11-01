import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.application import ApplicationStatus
from app.models.hackathon import ParticipationMode, ThemeImportance
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
    date_of_birth: date | None = None
    is_student: bool = False
    institution: str | None = None
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
    date_of_birth: date | None = None
    is_student: bool | None = None
    institution: str | None = Field(default=None, max_length=200)

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v):
        if v is not None:
            today = date.today()
            years = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
            if not 8 <= years <= 100:
                raise ValueError("date of birth must give an age between 8 and 100")
        return v

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


class Prize(BaseModel):
    title: str = Field(min_length=1, max_length=80)  # e.g. "Winner", "Best UI"
    amount: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=200)


# ---- Stage 1 shortlisting pipeline (docs/STAGE1_DESIGN.md §2.7)

class RubricCriterion(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,30}$")
    label: str = Field(min_length=1, max_length=60)
    max: int = Field(default=10, ge=1, le=100)
    weight: float = Field(gt=0, le=1)


class ProfileMatchSettings(BaseModel):
    weights: dict[Literal["skills", "experience", "theme"], float] = {"skills": 0.55, "experience": 0.20, "theme": 0.25}

    @model_validator(mode="after")
    def _sum(self):
        if set(self.weights) != {"skills", "experience", "theme"} or abs(sum(self.weights.values()) - 1) > 1e-6:
            raise ValueError("profile match weights for skills, experience and theme must sum to 1")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("profile match weights cannot be negative")
        return self


class PitchSettings(BaseModel):
    formats: list[Literal["pdf", "pptx"]] = ["pdf", "pptx"]
    max_mb: int = Field(default=20, ge=1, le=20)
    judges_per_entry: int = Field(default=2, ge=1, le=5)
    rubric: list[RubricCriterion] = Field(default_factory=lambda: [
        RubricCriterion(key="innovation", label="Innovation", weight=0.4),
        RubricCriterion(key="feasibility", label="Feasibility", weight=0.3),
        RubricCriterion(key="impact", label="Impact", weight=0.3),
    ], min_length=1, max_length=10)

    @model_validator(mode="after")
    def _rubric(self):
        if abs(sum(c.weight for c in self.rubric) - 1) > 1e-6:
            raise ValueError("rubric criterion weights must sum to 1")
        if len({c.key for c in self.rubric}) != len(self.rubric):
            raise ValueError("rubric criterion keys must be unique")
        return self


class PrototypeSettings(BaseModel):
    require_video: bool = True
    video_hosts: list[str] = ["youtube.com", "youtu.be", "vimeo.com", "drive.google.com"]


class ManualSettings(BaseModel):
    csv_scores: bool = True


class _Round(BaseModel):
    enabled: bool = False
    weight: float = Field(default=0, ge=0, le=1)


class ProfileMatchRound(_Round):
    key: Literal["profile_match"] = "profile_match"
    enabled: bool = True
    weight: float = Field(default=1, ge=0, le=1)
    settings: ProfileMatchSettings = Field(default_factory=ProfileMatchSettings)


class IdeaPitchRound(_Round):
    key: Literal["idea_pitch"] = "idea_pitch"
    settings: PitchSettings = Field(default_factory=PitchSettings)


class PrototypeRound(_Round):
    key: Literal["prototype"] = "prototype"
    settings: PrototypeSettings = Field(default_factory=PrototypeSettings)


class ManualRound(_Round):
    key: Literal["manual"] = "manual"
    settings: ManualSettings = Field(default_factory=ManualSettings)


Round = Annotated[ProfileMatchRound | IdeaPitchRound | PrototypeRound | ManualRound, Field(discriminator="key")]


class ShortlistConfig(BaseModel):
    version: Literal[1] = 1
    rounds: list[Round] = Field(
        default_factory=lambda: [ProfileMatchRound(), IdeaPitchRound(), PrototypeRound(), ManualRound()]
    )

    @model_validator(mode="after")
    def _rules(self):
        keys = [r.key for r in self.rounds]
        if len(set(keys)) != len(keys):
            raise ValueError("each round can appear only once")
        core = next((r for r in self.rounds if r.key == "profile_match"), None)
        if core is None or not core.enabled:
            raise ValueError("the AI profile-match round is the core round and must stay enabled")
        if abs(sum(r.weight for r in self.rounds if r.enabled) - 1) > 1e-6:
            raise ValueError("weights of the enabled rounds must sum to 1 (100%)")
        return self

    def enabled_keys(self) -> set[str]:
        return {r.key for r in self.rounds if r.enabled}


# ---- hackathon create / update / read

class _HackathonFields(BaseModel):
    """Field-level limits shared by create and update (all optional here)."""

    description: str | None = Field(default=None, max_length=5000)
    theme: str | None = Field(default=None, max_length=120)
    problem_statement: str | None = Field(default=None, max_length=5000)
    theme_importance: ThemeImportance | None = None
    prizes: list[Prize] | None = Field(default=None, max_length=20)
    fee_amount: Decimal | None = Field(default=None, ge=0, le=100_000)
    fee_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    participation_mode: ParticipationMode | None = None
    min_team_size: int | None = Field(default=None, ge=1, le=10)
    max_team_size: int | None = Field(default=None, ge=1, le=10)
    age_min: int | None = Field(default=None, ge=8, le=100)
    age_max: int | None = Field(default=None, ge=8, le=100)
    student_only: bool | None = None
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    shortlist_threshold: float | None = Field(default=None, ge=0, le=100)
    is_score_published: bool | None = None
    shortlist_config: ShortlistConfig | None = None
    requirements: list[RequirementIn] | None = Field(default=None, max_length=50)


def event_rule_errors(v: dict) -> list[str]:
    """Cross-field rules, applied to the full (merged) set of values."""
    errors = []
    dates = [v.get(k) for k in ("start_date", "end_date", "registration_opens_at", "registration_closes_at")]
    if any(d is not None and d.tzinfo is None for d in dates):
        return ["dates must include a timezone"]
    if v["end_date"] <= v["start_date"]:
        errors.append("end_date must be after start_date")
    opens, closes = v.get("registration_opens_at"), v.get("registration_closes_at")
    if opens and closes and closes <= opens:
        errors.append("registration must close after it opens")
    if closes and closes > v["end_date"]:
        errors.append("registration must close before the hackathon ends")
    mode = v.get("participation_mode")
    lo, hi = v.get("min_team_size") or 1, v.get("max_team_size") or 1
    if mode == ParticipationMode.SOLO and (lo, hi) != (1, 1):
        errors.append("a solo hackathon must have team size 1")
    if lo > hi:
        errors.append("minimum team size cannot exceed the maximum")
    if v.get("age_min") is not None and v.get("age_max") is not None and v["age_min"] > v["age_max"]:
        errors.append("minimum age cannot exceed the maximum age")
    return errors


class HackathonIn(_HackathonFields):
    event_name: str = Field(min_length=3, max_length=200)
    start_date: datetime
    end_date: datetime
    theme_importance: ThemeImportance = ThemeImportance.NORMAL
    fee_amount: Decimal = Field(default=Decimal(0), ge=0, le=100_000)
    fee_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    participation_mode: ParticipationMode = ParticipationMode.TEAM
    min_team_size: int = Field(default=1, ge=1, le=10)
    max_team_size: int = Field(default=4, ge=1, le=10)
    student_only: bool = False
    shortlist_threshold: float = Field(default=60, ge=0, le=100)
    is_score_published: bool = False
    shortlist_config: ShortlistConfig = Field(default_factory=ShortlistConfig)
    requirements: list[RequirementIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _rules(self):
        if errors := event_rule_errors(self.model_dump()):
            raise ValueError("; ".join(errors))
        return self


class HackathonUpdate(_HackathonFields):
    event_name: str | None = Field(default=None, min_length=3, max_length=200)
    start_date: datetime | None = None
    end_date: datetime | None = None


class HackathonOut(ORM):
    id: uuid.UUID
    event_name: str
    description: str | None
    theme: str | None
    start_date: datetime
    end_date: datetime
    problem_statement: str | None = None
    theme_importance: ThemeImportance = ThemeImportance.NORMAL
    prizes: list[Prize] | None = None
    fee_amount: Decimal = Decimal(0)
    fee_currency: str = "INR"
    participation_mode: ParticipationMode = ParticipationMode.TEAM
    min_team_size: int = 1
    max_team_size: int
    age_min: int | None = None
    age_max: int | None = None
    student_only: bool = False
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    shortlist_threshold: float
    shortlist_config: dict = {}
    is_score_published: bool = False
    results_published_at: datetime | None = None
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
    decision_published_at: datetime | None = None
    applied_at: datetime


class ApplicationWithUser(ApplicationOut):
    user: UserOut


class ApplicationWithHackathon(ApplicationOut):
    hackathon: HackathonOut


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus


class ParticipantApplicationOut(BaseModel):
    """The ONLY application shape participant routes may return. It has no score fields by design;
    `feedback` is filled only when the organizer opts in and results are published."""

    id: uuid.UUID
    hackathon_id: uuid.UUID
    state: Literal["under_review", "shortlisted", "rejected"]
    status_message: str
    resume_filename: str | None
    has_cv: bool
    has_pitch_deck: bool
    applied_at: datetime
    published_at: datetime | None
    feedback: dict | None = None


class ParticipantApplicationWithHackathon(ParticipantApplicationOut):
    hackathon: "HackathonOut"


class PublishResultsIn(BaseModel):
    notify: bool = True  # email every team member
    allow_undecided: bool = False  # publish even though some applications still need a decision


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
