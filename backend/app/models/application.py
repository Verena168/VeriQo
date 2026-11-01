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
    """One registration per TEAM (a solo entrant is a team of one); see docs/STAGE1_DESIGN.md §2.5."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("hackathon_id", "team_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))  # the lead
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
    # Team-level document; members' CVs live in TeamMemberArtifact. GridFS id, see app/mongo/files.py.
    pitch_deck_file_id: Mapped[str | None] = mapped_column(String(24))
    review_note: Mapped[str | None] = mapped_column(String(500))  # e.g. why the resume was unreadable
    # The decision (status) is a draft until the organizer publishes results. Until then the
    # participant only ever sees "under review"; see services/visibility.py.
    decision_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    team = relationship("Team", back_populates="application")
    hackathon = relationship("Hackathon", back_populates="applications")
