"""Email via Python's built-in smtplib (Gmail SMTP), delivered through the outbox table.

Flow: code that needs to email calls `enqueue(...)` inside its own DB transaction; the background
`run_sender()` loop (started in app.main) picks due rows and sends them with retries and backoff.

smtplib is blocking, so each send runs in a worker thread (asyncio.to_thread) and never stalls the
event loop. With no SMTP credentials configured, emails are written to the log instead ("console
mode"), so development and the demo work without a Gmail account.
"""

import asyncio
import html
import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import EmailOutbox

log = logging.getLogger("uvicorn.error")

BACKOFF_MINUTES = [1, 5, 15, 60, 360]  # after attempts 1..5; then the email is marked failed
BATCH_SIZE = 20
POLL_SECONDS = 5


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


# ------------------------------------------------------------------ templates

def _layout(title: str, paragraphs: list[str], code: str | None = None, link: tuple[str, str] | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 14px">{p}</p>' for p in paragraphs)
    if code:
        body += (f'<p style="font-size:28px;letter-spacing:6px;font-weight:700;font-family:monospace;'
                 f'margin:8px 0 18px">{html.escape(code)}</p>')
    if link:
        body += (f'<p><a href="{html.escape(link[1], quote=True)}" style="background:#2a78d6;color:#fff;'
                 f'padding:10px 16px;border-radius:8px;text-decoration:none">{html.escape(link[0])}</a></p>')
    return (f'<div style="font-family:system-ui,Segoe UI,sans-serif;max-width:520px;color:#0b0b0b">'
            f'<h2 style="margin:0 0 16px">{html.escape(title)}</h2>{body}'
            f'<p style="color:#898781;font-size:12px;margin-top:24px">Sent by VERIQO. '
            f'If you did not expect this email, you can ignore it.</p></div>')


def render(template: str, ctx: dict) -> Rendered:
    """Build subject, plain-text and HTML bodies. Every context value is escaped for HTML."""
    e = {k: html.escape(str(v)) for k, v in ctx.items()}
    app_url = get_settings().frontend_url.rstrip("/")

    if template == "application_received":
        # Deliberately says nothing about scores: the AI score is never shown to participants.
        title = f"Application received: {ctx['hackathon']}"
        lines = [f"Hi {e['name']},",
                 f"You have successfully registered for <b>{e['hackathon']}</b>.",
                 "Your application is under review, and you will be notified of your shortlisting status soon."]
        text = (f"Hi {ctx['name']},\n\nYou have successfully registered for {ctx['hackathon']}.\n"
                "Your application is under review, and you will be notified of your shortlisting status soon.\n")
        return Rendered(title, text, _layout(title, lines, link=("View your dashboard", f"{app_url}/hackathons")))

    if template == "team_invite_otp":
        title = f"Confirm joining {ctx['team']}"
        lines = [f"Hi {e['name']},",
                 f"<b>{e['lead']}</b> has added you to the team <b>{e['team']}</b> for <b>{e['hackathon']}</b>.",
                 f"To confirm that you agree to join, sign in to VERIQO and enter this code. "
                 f"It expires in {e['ttl_minutes']} minutes."]
        text = (f"Hi {ctx['name']},\n\n{ctx['lead']} has added you to the team {ctx['team']} for {ctx['hackathon']}.\n"
                f"To confirm, sign in to VERIQO and enter this code: {ctx['code']}\n"
                f"It expires in {ctx['ttl_minutes']} minutes. If you don't want to join, ignore this email.\n")
        return Rendered(title, text, _layout(title, lines, code=ctx["code"], link=("Open VERIQO", f"{app_url}/hackathons")))

    if template in ("result_shortlisted", "result_rejected", "result_waitlisted"):
        outcome = {"result_shortlisted": "Congratulations, your team has been shortlisted",
                   "result_waitlisted": "Your team has been placed on the waitlist",
                   "result_rejected": "Your team was not shortlisted this time"}[template]
        title = f"{ctx['hackathon']}: shortlisting results"
        lines = [f"Hi {e['name']},", f"{html.escape(outcome)} for <b>{e['hackathon']}</b>.",
                 "Sign in to VERIQO for details and next steps."]
        text = f"Hi {ctx['name']},\n\n{outcome} for {ctx['hackathon']}.\nSign in to VERIQO for details and next steps.\n"
        return Rendered(title, text, _layout(title, lines, link=("View results", f"{app_url}/hackathons")))

    if template == "test":
        title = "VERIQO email test"
        text = "If you can read this, VERIQO's Gmail SMTP settings work.\n"
        return Rendered(title, text, _layout(title, ["If you can read this, VERIQO's Gmail SMTP settings work."]))

    raise ValueError(f"unknown email template: {template}")


# ------------------------------------------------------------------ queueing

def enqueue(db: AsyncSession, to_email: str, template: str, context: dict, to_user_id=None) -> EmailOutbox:
    """Add an email to the outbox in the caller's transaction (it is sent after the caller commits)."""
    render(template, context)  # fail fast on a bad template or missing context key
    row = EmailOutbox(to_email=to_email, to_user_id=to_user_id, template=template, context=context,
                      status="queued", attempts=0, next_attempt_at=datetime.now(timezone.utc))
    db.add(row)
    return row


# ------------------------------------------------------------------ sending

def smtp_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_user and s.smtp_password)


