"""Seed a complete demo through the public API, end to end. Also serves as the system's E2E test.

    python scripts/seed_demo.py            # against http://localhost:8000
    python scripts/seed_demo.py --fresh    # create another demo hackathon even if one exists

What it does (every step goes through the real REST API, the Intelligence service and both DBs):
  1. registers an organizer, a judge and 7 participants (password: DEMO_PASSWORD)
  2. creates a hackathon with weighted skill requirements and adds a reference repo
  3. each participant applies with a resume; one PDF is deliberately unreadable -> needs review
  4. the organizer forms teams with the AI team builder
  5. posts SIMULATED IDE telemetry (clearly fake demo data: one team pastes most of its code)
  6. teams submit real public GitHub repos; one is the reference repo itself (plagiarism case)
  7. scans all submissions and prints the evaluation grid

The event window starts in 2015 so the public demo repos (created later) don't trip the
"code written before the event" check; a real hackathon would last a day or two.
"""

import argparse
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

DEMO_PASSWORD = "veriqo-demo-2026"
EVENT_NAME = "VERIQO Demo: Open Source Remix"
REFERENCE_REPO = "https://github.com/kennethreitz/maya"
REPOS = [  # one per team, in team order
    ("Records Explorer", "https://github.com/kennethreitz/records", "honest"),
    ("TimeKeeper", "https://github.com/kennethreitz/maya", "honest"),  # identical to the reference repo
    ("Parallel Mapper", "https://github.com/sindresorhus/p-map", "paster"),
]

PARTICIPANTS = [
    ("Aarav Mehta", "Python developer with 3 years of experience. Skills: Python, FastAPI, PostgreSQL, Docker, REST API design, pytest. "
                    "Built data pipelines with Pandas and deployed services on AWS. Comfortable with Git and CI/CD using GitHub Actions."),
    ("Diya Nair", "Frontend engineer. 2 years of experience building React and TypeScript apps with Tailwind CSS and Next.js. "
                  "Some Node.js and Express backends, MongoDB, Figma prototypes and UI/UX design work. Jest for unit testing."),
    ("Kabir Singh", "Machine learning student (B.Tech). Projects in PyTorch, scikit-learn and Hugging Face transformers for NLP. "
                    "Python, NumPy, Pandas, data visualization with matplotlib, Jupyter. Interned on computer vision with OpenCV."),
    ("Meera Iyer", "Full-stack developer, 4 years of experience. JavaScript, TypeScript, React, Node.js, GraphQL, PostgreSQL, Redis, "
                   "Docker and Kubernetes on Google Cloud. Led a team using Agile and Scrum. System design and microservices."),
    ("Rohan Desai", "Backend developer: Java, Spring Boot, MySQL, REST APIs, microservices, Docker. 1.5 years of experience. "
                    "Also writes Python scripts and SQL for analytics; familiar with Kafka and Linux administration."),
    ("Sara Thomas", "Graphic designer exploring the web. Skills: Photoshop, Illustrator, branding, typography, video editing. "
                    "Basic HTML and CSS from an online course. Interested in hackathons to learn to code with a team."),
    ("Vikram Rao", None),  # uploads an unreadable (scanned-style) PDF -> needs manual review
]

REQUIREMENTS = [
    {"skill": "Python", "priority": 5},
    {"skill": "React", "priority": 4},
    {"skill": "PostgreSQL", "priority": 3},
    {"skill": "Machine Learning", "priority": 3},
    {"skill": "Docker", "priority": 2},
    {"skill": "UI/UX Design", "priority": 1},
]


def die(msg: str) -> None:
    print(f"\n✗ {msg}")
    sys.exit(1)


