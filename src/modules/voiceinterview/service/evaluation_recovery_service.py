from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.models import AsyncTaskStatus
from modules.voiceinterview.listener.evaluate_message_producer import VoiceEvaluateMessageProducer
from modules.voiceinterview.repository.session_repository import VoiceInterviewSessionRepository

logger = logging.getLogger(__name__)


class VoiceEvaluationRecoveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sessions: VoiceInterviewSessionRepository,
        producer: VoiceEvaluateMessageProducer,
        interval_seconds: int = 60,
        pending_stale_seconds: int = 120,
        processing_stale_seconds: int = 600,
    ) -> None:
        self._session_factory = session_factory
        self._sessions = sessions
        self._producer = producer
        self._interval = max(1, interval_seconds)
        self._pending_stale = max(1, pending_stale_seconds)
        self._processing_stale = max(1, processing_stale_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="voice-evaluation-recovery")

    async def shutdown(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def recover_once(self) -> None:
        now = datetime.now()
        async with self._session_factory() as db:
            pending = await self._sessions.list_stale_evaluations(
                db, AsyncTaskStatus.PENDING, now - timedelta(seconds=self._pending_stale)
            )
            processing = await self._sessions.list_stale_evaluations(
                db, AsyncTaskStatus.PROCESSING, now - timedelta(seconds=self._processing_stale)
            )
            for session_id in [*pending, *processing]:
                await self._sessions.update_fields(
                    db, session_id, evaluate_status=AsyncTaskStatus.PENDING, evaluate_error=None
                )
            await db.commit()
        for session_id in dict.fromkeys([*pending, *processing]):
            await self._producer.send_evaluate_task_async(session_id)

    async def _run(self) -> None:
        while True:
            try:
                await self.recover_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("语音面试评估恢复扫描失败")
            await asyncio.sleep(self._interval)
