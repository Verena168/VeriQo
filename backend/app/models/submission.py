import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, pg_enum


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    LOCKED = "locked"  # deadline passed, no further edits
    SCANNING = "scanning"  # integrity engine running
    SCANNED = "scanned"
    SCAN_FAILED = "scan_failed"


class Submission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "submissions"
    # A team submits once per hackathon (re-submits update the row). Solo entries have
    # team_id NULL, which Postgres treats as distinct, so they are not constrained here.
    __table_args__ = (UniqueConstraint("hackathon_id", "team_id"),)

    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id"), index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )  # the member who submitted
    project_title: Mapped[str] = mapped_column(String(200))
    repository_url: Mapped[str] = mapped_column(String(500))
    # Pin the exact commit that was scanned so the report stays reproducible after later pushes.
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[SubmissionStatus] = mapped_column(
        pg_enum(SubmissionStatus, "submission_status"),
        default=SubmissionStatus.SUBMITTED,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    hackathon = relationship("Hackathon", back_populates="submissions")
    team = relationship("Team", back_populates="submissions")
    user = relationship("User", back_populates="submissions")
    report = relationship(
        "OriginalityReport", back_populates="submission", uselist=False, cascade="all, delete-orphan"
    )
