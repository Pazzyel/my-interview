import logging
from typing import Optional

from infrastructure.database.connection import async_session_factory
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService

logger = logging.getLogger(__name__)


class KnowledgeBaseVectorizeConsumerService:
    """知识库向量化消费者业务服务 / Business service for knowledgebase vectorize consumer."""

    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        knowledgebase_vector_service: KnowledgeBaseVectorService,
    ) -> None:
        self._knowledgebase_repository: KnowledgeBaseRepository = knowledgebase_repository
        self._knowledgebase_vector_service: KnowledgeBaseVectorService = knowledgebase_vector_service

    async def process_task(
        self,
        kb_id: int,
        content: str,
        kb_name: Optional[str],
        kb_category: Optional[str],
    ) -> None:
        """
        处理单条知识库向量化任务，执行状态流转与向量存储。

        Process one knowledgebase vectorization task with status transition and vector storage.

        执行步骤 / Execution Steps:
        1) 检查知识库是否存在，不存在则直接跳过。
        2) 标记状态为 PROCESSING，清空错误信息。
        3) 调用向量服务执行分块、嵌入与存储。
        4) 标记状态为 COMPLETED。

        说明 / Notes:
        - 若消息里缺少 `kb_name` 与 `kb_category`，会回退到数据库实体字段。
        - 该方法抛出的异常由消费者层处理并决定是否重试。
        """
        # 1) 查询知识库并标记处理中
        async with async_session_factory() as db:
            try:
                kb_entity: Optional[KnowledgeBaseEntity] = await self._knowledgebase_repository.find_by_id(db, kb_id)
                if kb_entity is None:
                    logger.warning("Knowledge base does not exist, skip vectorize task: kbId=%s", kb_id)
                    await db.commit()
                    return

                await self._knowledgebase_repository.update_vector_status(db, kb_id, VectorStatus.PROCESSING, None)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        # 2) 选择元信息（优先消息，回退数据库）
        final_kb_name: str = kb_name if kb_name is not None and kb_name.strip() != "" else kb_entity.name
        final_kb_category: str = (
            kb_category if kb_category is not None and kb_category.strip() != "" else (kb_entity.category or "general")
        )

        # 3) 执行向量化
        await self._knowledgebase_vector_service.vectorize_and_store(
            kb_id=kb_id,
            kb_name=final_kb_name,
            kb_category=final_kb_category,
            content=content,
        )

        # 4) 标记成功
        async with async_session_factory() as db:
            try:
                await self._knowledgebase_repository.update_vector_status(db, kb_id, VectorStatus.COMPLETED, None)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        logger.info("Knowledgebase vectorize completed: kbId=%s", kb_id)

    async def mark_failed(self, kb_id: int, error_message: str) -> None:
        """Mark knowledgebase vectorize status as FAILED with truncated error message."""
        truncated_error: str = error_message[:500] if len(error_message) > 500 else error_message
        async with async_session_factory() as db:
            try:
                await self._knowledgebase_repository.update_vector_status(
                    db,
                    kb_id,
                    VectorStatus.FAILED,
                    truncated_error,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
