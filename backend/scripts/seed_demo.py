"""Seed a complete demo through the public API, end to end. Also serves as the system's E2E test.

    python scripts/seed_demo.py            # against http://localhost:8000
    python scripts/seed_demo.py --fresh    # create another demo hackathon even if one exists

What it does (each step goes through the real REST API, the Intelligence service and both DBs):
  1. registers an organizer, a judge and 7 participants (password: DEMO_PASSWORD)
  2. creates a team hackathon (teams of 2-3) with weighted skill requirements and a reference repo
  3. team registration:
       Team Alpha: Meera (lead) invites Diya, who confirms by email OTP; both upload CV + GitHub
       Team Beta:  Aarav (lead) invites Rohan, who confirms; both upload CV + GitHub
       Kabir and Sara register alone, "looking for teammates"
       Vikram registers alone with an unreadable PDF -> needs manual review
  4. the organizer shortlists Sara by hand and the AI forms a team from the solo registrants
  5. results are published (no emails: demo addresses are not real inboxes)
  6. posts SIMULATED IDE telemetry (clearly fake demo data: the AI team pastes most of its code)
  7. teams submit real public GitHub repos; Team Beta's is the reference repo itself (plagiarism case)
  8. scans all submissions and prints the evaluation grid

Demo-only shortcut: demo emails are never sent, so the script can't read the OTP a member
receives. It sets that member's pending code to a known value directly in the database and then
confirms through the normal API (so OTP verification itself still runs). Needs backend/.env.

The event window starts in 2015 so the public demo repos (created later) don't trip the
"code written before the event" check; a real hackathon would last a day or two.
"""

import argparse
import asyncio
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

DEMO_PASSWORD = "veriqo-demo-2026"
EVENT_NAME = "VERIQO Demo: Team Remix"
REFERENCE_REPO = "https://github.com/kennethreitz/maya"
# team name -> (project, repo, telemetry profile)
PROJECTS = {
    "Team Alpha": ("Records Explorer", "https://github.com/kennethreitz/records", "honest"),
    "Team Beta": ("TimeKeeper", "https://github.com/kennethreitz/maya", "honest"),  # identical to the reference repo
    "AI": ("Parallel Mapper", "https://github.com/sindresorhus/p-map", "paster"),  # the AI-formed team
}

PARTICIPANTS = {
    "Aarav Mehta": "Python developer with 3 years of experience. Skills: Python, FastAPI, PostgreSQL, Docker, REST API design, pytest. "
                   "Built data pipelines with Pandas and deployed services on AWS. Comfortable with Git and CI/CD using GitHub Actions.",
    "Diya Nair": "Frontend engineer. 2 years of experience building React and TypeScript apps with Tailwind CSS and Next.js. "
                 "Some Node.js and Express backends, MongoDB, Figma prototypes and UI/UX design work. Jest for unit testing.",
    "Kabir Singh": "Machine learning student (B.Tech). Projects in PyTorch, scikit-learn and Hugging Face transformers for NLP. "
                   "Python, NumPy, Pandas, data visualization with matplotlib, Jupyter. Interned on computer vision with OpenCV.",
    "Meera Iyer": "Full-stack developer, 4 years of experience. JavaScript, TypeScript, React, Node.js, GraphQL, PostgreSQL, Redis, "
                  "Docker and Kubernetes on Google Cloud. Led a team using Agile and Scrum. System design and microservices.",
    "Rohan Desai": "Backend developer: Java, Spring Boot, MySQL, REST APIs, microservices, Docker. 1.5 years of experience. "
                   "Also writes Python scripts and SQL for analytics; familiar with Kafka and Linux administration.",
    "Sara Thomas": "Graphic designer exploring the web. Skills: Photoshop, Illustrator, branding, typography, video editing. "
                   "Basic HTML and CSS from an online course. Interested in hackathons to learn to code with a team.",
    "Vikram Rao": None,  # uploads an unreadable (scanned-style) PDF -> needs manual review
}

REQUIREMENTS = [
    {"skill": "Python", "priority": 5},
    {"skill": "React", "priority": 4},
    {"skill": "PostgreSQL", "priority": 3},
    {"skill": "Machine Learning", "priority": 3},
    {"skill": "Docker", "priority": 2},
    {"skill": "UI/UX Design", "priority": 1},
]
UNREADABLE_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def die(msg: str) -> None:
    print(f"\n✗ {msg}")
    sys.exit(1)


