"""Colour band for the organizer grid. Every band carries the reasons that produced it.

The band is triage for judges, never an automatic verdict: AI-code detection is unreliable on
source code (see whitebook Ch. 2), so no single signal can mark a submission red on its own
except near-certain evidence (most of the code copied, or written before the event).
"""

from app.models.report import RiskLevel

RED_PLAGIARISM = 60.0
AMBER_PLAGIARISM = 25.0
RED_PRE_EVENT = 50.0
AMBER_PRE_EVENT = 20.0
LOW_COVERAGE = 0.5


def assess(plagiarism: float | None, pre_event: float | None, telemetry_flag: str, coverage: float | None,
           commits_after_deadline: int = 0) -> tuple[RiskLevel, list[str]]:
    red, amber, info = [], [], []
    p = plagiarism or 0.0
    pre = pre_event or 0.0
    if p >= RED_PLAGIARISM:
        red.append(f"{p:.0f}% of the code matches other sources")
    elif p >= AMBER_PLAGIARISM:
        amber.append(f"{p:.0f}% of the code matches other sources")
    if pre >= RED_PRE_EVENT:
        red.append(f"{pre:.0f}% of the final code already existed before the hackathon started")
    elif pre >= AMBER_PRE_EVENT:
        amber.append(f"{pre:.0f}% of the final code already existed before the hackathon started")
    if telemetry_flag == "high":
        (red if p >= AMBER_PLAGIARISM else amber).append("IDE telemetry: mostly pasted or bulk-inserted code with little typing")
    elif telemetry_flag == "medium":
        amber.append("IDE telemetry: elevated paste / bulk-insert ratio")
    if coverage is not None and coverage < LOW_COVERAGE:
        amber.append(f"IDE telemetry missing for {round((1 - coverage) * 100)}% of team members")
    if commits_after_deadline:
        info.append(f"Note: {commits_after_deadline} commit(s) pushed after the deadline were not evaluated")
    if red:
        return RiskLevel.RED, red + amber + info
    if amber:
        return RiskLevel.AMBER, amber + info
    return RiskLevel.GREEN, ["No integrity concerns found", *info]
