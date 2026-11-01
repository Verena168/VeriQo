"""Whitebook Algorithm 2: Telemetry Suspicion Scoring, applied per team member."""

PASTE_RATIO_HIGH = 0.60
PASTE_RATIO_MEDIUM = 0.40
MIN_EXPECTED_TYPING = 3000  # characters typed over a whole hackathon by someone who actually coded


def suspicion(summary: dict) -> str:
    """summary comes from mongo.telemetry.summarize_user."""
    if not summary.get("batches"):
        return "no_data"
    ratio = summary.get("paste_ratio") or 0.0
    if ratio > PASTE_RATIO_HIGH and summary["typed_chars"] < MIN_EXPECTED_TYPING:
        return "high"  # "High - Potential AI Generation / Pre-built Code"
    if ratio > PASTE_RATIO_MEDIUM:
        return "medium"
    return "low"


def team_flag(member_flags: list[str]) -> str:
    """Worst flag among members that have data; no_data only if nobody has data."""
    order = ["high", "medium", "low"]
    present = [f for f in member_flags if f != "no_data"]
    return min(present, key=order.index) if present else "no_data"
