"""
Audit log ORM model.

Immutable append-only log of all significant system events.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only audit trail.

    Never update or delete rows from this table.
    """

    __tablename__ = "audit_logs"

    # Optional contextual foreign keys (nullable for system-level events)
    repair_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repair_attempts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Who/what produced the event
    actor: Mapped[str] = mapped_column(String(200), nullable=False)  # "system", "worker", etc.
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Human-readable summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured details (old_state, new_state, tool name, etc.)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Correlation / tracing
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
