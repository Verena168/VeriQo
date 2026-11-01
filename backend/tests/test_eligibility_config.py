from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models import Hackathon, User
from app.models.hackathon import ParticipationMode
from app.schemas import HackathonIn, ProfileUpdate, ShortlistConfig, event_rule_errors
from app.services.eligibility import age_on, person_violations, registration_problem

START = datetime(2027, 3, 10, 9, 0, tzinfo=timezone.utc)


def hk(**kw):
    base = dict(start_date=START, end_date=START + timedelta(days=2), age_min=None, age_max=None, student_only=False,
                registration_opens_at=None, registration_closes_at=None)
    return Hackathon(**(base | kw))


def user(dob=None, student=False):
    return User(name="A", email="a@b.c", date_of_birth=dob, is_student=student)


def test_age_counts_birthdays_correctly():
    assert age_on(date(2009, 3, 10), date(2027, 3, 10)) == 18  # birthday on the start day
    assert age_on(date(2009, 3, 11), date(2027, 3, 10)) == 17  # day after
    assert age_on(date(2008, 2, 29), date(2027, 2, 28)) == 18  # leap-day birthday not yet reached


def test_age_limits_checked_at_event_start():
    event = hk(age_min=18, age_max=25)
    assert person_violations(user(date(2009, 3, 10)), event) == []
    assert "at least 18" in person_violations(user(date(2009, 3, 11)), event)[0]
    assert "25 or younger" in person_violations(user(date(2000, 1, 1)), event)[0]
    assert "date of birth" in person_violations(user(None), event)[0]
    assert person_violations(user(None), hk()) == []  # no age rule: DOB not required


def test_student_only():
    assert "students only" in person_violations(user(student=False), hk(student_only=True))[0]
    assert person_violations(user(student=True), hk(student_only=True)) == []


def test_registration_window():
    event = hk(registration_opens_at=START - timedelta(days=10), registration_closes_at=START - timedelta(days=1))
    assert "opens" in registration_problem(event, START - timedelta(days=11))
    assert registration_problem(event, START - timedelta(days=5)) is None
    assert "closed" in registration_problem(event, START)
    assert registration_problem(hk(), START + timedelta(days=1)) is None  # no window: open until the end
    assert "closed" in registration_problem(hk(), START + timedelta(days=3))


def test_default_pipeline_is_ai_only():
    assert ShortlistConfig().enabled_keys() == {"profile_match"}


@pytest.mark.parametrize("rounds,message", [
    ([{"key": "profile_match", "enabled": False, "weight": 1}], "core round"),
    ([{"key": "profile_match", "weight": 0.5}], "sum to 1"),
    ([{"key": "profile_match", "weight": 0.6}, {"key": "idea_pitch", "enabled": True, "weight": 0.4},
      {"key": "idea_pitch", "enabled": False}], "only once"),
    ([{"key": "profile_match", "weight": 0.5}, {"key": "idea_pitch", "enabled": True, "weight": 0.5,
      "settings": {"rubric": [{"key": "x", "label": "X", "weight": 0.5}]}}], "rubric"),
    ([{"key": "profile_match", "weight": 1, "settings": {"weights": {"skills": 1, "experience": 0.2, "theme": 0}}}], "sum to 1"),
    ([{"key": "telepathy", "weight": 1}], "telepathy"),
])
def test_pipeline_validation(rounds, message):
    with pytest.raises(ValidationError, match=message):
        ShortlistConfig.model_validate({"rounds": rounds})


def test_valid_multi_round_pipeline():
    c = ShortlistConfig.model_validate({"rounds": [{"key": "profile_match", "weight": 0.6},
                                                   {"key": "idea_pitch", "enabled": True, "weight": 0.4}]})
    assert c.enabled_keys() == {"profile_match", "idea_pitch"}


def _event(**kw):
    return dict(event_name="Hack", start_date=START, end_date=START + timedelta(days=1)) | kw


@pytest.mark.parametrize("kw,message", [
    ({"end_date": START}, "end_date must be after"),
    ({"participation_mode": "solo", "max_team_size": 4}, "solo hackathon"),
    ({"min_team_size": 5, "max_team_size": 3}, "minimum team size"),
    ({"age_min": 25, "age_max": 18}, "minimum age"),
    ({"registration_opens_at": START, "registration_closes_at": START - timedelta(hours=1)}, "close after it opens"),
    ({"registration_closes_at": START + timedelta(days=5)}, "before the hackathon ends"),
])
def test_event_rules(kw, message):
    with pytest.raises(ValidationError, match=message):
        HackathonIn(**_event(**kw))


def test_event_rules_on_merged_values():
    merged = {"start_date": START, "end_date": START + timedelta(days=1), "participation_mode": ParticipationMode.SOLO,
              "min_team_size": 1, "max_team_size": 3}
    assert any("solo" in e for e in event_rule_errors(merged))


def test_profile_dob_bounds():
    ProfileUpdate(date_of_birth=date(2004, 5, 1))
    with pytest.raises(ValidationError, match="between 8 and 100"):
        ProfileUpdate(date_of_birth=date.today())