class Api:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base.rstrip("/") + "/api/v1", timeout=180)

    def call(self, method, path, token=None, expect=(200, 201, 202, 204), **kw):
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


def github_for(name: str) -> str:
    # Deliberately not real GitHub accounts, so the demo never pulls real people's profiles.
    return f"https://github.com/veriqo-demo-{name.split()[0].lower()}-x9"


def set_known_otp(user_email: str, team_id: str, code: str = "135790") -> str:
    """Demo-only: give a member's pending invitation code a known value (see module docstring)."""
    from sqlalchemy import select

    from app.db.session import SessionLocal, engine
    from app.models import OtpCode, User
    from app.services.otp import _hash

    async def run():
        async with SessionLocal() as db:
            uid = await db.scalar(select(User.id).where(User.email == user_email))
            row = await db.scalar(select(OtpCode).where(OtpCode.user_id == uid, OtpCode.subject_id == uuid.UUID(team_id),
                                                        OtpCode.consumed_at.is_(None)))
            row.code_hash = _hash(code)
            await db.commit()
        await engine.dispose()

    asyncio.run(run())
    return code


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
    org, _ = api.account("Demo Organizer", "organizer@demo.veriqo.dev", "organizer")
    judge, _ = api.account("Demo Judge", "judge@demo.veriqo.dev", "judge")
    people = {name: api.account(name, email_for(name), "participant") for name in PARTICIPANTS}
    tok = {name: t for name, (t, _) in people.items()}
    uid = {name: u["id"] for name, (_, u) in people.items()}
    print(f"   organizer, judge and {len(people)} participants (password: {DEMO_PASSWORD})")

    print("2. Hackathon")
    existing = [h for h in api.call("GET", "/hackathons/mine", org) if h["event_name"].startswith(EVENT_NAME)]
    if existing and not args.fresh:
        print(f"   '{existing[0]['event_name']}' already exists; re-run with --fresh to create another.")
        return
    name = EVENT_NAME if not existing else f"{EVENT_NAME} #{len(existing) + 1}"
    hk = api.call("POST", "/hackathons", org, json={
        "event_name": name, "theme": "Developer tools", "participation_mode": "team", "min_team_size": 2, "max_team_size": 3,
        "description": "Demo event seeded by scripts/seed_demo.py. Telemetry in this event is simulated.",
        "problem_statement": "Build tools that make everyday developer workflows faster and safer.",
        "start_date": "2015-01-01T00:00:00+00:00",
        "end_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "shortlist_threshold": 40, "requirements": REQUIREMENTS,
        "prizes": [{"title": "Winner", "amount": 25000}, {"title": "Best newcomer team", "amount": 10000}],
    })
    hid = hk["id"]
    api.call("POST", f"/hackathons/{hid}/references", org, json={"repo_url": REFERENCE_REPO, "label": "2025 winning project", "kind": "reference"})
    print(f"   {name} ({hid}); reference repo queued")

    def upload(by, team_id, who):
        resume = PARTICIPANTS[who]
        cv = ("scan.pdf", UNREADABLE_PDF, "application/pdf") if resume is None else \
             (f"{who.split()[0].lower()}_cv.txt", f"{who}\n{email_for(who)}\n\n{resume}".encode(), "text/plain")
        api.call("PUT", f"/registrations/{team_id}/members/{uid[who]}/artifacts", tok[by],
                 files={"cv": cv}, data={"github_url": github_for(who)})

    def register(lead, team_name=None, members=(), seeking=False):
        reg = api.call("POST", f"/hackathons/{hid}/registrations", tok[lead],
                       json={"team_name": team_name or f"{lead} (solo)", "seeking_teammates": seeking})
        tid = reg["team_id"]
        for m in members:
            api.call("POST", f"/registrations/{tid}/members", tok[lead], json={"email": email_for(m)})
            code = set_known_otp(email_for(m), tid)  # demo-only shortcut, see docstring
            api.call("POST", f"/team-invitations/{tid}/verify", tok[m], json={"code": code})
        for who in (lead, *members):
            upload(lead, tid, who)  # the lead uploads every member's CV and GitHub link
        reg = api.call("POST", f"/registrations/{tid}/submit", tok[lead])
        return tid, reg

    print("3. Team registration (invite -> OTP confirm -> CVs -> submit)")
    teams = {}
    for lead, team_name, members, seeking in (
        ("Meera Iyer", "Team Alpha", ["Diya Nair"], False),
        ("Aarav Mehta", "Team Beta", ["Rohan Desai"], False),
        ("Kabir Singh", None, [], True),
        ("Sara Thomas", None, [], True),
        ("Vikram Rao", None, [], True),
    ):
        tid, reg = register(lead, team_name, members, seeking)
        teams[reg["team_name"]] = tid
        print(f"   {reg['team_name']:22s} {len(reg['members'])} member(s), submitted -> participant sees '{reg['application']['state']}'")

    grid = {a["team_name"]: a for a in api.call("GET", f"/hackathons/{hid}/applications", org)}
    for t, a in grid.items():
        print(f"   organizer view: {t:22s} score={a['score'] if a['score'] is not None else '—':>5}  AI suggests {a['status']}")

    print("4. Organizer decisions + AI team formation")
    sara = grid["Sara Thomas (solo)"]
    if sara["status"] != "shortlisted":
        api.call("PATCH", f"/applications/{sara['id']}", org, json={"status": "shortlisted"})
        print("   organizer shortlists Sara by hand (overriding the AI suggestion)")
    formed = api.call("POST", f"/hackathons/{hid}/teams/form", org)
    for t in formed:
        print(f"   {t['team_name']}: {', '.join(m['user']['name'] for m in t['members'])} · coverage {t['coverage']}%")
    ai_team = formed[0]

    print("5. Publish results (no emails for demo addresses)")
    pub = api.call("POST", f"/hackathons/{hid}/results/publish", org, json={"notify": False, "allow_undecided": True})
    print(f"   {pub['shortlisted']} shortlisted, {pub['rejected']} not shortlisted, {pub['still_under_review']} still under review")

    print("6. Simulated IDE telemetry")
    roster = {"Team Alpha": ["Meera Iyer", "Diya Nair"], "Team Beta": ["Aarav Mehta", "Rohan Desai"],
              "AI": [m["user"]["name"] for m in ai_team["members"]]}
    for team, members in roster.items():
        for m in members:
            for b in simulated_batches(hid, PROJECTS[team][2], rng):
                api.call("POST", "/telemetry", tok[m], json=b)
        print(f"   {ai_team['team_name'] if team == 'AI' else team}: {PROJECTS[team][2]} profile, 24 windows per member")

    print("7. Submissions")
    for team, members in roster.items():
        title, repo, _ = PROJECTS[team]
        api.call("POST", f"/hackathons/{hid}/submissions", tok[members[0]], json={"project_title": title, "repository_url": repo})
        print(f"   {ai_team['team_name'] if team == 'AI' else team}: {title} -> {repo}")

    print("8. Integrity scan")
    for _ in range(60):  # wait for the reference repo analysis
        if all(r["status"] != "pending" for r in api.call("GET", f"/hackathons/{hid}/references", org)):
            break
        time.sleep(2)
    api.call("POST", f"/hackathons/{hid}/scan", org)
    for _ in range(150):
        rows = api.call("GET", f"/hackathons/{hid}/reports", judge)
        if all(r["submission"]["status"] not in ("scanning", "submitted") for r in rows):
            break
        time.sleep(3)
    else:
        die("scan did not finish in time")
    print(f"\n   {'team':12s} {'project':17s} {'risk':6s} {'matched':>8s} {'pre-event':>9s} {'paste':>6s}  telemetry")
    for r in rows:
        rep = r["report"] or {}

        def pct(v):
            return "—" if v is None else f"{v:.0f}%"
        print(f"   {r['team_name'] or '-':12s} {r['submission']['project_title']:17s} {str(rep.get('risk_level')):6s} "
              f"{pct(rep.get('plagiarism_score')):>8s} {pct(rep.get('pre_event_share')):>9s} "
              f"{pct((rep.get('paste_ratio') or 0) * 100):>6s}  {rep.get('telemetry_flag')}")
    print(f"\n✓ Done. Open http://localhost:5173 and sign in as organizer@demo.veriqo.dev / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
