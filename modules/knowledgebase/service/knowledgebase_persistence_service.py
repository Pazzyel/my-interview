import logging
from typing import Dict, Any, Optional

from fastapi import UploadFile

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository

logger = logging.getLogger(__name__)


class KnowledgeBasePersistenceService:
    """
    知识库持久化服务

    Handles all database operations for knowledge base entities,
    including saving, dedup handling, and status updates.
    """
    def __init__(self, knowledge_base_repository: KnowledgeBaseRepository):
        self.knowledge_base_repository: KnowledgeBaseRepository = knowledge_base_repository

    async def handle_duplicate_knowledge_base(
        self, kb: KnowledgeBaseEntity, file_hash: str
    ) -> Dict[str, Any]:
        """
        处理重复知识库（更新访问计数，返回已有记录）。

        Handle duplicate knowledge base upload: increment access count
        and return the existing record info.
        """
        logger.info("检测到重复知识库，返回已有记录: kb_id=%s", kb.id)

        # 更新访问计数
        if kb.id is not None:
            await self.knowledge_base_repository.increment_access_count(kb.id)

        return {
            "knowledgeBase": {
                "id": kb.id,
                "name": kb.name,
                "fileSize": kb.file_size,
                "contentLength": 0,
            },
            "storage": {
                "fileKey": kb.storage_key or "",
                "fileUrl": kb.storage_url or "",
            },
            "duplicate": True,
        }

    async def save_knowledge_base(
        self,
        file: UploadFile,
        name: Optional[str],
        category: Optional[str],
        storage_key: str,
        storage_url: str,
        file_hash: str,
    ) -> KnowledgeBaseEntity:
        """
        保存新知识库元数据到数据库。

        Build and persist a new knowledge base entity.
        Returns the saved entity with generated ID.
        """
        try:
            # 从文件名提取名称（如果用户没有提供）
            resolved_name: str = name if name and name.strip() else self._extract_name_from_filename(file.filename)
            resolved_category: Optional[str] = category.strip() if category and category.strip() else None

            kb = KnowledgeBaseEntity(
                file_hash=file_hash,
                name=resolved_name,
                category=resolved_category,
                original_filename=file.filename or "unknown",
                file_size=file.size or 0,
                content_type=file.content_type or "application/octet-stream",
                storage_key=storage_key,
                storage_url=storage_url,
            )

            saved_kb: KnowledgeBaseEntity = await self.knowledge_base_repository.save(kb)
            logger.info(
                "知识库已保存: id=%s, name=%s, category=%s, hash=%s",
                saved_kb.id, saved_kb.name, saved_kb.category, file_hash,
            )
            return saved_kb
        except Exception as e:
            logger.error("保存知识库失败: %s", str(e), exc_info=True)
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "保存知识库失败")

    async def update_vector_status_to_pending(self, kb_id: int) -> None:
        """
        更新知识库向量化状态为 PENDING（用于重新向量化）。

        Reset vector status to PENDING for re-vectorization.
        """
        existing_kb: Optional[KnowledgeBaseEntity] = await self.knowledge_base_repository.find_by_id(kb_id)
        if existing_kb is None:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "知识库不存在")

        await self.knowledge_base_repository.update_vector_status(kb_id, VectorStatus.PENDING, None)
        logger.info("知识库向量化状态已更新为 PENDING: kb_id=%s", kb_id)

    def _extract_name_from_filename(self, filename: Optional[str]) -> str:
        """从文件名提取知识库名称（去除扩展名）"""
        if not filename:
            return "未命名知识库"
        last_dot: int = filename.rfind(".")
        if last_dot > 0:
            return filename[:last_dot]
        return filename
