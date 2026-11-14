"""
Base Redis Streams worker.

Implements the consumer group pattern:
- XREADGROUP to claim messages
- XACK to acknowledge after successful processing
- XAUTOCLAIM to recover messages from crashed workers
- Graceful shutdown on SIGTERM

Workers are run as asyncio tasks inside the FastAPI process.
Each worker loop:
1. Tries to claim stale messages from crashed workers (XAUTOCLAIM)
2. Reads new messages for itself (XREADGROUP)
3. Processes each message
4. ACKs on success; leaves in PEL on failure so it can be retried

Never rely on Redis for durable state — always checkpoint to Postgres first.
"""
from __future__ import annotations

import asyncio
import json
import signal
import socket
from abc import ABC, abstractmethod
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

# How long a message must sit in the PEL before we auto-claim it (ms)
_AUTOCLAIM_MIN_IDLE_MS = 10 * 60 * 1000  # 10 minutes


class BaseWorker(ABC):
    """
    Abstract base for Redis Streams consumer group workers.

    Subclass and implement `process_message(message_id, fields)`.
    """

    def __init__(
        self,
        stream_key: str,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self._stream_key = stream_key
        self._group = consumer_group or settings.redis_consumer_group
        self._consumer = consumer_name or f"{socket.gethostname()}-{self.__class__.__name__}"
        self._settings = settings
        self._running = False
        self._redis: aioredis.Redis | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Connect to Redis, ensure consumer group exists, start the loop."""
        self._redis = aioredis.from_url(
            str(self._settings.redis_url),
            decode_responses=True,
        )
        await self._ensure_group()
        self._running = True
        logger.info(
            "worker_started",
            worker=self.__class__.__name__,
            stream=self._stream_key,
            group=self._group,
            consumer=self._consumer,
        )
        try:
            await self._run_loop()
        finally:
            await self._redis.aclose()
            logger.info("worker_stopped", worker=self.__class__.__name__)

    async def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._running = False

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _ensure_group(self) -> None:
        """Create the consumer group if it doesn't exist."""
        try:
            await self._redis.xgroup_create(
                self._stream_key,
                self._group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "consumer_group_created",
                stream=self._stream_key,
                group=self._group,
            )
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                # Group already exists — that's fine
                pass
            else:
                raise

    async def _run_loop(self) -> None:
        """Main event loop: autoclaim stale + read new messages."""
        while self._running:
            try:
                # Step 1: Claim any messages idle for too long (crash recovery)
                await self._autoclaim_stale()

                # Step 2: Read new messages
                messages = await self._redis.xreadgroup(
                    groupname=self._group,
                    consumername=self._consumer,
                    streams={self._stream_key: ">"},
                    count=10,
                    block=2000,  # block for 2s if no messages
                )

                if not messages:
                    continue

                for _stream, entries in messages:
                    for message_id, fields in entries:
                        await self._handle_message(message_id, fields)

            except aioredis.ConnectionError as exc:
                logger.error(
                    "worker_redis_connection_error",
                    worker=self.__class__.__name__,
                    error=str(exc),
                )
                await asyncio.sleep(5)
            except Exception as exc:
                logger.error(
                    "worker_unexpected_error",
                    worker=self.__class__.__name__,
                    error=str(exc),
                )
                await asyncio.sleep(1)

    async def _autoclaim_stale(self) -> None:
        """Reclaim messages that were delivered to dead consumers."""
        try:
            result = await self._redis.xautoclaim(
                self._stream_key,
                self._group,
                self._consumer,
                min_idle_time=_AUTOCLAIM_MIN_IDLE_MS,
                start_id="0-0",
                count=10,
            )
            # result = (next_start_id, [(id, fields), ...], [deleted_ids])
            claimed = result[1] if result else []
            if claimed:
                logger.info(
                    "worker_autoclaimed_messages",
                    worker=self.__class__.__name__,
                    count=len(claimed),
                )
                for message_id, fields in claimed:
                    await self._handle_message(message_id, fields)
        except Exception as exc:
            # XAUTOCLAIM is Redis 6.2+ — degrade gracefully on older versions
            logger.debug(
                "worker_autoclaim_skipped",
                error=str(exc),
            )

    async def _handle_message(
        self,
        message_id: str,
        fields: dict[str, str],
    ) -> None:
        """Process a single message and ACK or leave in PEL."""
        try:
            await self.process_message(message_id, fields)
            await self._redis.xack(self._stream_key, self._group, message_id)
            logger.debug(
                "worker_message_acked",
                worker=self.__class__.__name__,
                message_id=message_id,
            )
        except Exception as exc:
            logger.error(
                "worker_message_processing_failed",
                worker=self.__class__.__name__,
                message_id=message_id,
                error=str(exc),
            )
            # Leave message in PEL — XAUTOCLAIM will retry it

    # ------------------------------------------------------------------ #
    # Subclass interface
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def process_message(
        self,
        message_id: str,
        fields: dict[str, str],
    ) -> None:
        """
        Process a single stream message.

        Raise an exception to leave the message in the PEL for retry.
        """
        ...

    # ------------------------------------------------------------------ #
    # Helpers for subclasses
    # ------------------------------------------------------------------ #

    async def publish(self, stream_key: str, fields: dict[str, Any]) -> str:
        """Publish a message to another stream."""
        str_fields = {k: json.dumps(v) if not isinstance(v, str) else v
                      for k, v in fields.items()}
        msg_id = await self._redis.xadd(stream_key, str_fields)
        return msg_id
