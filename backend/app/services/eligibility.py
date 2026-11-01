"""Hackathon eligibility rules, checked on the server when someone registers.

Eligibility is a pass/fail gate, never part of the AI score: an ineligible applicant is stopped at
registration instead of being ranked lower (docs/STAGE1_DESIGN.md §3.6).
"""

from datetime import date, datetime, timezone

from app.models import Hackathon, User


def age_on(dob: date, day: date) -> int:
    return day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day))


def person_violations(user: User, hk: Hackathon) -> list[str]:
    """Reasons this person may not take part (empty list = eligible)."""
    problems = []
    if hk.age_min is not None or hk.age_max is not None:
        if user.date_of_birth is None:
            problems.append("Add your date of birth to your profile: this hackathon has an age requirement.")
        else:
            age = age_on(user.date_of_birth, hk.start_date.date())
            if hk.age_min is not None and age < hk.age_min:
                problems.append(f"You must be at least {hk.age_min} when the hackathon starts (you will be {age}).")
            if hk.age_max is not None and age > hk.age_max:
                problems.append(f"You must be {hk.age_max} or younger when the hackathon starts (you will be {age}).")
    if hk.student_only and not user.is_student:
        problems.append("This hackathon is for students only. Mark yourself as a student in your profile if you are one.")
    return problems


def registration_problem(hk: Hackathon, now: datetime | None = None) -> str | None:
    """Why registration is closed right now, or None if it is open."""
    now = now or datetime.now(timezone.utc)
    if hk.registration_opens_at and now < hk.registration_opens_at:
        return f"Registration opens on {hk.registration_opens_at:%d %b %Y, %H:%M} UTC."
    closes = hk.registration_closes_at or hk.end_date
    if now > closes:
        return "Registration for this hackathon has closed."
    return None
