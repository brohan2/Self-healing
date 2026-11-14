"""
Worker manager.

Starts and stops all background worker tasks within the FastAPI process.
Workers run as asyncio Tasks (not separate processes) — suitable for
the current scale. They can be moved to separate processes/containers later.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.observability.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

_tasks: list[asyncio.Task] = []


async def start_workers() -> None:
    """Spawn all worker coroutines as background asyncio tasks."""
    from app.workers.webhook_worker import WebhookWorker
    from app.workers.investigation_worker import InvestigationWorker

    workers = [
        WebhookWorker(),
        InvestigationWorker(),
    ]

    for worker in workers:
        task = asyncio.create_task(
            worker.start(),
            name=worker.__class__.__name__,
        )
        _tasks.append(task)
        logger.info("worker_task_created", worker=worker.__class__.__name__)


async def stop_workers() -> None:
    """Cancel all running worker tasks."""
    for task in _tasks:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
    _tasks.clear()
    logger.info("all_workers_stopped")
