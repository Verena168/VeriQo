import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class TeamStatus(str, enum.Enum):
    DRAFT = "draft"            # the lead is still assembling the team
    SUBMITTED = "submitted"    # registration submitted: locked, has an application
    WITHDRAWN = "withdrawn"
    MERGED = "merged"          # a solo registrant's team, merged into an AI-formed team


class MemberStatus(str, enum.Enum):
    INVITED = "invited"        # OTP sent; waiting for the member to confirm in their own account
    CONFIRMED = "confirmed"    # the member agreed to join (or is the lead)
    DECLINED = "declined"
    REMOVED = "removed"        # removed by the lead before submission, or moved by a merge


# Statuses that occupy a person's single slot in a hackathon (one live team per person).
ACTIVE_MEMBER_STATUSES = (MemberStatus.INVITED, MemberStatus.CONFIRMED)


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("hackathon_id", "team_name"),)

    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id", ondelete="CASCADE"), index=True
    )
    team_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[TeamStatus] = mapped_column(
        pg_enum(TeamStatus, "team_status"), default=TeamStatus.DRAFT, server_default="draft"
    )
    formed_by: Mapped[str] = mapped_column(String(10), default="self", server_default="self")  # "self" / "ai"
    # A solo registrant in a team event who wants the organizer's AI to place them in a team.
    seeking_teammates: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    hackathon = relationship("Hackathon", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    artifacts = relationship("TeamMemberArtifact", back_populates="team", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="team")
    application = relationship("Application", back_populates="team", uselist=False)


class TeamMember(Base):
    """Association between TEAM and USER (the M:N "has members" edge in the ER diagram)."""

    __tablename__ = "team_members"
    # One live team per person per hackathon. Declined/removed rows are history and don't count,
    # so a person who declined one invitation can still join another team.
    __table_args__ = (
        Index("uq_team_members_active", "hackathon_id", "user_id", unique=True,
              postgresql_where=text("status IN ('invited', 'confirmed')")),
    )

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
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[MemberStatus] = mapped_column(
        pg_enum(MemberStatus, "member_status"), default=MemberStatus.CONFIRMED, server_default="confirmed"
    )
    joined_at: Mapped[datetime] = mapped_column(  # when invited / added
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")


class TeamMemberArtifact(TimestampMixin, Base):
    """Each member's CV and GitHub profile for one team's registration.

    Snapshotted per registration, so a later profile change doesn't alter what was evaluated.
    """

    __tablename__ = "team_member_artifacts"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    cv_file_id: Mapped[str | None] = mapped_column(String(24))  # GridFS ObjectId (app/mongo/files.py)
    cv_filename: Mapped[str | None] = mapped_column(String(255))
    github_url: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # pending -> ok / unreadable / failed; parsed_profile holds the NLP output (skills, experience, github)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    parse_note: Mapped[str | None] = mapped_column(String(500))
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    team = relationship("Team", back_populates="artifacts")
