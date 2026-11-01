import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.report import RiskLevel
from app.mongo.telemetry import TelemetryBatchIn
from app.services.risk import assess
from app.services.telemetry_scoring import suspicion, team_flag


def summary(typed, pasted, bulk=0, batches=10):
    written = typed + pasted + bulk
    return {"typed_chars": typed, "pasted_chars": pasted, "bulk_insert_chars": bulk, "batches": batches,
            "paste_ratio": (pasted + bulk) / written if written else None}


def test_algorithm_2_flags():
    assert suspicion(summary(0, 0, batches=0)) == "no_data"
    assert suspicion(summary(20000, 500)) == "low"
    assert suspicion(summary(10000, 9000)) == "medium"  # ratio > 0.4
    assert suspicion(summary(800, 9000)) == "high"  # ratio > 0.6 and little typing
    assert suspicion(summary(50000, 90000)) == "medium"  # high ratio but lots of real typing


def test_team_flag_takes_worst_member_with_data():
    assert team_flag(["low", "high", "no_data"]) == "high"
    assert team_flag(["no_data", "no_data"]) == "no_data"
    assert team_flag(["low", "medium"]) == "medium"


@pytest.mark.parametrize("args,level", [
    ((5, 0, "low", 1.0), RiskLevel.GREEN),
    ((30, 0, "low", 1.0), RiskLevel.AMBER),
    ((70, 0, "low", 1.0), RiskLevel.RED),
    ((5, 60, "low", 1.0), RiskLevel.RED),
    ((5, 0, "high", 1.0), RiskLevel.AMBER),  # telemetry alone never makes red
    ((30, 0, "high", 1.0), RiskLevel.RED),  # but corroborates code evidence
    ((5, 0, "low", 0.25), RiskLevel.AMBER),  # missing telemetry
    ((None, None, "no_data", None), RiskLevel.GREEN),
])
def test_risk_bands(args, level):
    got, reasons = assess(*args)
    assert got == level and reasons


def test_post_deadline_commits_are_informational():
    level, reasons = assess(0, 0, "low", 1.0, commits_after_deadline=3)
    assert level == RiskLevel.GREEN and any("after the deadline" in r for r in reasons)


def batch(**over):
    now = datetime.now(timezone.utc)
    base = {"batch_id": uuid.uuid4(), "session_id": uuid.uuid4(), "hackathon_id": uuid.uuid4(),
            "window_start": now - timedelta(seconds=30), "window_end": now,
            "metrics": {"typed_chars": 10}, "extension_version": "0.1.0"}
    return TelemetryBatchIn(**{**base, **over})


def test_telemetry_schema_rejects_paths_and_bad_windows():
    batch()
    with pytest.raises(ValidationError):
        batch(metrics={"chars_by_ext": {"src/secret/file.py": 3}})
    with pytest.raises(ValidationError):
        batch(paste_events=[{"ts": datetime.now(timezone.utc), "chars": 5, "lines": 1, "file_ext": "C:/Users/x/a.py"}])
    with pytest.raises(ValidationError):
        now = datetime.now(timezone.utc)
        batch(window_start=now, window_end=now - timedelta(seconds=1))
