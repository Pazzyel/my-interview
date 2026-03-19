import logging

from common.models import AsyncTaskStatus
from infrastructure.database.connection import async_session_factory
from modules.interview.service.interview_agent_service import InterviewAgentService
from modules.interview.repository.interview_repository import InterviewRepository

logger = logging.getLogger(__name__)


class InterviewEvaluateConsumerService:
    """
    面试评估消费者业务服务，消费 MQ 后执行评估报告生成。

    Business service for interview evaluation consumer, generating report after MQ consumption.
    """

    def __init__(
        self,
        interview_agent_service: InterviewAgentService,
        interview_repository: InterviewRepository,
    ) -> None:
        self._interview_agent_service: InterviewAgentService = interview_agent_service
        self._interview_repository: InterviewRepository = interview_repository

    async def process_task(self, session_id: str) -> None:
        """
        执行单条面试评估任务，完成状态流转与报告持久化。

        Process one interview evaluation task including status transition and report persistence.

        关键步骤：
        1) 读取会话，若不存在则跳过。
        2) 调用 interview_agent_service.generate_report 完成评估。
        3) 评估成功后状态由 generate_report 内部落库为 COMPLETED。
        """
        async with async_session_factory() as db:
            try:
                session_entity = await self._interview_repository.find_by_session_id(db, session_id)
                if session_entity is None:
                    logger.warning("会话不存在，跳过评估任务: sessionId=%s", session_id)
                    await db.commit()
                    return
            except Exception:
                await db.rollback()
                raise

        async with async_session_factory() as db:
            try:
                await self._interview_agent_service.generate_report(db, session_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def mark_failed(self, session_id: str, error_message: str) -> None:
        """将评估任务标记为失败。"""
        truncated_error: str = error_message[:500] if len(error_message) > 500 else error_message
        async with async_session_factory() as db:
            try:
                await self._interview_repository.update_evaluate_status(
                    db,
                    session_id,
                    AsyncTaskStatus.FAILED.value,
                    truncated_error,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
