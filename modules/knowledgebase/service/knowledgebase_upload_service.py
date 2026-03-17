import logging
from typing import Dict, Any, Optional

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.file.file_hash_service import FileHashService
from infrastructure.file.file_storage_service import FileStorageService
from infrastructure.file.file_validation_service import FileValidationService
from modules.knowledgebase.listener.vectorize_message_producer import VectorizeMessageProducer
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.service.knowledgebase_parse_service import KnowledgeBaseParseService
from modules.knowledgebase.service.knowledgebase_persistence_service import KnowledgeBasePersistenceService

logger = logging.getLogger(__name__)


class KnowledgeBaseUploadService:
    """
    知识库上传服务

    Main orchestrator for knowledge base upload:
    validate → dedup → parse → store → persist → dispatch vectorize task.
    """
    def __init__(
        self,
        parse_service: KnowledgeBaseParseService,
        persistence_service: KnowledgeBasePersistenceService,
        storage_service: FileStorageService,
        knowledge_base_repository: KnowledgeBaseRepository,
        file_validation_service: FileValidationService,
        file_hash_service: FileHashService,
        vectorize_stream_producer: VectorizeMessageProducer,
    ):
        self.parse_service: KnowledgeBaseParseService = parse_service
        self.persistence_service: KnowledgeBasePersistenceService = persistence_service
        self.storage_service: FileStorageService = storage_service
        self.knowledge_base_repository: KnowledgeBaseRepository = knowledge_base_repository
        self.file_validation_service: FileValidationService = file_validation_service
        self.file_hash_service: FileHashService = file_hash_service
        self.vectorize_stream_producer: VectorizeMessageProducer = vectorize_stream_producer

    async def upload_knowledge_base(
        self,
        db: AsyncSession,
        file: UploadFile,
        name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        上传知识库文件。

        Complete upload flow:
        1. Validate file size (50MB limit)
        2. Detect and validate content type
        3. Hash-based dedup check
        4. Parse text content
        5. Upload to RustFS
        6. Save metadata to DB (status PENDING)
        7. Send vectorize task to RocketMQ
        8. Return result dict
        """
        # 1. 验证文件大小
        file_size: int = await self.file_validation_service.validate_file(
            file, app_config.kb_max_file_size_bytes, "知识库"
        )
        file_name: str = file.filename or "unknown"
        logger.info("收到知识库上传请求: %s, 大小: %d bytes, category: %s", file_name, file_size, category)

        # 2. 验证文件类型
        content_type: str = self.parse_service.detect_content_type(file)
        self.file_validation_service.validate_content_type_by_list(
            content_type,
            app_config.kb_allowed_types,
            f"不支持的文件类型: {content_type}，支持的类型：PDF、DOCX、DOC、TXT、MD等",
        )

        # 3. 检查知识库是否已存在（去重）
        file_hash: str = await self.file_hash_service.calculate_hash_file(file)
        existing_kb: Optional[KnowledgeBaseEntity] = await self.knowledge_base_repository.find_by_file_hash(db, file_hash)
        if existing_kb is not None:
            logger.info("检测到重复知识库: hash=%s", file_hash)
            return await self.persistence_service.handle_duplicate_knowledge_base(db, existing_kb, file_hash)

        # 4. 解析知识库文本（用于后续向量化）
        content: str = await self.parse_service.parse_content(file)
        if not content or not content.strip():
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "无法从文件中提取文本内容，请确保文件格式正确")

        # 5. 保存文件到RustFS
        file_key: str = await self.storage_service.upload_knowledgebase(file)
        file_url: str = await self.storage_service.get_file_url(file_key)
        logger.info("知识库已存储到RustFS: %s", file_key)

        # 6. 保存知识库元数据到数据库（状态为 PENDING）
        saved_kb: KnowledgeBaseEntity = await self.persistence_service.save_knowledge_base(
            db, file, name, category, file_key, file_url, file_hash
        )

        # 7. 发送向量化任务到 RocketMQ（异步处理）
        if saved_kb.id is None:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "保存的知识库没有id")
        self.vectorize_stream_producer.send_vectorize_task(saved_kb.id,saved_kb.name, saved_kb.category, content)

        logger.info("知识库上传完成，向量化任务已入队: %s, kb_id=%s", file_name, saved_kb.id)

        # 8. 返回结果（状态为 PENDING，前端可轮询获取最新状态）
        return {
            "knowledgeBase": {
                "id": saved_kb.id,
                "name": saved_kb.name,
                "category": saved_kb.category or "",
                "fileSize": saved_kb.file_size,
                "contentLength": len(content),
                "vectorStatus": VectorStatus.PENDING.value,
            },
            "storage": {
                "fileKey": file_key,
                "fileUrl": file_url,
            },
            "duplicate": False,
        }

    async def revectorize(self, db: AsyncSession, kb_id: int) -> None:
        """
        重新向量化知识库（手动重试）。

        Re-download the file from RustFS, re-parse, and resend
        the vectorize task to the message queue.
        """
        existing_kb: Optional[KnowledgeBaseEntity] = await self.knowledge_base_repository.find_by_id(db, kb_id)
        if existing_kb is None:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "知识库不存在")

        logger.info("开始重新向量化知识库: kb_id=%s, name=%s", kb_id, existing_kb.name)

        # 1. 下载文件并解析内容
        if not existing_kb.storage_key:
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "知识库文件存储Key缺失，无法重新向量化")

        file_bytes: bytes = await self.storage_service.download_file(existing_kb.storage_key)
        content: str = await self.parse_service.parse_content_from_bytes(file_bytes, existing_kb.original_filename)

        if not content or not content.strip():
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "无法从文件中提取文本内容")

        # 2. 更新状态为 PENDING
        await self.persistence_service.update_vector_status_to_pending(db, kb_id)

        # 3. 发送向量化任务到 MQ
        self.vectorize_stream_producer.send_vectorize_task(existing_kb.id,existing_kb.name, existing_kb.category, content)

        logger.info("重新向量化任务已发送: kb_id=%s", kb_id)
