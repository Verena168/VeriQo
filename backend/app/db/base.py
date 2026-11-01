import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Postgres ENUM that stores member values ("pending"), not names ("PENDING")."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
