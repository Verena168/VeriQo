"""Email one-time passcodes (OTP), e.g. a member confirming they agree to join a team.

The 6-digit code is sent by email and stored only as HMAC-SHA256(jwt_secret, code), so a database
leak doesn't reveal live codes. Codes expire, allow a limited number of guesses, and can be resent
only after a cooldown and a limited number of times.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import OtpCode


class OtpError(ValueError):
    """User-facing reason a code couldn't be issued or verified."""


def _hash(code: str) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _active(db: AsyncSession, user_id: uuid.UUID, purpose: str, subject_id: uuid.UUID | None) -> OtpCode | None:
    return await db.scalar(
        select(OtpCode)
        .where(OtpCode.user_id == user_id, OtpCode.purpose == purpose, OtpCode.subject_id == subject_id,
               OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )


async def issue(db: AsyncSession, user_id: uuid.UUID, purpose: str, subject_id: uuid.UUID | None = None) -> str:
    """Create (or replace) the code for this purpose and return it, for the caller to email.

    Enforces the resend cooldown and the maximum number of sends. The caller commits.
    """
    s = get_settings()
    now = datetime.now(timezone.utc)
    current = await _active(db, user_id, purpose, subject_id)
    code = generate_code()
    if current is None:
        db.add(OtpCode(user_id=user_id, purpose=purpose, subject_id=subject_id, code_hash=_hash(code),
                       expires_at=now + timedelta(minutes=s.otp_ttl_minutes), attempts=0, send_count=1,
                       last_sent_at=now))
        return code
    wait = s.otp_resend_cooldown_s - (now - current.last_sent_at).total_seconds()
    if wait > 0:
        raise OtpError(f"Please wait {int(wait) + 1} seconds before requesting another code")
    if current.send_count >= s.otp_max_sends:
        raise OtpError("Too many codes requested. Ask the team lead to remove and re-add you.")
    # A resend replaces the old code: only the newest one works, with a fresh lifetime and guesses.
    current.code_hash = _hash(code)
    current.expires_at = now + timedelta(minutes=s.otp_ttl_minutes)
    current.attempts = 0
    current.send_count += 1
    current.last_sent_at = now
    return code


async def verify(db: AsyncSession, user_id: uuid.UUID, purpose: str, code: str, subject_id: uuid.UUID | None = None) -> None:
    """Check a code; on success mark it used. Raises OtpError otherwise. The caller commits.

    Commit even on failure, so a wrong guess still counts against the attempt limit.
    """
    s = get_settings()
    now = datetime.now(timezone.utc)
    current = await _active(db, user_id, purpose, subject_id)
    if current is None:
        raise OtpError("No active code. Request a new one.")
    if now >= current.expires_at:
        raise OtpError("This code has expired. Request a new one.")
    if current.attempts >= s.otp_max_attempts:
        raise OtpError("Too many incorrect attempts. Request a new code.")
    current.attempts += 1
    code = (code or "").strip()
    if not (len(code) == 6 and code.isdigit()) or not hmac.compare_digest(current.code_hash, _hash(code)):
        left = s.otp_max_attempts - current.attempts
        raise OtpError(f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left." if left else
                       "Too many incorrect attempts. Request a new code.")
    current.consumed_at = now
