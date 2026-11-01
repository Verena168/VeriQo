import enum
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class ReferenceKind(str, enum.Enum):
    REFERENCE = "reference"  # code that submissions must NOT copy (past projects, public repos)
    TEMPLATE = "template"  # starter code participants are ALLOWED to use; excluded from matching


class ReferenceRepo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Organizer-supplied repositories that make up the plagiarism corpus for one hackathon."""

    __tablename__ = "reference_repos"

    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hackathons.id", ondelete="CASCADE"), index=True
    )
    repo_url: Mapped[str] = mapped_column(String(500))
    label: Mapped[str] = mapped_column(String(200))
    kind: Mapped[ReferenceKind] = mapped_column(pg_enum(ReferenceKind, "reference_kind"))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / ready / failed
    error: Mapped[str | None] = mapped_column(String(500))

    hackathon = relationship("Hackathon", back_populates="reference_repos")
