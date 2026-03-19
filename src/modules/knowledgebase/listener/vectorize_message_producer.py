import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from common.async_task.abstract_message_producer import AbstractMessageProducer
from common.config import app_config
from infrastructure.database.connection import async_session_factory
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository

logger = logging.getLogger(__name__)


@dataclass
class VectorizeTaskPayload:
    """向量化任务载荷"""
    kb_id: int
    kb_name: str
    kb_category: str
    content: str
    retry_count: int = 0


class VectorizeMessageProducer(AbstractMessageProducer[VectorizeTaskPayload]):
    """
    向量化任务生产者。
    负责发送向量化任务到 RocketMQ。
    """

    def __init__(self, knowledge_base_repository: KnowledgeBaseRepository) -> None:
        super().__init__()
        self._knowledge_base_repository: KnowledgeBaseRepository = knowledge_base_repository

    # ────────── 公开 API ──────────

    def send_vectorize_task(
        self,
        kb_id: int,
        kb_name: str,
        kb_category: str,
        content: str,
        retry_count: int = 0,
    ) -> None:
        """
        发送向量化任务到 RocketMQ。

        :param kb_id:   知识库 ID
        :param content: 文档文本内容
        """
        self.send_task(
            VectorizeTaskPayload(
                kb_id=kb_id,
                kb_name=kb_name,
                kb_category=kb_category,
                content=content,
                retry_count=retry_count,
            )
        )

    # ────────── 抽象方法实现 ──────────

    def task_display_name(self) -> str:
        return "向量化"

    def topic(self) -> str:
        return app_config.kb_vectorize_topic

    def tag(self) -> str:
        return app_config.kb_vectorize_tag

    def build_message(self, payload: VectorizeTaskPayload) -> Dict[str, Any]:
        return {
            "kbId": payload.kb_id,
            "kbName": payload.kb_name,
            "kbCategory": payload.kb_category,
            "content": payload.content,
            "retryCount": payload.retry_count,
        }

    def payload_identifier(self, payload: VectorizeTaskPayload) -> str:
        return f"kb_id={payload.kb_id}"

    def on_send_failed(self, payload: VectorizeTaskPayload, error: str) -> None:
        asyncio.run(self._update_vector_status(
            payload.kb_id,
            VectorStatus.FAILED,
            self.truncate_error(error),
        ))

    # ────────── 私有方法 ──────────

    async def _update_vector_status(
        self,
        kb_id: int,
        status: VectorStatus,
        error: Optional[str],
    ) -> None:
        """
        更新向量化状态到数据库。
        注意：此方法为 async，在同步回调 on_send_failed 中
        需要通过 asyncio.run 调度执行。
        """
        try:
            logger.warning(
                "向量化任务发送失败，更新状态: kb_id=%s, status=%s, error=%s",
                kb_id, status.value, error,
            )
            async with async_session_factory() as db:
                try:
                    await self._knowledge_base_repository.update_vector_status(db, kb_id, status, error)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except Exception as e:
            logger.error("更新向量化状态失败: kb_id=%s, error=%s", kb_id, str(e))
