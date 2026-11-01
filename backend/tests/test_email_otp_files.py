import smtplib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.models import EmailOutbox, OtpCode
from app.mongo import files
from app.services import email, otp


# ------------------------------------------------------------------ helpers

class FakeSession:
    """Just enough of AsyncSession for the services under test."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def scalar(self, _query):
        live = [r for r in self.added + self.rows if isinstance(r, OtpCode) and r.consumed_at is None]
        return live[-1] if live else None

    async def scalars(self, _query):
        return [r for r in self.rows if r.status == "queued"]

    async def commit(self):
        self.commits += 1


@pytest.fixture
def smtp_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_user", "team@example.com")
    monkeypatch.setattr(s, "smtp_password", "app-password")
    monkeypatch.setattr(s, "smtp_port", 587)
    return s


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, msg):
        self.sent.append(msg)


# ------------------------------------------------------------------ email

def test_templates_escape_input_and_never_mention_scores():
    r = email.render("application_received", {"name": "<script>x</script>", "hackathon": "Hack & Build"})
    assert "<script>" not in r.html and "&lt;script&gt;" in r.html
    assert "Hack &amp; Build" in r.html
    for text in (r.text.lower(), r.html.lower()):
        assert "score" not in text  # the AI score is never disclosed to participants
    assert "under review" in r.text


def test_unknown_template_and_missing_context_fail_fast():
    with pytest.raises(ValueError):
        email.render("nope", {})
    with pytest.raises(KeyError):
        email.enqueue(FakeSession(), "a@b.c", "application_received", {"name": "x"})


def test_subject_cannot_inject_headers(smtp_settings):
    msg = email.build_message("to@example.com", email.Rendered("Hi\r\nBcc: evil@example.com", "t", "<p>h</p>"))
    assert "\n" not in msg["Subject"] and msg["Bcc"] is None


def test_smtp_starttls_then_login_then_send(smtp_settings, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    msg = email.build_message("to@example.com", email.render("test", {}))
    email.send_blocking(msg)
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.calls[:2] == ["starttls", ("login", "team@example.com")]  # never log in before TLS
    assert smtp.sent[0]["To"] == "to@example.com"
    assert smtp.sent[0].get_content_type() == "multipart/alternative"  # text + HTML parts


def test_port_465_uses_implicit_ssl(smtp_settings, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtp_settings, "smtp_port", 465)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("plain SMTP used on port 465"))
    email.send_blocking(email.build_message("to@example.com", email.render("test", {})))
    assert "starttls" not in FakeSMTP.instances[0].calls


def _row(template="test", context=None):
    return EmailOutbox(id=uuid.uuid4(), to_email="student@college.edu", template=template, context=context or {},
                       status="queued", attempts=0, next_attempt_at=datetime.now(timezone.utc))


async def test_failed_send_backs_off_then_gives_up(smtp_settings, monkeypatch):
    async def boom(_row):
        raise smtplib.SMTPServerDisconnected("down")
    monkeypatch.setattr(email, "deliver", boom)
    row = _row()
    now = datetime.now(timezone.utc)
    for expected in email.BACKOFF_MINUTES[:-1]:
        await email.process_due(FakeSession([row]), now)
        assert row.status == "queued" and row.next_attempt_at == now + timedelta(minutes=expected)
    await email.process_due(FakeSession([row]), now)
    assert row.status == "failed" and row.attempts == len(email.BACKOFF_MINUTES)


async def test_bad_credentials_fail_immediately(smtp_settings, monkeypatch):
    async def denied(_row):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
    monkeypatch.setattr(email, "deliver", denied)
    row = _row()
    await email.process_due(FakeSession([row]))
    assert row.status == "failed" and row.attempts == 1 and "535" in row.last_error


async def test_otp_code_is_redacted_once_sent(monkeypatch):
    async def ok(_row):
        return None
    monkeypatch.setattr(email, "deliver", ok)
    row = _row("team_invite_otp", {"name": "A", "lead": "B", "team": "T", "hackathon": "H", "ttl_minutes": 15, "code": "123456"})
    await email.process_due(FakeSession([row]))
    assert row.status == "sent" and row.context["code"] == "[redacted]"


async def test_console_mode_without_credentials(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_user", "")
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP used without credentials"))
    row = _row()
    await email.process_due(FakeSession([row]))
    assert row.status == "sent"


# ------------------------------------------------------------------ otp

async def test_otp_issue_verify_and_single_use():
    db, user, subject = FakeSession(), uuid.uuid4(), uuid.uuid4()
    code = await otp.issue(db, user, "team_join", subject)
    stored = db.added[0]
    assert len(code) == 6 and code.isdigit()
    assert code not in stored.code_hash and len(stored.code_hash) == 64  # only the HMAC is stored
    await otp.verify(db, user, "team_join", code, subject)
    assert stored.consumed_at is not None
    with pytest.raises(otp.OtpError, match="No active code"):
        await otp.verify(db, user, "team_join", code, subject)


async def test_otp_wrong_guesses_lock_out():
    db, user = FakeSession(), uuid.uuid4()
    code = await otp.issue(db, user, "team_join")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(get_settings().otp_max_attempts):
        with pytest.raises(otp.OtpError):
            await otp.verify(db, user, "team_join", wrong)
    with pytest.raises(otp.OtpError, match="Too many"):
        await otp.verify(db, user, "team_join", code)  # even the right code is refused now


async def test_otp_expiry_and_resend_rules():
    db, user = FakeSession(), uuid.uuid4()
    code = await otp.issue(db, user, "team_join")
    stored = db.added[0]
    with pytest.raises(otp.OtpError, match="wait"):
        await otp.issue(db, user, "team_join")  # inside the cooldown
    stored.last_sent_at -= timedelta(seconds=get_settings().otp_resend_cooldown_s + 1)
    new_code = await otp.issue(db, user, "team_join")  # resend replaces the code
    assert stored.send_count == 2
    if new_code != code:
        with pytest.raises(otp.OtpError, match="Incorrect"):
            await otp.verify(db, user, "team_join", code)
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(otp.OtpError, match="expired"):
        await otp.verify(db, user, "team_join", new_code)


# ------------------------------------------------------------------ file validation

@pytest.mark.parametrize("name,data,ok", [
    ("cv.pdf", b"%PDF-1.7 ...", True),
    ("cv.PDF", b"%PDF-1.4 ...", True),
    ("cv.pdf", b"<html>not a pdf</html>", False),          # extension lies
    ("cv.exe", b"%PDF-1.7 ...", False),                     # content fine, extension not allowed
    ("cv.docx", b"PK\x03\x04rest-of-zip", True),
    ("cv.txt", "Résumé — Python, React".encode(), True),
    ("cv.txt", b"MZ\x90\x00\x03binary", False),             # binary pretending to be text
    ("cv.pdf", b"", False),
])
def test_cv_validation_by_content(name, data, ok):
    if ok:
        assert files.validate(files.CV, name, data)
    else:
        with pytest.raises(files.FileRejected):
            files.validate(files.CV, name, data)


def test_size_limits():
    with pytest.raises(files.FileRejected, match="5 MB"):
        files.validate(files.CV, "cv.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024))
    assert files.validate(files.PITCH_DECK, "deck.pptx", b"PK\x03\x04" + b"0" * 100)
    with pytest.raises(files.FileRejected):
        files.validate(files.PITCH_DECK, "deck.docx", b"PK\x03\x04")  # a ZIP, but not a deck


async def test_suppressed_demo_domains_are_skipped(smtp_settings, monkeypatch):
    async def must_not_send(_row):
        pytest.fail("email sent to a suppressed domain")
    monkeypatch.setattr(email, "deliver", must_not_send)
    row = _row()
    row.to_email = "meera.iyer@Demo.Veriqo.Dev"
    await email.process_due(FakeSession([row]))
    assert row.status == "skipped" and row.attempts == 0
