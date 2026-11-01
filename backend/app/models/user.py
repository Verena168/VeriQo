import enum

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class UserRole(str, enum.Enum):
    PARTICIPANT = "participant"
    ORGANIZER = "organizer"
    JUDGE = "judge"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    github_url: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), default=UserRole.PARTICIPANT
    )
    # Output of the NLP service: {"skills": [...], "experience_level": "...", ...}
    parsed_skills: Mapped[dict | None] = mapped_column(JSONB)

    applications = relationship("Application", back_populates="user")
    team_memberships = relationship("TeamMember", back_populates="user")
    submissions = relationship("Submission", back_populates="user")
