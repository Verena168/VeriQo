import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, pg_enum


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    REVIEWED = "reviewed"  # a judge has looked at it and recorded a decision


class RiskLevel(str, enum.Enum):
    """Colour band shown on the organizer grid. Evidence for review, never an automatic verdict."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class OriginalityReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "originality_reports"
    __table_args__ = (
        CheckConstraint("plagiarism_score BETWEEN 0 AND 100", name="ck_plagiarism_score_range"),
        CheckConstraint("ai_generated_prob BETWEEN 0 AND 1", name="ck_ai_prob_range"),
        CheckConstraint("paste_ratio BETWEEN 0 AND 1", name="ck_paste_ratio_range"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[ReportStatus] = mapped_column(
        pg_enum(ReportStatus, "report_status"), default=ReportStatus.PENDING
    )

    # Module C: AST / token similarity against reference repos (percentage of matched code).
    plagiarism_score: Mapped[float | None] = mapped_column(Float)
    # Module C: AI-code detector output. Nullable and weak by design: detectors are unreliable
    # on code, so this is one signal alongside telemetry, not a deciding score.
    ai_generated_prob: Mapped[float | None] = mapped_column(Float)

    # Module B: telemetry summary, snapshotted from MongoDB when the report is generated.
    paste_ratio: Mapped[float | None] = mapped_column(Float)
    active_minutes: Mapped[int | None] = mapped_column(Integer)
    telemetry_coverage: Mapped[float | None] = mapped_column(Float)  # share of members with telemetry

    # Module C extras: share of code covered by allowed starter templates, and share that already
    # existed in the repo before the hackathon started (from git history).
    template_share: Mapped[float | None] = mapped_column(Float)
    pre_event_share: Mapped[float | None] = mapped_column(Float)
    telemetry_flag: Mapped[str | None] = mapped_column(String(20))  # low / medium / high / no_data

    risk_level: Mapped[RiskLevel | None] = mapped_column(pg_enum(RiskLevel, "risk_level"))
    # Explanations, per-member telemetry, top matched sources, commit stats.
    details: Mapped[dict | None] = mapped_column(JSONB)
    # Evidence behind the scores: [{"source_repo": ..., "file": ..., "lines": [a, b], "similarity": ...}]
    matches: Mapped[list | None] = mapped_column(JSONB)
    judge_notes: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submission = relationship("Submission", back_populates="report")
