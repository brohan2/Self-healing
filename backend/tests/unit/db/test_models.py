"""
Unit tests for ORM models.

Verifies that models can be instantiated, persisted and queried
via the in-memory SQLite engine provided by conftest.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github import GitHubInstallation, Repository, User, WebhookEvent
from app.db.models.investigation import Investigation
from app.db.models.repair import RepairAttempt, RepairStatus, VALID_TRANSITIONS
from app.db.models.workflow import WorkflowRun


class TestUserModel:
    @pytest.mark.asyncio
    async def test_create_and_retrieve_user(self, db_session: AsyncSession) -> None:
        user = User(email="test@example.com", display_name="Test User")
        db_session.add(user)
        await db_session.flush()

        result = await db_session.execute(select(User).where(User.email == "test@example.com"))
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.display_name == "Test User"
        assert found.is_active is True
        assert isinstance(found.id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_user_uuid_is_unique(self, db_session: AsyncSession) -> None:
        u1 = User(email="a@example.com", display_name="A")
        u2 = User(email="b@example.com", display_name="B")
        db_session.add_all([u1, u2])
        await db_session.flush()
        assert u1.id != u2.id


class TestWebhookEventModel:
    @pytest.mark.asyncio
    async def test_create_webhook_event(self, db_session: AsyncSession) -> None:
        event = WebhookEvent(
            github_delivery_id="abc-delivery-001",
            event_type="workflow_run",
            action="completed",
            raw_payload={"action": "completed"},
        )
        db_session.add(event)
        await db_session.flush()

        result = await db_session.execute(
            select(WebhookEvent).where(
                WebhookEvent.github_delivery_id == "abc-delivery-001"
            )
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.processed is False
        assert found.event_type == "workflow_run"


class TestRepairStatus:
    def test_valid_transitions_from_received(self) -> None:
        allowed = VALID_TRANSITIONS[RepairStatus.RECEIVED]
        assert RepairStatus.VALIDATING in allowed
        assert RepairStatus.FAILED in allowed

    def test_completed_has_no_transitions(self) -> None:
        assert len(VALID_TRANSITIONS[RepairStatus.COMPLETED]) == 0

    def test_failed_has_no_transitions(self) -> None:
        assert len(VALID_TRANSITIONS[RepairStatus.FAILED]) == 0

    def test_escalated_has_no_transitions(self) -> None:
        assert len(VALID_TRANSITIONS[RepairStatus.ESCALATED]) == 0

    def test_all_states_have_transition_entries(self) -> None:
        for status in RepairStatus:
            assert status in VALID_TRANSITIONS, f"{status} missing from VALID_TRANSITIONS"

    def test_no_transition_back_to_received(self) -> None:
        """RECEIVED must not be reachable from any other state."""
        for _from, destinations in VALID_TRANSITIONS.items():
            if _from != RepairStatus.RECEIVED:
                assert RepairStatus.RECEIVED not in destinations
