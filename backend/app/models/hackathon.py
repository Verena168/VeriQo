import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Hackathon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hackathons"

    event_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    organizer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    # Applicants scoring at least this (0-100) are shortlisted automatically.
    shortlist_threshold: Mapped[float] = mapped_column(Float, default=60.0, server_default="60")
    max_team_size: Mapped[int] = mapped_column(SmallInteger, default=4, server_default="4")
    # Set when the organizer publishes shortlisting results (re-publishing updates it).
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Off by default: AI scores stay hidden from participants even after results are published.
    is_score_published: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    requirements = relationship(
        "HackathonRequirement", back_populates="hackathon", cascade="all, delete-orphan"
    )
    teams = relationship("Team", back_populates="hackathon")
    applications = relationship("Application", back_populates="hackathon")
    submissions = relationship("Submission", back_populates="hackathon")
    reference_repos = relationship("ReferenceRepo", back_populates="hackathon", cascade="all, delete-orphan")


class HackathonRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "hackathon_requirements"

    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(SmallInteger, default=1)  # weight in match score
    description: Mapped[str | None] = mapped_column(Text)

    hackathon = relationship("Hackathon", back_populates="requirements")
