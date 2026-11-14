"""
Investigation Worker.

Consumes from: autofix:investigations
Produces to:   autofix:repairs (Phase 3+)

For each message:
1. Load RepairAttempt + Investigation from DB
2. Transition RepairAttempt → FETCHING_LOGS → INVESTIGATING
3. Run InvestigationEngine
4. Transition → ANALYZING_REPOSITORY (Phase 3) or ESCALATED (unknown)
5. Write audit log
6. Enqueue to repair stream (Phase 3)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog
from app.db.models.investigation import Investigation, InvestigationStatus
from app.db.models.repair import RepairAttempt, RepairStatus, VALID_TRANSITIONS
from app.db.session import get_db_session
from app.observability.logging import get_logger
from app.services.github.client import GitHubClient
from app.services.investigation.engine import InvestigationEngine
from app.workers.base import BaseWorker

logger = get_logger(__name__)


class InvestigationWorker(BaseWorker):
    """Processes investigation jobs from the autofix:investigations stream."""

    def __init__(self) -> None:
        from app.config import get_settings
        settings = get_settings()
        super().__init__(stream_key=settings.redis_stream_investigations)
        self._settings = settings

    async def process_message(
        self,
        message_id: str,
        fields: dict[str, str],
    ) -> None:
        repair_attempt_id = fields.get("repair_attempt_id")
        investigation_id = fields.get("investigation_id")
        workflow_run_id = fields.get("workflow_run_id")
        installation_id_str = fields.get("installation_id")

        if not all([repair_attempt_id, investigation_id, workflow_run_id, installation_id_str]):
            logger.warning(
                "investigation_worker_missing_fields",
                fields=list(fields.keys()),
                message_id=message_id,
            )
            return

        installation_id = int(installation_id_str)

        async with get_db_session() as db:
            await self._run_investigation(
                db=db,
                repair_attempt_id=uuid.UUID(repair_attempt_id),
                investigation_id=uuid.UUID(investigation_id),
                workflow_run_id=uuid.UUID(workflow_run_id),
                installation_id=installation_id,
            )

    async def _run_investigation(
        self,
        db: AsyncSession,
        repair_attempt_id: uuid.UUID,
        investigation_id: uuid.UUID,
        workflow_run_id: uuid.UUID,
        installation_id: int,
    ) -> None:
        # ------------------------------------------------------------------ #
        # 1. Load repair attempt
        # ------------------------------------------------------------------ #
        ra_result = await db.execute(
            select(RepairAttempt).where(RepairAttempt.id == repair_attempt_id)
        )
        repair_attempt = ra_result.scalar_one_or_none()
        if not repair_attempt:
            logger.error(
                "investigation_worker_repair_attempt_not_found",
                repair_attempt_id=str(repair_attempt_id),
            )
            return

        # ------------------------------------------------------------------ #
        # 2. Transition: RECEIVED → VALIDATING → FETCHING_LOGS
        # ------------------------------------------------------------------ #
        if not self._transition(repair_attempt, RepairStatus.VALIDATING):
            return
        await db.flush()

        if not self._transition(repair_attempt, RepairStatus.FETCHING_LOGS):
            return
        await db.flush()

        logger.info(
            "investigation_worker_fetching_logs",
            repair_attempt_id=str(repair_attempt_id),
            installation_id=installation_id,
        )

        # ------------------------------------------------------------------ #
        # 3. Transition: FETCHING_LOGS → INVESTIGATING
        # ------------------------------------------------------------------ #
        if not self._transition(repair_attempt, RepairStatus.INVESTIGATING):
            return
        await db.flush()

        # ------------------------------------------------------------------ #
        # 4. Run investigation engine
        # ------------------------------------------------------------------ #
        try:
            github_client = GitHubClient()
            engine = InvestigationEngine(db=db, github_client=github_client)
            investigation = await engine.investigate(
                workflow_run_id=workflow_run_id,
                installation_id=installation_id,
            )

            # ------------------------------------------------------------------ #
            # 5. Decide next state based on result
            # ------------------------------------------------------------------ #
            from app.db.models.investigation import FailureCategory
            if (
                investigation.failure_category == FailureCategory.UNKNOWN.value
                and (investigation.confidence or 0) < 0.4
            ):
                # Too uncertain — escalate for human review
                self._transition(repair_attempt, RepairStatus.ESCALATED)
                repair_attempt.error_message = (
                    f"Low confidence ({investigation.confidence}) UNKNOWN failure. "
                    "Escalated for human review."
                )
                logger.warning(
                    "investigation_worker_escalating",
                    repair_attempt_id=str(repair_attempt_id),
                    confidence=investigation.confidence,
                )
            else:
                # Proceed to repository analysis (Phase 3)
                self._transition(repair_attempt, RepairStatus.ANALYZING_REPOSITORY)
                # Enqueue to repairs stream (Phase 3 will consume this)
                await self.publish(
                    self._settings.redis_stream_repairs,
                    {
                        "repair_attempt_id": str(repair_attempt_id),
                        "investigation_id": str(investigation.id),
                        "workflow_run_id": str(workflow_run_id),
                        "installation_id": str(installation_id),
                        "failure_category": investigation.failure_category or "UNKNOWN",
                    },
                )
                logger.info(
                    "investigation_worker_enqueued_repair",
                    repair_attempt_id=str(repair_attempt_id),
                    category=investigation.failure_category,
                    confidence=investigation.confidence,
                )

            await db.flush()

        except Exception as exc:
            logger.error(
                "investigation_worker_investigation_failed",
                repair_attempt_id=str(repair_attempt_id),
                error=str(exc),
            )
            self._transition(repair_attempt, RepairStatus.FAILED)
            repair_attempt.error_message = str(exc)[:500]
            await db.flush()
            raise

        # ------------------------------------------------------------------ #
        # 6. Audit log
        # ------------------------------------------------------------------ #
        audit = AuditLog(
            repair_attempt_id=repair_attempt.id,
            investigation_id=investigation_id,
            actor="investigation_worker",
            action="investigation_completed",
            summary=f"Investigation completed: {repair_attempt.status}",
            details={
                "failure_category": investigation.failure_category,
                "confidence": investigation.confidence,
                "new_status": repair_attempt.status,
            },
        )
        db.add(audit)
        await db.flush()

    @staticmethod
    def _transition(repair_attempt: RepairAttempt, new_status: RepairStatus) -> bool:
        """
        Apply a state transition if it's valid.

        Returns True on success, False (with a log warning) if invalid.
        """
        current = RepairStatus(repair_attempt.status)
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            logger.warning(
                "invalid_state_transition",
                current=current,
                attempted=new_status,
                repair_attempt_id=str(repair_attempt.id),
            )
            return False
        repair_attempt.status = new_status.value
        logger.debug(
            "state_transition",
            from_state=current,
            to_state=new_status,
            repair_attempt_id=str(repair_attempt.id),
        )
        return True
