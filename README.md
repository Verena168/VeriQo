# VERIQO

AI-powered platform for hackathon management, participant evaluation, code-integrity verification and developer analytics.
Major Project, Department of Computer Engineering, St. Francis Institute of Technology (2026–27).

| Module | What it does | Where |
|---|---|---|
| **A** Shortlisting & teams | Parses PDF/DOCX/TXT resumes (spaCy rule-based skill NER over a 113-skill taxonomy), reads public GitHub profiles, scores applicants against weighted requirements (exact → MiniLM embedding cosine → same-category credit), forms skill-balanced teams | `backend/intelligence/app/nlp` |
| **B** IDE telemetry | VS Code extension: typed vs pasted vs bulk-inserted characters, active time, large-paste events; offline queue; never sends code | `extension/` |
| **C** Code integrity | tree-sitter parsing → normalised tokens + AST k-grams → winnowing fingerprints → trained clone classifier; cross-submission + reference-repo matching, allowed templates, "code existed before the event" check from git history, deadline-pinned commits | `backend/intelligence/app/ast_engine` |
| **D** Dashboards | Organizer evaluation grid + report evidence, applicant ranking, AI team board; participant "Year in Code" | `frontend/` |

## Architecture

```
frontend (React + Vite + Tailwind, :5173) ──/api proxy──▶ API (FastAPI, :8000) ──HTTP──▶ Intelligence (FastAPI, :8001)
VS Code extension ──────────── HTTPS/JSON ─────────────▶      │                         spaCy · MiniLM · tree-sitter · sklearn
                                                              ├── PostgreSQL (Neon)  users, hackathons, applications, teams, submissions, reports
                                                              └── MongoDB (Atlas)    telemetry_logs, code_sources, code_files (fingerprints)
```

The API never imports ML code; heavy work runs in the Intelligence service so a repo scan can't block web requests.

## Running locally

Prerequisites: Python 3.13, Node 20+, git, a PostgreSQL and a MongoDB connection string (Neon + Atlas free tiers work).

```powershell
# 1. Backend API
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then fill in POSTGRES_DSN, MONGO_URI, JWT_SECRET
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload

# 2. Intelligence service (separate venv: PyTorch etc.)
cd backend\intelligence
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload --reload-dir app

# 3. Frontend
cd frontend; npm install; npm run dev            # http://localhost:5173

# 4. VS Code extension
cd extension; npm install; npm run package       # -> veriqo-telemetry-0.1.0.vsix
code --install-extension veriqo-telemetry-0.1.0.vsix
```

Health: `GET http://localhost:8000/health` reports Postgres and Mongo; interactive API docs at `/docs`.

### Demo data

```powershell
cd backend; .venv\Scripts\python scripts\seed_demo.py
```

Creates an organizer, a judge and 7 participants (password `veriqo-demo-2026`; e.g. `organizer@demo.veriqo.dev`) and a
team hackathon, then runs the whole Stage 1 flow through the API: Team Leads invite members who confirm by email OTP,
every member's CV and GitHub profile is analysed, teams are scored on their pooled skills, solo registrants are merged
into an AI-formed team, results are published, and three teams submit real public GitHub repos (one copied from the
reference repo) with **simulated** telemetry before the integrity scan runs.

## Tests

```powershell
cd backend; $env:PYTHONPATH="."; .venv\Scripts\python -m pytest -q tests          # risk bands, Algorithm 2, telemetry schema
cd backend\intelligence; .venv\Scripts\python -m pytest -q tests                  # NER, matching, teams, tokenizer, winnowing, compare
cd extension; npm test                                                            # typed/paste/bulk classification, active time
```

`scripts/seed_demo.py` is the end-to-end test: it exercises every API module against the live services and databases.

## ML models

See [docs/ML_MODELS.md](docs/ML_MODELS.md) for the clone classifier's training data, method and measured results,
and for the measured calibration of the skill-matching threshold.

```powershell
cd backend\intelligence
.venv\Scripts\python -m training.build_dataset --js-root ..\..\frontend\node_modules
.venv\Scripts\python -m training.train_clone_classifier
```

## Known limitations

- **AI-generated code is not "detected".** Published detectors perform near chance on source code (whitebook Ch. 2), so
  `ai_generated_prob` is left empty; IDE telemetry (bulk insertions, paste spikes) is the signal used instead.
- **Telemetry is client-side** and can be avoided by not installing the extension; reports show telemetry coverage
  so missing data is visible rather than read as "clean".
- **VS Code exposes no paste event or AI-assistant activity.** Pastes are detected by wrapping the paste keybinding;
  AI completions are inferred from large non-paste insertions.
- **Git timestamps can be forged**, so the pre-event check is supporting evidence.
- **The plagiarism corpus is bounded**: other submissions + organizer-added reference repos, not all of GitHub.
- Risk bands are triage for judges, never automatic verdicts.
