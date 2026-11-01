# VERIQO Stage 1 Design: Hackathon Configuration, Team Registration and AI Shortlisting

Status: design for review · 1 Nov 2026 · supersedes the per-person shortlisting flow currently in `main`

This document specifies the schema, API and frontend for the Stage 1 onboarding pipeline. It is written against
the current codebase, so §1 lists what changes and §8 gives the build order.

---

## 1. What changes from today's implementation

| Area | Today (`main`) | Stage 1 design |
|---|---|---|
| Unit of application | One `applications` row **per person** | One application **per team**; solo entrants are teams of one |
| Who registers | Each participant applies alone | The **Team Lead** registers the whole team |
| Team formation | Organizer runs AI team formation after shortlisting | Teams self-form at registration; AI formation stays as an option for solo pools |
| Member consent | None | Each invited member confirms with an **email OTP** |
| Score visibility | Participant page **shows** score and per-skill breakdown | Score **never** reaches participants (enforced in API schemas, not just hidden in the UI) |
| Decision | AI decides at apply time (score ≥ threshold) | AI **recommends**; organizer decides; decisions stay hidden until **Publish Results** |
| Evaluation | Profile match only | Configurable pipeline: Profile Match, Idea Pitch, Prototype, Manual/CSV |
| Eligibility | None | Hard gates: age, student-only, team size, one team per hackathon |

The participant-facing score leak is the most important item: `GET /applications/mine` and
`HackathonDetail.jsx` both expose `score` and `match_details` today.

---

## 2. Database schema (SQLAlchemy / PostgreSQL)

Conventions follow the existing models: UUID primary keys (`UUIDPrimaryKeyMixin`), `created_at` (`TimestampMixin`),
and enums stored by value through `pg_enum`.

### 2.1 Users: demographics and student status

```python
class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # ...existing: name, email, hashed_password, github_url, role, parsed_skills...

    # Store date of birth, never "age": age depends on the event date and changes every year.
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    is_student: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    institution: Mapped[str | None] = mapped_column(String(200))
    # Self-declared student status is not proof. Set when verified (college-domain email or ID check).
    student_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    student_verification_method: Mapped[str | None] = mapped_column(String(30))  # "edu_email" / "id_upload"
```

### 2.2 Hackathons: event details and pipeline configuration

```python
class ParticipationMode(str, enum.Enum):
    SOLO = "solo"
    TEAM = "team"


class ThemeImportance(str, enum.Enum):
    OFF = "off"
    NORMAL = "normal"
    HIGH = "high"


class Hackathon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hackathons"
    # ...existing: event_name, description, theme, start_date, end_date, organizer_id, requirements...

    problem_statement: Mapped[str | None] = mapped_column(Text)          # used by theme relevance
    prizes: Mapped[list | None] = mapped_column(JSONB)                   # "stakes": [{"rank": 1, "amount": 50000, "note": "..."}]
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    fee_currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    participation_mode: Mapped[ParticipationMode] = mapped_column(pg_enum(ParticipationMode, "participation_mode"))
    min_team_size: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    max_team_size: Mapped[int]  # existing column

    age_min: Mapped[int | None] = mapped_column(SmallInteger)            # checked at start_date, per member
    age_max: Mapped[int | None] = mapped_column(SmallInteger)
    student_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    require_verified_students: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    registration_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Dynamic Stage 1 pipeline; validated by ShortlistConfig (§2.7) on every write.
    shortlist_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    theme_importance: Mapped[ThemeImportance] = mapped_column(pg_enum(ThemeImportance, "theme_importance"),
                                                             default=ThemeImportance.NORMAL)

    # Visibility
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Even after publishing, scores stay hidden unless the organizer opts in to share feedback.
    is_score_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
```

