"""Declarative base and the column conventions every table shares.

Conventions live here rather than being repeated per model, so "UUID primary
keys, created_at/updated_at, schema_version on artifact rows" is enforced by
construction instead of by review.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints: Alembic cannot reliably drop unnamed ones in later migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """UUID primary key, generated application-side so it is known before insert."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampsMixin:
    """Creation and update timestamps, both database-generated and timezone-aware."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SchemaVersionMixin:
    """Artifact rows record the schema version they were written with (PRD §32)."""

    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
