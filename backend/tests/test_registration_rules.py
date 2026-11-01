import uuid
from datetime import date, datetime, timedelta, timezone

from app.models import Hackathon, Team, TeamMember, TeamMemberArtifact, User
from app.models.hackathon import ParticipationMode
from app.models.team import MemberStatus, TeamStatus
from app.services.registration import checklist, member_skills

NOW = datetime(2027, 1, 10, tzinfo=timezone.utc)


def hk(**kw):
    base = dict(start_date=NOW + timedelta(days=5), end_date=NOW + timedelta(days=7), participation_mode=ParticipationMode.TEAM,
                min_team_size=2, max_team_size=3, age_min=None, age_max=None, student_only=False,
                registration_opens_at=None, registration_closes_at=None)
    return Hackathon(**(base | kw))


def person(name, **kw):
    return User(id=uuid.uuid4(), name=name, email=f"{name.lower()}@x.dev", is_student=kw.get("student", True),
                date_of_birth=kw.get("dob"))


def team(members, artifacts=True, seeking=False):
    t = Team(id=uuid.uuid4(), team_name="T", status=TeamStatus.DRAFT, seeking_teammates=seeking, members=[], artifacts=[])
    for i, (user, status) in enumerate(members):
        t.members.append(TeamMember(user_id=user.id, user=user, is_lead=i == 0, status=status))
        if artifacts:
            t.artifacts.append(TeamMemberArtifact(user_id=user.id, cv_file_id="a" * 24, github_url="https://github.com/x",
                                                  parse_status="ok"))
    return t


def test_complete_team_is_ready():
    lead, b = person("Lead"), person("Bea")
    assert checklist(team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.CONFIRMED)]), hk(), NOW) == []


def test_pending_invites_and_team_size():
    lead, b = person("Lead"), person("Bea")
    items = checklist(team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.INVITED)]), hk(), NOW)
    assert any("Bea hasn't confirmed" in i for i in items)
    assert any("at least 2 confirmed members" in i for i in items)  # invited members don't count


def test_too_many_members():
    people = [(person(n), MemberStatus.CONFIRMED) for n in ("A", "B", "C", "D")]
    assert any("maximum is 3" in i for i in checklist(team(people), hk(), NOW))


def test_missing_documents_named_per_member():
    lead, b = person("Lead"), person("Bea")
    t = team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.CONFIRMED)], artifacts=False)
    t.artifacts.append(TeamMemberArtifact(user_id=b.id, cv_file_id=None, github_url=None, parse_status="pending"))
    items = checklist(t, hk(), NOW)
    assert "Your CV is missing." in items and "Your GitHub profile link is missing." in items
    assert "Bea's CV is missing." in items and "Bea's GitHub profile link is missing." in items


def test_failed_analysis_asks_for_reupload():
    lead, b = person("Lead"), person("Bea")
    t = team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.CONFIRMED)])
    t.artifacts[1].parse_status = "failed"
    assert any("Bea's CV couldn't be analysed" in i for i in checklist(t, hk(), NOW))
    t.artifacts[1].parse_status = "unreadable"  # allowed: the team goes to manual review instead
    assert checklist(t, hk(), NOW) == []


def test_solo_seeker_may_submit_below_minimum():
    lead = person("Lead")
    assert checklist(team([(lead, MemberStatus.CONFIRMED)], seeking=True), hk(), NOW) == []
    assert checklist(team([(lead, MemberStatus.CONFIRMED)], seeking=False), hk(), NOW)


def test_every_member_must_be_eligible():
    lead, b = person("Lead"), person("Bea", student=False)
    items = checklist(team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.CONFIRMED)]), hk(student_only=True), NOW)
    assert any(i.startswith("Bea:") and "students only" in i for i in items)
    c = person("Cy", dob=date(1990, 1, 1))
    items = checklist(team([(lead, MemberStatus.CONFIRMED), (c, MemberStatus.CONFIRMED)]), hk(age_max=25), NOW)
    assert any(i.startswith("Cy:") for i in items) and any(i.startswith("Lead:") and "date of birth" in i for i in items)


def test_closed_registration_blocks_submit():
    lead, b = person("Lead"), person("Bea")
    t = team([(lead, MemberStatus.CONFIRMED), (b, MemberStatus.CONFIRMED)])
    assert any("closed" in i for i in checklist(t, hk(registration_closes_at=NOW - timedelta(hours=1)), NOW))


def test_submitted_team_has_no_checklist():
    t = team([(person("Lead"), MemberStatus.CONFIRMED)])
    t.status = TeamStatus.SUBMITTED
    assert checklist(t, hk(), NOW) == []


def test_member_skills_reads_both_profile_formats():
    new = TeamMemberArtifact(parsed_profile={"resume": {"skills": [{"name": "React"}]}, "github": {"skills": [{"name": "Python"}]}})
    legacy = TeamMemberArtifact(parsed_profile={"skills": [{"name": "Docker"}]})
    assert [s["name"] for s in member_skills(new)] == ["React", "Python"]
    assert [s["name"] for s in member_skills(legacy)] == ["Docker"]
    assert member_skills(None) == []