`shortlist_threshold` (today's auto-shortlist cutoff) is kept only as an optional **suggestion line** on the
organizer grid; it no longer decides anything.

### 2.3 Teams and members: lead, invitations and consent

```python
class TeamStatus(str, enum.Enum):
    DRAFT = "draft"                  # lead is assembling the team
    SUBMITTED = "submitted"          # locked; application exists
    WITHDRAWN = "withdrawn"


class MemberStatus(str, enum.Enum):
    INVITED = "invited"              # OTP sent, waiting for the member
    CONFIRMED = "confirmed"          # member verified the OTP: consent recorded
    DECLINED = "declined"
    EXPIRED = "expired"              # OTP attempts or lifetime exhausted; lead can re-invite


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    # ...existing: hackathon_id, team_name, description...
    lead_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[TeamStatus] = mapped_column(pg_enum(TeamStatus, "team_status"), default=TeamStatus.DRAFT)
    formed_by: Mapped[str] = mapped_column(String(10), default="self")  # "self" / "ai" (solo pool)


class TeamMember(Base):
    __tablename__ = "team_members"
    # ...existing PK (team_id, user_id), hackathon_id, role, ai_recommended...
    # UNIQUE (hackathon_id, user_id) already guarantees one team per person per hackathon.
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[MemberStatus] = mapped_column(pg_enum(MemberStatus, "member_status"), default=MemberStatus.INVITED)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

The lead's own row is created with `is_lead=True, status=CONFIRMED`.

### 2.4 OTP verifications

```python
class OtpVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "otp_verifications"
    __table_args__ = (Index("ix_otp_active", "team_id", "user_id", "purpose"),)

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20), default="team_join")
    code_hash: Mapped[str] = mapped_column(String(128))       # HMAC-SHA256(secret, code); never store the code
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))   # 15 minutes
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)          # max 5, then EXPIRED
    send_count: Mapped[int] = mapped_column(SmallInteger, default=1)        # max 5 resends
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### 2.5 Applications: one per team, with hidden AI fields

```python
class ApplicationStatus(str, enum.Enum):     # lifecycle, visible to the team
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    NEEDS_REVIEW = "needs_review"            # unreadable CV / failed parse: organizer must look manually


class Decision(str, enum.Enum):              # organizer's decision, hidden until published
    PENDING = "pending"
    SHORTLISTED = "shortlisted"
    WAITLISTED = "waitlisted"
    REJECTED = "rejected"


class Application(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("hackathon_id", "team_id"),)

    hackathon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hackathons.id"), index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))  # the lead
    status: Mapped[ApplicationStatus] = mapped_column(pg_enum(ApplicationStatus, "application_status"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- AI (organizer/judge only; never serialized to participants) ---
    team_fit_score: Mapped[float | None] = mapped_column(Float)          # 0-100, Mode 1
    ai_breakdown: Mapped[dict | None] = mapped_column(JSONB)             # skills / experience / theme components + evidence
    eligibility: Mapped[dict | None] = mapped_column(JSONB)              # {"passed": bool, "violations": [...]}
    stage1_score: Mapped[float | None] = mapped_column(Float)            # weighted across enabled rounds
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Human decision ---
    decision: Mapped[Decision] = mapped_column(pg_enum(Decision, "decision"), default=Decision.PENDING)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organizer_notes: Mapped[str | None] = mapped_column(Text)
    decision_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Per-member artifacts are **snapshotted per application**, so a later CV change doesn't alter what was judged:

```python
class ApplicationMemberArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_member_artifacts"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    cv_file_id: Mapped[str] = mapped_column(String(24))                  # MongoDB GridFS ObjectId (app/mongo/files.py)
    cv_sha256: Mapped[str] = mapped_column(String(64))
    github_url: Mapped[str] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))  # lead or member
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / ok / unreadable / failed
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)           # skills, experience, projects, github repos
```

### 2.6 Rounds, scores and email outbox

```python
class RoundSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mode 2 pitch deck / Mode 3 prototype submitted by the team."""
    __tablename__ = "round_submissions"
    __table_args__ = (UniqueConstraint("application_id", "round_key"),)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"))
    round_key: Mapped[str] = mapped_column(String(30))                   # "idea_pitch" / "prototype"
    payload: Mapped[dict] = mapped_column(JSONB)  # {"file_key", "pdf_key"} or {"video_url", "repo_url"}


class RoundScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One score per (application, round, scorer). AI, judges and CSV imports all land here."""
    __tablename__ = "round_scores"
    __table_args__ = (UniqueConstraint("application_id", "round_key", "scorer_id", "source"),)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"))
    round_key: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(10))                      # "ai" / "judge" / "csv" / "manual"
    scorer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    criteria: Mapped[dict | None] = mapped_column(JSONB)                 # {"innovation": 8, "feasibility": 6}
    total: Mapped[float] = mapped_column(Float)                          # normalised 0-100
    comment: Mapped[str | None] = mapped_column(Text)


class EmailOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transactional outbox: rows are written in the same DB transaction as the state change,
    then sent by a worker, so 'Publish Results' can never update statuses without queuing mail."""
    __tablename__ = "email_outbox"
    to_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    template: Mapped[str] = mapped_column(String(40))                    # "team_invite_otp" / "result_shortlisted" ...
    context: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="queued")    # queued / sent / failed
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
```

### 2.7 `shortlist_config` JSONB contract

Validated with a Pydantic discriminated union on every write, so malformed configs never reach the database:

```json
{
  "version": 1,
  "rounds": [
    { "key": "profile_match", "enabled": true, "weight": 0.5,
      "settings": { "weights": { "skills": 0.55, "experience": 0.20, "theme": 0.25 } } },
    { "key": "idea_pitch", "enabled": true, "weight": 0.3,
      "settings": { "formats": ["pdf", "pptx"], "max_mb": 20, "judges_per_entry": 2,
                    "rubric": [ { "key": "innovation", "label": "Innovation", "max": 10, "weight": 0.4 },
                                { "key": "feasibility", "label": "Feasibility", "max": 10, "weight": 0.3 },
                                { "key": "impact", "label": "Impact", "max": 10, "weight": 0.3 } ] } },
    { "key": "prototype", "enabled": false, "weight": 0.2,
      "settings": { "require_video": true, "video_hosts": ["youtube.com", "youtu.be", "vimeo.com", "drive.google.com"] } },
    { "key": "manual", "enabled": false, "weight": 0.0, "settings": { "csv_scores": true } }
  ]
}
```

Rules enforced by the validator:
- `profile_match` is always enabled (it is the core round).
- Weights of enabled rounds sum to 1.0 (manual may carry weight 0 if used only for status toggling).
- Rubric criterion weights sum to 1.0, and each `max` is between 1 and 100.
- Rounds can't be added or removed once the first application is submitted; weights may still change, and all
  `stage1_score` values are then recomputed.

### 2.8 Migration from today's schema

One Alembic revision, in this order:
1. Add the new columns and tables (all nullable or defaulted).
2. **Data migration:** for each existing per-person application, create a solo team (lead = applicant, status
   `submitted`) and move `score` → `team_fit_score` and `match_details` → `ai_breakdown`.
3. Map the old `status`: `shortlisted`/`rejected` → `decision`, and set `decision_published_at` (they were already
   visible), `needs_review` → status `needs_review`.
4. Make `applications.team_id` non-null, then drop `applications.user_id`, `score`, `match_details`.

Write the downgrade too, and test both directions on a Neon branch, not the shared database.

---

## 3. Backend API (FastAPI)

### 3.1 Organizer: configuration

| Method & path | Purpose |
|---|---|
| `POST /hackathons`, `PATCH /hackathons/{id}` | Extended fields from §2.2 |
| `PUT /hackathons/{id}/pipeline` | Replace `shortlist_config`; validated per §2.7 |
| `GET /hackathons/{id}/public` | Participant-safe view: details, eligibility rules, enabled round **names** and deadlines (no weights) |

### 3.2 Participant: team registration

| Method & path | Who | Rules |
|---|---|---|
| `POST /hackathons/{id}/registrations` `{team_name}` | Lead | Registration window open; caller passes eligibility themselves; not already in a team for this event. Creates a `draft` team with the caller as confirmed lead. Solo events skip invites. |
| `POST /registrations/{team_id}/members` `{email}` | Lead | Team draft; size < `max_team_size`; email has a VERIQO account (otherwise 404 "ask them to sign up"); invitee not in another team for this event. Creates `INVITED` member and queues the OTP email. |
| `POST /registrations/{team_id}/members/{user_id}/resend` | Lead | 60 s cooldown, max 5 sends; a new code replaces the old one |
| `DELETE /registrations/{team_id}/members/{user_id}` | Lead | Draft only |
| `GET /me/team-invitations` | Invitee | Pending invites with team, lead and hackathon names |
| `POST /team-invitations/{team_id}/verify` `{code}` | **Invitee, logged in** | Constant-time HMAC compare; 15 min expiry; 5 attempts. On success: `CONFIRMED` and `confirmed_at` set. |
| `POST /team-invitations/{team_id}/decline` | Invitee | |
| `PUT /registrations/{team_id}/members/{user_id}/artifacts` (multipart CV + `github_url`) | Lead or that member | PDF only, ≤ 5 MB, checked by magic bytes; GitHub profile URL validated; queues CV parsing |
| `GET /registrations/{team_id}/checklist` | Lead | Blocking items for submit (see below) |
| `POST /registrations/{team_id}/submit` | Lead | All gates pass → team `submitted`, application created, scoring job queued |
| `POST /registrations/{team_id}/rounds/{round_key}` | Lead | Mode 2 file upload / Mode 3 `{video_url, repo_url}`, while the round is open |
| `GET /me/registrations` | Any member | **Participant-safe schema only** (§3.5) |

**Who enters the OTP:** the invited **member** enters it in their own logged-in session (a "Team invitations" card
on their dashboard). If the lead typed in a code the member read out to them, that would prove only that the
lead can reach the member, not that the member agreed. The OTP email also includes a one-click link to the same
screen.

**Submit gates** (returned by `/checklist` and re-checked on submit):
- Every member is `CONFIRMED`, and team size is within `[min_team_size, max_team_size]`.
- Every member has a CV and a GitHub URL.
- The registration window is still open.
- Eligibility hard gates: age at `start_date` within range for every member, and `is_student` (plus
  `student_verified_at` when `require_verified_students`) if the event is student-only.

### 3.3 Organizer and judges: review and decisions

| Method & path | Purpose |
|---|---|
| `GET /hackathons/{id}/applications?sort=-stage1_score&decision=&eligible=` | Data grid: team, members, `team_fit_score`, round scores, `stage1_score`, eligibility flags, decision |
| `GET /applications/{id}` | Detail: per-member CVs (signed URLs, 10 min), GitHub summaries, AI breakdown with evidence |
| `PATCH /applications/{id}/decision` `{decision, notes}` | Draft decision: **not visible** to the team |
| `POST /hackathons/{id}/applications/bulk-decision` `{ids, decision}` | |
| `GET /hackathons/{id}/pitch-queue` | Judge's Mode 2 queue, entries assigned round-robin `judges_per_entry` times |
| `PUT /applications/{id}/rounds/idea_pitch/score` `{criteria, comment}` | Judge's rubric score (upsert per judge) |
| `POST /hackathons/{id}/manual-scores/import?dry_run=true` (CSV) | Mode 4: `team_id or lead_email, score, decision, note`; dry run returns per-row errors; `dry_run=false` commits atomically |
| `POST /applications/{id}/rescore` | Re-run AI scoring (e.g. after a CV fix) |
| `POST /hackathons/{id}/results/publish` `{notify: true, allow_undecided: false}` | §3.4 |

### 3.4 Publish Results

One database transaction:
1. Refuse if any eligible application is still `PENDING`, unless `allow_undecided` is set.
2. Set `decision_published_at = now()` on every decided, unpublished application.
3. Write one `email_outbox` row per team member, using the template for the decision.
4. Set `hackathons.results_published_at`.

A background worker then sends queued emails with retries. Re-running publish is **idempotent**: it only picks up
decisions made since the last publish, so late waitlist promotions notify only the affected teams.

Email is sent with Python's built-in `smtplib` through Gmail SMTP (implemented in `app/services/email.py`; no
external email API). Without `SMTP_USER`/`SMTP_PASSWORD` the sender logs emails to the console instead.
Gmail caps sending at roughly 500 recipients a day for a personal account; enough for a college event.

### 3.5 Score never reaches participants: enforced in the API

Participants get a **separate response schema** without score fields. It is not the organizer schema with fields
blanked out in the UI:

```python
class ParticipantApplicationOut(BaseModel):   # used by every participant-facing route
    hackathon_id: uuid.UUID
    team_id: uuid.UUID
    status_message: str          # "Successfully registered. Your application is under review, ..."
    decision: Decision | None    # None until decision_published_at is set
    feedback: dict | None        # only when hackathon.is_score_published and results are published
```

A test asserts that no participant route's JSON contains `score`, `team_fit_score`, `ai_breakdown` or
`stage1_score`. Removing today's leak (`/applications/mine`, `HackathonDetail.jsx`) is part of Phase 1 (§8).

### 3.6 AI aggregation: one Team_Fit_Score per team

Runs in the Intelligence service (`POST /teams/score`), triggered on submit and on rescore. Inputs: each member's
parsed CV and GitHub profile, the requirements, theme text and config weights.

```python
def team_fit(members, requirements, theme_text, weights, theme_importance) -> dict:
    # 1. Skills: pool every member's skills; each requirement takes its BEST credit from ANY member.
    #    React from Member A + Python from Member B satisfies "React + Python".
    pooled = union(m.skills for m in members)
    skills = match(pooled, requirements)            # existing Algorithm 1: exact 1.0 / semantic cos / category 0.5
    coverage = {req: best_member_for(req, members)} # who covers what, for the organizer's explanation

    # 2. Experience: a strong lead matters, but so does the rest of the team.
    level = {"beginner": 0.3, "intermediate": 0.6, "advanced": 1.0}
    lv = [level[m.experience_level] for m in members]
    experience = 0.6 * max(lv) + 0.4 * mean(lv)

    # 3. Theme relevance: have they built something related before?
    docs = [p.text for m in members for p in m.cv_projects] \
         + [f"{r.name}. {r.description}. {' '.join(r.topics)}. {r.readme[:1500]}" for m in members for r in m.repos]
    sims = cosine(embed(theme_text), embed(docs))   # theme_text = theme + problem statement + description
    theme = calibrate(mean(top_k(sims, 3)))         # map raw cosine onto 0..1 (calibrated, see note)
    evidence = top_k_docs(sims, 3)                  # shown to the organizer: "repo X matches the theme"

    # 4. Combine. Theme weight depends on organizer's importance setting; weights renormalised to 1.
    w = {**weights, "theme": {"off": 0, "normal": weights["theme"], "high": max(weights["theme"], 0.35)}[theme_importance]}
    w = normalise(w)
    score = 100 * (w["skills"] * skills.score / 100 + w["experience"] * experience + w["theme"] * theme)
    return {"team_fit_score": round(score, 1), "components": {...}, "coverage": coverage, "theme_evidence": evidence}
```

**Eligibility is a gate, not a score component.** An ineligible team is blocked at submit. If eligibility data
changes afterwards (e.g. a DOB correction), the application is flagged on the grid rather than silently
re-scored. Folding eligibility into the score would let a strong team that breaks a rule outrank a compliant one.

**Theme relevance needs calibration:** MiniLM cosine scores between short project descriptions and a theme
typically land around 0.1–0.6, not 0–1. Collect 30–50 labelled (project, theme) pairs, fit the mapping, and record
it in `docs/ML_MODELS.md`, as done for the 0.65 skill threshold.

**Data to collect for it:**
- **CV project sections:** split the CV text on a "Projects" heading (the regex-based section splitter is new code).
- **GitHub READMEs:** one extra API call per repo. Limit to the 10 most recently pushed non-fork repos per member,
  and set `GITHUB_TOKEN`: unauthenticated requests are limited to 60 per hour, which a few registrations exhaust.

**Stage 1 score:** `stage1_score = Σ round_weight × round_total` over enabled rounds that have scores, normalised
by the weights present. Mode 2 averages its judges; Mode 4 CSV scores enter as `source="csv"`.

### 3.7 Background work

Parsing CVs, fetching GitHub data and scoring take seconds to minutes, so they must not run inside the request.
FastAPI `BackgroundTasks` (already used for scans) is enough for the prototype. Move to a queue (arq or RQ on Redis)
before a real event: background tasks are lost if the API restarts mid-job.

---

## 4. Frontend architecture (React)

### 4.1 Participant: hackathon page and Registration Wizard

```
pages/hackathon/
  HackathonPublicPage.jsx        tabs: Overview · Eligibility · Stages timeline · Prizes · Team rules
  RegistrationWizard.jsx         route /hackathons/:id/register (lead only)
    WizardShell                  stepper; current step is DERIVED from server state, so refresh/resume works
    steps/
      EligibilityStep            event rules vs. the lead's profile (DOB, student status); blocks early
      TeamStep                   team name + <MemberInviteList>
        MemberInviteRow          email input · status chip (Invited / Confirmed / Declined / Expired) · Resend (cooldown timer) · Remove
      ArtifactsStep              one <MemberArtifactCard> per member
        MemberArtifactCard       <CvDropzone> (PDF ≤ 5 MB) · <GitHubUrlField> · parse status
      RoundSubmissionsStep       renders only enabled rounds: <PitchUpload>, <PrototypeForm>
      ReviewSubmitStep           server /checklist rendered as a list of blockers; Submit enabled when empty
  SubmittedState.jsx             "Successfully registered. Your application is under review…" (no score, ever)
pages/me/
  TeamInvitationsCard.jsx        invitee side: pending invites → <OtpInput> (6 boxes, paste-aware) → Confirm / Decline
```

State management:
- **The server is the source of truth.** The wizard reads one `registration` resource (team, members with
  statuses, artifacts, checklist) and re-fetches after each action. While invites are pending it polls every
  10 s so the lead sees "Confirmed" appear without reloading. There is no client-side wizard state to fall out of
  sync.
- Uploads show progress and keep the CV filename and hash, so re-uploading the same file is a no-op.

### 4.2 Organizer: pipeline builder and Shortlisting Dashboard

```
pages/manage/
  PipelineBuilder.jsx            in hackathon Settings
    RoundToggleCard ×4           enable switch · weight input · mode-specific settings
    RubricEditor                 criteria rows (label, max, weight) with live "weights sum to 100%" check
    ThemeImportanceSelect        Off / Normal / High
  ShortlistingDashboard.jsx      route /manage/:id/shortlisting
    SummaryBar                   counts per decision · undecided · eligibility flags · "Results: not published"
    FilterBar                    eligibility · decision · score range · round
    TeamsDataGrid                TanStack Table: rank · team · member avatars · Team_Fit_Score (breakdown popover)
                                 · round scores · Stage 1 score · eligibility · decision select; row selection
    BulkActionsBar               Shortlist / Waitlist / Reject selected
    TeamDetailDrawer             tabs: Members (CV viewer + GitHub summary) · AI explanation
                                 (member × skill coverage matrix, theme evidence) · Submissions · Notes & decision
    CsvImportDialog              Mode 4: upload → preview table with per-row errors → confirm
    PublishResultsDialog         counts per decision · email preview · "type PUBLISH to confirm" · send progress from outbox
  PitchReviewWorkspace.jsx       judges, Mode 2: split pane
    PdfViewer (left)             pdf.js; PPT/PPTX converted to PDF on upload (LibreOffice in the Intelligence service)
    RubricForm (right)           criteria sliders · comment · autosave · Prev / Next in queue
```

**New dependency:** `@tanstack/react-table`, for sorting, selection and column visibility at a few hundred rows.
`pdfjs-dist` is optional: an `<iframe>` on a signed PDF URL is enough at first.

---

## 5. Security and privacy

- **OTPs:** 6 digits, stored as HMAC-SHA256, 15 min expiry, 5 attempts, 60 s resend cooldown, 5 resends; compared
  in constant time.
- **Account lookup:** "no VERIQO account for this email" lets someone check whether an email is registered. Rate-limit
  member invites (e.g. 20 per lead per hour) to make bulk probing impractical.
- **Files:** stored in MongoDB GridFS (no external storage service); validated by content, not extension; served
  only through access-checked API routes, never a public URL. Atlas M0 has 512 MB in total, shared with telemetry:
  at ~1 MB per CV and ~5 MB per deck, plan for a paid tier or deletion after the event at around 300 teams.
- **Personal data (India's DPDP Act, 2023):** DOB, student status and CVs are personal data. Record each member's
  consent with the OTP confirmation, state the purpose on the registration screen, and delete CVs a fixed time
  after the event (e.g. 90 days).
- **Score visibility:** enforced by schemas plus the test in §3.5.

---

## 6. What the scores can and can't claim

- Team_Fit_Score ranks applicants for **human review**. Like the per-person score today, its weights are
  hand-chosen, not learned; there is no labelled data yet to train them.
- Theme relevance shows what a team **has built before**, which is evidence of interest, not of ability to build
  something new. Keep its weight moderate unless the organizer sets High.
- Student status is **self-declared** unless verified; `require_verified_students` exists for events that need proof.

---

## 7. Testing

| Layer | Tests |
|---|---|
| Schema | Migration upgrade/downgrade on a Neon branch; existing per-person data migrated to solo teams |
| Pipeline config | Validator rejects bad weights, missing core round, edits after first submission |
| Registration | Only the lead can invite/submit; one team per person per event; size limits; window enforcement |
| OTP | Expiry, attempt limit, resend cooldown, wrong user can't verify, code never stored in plaintext |
| Visibility | No participant route returns any score field (before and after publish, with `is_score_published` false) |
| Aggregation | Pooled skills cover requirements across members; experience formula; theme importance off/normal/high |
| Publish | Idempotent; outbox rows written in the same transaction; re-publish notifies only new decisions |

---

## 8. Build order

| Phase | Scope | Roughly |
|---|---|---|
| 1 | Schema + migration; **remove today's participant score leak**; participant-safe schemas | 3–4 days |
| 2 | Team registration: lead flow, invites, OTP (console email backend), artifacts, checklist, submit | 1 week |
| 3 | Team aggregation in the Intelligence service: pooled skills, experience, eligibility gates | 3–4 days |
| 4 | Organizer Shortlisting Dashboard: grid, drawer, decisions, Publish Results + real email provider | 1 week |
| 5 | Theme relevance: CV project sections, README fetch, calibration set | 4–5 days |
| 6 | Modes 2–4: pitch upload + judge workspace, prototype form, CSV import | 1.5 weeks |

Phases 1–4 give a complete, demonstrable Stage 1 with Mode 1; Modes 2–4 build on the same `round_scores` table.

---

## 9. Open decisions (needed before building)

1. ~~Email provider~~ **Decided:** Gmail SMTP via `smtplib` (implemented).
2. ~~File storage~~ **Decided:** MongoDB GridFS (implemented).
3. **Age groups:** a single min–max range per event (this design), or several named brackets (e.g. "Under 18",
   "18–25")?
4. **Fees:** stored and displayed only, or real payment (Razorpay)? Payment is a separate, sizeable feature.
5. **Student verification:** accept self-declaration, require a college email domain, or ID upload with manual check?
