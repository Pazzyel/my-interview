import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.knowledgebase.listener.question_generation_message_producer import (
    QuestionGenerationMessageProducer,
)
from modules.knowledgebase.model.knowledgebase_question import QuestionGenStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.question_generation_state_service import (
    QuestionGenerationStateService,
)

logger = logging.getLogger(__name__)


class QuestionGenerationRecoveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repository: KnowledgeBaseRepository,
        state_service: QuestionGenerationStateService,
        producer: QuestionGenerationMessageProducer,
        interval_seconds: float = 60,
    ) -> None:
        self.session_factory = session_factory
        self.repository = repository
        self.state_service = state_service
        self.producer = producer
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="question-generation-recovery")

    async def shutdown(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("Question generation recovery failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def run_once(self, now: datetime | None = None) -> int:
        current = now or datetime.now()
        recovered = 0
        for status, threshold in (
            (QuestionGenStatus.QUEUED, current - timedelta(minutes=2)),
            (QuestionGenStatus.PROCESSING, current - timedelta(minutes=20)),
        ):
            async with self.session_factory() as db:
                tasks = await self.repository.find_stale_question_generation_tasks(db, status, threshold)
            for task in tasks:
                if not task.question_gen_task_id:
                    continue
                async with self.session_factory() as db:
                    try:
                        changed = await self.state_service.recover_if_stale(
                            db, task.id, task.question_gen_task_id, status, threshold
                        )
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise
                if changed:
                    self.producer.send_generate_task(task.id, task.question_gen_task_id)
                    recovered += 1
        return recovered
