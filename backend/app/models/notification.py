import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Emails waiting to be sent (transactional outbox).

    A row is written in the same transaction as the change that causes the email, then the
    background sender (services/email.py) delivers it over SMTP with retries. So a status change
    can never commit without its email being queued, and a slow or failing SMTP server never
    blocks or breaks the API request.
    """

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_due", "status", "next_attempt_at"),)

    to_email: Mapped[str] = mapped_column(String(255))
    to_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    template: Mapped[str] = mapped_column(String(40))
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued / sent / failed
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class OtpCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A one-time passcode sent by email. The code itself is never stored, only its HMAC.

    (purpose, subject_id) say what the code confirms, e.g. ("team_join", team_id): generic so the
    same table serves team invitations now and email verification later.
    """

    __tablename__ = "otp_codes"
    __table_args__ = (Index("ix_otp_codes_lookup", "user_id", "purpose", "subject_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(30))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    send_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
