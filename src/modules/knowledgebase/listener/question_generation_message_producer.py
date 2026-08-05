from dataclasses import dataclass
from typing import Any

from common.async_task.abstract_message_producer import AbstractMessageProducer
from common.config import app_config
from infrastructure.database.connection import async_session_factory
from modules.knowledgebase.service.question_generation_state_service import (
    QuestionGenerationStateService,
)


@dataclass
class QuestionGenerationTaskPayload:
    kb_id: int
    task_id: str
    retry_count: int = 0


class QuestionGenerationMessageProducer(AbstractMessageProducer[QuestionGenerationTaskPayload]):
    def __init__(self, state_service: QuestionGenerationStateService) -> None:
        super().__init__()
        self.state_service = state_service

    def send_generate_task(self, kb_id: int, task_id: str, retry_count: int = 0) -> None:
        self.send_task(QuestionGenerationTaskPayload(kb_id, task_id, retry_count))

    def task_display_name(self) -> str:
        return "Knowledgebase question generation"

    def topic(self) -> str:
        return app_config.kb_question_gen_topic

    def tag(self) -> str:
        return app_config.kb_question_gen_tag

    def producer_group(self) -> str:
        return app_config.kb_question_gen_producer_group

    def build_message(self, payload: QuestionGenerationTaskPayload) -> dict[str, Any]:
        return {"kbId": payload.kb_id, "taskId": payload.task_id, "retryCount": payload.retry_count}

    def payload_identifier(self, payload: QuestionGenerationTaskPayload) -> str:
        return f"kbId={payload.kb_id}, taskId={payload.task_id}"

    def on_send_failed(self, payload: QuestionGenerationTaskPayload, error: str) -> None:
        self.run_coroutine_safely(self._mark_failed(payload))

    async def _mark_failed(self, payload: QuestionGenerationTaskPayload) -> None:
        async with async_session_factory() as db:
            try:
                await self.state_service.mark_failed(db, payload.kb_id, payload.task_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
