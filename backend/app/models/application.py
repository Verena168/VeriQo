import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, pg_enum


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"  # unreadable resume -> manual organizer review


class Application(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "hackathon_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id"), index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        default=ApplicationStatus.PENDING,
    )
    score: Mapped[float | None] = mapped_column(Float)  # compatibility 0-100
    # Per-requirement explanation from the matcher: [{"skill", "weight", "matched_by", "evidence", "score"}]
    match_details: Mapped[list | None] = mapped_column(JSONB)
    resume_filename: Mapped[str | None] = mapped_column(String(255))
    review_note: Mapped[str | None] = mapped_column(String(500))  # e.g. why the resume was unreadable
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="applications")
    hackathon = relationship("Hackathon", back_populates="applications")
