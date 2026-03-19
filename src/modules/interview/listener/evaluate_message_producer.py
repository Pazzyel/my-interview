import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from common.async_task.abstract_message_producer import AbstractMessageProducer
from common.config import app_config
from common.models import AsyncTaskStatus
from infrastructure.database.connection import async_session_factory
from modules.interview.repository.interview_repository import InterviewRepository

logger = logging.getLogger(__name__)


@dataclass
class EvaluateTaskPayload:
    """面试评估任务载荷。"""

    session_id: str
    retry_count: int = 0


class EvaluateMessageProducer(AbstractMessageProducer[EvaluateTaskPayload]):
    """
    面试评估任务生产者，负责将评估任务发送到 RocketMQ。

    Interview evaluation task producer for sending evaluation jobs to RocketMQ.
    """

    def __init__(self, interview_repository: InterviewRepository) -> None:
        super().__init__()
        self._interview_repository: InterviewRepository = interview_repository

    def send_evaluate_task(self, session_id: str, retry_count: int = 0) -> None:
        """发送面试评估任务消息。"""
        self.send_task(EvaluateTaskPayload(session_id=session_id, retry_count=retry_count))

    def task_display_name(self) -> str:
        return "面试评估"

    def topic(self) -> str:
        return app_config.interview_evaluate_topic

    def tag(self) -> str:
        return app_config.interview_evaluate_tag

    def build_message(self, payload: EvaluateTaskPayload) -> Dict[str, Any]:
        return {
            "sessionId": payload.session_id,
            "retryCount": payload.retry_count,
        }

    def payload_identifier(self, payload: EvaluateTaskPayload) -> str:
        return f"sessionId={payload.session_id}"

    def on_send_failed(self, payload: EvaluateTaskPayload, error: str) -> None:
        asyncio.run(
            self._update_evaluate_status(
                payload.session_id,
                AsyncTaskStatus.FAILED,
                self.truncate_error(error),
            )
        )

    async def _update_evaluate_status(
        self,
        session_id: str,
        status: AsyncTaskStatus,
        error: Optional[str],
    ) -> None:
        """
        发送失败时回写评估状态，避免任务丢失后状态无感知。

        Update evaluation status when enqueue fails so the task failure is visible.
        """
        try:
            async with async_session_factory() as db:
                try:
                    await self._interview_repository.update_evaluate_status(
                        db,
                        session_id,
                        status.value,
                        error,
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except Exception as exception:
            logger.error(
                "更新面试评估状态失败: sessionId=%s, error=%s",
                session_id,
                str(exception),
            )
