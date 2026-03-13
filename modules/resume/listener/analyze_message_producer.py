import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from common.async_task.abstract_message_producer import AbstractMessageProducer
from common.config import app_config
from common.models import AsyncTaskStatus
from modules.resume.repository.resume_repository import ResumeRepository
from infrastructure.database.connection import async_session_factory

logger = logging.getLogger(__name__)


@dataclass
class AnalyzeTaskPayload:
    """简历分析任务载荷。"""
    resume_id: int
    content: str


class AnalyzeMessageProducer(AbstractMessageProducer[AnalyzeTaskPayload]):
    """
    简历分析任务生产者。
    负责发送分析任务到 RocketMQ。
    """

    def __init__(self, resume_repository: ResumeRepository) -> None:
        super().__init__()
        self._resume_repository = resume_repository

    # ────────── 公开 API ──────────

    def send_analyze_task(self, resume_id: int, content: str) -> None:
        """
        发送简历分析任务到 RocketMQ。

        :param resume_id: 简历 ID
        :param content:   简历文本内容
        """
        self.send_task(AnalyzeTaskPayload(resume_id=resume_id, content=content))

    # ────────── 抽象方法实现 ──────────

    def task_display_name(self) -> str:
        return "分析"

    def topic(self) -> str:
        return app_config.resume_analyze_topic

    def tag(self) -> str:
        return app_config.resume_analyze_tag

    def build_message(self, payload: AnalyzeTaskPayload) -> Dict[str, Any]:
        return {
            "resumeId": payload.resume_id,
            "content": payload.content,
            "retryCount": 0,
        }

    def payload_identifier(self, payload: AnalyzeTaskPayload) -> str:
        return f"resumeId={payload.resume_id}"

    def on_send_failed(self, payload: AnalyzeTaskPayload, error: str) -> None:
        asyncio.run(self._update_analyze_status(
            payload.resume_id,
            AsyncTaskStatus.FAILED,
            self.truncate_error(error),
        ))

    # ────────── 私有方法 ──────────

    async def _update_analyze_status(
        self,
        resume_id: int,
        status: AsyncTaskStatus,
        error: Optional[str],
    ) -> None:
        """
        更新简历分析状态到数据库。
        注意：此方法为 async，在同步回调 on_send_failed 中
        需要通过 asyncio.run / event-loop 调度执行。
        """
        try:
            # ResumeRepository 使用 async session，
            # 此处记录日志
            logger.warning(
                "分析任务发送失败，需更新状态: resumeId=%s, status=%s, error=%s",
                resume_id,
                status.value,
                error,
            )
            # DB 更新状态为错误
            async with async_session_factory() as db:
                resume = await self._resume_repository.find_by_id(db, resume_id)
                if resume is not None:
                    resume.analyzeStatus = status
                    if error is not None:
                        resume.analyzeError = error[:500] if len(error) > 500 else error
                    await self._resume_repository.save(db, resume)
        except Exception as e:
            logger.error("更新分析状态失败: resumeId=%s, error=%s", resume_id, str(e))
