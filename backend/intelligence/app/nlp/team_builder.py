"""Group shortlisted participants into skill-balanced teams (Module A).

Greedy set-cover with balancing:
  1. n_teams = ceil(N / team_size); the n_teams highest-scoring participants seed one team each,
     so strong candidates are spread out rather than stacked.
  2. Repeatedly take the weakest non-full team (lowest weighted requirement coverage) and give it
     the unassigned participant with the largest marginal gain: weight of the required skills they
     add that the team still lacks, plus a small tie-breaker on their match score.
"""

import math

from app.nlp.taxonomy import canonicalize


def _norm(skills) -> set[str]:
    return {(canonicalize(s) or s).lower() for s in skills}


def form_teams(participants: list[dict], requirements: list[dict], team_size: int) -> dict:
    """participants: [{"id", "skills": [str], "score": float}] ; requirements: [{"skill", "weight"}]."""
    if team_size < 1:
        raise ValueError("team_size must be >= 1")
    if not participants:
        return {"teams": [], "unassigned": []}

    display = {(canonicalize(r["skill"]) or r["skill"]).lower(): canonicalize(r["skill"]) or r["skill"] for r in requirements}
    req_weight = {(canonicalize(r["skill"]) or r["skill"]).lower(): max(int(r.get("weight", 1)), 1) for r in requirements}
    total_weight = sum(req_weight.values()) or 1
    people = {p["id"]: {**p, "_skills": _norm(p.get("skills", []))} for p in participants}

    def coverage(skills: set[str]) -> float:
        return sum(w for s, w in req_weight.items() if s in skills) / total_weight

    n_teams = math.ceil(len(people) / team_size)
    ranked = sorted(people.values(), key=lambda p: (-(p.get("score") or 0), str(p["id"])))
    teams = [{"members": [p["id"]], "skills": set(p["_skills"])} for p in ranked[:n_teams]]
    unassigned = [p["id"] for p in ranked[n_teams:]]

    while unassigned:
        open_teams = [t for t in teams if len(t["members"]) < team_size]
        team = min(open_teams, key=lambda t: (coverage(t["skills"]), len(t["members"])))

        def gain(pid):
            p = people[pid]
            added = sum(w for s, w in req_weight.items() if s in p["_skills"] and s not in team["skills"])
            return added + 0.01 * (p.get("score") or 0)

        best = max(unassigned, key=lambda pid: (gain(pid), str(pid)))
        unassigned.remove(best)
        team["members"].append(best)
        team["skills"] |= people[best]["_skills"]

    out = []
    for i, t in enumerate(teams, 1):
        missing = [display[s] for s in req_weight if s not in t["skills"]]
        members = []
        for pid in t["members"]:
            # The member's "role" is the required skill they contribute with the highest weight.
            contrib = sorted((s for s in people[pid]["_skills"] if s in req_weight), key=lambda s: -req_weight[s])
            members.append({"id": pid, "role": display[contrib[0]] if contrib else None})
        out.append({
            "name": f"Team {i}",
            "members": members,
            "coverage": round(100 * coverage(t["skills"]), 1),
            "missing_skills": missing,
        })
    return {"teams": out, "unassigned": []}
