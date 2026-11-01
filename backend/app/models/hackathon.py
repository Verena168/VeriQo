import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class ParticipationMode(str, enum.Enum):
    SOLO = "solo"
    TEAM = "team"


class ThemeImportance(str, enum.Enum):
    """How much the AI weighs past projects related to the theme / problem statement."""

    OFF = "off"
    NORMAL = "normal"
    HIGH = "high"


class Hackathon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hackathons"

    event_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[str | None] = mapped_column(String(120))
    problem_statement: Mapped[str | None] = mapped_column(Text)
    theme_importance: Mapped[ThemeImportance] = mapped_column(
        pg_enum(ThemeImportance, "theme_importance"), default=ThemeImportance.NORMAL, server_default="normal"
    )
    # "Stakes": [{"title": "Winner", "amount": 50000, "note": "..."}]
    prizes: Mapped[list | None] = mapped_column(JSONB)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, server_default="0")
    fee_currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    organizer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    # Applicants scoring at least this (0-100) are shortlisted automatically.
    shortlist_threshold: Mapped[float] = mapped_column(Float, default=60.0, server_default="60")
    participation_mode: Mapped[ParticipationMode] = mapped_column(
        pg_enum(ParticipationMode, "participation_mode"), default=ParticipationMode.TEAM, server_default="team"
    )
    min_team_size: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    max_team_size: Mapped[int] = mapped_column(SmallInteger, default=4, server_default="4")
    # Eligibility (checked per person at the event's start date; see services/eligibility.py).
    age_min: Mapped[int | None] = mapped_column(SmallInteger)
    age_max: Mapped[int | None] = mapped_column(SmallInteger)
    student_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Registration window; when unset, registration is open until the event ends.
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dynamic Stage 1 pipeline, validated by schemas.ShortlistConfig (docs/STAGE1_DESIGN.md §2.7).
    shortlist_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
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