class Api:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base.rstrip("/") + "/api/v1", timeout=180)

    def call(self, method, path, token=None, expect=(200, 201, 202), **kw):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = self.http.request(method, path, headers=headers, **kw)
        if r.status_code not in expect:
            die(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def account(self, name, email, role):
        r = self.http.post("/auth/register", json={"name": name, "email": email, "password": DEMO_PASSWORD, "role": role})
        if r.status_code == 409:
            r = self.http.post("/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        if r.status_code not in (200, 201):
            die(f"account {email}: {r.status_code} {r.text[:200]}")
        return r.json()["access_token"], r.json()["user"]


def email_for(name: str) -> str:
    return name.lower().replace(" ", ".") + "@demo.veriqo.dev"


def simulated_batches(hackathon_id: str, profile: str, rng: random.Random) -> list[dict]:
    """SIMULATED telemetry for the demo: 24 half-hour windows ending now."""
    session = str(uuid.uuid4())
    end = datetime.now(timezone.utc)
    out = []
    for i in range(24, 0, -1):
        w_end = end - timedelta(minutes=30 * (i - 1))
        w_start = w_end - timedelta(minutes=30)
        if profile == "honest":
            typed, pasted, bulk, n_paste = rng.randint(500, 1400), rng.randint(0, 150), rng.randint(0, 120), rng.randint(0, 2)
            active, events = rng.randint(900, 1700), []
        else:  # pastes most of the code in a few big chunks, types very little
            typed, n_paste = rng.randint(10, 80), rng.randint(1, 3)
            pasted, bulk, active = rng.randint(1500, 4000), rng.randint(200, 900), rng.randint(200, 600)
            events = [{"ts": (w_start + timedelta(minutes=rng.randint(1, 29))).isoformat(), "chars": pasted // n_paste,
                       "lines": pasted // n_paste // 32, "file_ext": ".js", "source": "clipboard"} for _ in range(n_paste)]
        out.append({
            "batch_id": str(uuid.uuid4()), "session_id": session, "hackathon_id": hackathon_id,
            "window_start": w_start.isoformat(), "window_end": w_end.isoformat(),
            "metrics": {"typed_chars": typed, "pasted_chars": pasted, "paste_count": n_paste, "deleted_chars": typed // 6,
                        "active_seconds": active, "bulk_insert_chars": bulk, "ai_completion_accepts": bulk // 150,
                        "chars_by_ext": {"py": typed * 2 // 3, "tsx": typed - typed * 2 // 3} if profile == "honest" else {"js": typed}},
            "paste_events": events, "extension_version": "0.1.0-demo",
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    api, rng = Api(args.api), random.Random(42)

    print("1. Accounts")
    org_token, _ = api.account("Demo Organizer", "organizer@demo.veriqo.dev", "organizer")
    judge_token, _ = api.account("Demo Judge", "judge@demo.veriqo.dev", "judge")
    people = {}
    for name, _ in PARTICIPANTS:
        people[name] = api.account(name, email_for(name), "participant")
    print(f"   organizer, judge and {len(people)} participants (password: {DEMO_PASSWORD})")

    print("2. Hackathon")
    existing = [h for h in api.call("GET", "/hackathons/mine", org_token) if h["event_name"].startswith(EVENT_NAME)]
    if existing and not args.fresh:
        print(f"   '{existing[0]['event_name']}' already exists; re-run with --fresh to create another.")
        return
    name = EVENT_NAME if not existing else f"{EVENT_NAME} #{len(existing) + 1}"
    hk = api.call("POST", "/hackathons", org_token, json={
        "event_name": name, "theme": "Developer tools",
        "description": "Demo event seeded by scripts/seed_demo.py. Telemetry in this event is simulated.",
        "start_date": "2015-01-01T00:00:00+00:00",
        "end_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "shortlist_threshold": 40, "max_team_size": 2, "requirements": REQUIREMENTS,
    })
    hid = hk["id"]
    ref = api.call("POST", f"/hackathons/{hid}/references", org_token, json={"repo_url": REFERENCE_REPO, "label": "2025 winning project", "kind": "reference"})
    print(f"   {name} ({hid}); reference repo queued")

    print("3. Applications (resume parsing + GitHub-free matching)")
    for pname, resume in PARTICIPANTS:
        token = people[pname][0]
        if resume is None:
            files = {"resume": ("scan.pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "application/pdf")}
        else:
            files = {"resume": (f"{pname.split()[0].lower()}_resume.txt", f"{pname}\n{email_for(pname)}\n\n{resume}".encode(), "text/plain")}
        app = api.call("POST", f"/hackathons/{hid}/applications", token, files=files)
        print(f"   {pname:13s} score={app['score'] if app['score'] is not None else '—':>5}  {app['status']}")

    print("4. AI team formation")
    teams = api.call("POST", f"/hackathons/{hid}/teams/form", org_token)
    for t in teams:
        print(f"   {t['team_name']}: {', '.join(m['user']['name'] + ' (' + (m['role'] or '-') + ')' for m in t['members'])} · coverage {t['coverage']}%")

    print("5. Simulated IDE telemetry")
    for i, t in enumerate(teams):
        profile = REPOS[i % len(REPOS)][2]
        for m in t["members"]:
            token = people[m["user"]["name"]][0]
            for b in simulated_batches(hid, profile, rng):
                api.call("POST", "/telemetry", token, json=b)
        print(f"   {t['team_name']}: {profile} profile, 24 windows per member")

    print("6. Submissions")
    for i, t in enumerate(teams[: len(REPOS)]):
        title, repo, _ = REPOS[i]
        token = people[t["members"][0]["user"]["name"]][0]
        api.call("POST", f"/hackathons/{hid}/submissions", token, json={"project_title": title, "repository_url": repo})
        print(f"   {t['team_name']}: {title} -> {repo}")

    print("7. Integrity scan")
    for _ in range(60):  # wait for the reference repo analysis
        if all(r["status"] != "pending" for r in api.call("GET", f"/hackathons/{hid}/references", org_token)):
            break
        time.sleep(2)
    api.call("POST", f"/hackathons/{hid}/scan", org_token)
    for _ in range(150):
        rows = api.call("GET", f"/hackathons/{hid}/reports", judge_token)
        if all(r["submission"]["status"] not in ("scanning", "submitted") for r in rows):
            break
        time.sleep(3)
    else:
        die("scan did not finish in time")
    print(f"\n   {'team':8s} {'project':17s} {'risk':6s} {'matched':>8s} {'pre-event':>9s} {'paste':>6s}  telemetry")
    for r in rows:
        rep = r["report"] or {}
        def pct(v): return "—" if v is None else f"{v:.0f}%"
        print(f"   {r['team_name'] or '-':8s} {r['submission']['project_title']:17s} {str(rep.get('risk_level')):6s} "
              f"{pct(rep.get('plagiarism_score')):>8s} {pct(rep.get('pre_event_share')):>9s} "
              f"{pct((rep.get('paste_ratio') or 0) * 100):>6s}  {rep.get('telemetry_flag')}")
    print(f"\n✓ Done. Open http://localhost:5173 and sign in as organizer@demo.veriqo.dev / {DEMO_PASSWORD}")
    _ = ref


if __name__ == "__main__":
    main()
