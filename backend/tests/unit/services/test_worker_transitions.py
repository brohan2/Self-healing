"""
Unit tests for state-machine transitions inside workers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from app.db.models.repair import RepairAttempt, RepairStatus, VALID_TRANSITIONS
from app.workers.investigation_worker import InvestigationWorker


@dataclass
class _FakeRepairAttempt:
    """Lightweight stand-in for RepairAttempt that avoids SQLAlchemy instrumentation."""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: str = RepairStatus.RECEIVED.value


class TestStateTransitions:
    """Test the _transition helper used in workers."""

    def test_valid_transition_succeeds(self) -> None:
        ra = _FakeRepairAttempt(status=RepairStatus.RECEIVED.value)
        # RECEIVED → VALIDATING is the first worker step
        result = InvestigationWorker._transition(ra, RepairStatus.VALIDATING)  # type: ignore[arg-type]
        assert result is True
        assert ra.status == RepairStatus.VALIDATING.value
        # VALIDATING → FETCHING_LOGS
        result2 = InvestigationWorker._transition(ra, RepairStatus.FETCHING_LOGS)  # type: ignore[arg-type]
        assert result2 is True
        assert ra.status == RepairStatus.FETCHING_LOGS.value

    def test_invalid_transition_returns_false(self) -> None:
        """Cannot jump from RECEIVED directly to TESTING."""
        ra = _FakeRepairAttempt(status=RepairStatus.RECEIVED.value)
        result = InvestigationWorker._transition(ra, RepairStatus.TESTING)  # type: ignore[arg-type]
        assert result is False
        # Status must remain unchanged
        assert ra.status == RepairStatus.RECEIVED.value

    def test_terminal_state_cannot_transition(self) -> None:
        ra = _FakeRepairAttempt(status=RepairStatus.COMPLETED.value)
        result = InvestigationWorker._transition(ra, RepairStatus.FAILED)  # type: ignore[arg-type]
        assert result is False

    def test_received_to_failed_is_valid(self) -> None:
        """Direct failure from RECEIVED must be allowed."""
        ra = _FakeRepairAttempt(status=RepairStatus.RECEIVED.value)
        result = InvestigationWorker._transition(ra, RepairStatus.FAILED)  # type: ignore[arg-type]
        assert result is True

    def test_all_transitions_lead_to_valid_states(self) -> None:
        """Every listed destination state must exist in RepairStatus."""
        all_statuses = set(RepairStatus)
        for _from, destinations in VALID_TRANSITIONS.items():
            for dest in destinations:
                assert dest in all_statuses, f"{dest} not in RepairStatus"
