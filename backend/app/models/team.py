import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("hackathon_id", "team_name"),)

    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id", ondelete="CASCADE"), index=True
    )
    team_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    hackathon = relationship("Hackathon", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="team")


class TeamMember(Base):
    """Association between TEAM and USER (the M:N "has members" edge in the ER diagram)."""

    __tablename__ = "team_members"
    # hackathon_id is denormalised here so the DB itself guarantees one team per user per event.
    __table_args__ = (UniqueConstraint("hackathon_id", "user_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id", ondelete="CASCADE")
    )
    role: Mapped[str | None] = mapped_column(String(60))  # e.g. "frontend", "ml"
    # True when the member was placed by the team-formation algorithm rather than self-joined.
    ai_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")
