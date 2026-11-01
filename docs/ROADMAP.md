# VERIQO — 3-Month Development Roadmap

**Window:** Mon 12 Oct 2026 → Sun 10 Jan 2027 (13 weeks)
**Team:** 4 members. Each person owns one module end to end (intelligence code, API endpoints and UI for it). The API contract and DB schema are shared and change only through a PR that everyone reviews.

| Owner | Module | Main code |
|---|---|---|
| Member 1 | A: Shortlisting & Team Formation | `backend/intelligence/app/nlp`, `api/v1/endpoints/{applications,teams}.py` |
| Member 2 | B: VS Code Telemetry | `extension/`, `app/mongo/telemetry.py`, `endpoints/telemetry.py` |
| Member 3 | C: Code Integrity Engine | `backend/intelligence/app/ast_engine`, `endpoints/submissions.py` |
| Member 4 | D: Dashboards & Analytics | `frontend/`, `endpoints/{reports,analytics}.py` |

---

## Month 1: Foundations + Module A (Weeks 1–4)

**Week 1 (12–18 Oct): Infrastructure (everyone)**
- `docker compose up` brings up Postgres and Mongo; set up Alembic and create the first migration from the existing models.
- Auth: register/login, JWT, role guard (participant / organizer / judge).
- CI on every PR: ruff and pytest for the backend, eslint and tsc for the frontend and extension.
- Frontend shell: Vite, React, Tailwind, React Router, auth pages, API client.
- Extension scaffold (`yo code`, TypeScript) plus a "Sign in to VERIQO" command that stores a device token in `SecretStorage`.

**Week 2 (19–25 Oct): Hackathons + resume ingestion**
- Hackathon CRUD with skill requirements (organizer).
- Application endpoint with PDF/DOCX upload; text extraction with `pdfplumber` / `python-docx`.
- Skill extraction: off-the-shelf spaCy NER has **no** "skill" label. Use a spaCy `EntityRuler` built on a curated skill taxonomy (languages, frameworks, tools, with aliases such as "JS" → "JavaScript"). Store the output in `users.parsed_skills`.
- Unreadable resume → `needs_review` status (whitebook Use Case 1, exception path).

**Week 3 (26 Oct–1 Nov): Matching**
- GitHub profile signals: languages from public repos, recent activity, through the GitHub REST API (authenticated, to stay within rate limits).
- Sentence-BERT embeddings plus cosine similarity, implementing whitebook **Algorithm 1**. Weight each requirement by `hackathon_requirements.priority`.
- Organizer shortlist table with sortable score, per-skill breakdown and a manual override.
- Extension: listeners for `onDidChangeTextDocument`, window focus and idle detection.

**Week 4 (2–8 Nov): Team formation**
- Greedy team builder: seed each team with its strongest candidate, then repeatedly add the person who covers the most still-missing required skills, subject to team size.
- Kanban board where organizers drag members between teams; writes `team_members.ai_recommended`.
- Extension: local event buffer and a 30 s batch flush to `POST /api/v1/telemetry`.

**Milestone M1 (8 Nov):** demo register → upload resume → shortlisted → placed in a team.

---

## Month 2: Module B complete + Module C (Weeks 5–8)

**Week 5 (9–15 Nov): Telemetry hardening + AST tokenizer**
- Restrict tracking to the hackathon workspace folder only (privacy NFR). Show a consent screen on first run. Never send code content.
- Offline queue with retry; `batch_id` makes retries idempotent (already enforced by a unique index).
- Implement whitebook **Algorithm 2** on top of `summarize_user()`.
- Module C: tree-sitter parsing for Python, JavaScript/TypeScript and Java; normalise identifiers and literals into token streams.

**Week 6 (16–22 Nov): Fingerprinting**
- k-gram hashing and winnowing (the approach MOSS uses) over normalised tokens.
- Compare each submission against every other submission in the same hackathon. This needs no external data and catches copying between teams.
- Reference corpus: you cannot scan "all of GitHub". Build a bounded corpus per hackathon: repos found through GitHub search on the theme keywords, the participants' own pre-event public repos, and past-event submissions.

**Week 7 (23–29 Nov): Scan pipeline**
- At the deadline: lock submissions → clone at `commit_sha` → scan as a background job → write `originality_reports`.
- Store match evidence (source repo, file, line spans) in `originality_reports.matches` so judges can see *why* something was flagged.
- Also flag files committed with timestamps earlier than `hackathon.start_date`, a cheap and strong pre-built-code signal.

**Week 8 (30 Nov–6 Dec): Report aggregation**
- AI-generated-code signal: keep it optional and low-weight. The paper surveyed in Ch. 2 found detectors perform near chance on code. Telemetry (bulk insertions, paste spikes) is the stronger evidence.
- Risk band rules (green / amber / red) combining plagiarism score, paste ratio and telemetry coverage. Document the thresholds; they are tuned in Week 12.

**Milestone M2 (6 Dec):** a submitted repo produces a complete Originality Report row with evidence.

---

## Month 3: Module D, integration, evaluation (Weeks 9–13)

**Week 9 (7–13 Dec): Organizer evaluation view**
- High-density grid (TanStack Table) with colour-coded risk, sortable by each signal.
- Report detail page: side-by-side diff of matched code and a telemetry timeline (paste events over time).

**Week 10 (14–20 Dec): Year in Code**
- Analytics endpoints aggregating Mongo telemetry and Postgres history.
- Recharts: contribution-style heatmap, language pie, active-hours line chart, hackathon stats.

**Week 11 (21–27 Dec): Dry-run hackathon**
- Run a 3–4 hour mock event with 10–20 classmates (with written consent). Some participants follow scripted "cheating" scenarios: paste a pre-built repo, paste LLM output, copy from another team.
- Load-test telemetry ingestion with Locust at 300+ simulated clients (scalability NFR).

**Week 12 (28 Dec–3 Jan): Evaluation experiments**
These produce the measured results for the final whitebook. Report what you actually measure, including weak results.
- **Plagiarism engine:** precision and recall on a labelled clone set (a public dataset such as IR-Plag or BigCloneBench, plus your own obfuscated variants: renaming, reordering, comment changes).
- **Telemetry flag:** detection rate against the dry run's scripted scenarios, and the false-positive rate on honest participants.
- **Shortlisting:** rank agreement (e.g. Spearman) between the system's scores and two human reviewers on 30 or more resumes.

**Week 13 (4–10 Jan): Buffer and write-up**
- Bug fixes, README and setup docs, demo video, whitebook chapters on implementation and results.

---

## Known technical risks (address early)

1. **VS Code has no "paste" event.** Detect pastes by registering a command bound to the paste keybinding that records the clipboard length and then calls the built-in paste. Insertions arriving through `onDidChangeTextDocument` with no paste command are logged as `bulk_insert`.
2. **AI-assistant prompts are not observable.** The VS Code API does not expose Copilot or chat interactions to other extensions. "AI assistance" can only be inferred from bulk inserts. The whitebook should say so rather than claim direct capture.
3. **Telemetry is client-side.** A participant can disable the extension or code elsewhere. `telemetry_coverage` makes missing data visible; it must not be read as "clean".
4. **Scores are evidence, not verdicts.** The UI should send flagged submissions to a judge for review, never auto-disqualify.

## Deferred

- **Integrated Virtual Rooms** (whitebook §2.3): real-time video/collab is a large separate system and not part of the project's novelty. Propose moving it to future scope.
