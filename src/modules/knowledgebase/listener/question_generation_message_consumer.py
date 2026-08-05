import logging
from dataclasses import dataclass
from typing import Any, Coroutine

from common.async_task.abstract_stream_consumer import AbstractStreamConsumer
from common.config import app_config
from infrastructure.database.connection import async_session_factory
from modules.knowledgebase.listener.question_generation_message_producer import (
    QuestionGenerationMessageProducer,
)
from modules.knowledgebase.service.knowledgebase_question_generation_service import (
    KnowledgeBaseQuestionGenerationService,
)
from modules.knowledgebase.service.question_generation_state_service import (
    QuestionGenerationStateService,
)

logger = logging.getLogger(__name__)


@dataclass
class QuestionGenerationMessagePayload:
    kb_id: int
    task_id: str
    retry_count: int


class QuestionGenerationMessageConsumer(AbstractStreamConsumer[QuestionGenerationMessagePayload]):
    def __init__(
        self,
        generation_service: KnowledgeBaseQuestionGenerationService,
        state_service: QuestionGenerationStateService,
        producer: QuestionGenerationMessageProducer,
    ) -> None:
        super().__init__()
        self.generation_service = generation_service
        self.state_service = state_service
        self.producer = producer

    def consumer_display_name(self) -> str:
        return "Knowledgebase question generation"

    def consumer_group(self) -> str:
        return app_config.kb_question_gen_consumer_group

    def topic(self) -> str:
        return app_config.kb_question_gen_topic

    def tag(self) -> str:
        return app_config.kb_question_gen_tag

    def parse_payload(self, payload_dict: Any) -> QuestionGenerationMessagePayload | None:
        try:
            kb_id = int(payload_dict["kbId"])
            task_id = str(payload_dict["taskId"])
            retry_count = int(payload_dict.get("retryCount", 0))
        except (KeyError, TypeError, ValueError):
            logger.warning("Invalid question generation message: %s", payload_dict)
            return None
        if not task_id:
            return None
        return QuestionGenerationMessagePayload(kb_id, task_id, retry_count)

    def process_payload(self, payload: QuestionGenerationMessagePayload) -> Coroutine[Any, Any, None]:
        return self._process(payload)

    async def _process(self, payload: QuestionGenerationMessagePayload) -> None:
        async with async_session_factory() as db:
            try:
                claimed = await self.state_service.try_mark_processing(db, payload.kb_id, payload.task_id)
                if not claimed:
                    await db.rollback()
                    return
                config = await self.state_service.get_config(db, payload.kb_id, payload.task_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        await self.generation_service.execute_generation(payload.kb_id, payload.task_id, config)

    def requeue_payload(self, payload: QuestionGenerationMessagePayload, retry_count: int) -> None:
        self._run_coroutine(self._reset_and_requeue(payload, retry_count))

    async def _reset_and_requeue(
        self, payload: QuestionGenerationMessagePayload, retry_count: int
    ) -> None:
        async with async_session_factory() as db:
            try:
                reset = await self.state_service.reset_for_retry(db, payload.kb_id, payload.task_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        if reset:
            self.producer.send_generate_task(payload.kb_id, payload.task_id, retry_count)

    def mark_failed(
        self, payload: QuestionGenerationMessagePayload, error_message: str
    ) -> Coroutine[Any, Any, None]:
        return self._mark_failed(payload)

    async def _mark_failed(self, payload: QuestionGenerationMessagePayload) -> None:
        async with async_session_factory() as db:
            try:
                await self.state_service.mark_failed(db, payload.kb_id, payload.task_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    def payload_retry_count(self, payload: QuestionGenerationMessagePayload) -> int:
        return payload.retry_count

    def payload_identifier(self, payload: QuestionGenerationMessagePayload) -> str:
        return f"kbId={payload.kb_id}, taskId={payload.task_id}"