def build_message(to_email: str, rendered: Rendered) -> EmailMessage:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = formataddr((s.smtp_from_name, s.smtp_user or "veriqo@localhost"))
    msg["To"] = to_email
    msg["Subject"] = rendered.subject.replace("\r", " ").replace("\n", " ")  # no header injection
    msg["Message-ID"] = make_msgid(domain="veriqo.local")
    msg.set_content(rendered.text)
    msg.add_alternative(rendered.html, subtype="html")
    return msg


def send_blocking(msg: EmailMessage) -> None:
    """Deliver one message with smtplib. Runs in a worker thread. Raises on failure."""
    s = get_settings()
    context = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s, context=context) as smtp:
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s) as smtp:
            smtp.starttls(context=context)
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


async def deliver(row: EmailOutbox) -> None:
    rendered = render(row.template, row.context)
    if not smtp_configured():
        log.info("EMAIL (console mode, SMTP not configured) to=%s subject=%r\n%s", row.to_email, rendered.subject, rendered.text)
        return
    await asyncio.to_thread(send_blocking, build_message(row.to_email, rendered))


async def process_due(db: AsyncSession, now: datetime | None = None) -> int:
    """Send up to BATCH_SIZE due emails. Returns how many were attempted."""
    now = now or datetime.now(timezone.utc)
    rows = list(await db.scalars(
        select(EmailOutbox)
        .where(EmailOutbox.status == "queued", EmailOutbox.next_attempt_at <= now)
        .order_by(EmailOutbox.next_attempt_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)  # safe if more than one API process runs the sender
    ))
    for row in rows:
        row.attempts += 1
        try:
            await deliver(row)
            row.status, row.sent_at, row.last_error = "sent", datetime.now(timezone.utc), None
        except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
            row.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if isinstance(exc, smtplib.SMTPAuthenticationError) or row.attempts >= len(BACKOFF_MINUTES):
                row.status = "failed"  # wrong credentials won't fix themselves by retrying
                log.warning("Email %s to %s failed permanently: %s", row.id, row.to_email, row.last_error)
            else:
                row.next_attempt_at = now + timedelta(minutes=BACKOFF_MINUTES[row.attempts - 1])
        if row.status != "queued" and "code" in row.context:
            # OTP codes must not stay readable in the database once the email is done with.
            row.context = {**row.context, "code": "[redacted]"}
    await db.commit()
    return len(rows)


async def run_sender(stop: asyncio.Event) -> None:
    """Background loop started by the API; sends queued emails until `stop` is set."""
    if not smtp_configured():
        log.warning("SMTP not configured (SMTP_USER/SMTP_PASSWORD): emails will be logged, not sent")
    while not stop.is_set():
        try:
            async with SessionLocal() as db:
                busy = await process_due(db)
        except Exception as exc:  # e.g. database briefly unreachable: keep the loop alive
            log.warning("Email sender error: %s", exc)
            busy = 0
        if not busy:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
