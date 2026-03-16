import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO, KnowledgeBaseStatsDTO
from modules.knowledgebase.model.rag_chat_message_entity import MessageType
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.repository.rag_chat_repository import RagChatRepository
from infrastructure.file.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

class KnowledgeBaseListService:
    """
    知识库查询服务
    负责知识库列表和详情的查询
    
    KnowledgeBase list service.
    Responsible for fetching knowledge base lists and details.
    """
    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        rag_chat_repository: RagChatRepository,
        file_storage_service: FileStorageService,
    ):
        self.knowledgebase_repository = knowledgebase_repository
        self.rag_chat_repository = rag_chat_repository
        self.file_storage_service = file_storage_service

    async def list_knowledge_bases(
        self, db: AsyncSession, vector_status: Optional[VectorStatus] = None, sort_by: Optional[str] = None
    ) -> List[KnowledgeBaseListItemDTO]:
        """
        获取知识库列表（支持状态过滤和排序）
        Get knowledge base list (supports status filtering and sorting)
        """
        if vector_status:
            entities = await self.knowledgebase_repository.find_by_vector_status_ordered(db, vector_status)
        else:
            entities = await self.knowledgebase_repository.find_all_ordered_by_uploaded_at_desc(db)

        if sort_by and sort_by.lower() != "time":
            entities = self._sort_entities(entities, sort_by)

        return [self._to_list_item_dto(entity) for entity in entities]

    async def get_knowledge_base(self, db: AsyncSession, kb_id: int) -> Optional[KnowledgeBaseListItemDTO]:
        """根据ID获取知识库详情 / Get knowledge base details by ID"""
        entity = await self.knowledgebase_repository.find_by_id(db, kb_id)
        if entity:
            return self._to_list_item_dto(entity)
        return None

    async def get_knowledge_base_names(self, db: AsyncSession, ids: List[int]) -> List[str]:
        """根据ID列表获取知识库名称列表"""
        names: List[str] = []
        for kb_id in ids:
            name: Optional[str] = await self.knowledgebase_repository.find_by_id(db, kb_id)
            if name:
                names.append(name)
            else:
                names.append("未知知识库")
        return names

    # ========== 分类管理 / Category Management ==========

    async def get_all_categories(self, db: AsyncSession) -> List[str]:
        """获取所有分类 / Get all categories"""
        return await self.knowledgebase_repository.find_all_categories(db)

    async def list_by_category(self, db: AsyncSession, category: Optional[str]) -> List[KnowledgeBaseListItemDTO]:
        """根据分类获取知识库列表 / Get knowledge bases by category"""
        entities = await self.knowledgebase_repository.find_by_category_ordered(db, category)
        return [self._to_list_item_dto(entity) for entity in entities]

    async def update_category(self, db: AsyncSession, kb_id: int, category: Optional[str]) -> None:
        """更新知识库分类 / Update knowledge base category"""
        if category is None:
            return

        await self.knowledgebase_repository.update_category(db, kb_id, category)


    # ========== 搜索功能 / Search Features ==========

    async def search(self, db: AsyncSession, keyword: str) -> List[KnowledgeBaseListItemDTO]:
        """按关键词搜索知识库 / Search knowledge bases by keyword"""
        if not keyword or not keyword.strip():
            return await self.list_knowledge_bases(db)
            
        entities = await self.knowledgebase_repository.search_by_keyword(db, keyword.strip())
        return [self._to_list_item_dto(entity) for entity in entities]

    # ========== 统计功能 / Stat Features ==========

    async def get_statistics(self, db: AsyncSession) -> KnowledgeBaseStatsDTO:
        """
        获取知识库统计信息 / Get knowledge base statistics
        总提问次数从用户消息数统计，确保多知识库提问只算一次
        """
        total_count = await self.knowledgebase_repository.count_total(db)
        total_questions = await self.rag_chat_repository.count_messages_by_type(db, MessageType.USER.value)
        total_access = await self.knowledgebase_repository.sum_access_count(db)
        completed_vectors = await self.knowledgebase_repository.count_by_vector_status(db, VectorStatus.COMPLETED)
        processing_vectors = await self.knowledgebase_repository.count_by_vector_status(db, VectorStatus.PROCESSING)

        return KnowledgeBaseStatsDTO(
            totalCount=total_count,
            totalQuestions=total_questions,
            totalAccess=total_access,
            completedVectors=completed_vectors,
            processingVectors=processing_vectors
        )

    # ========== 下载功能 / Download Features ==========

    async def get_entity_for_download(self, db: AsyncSession, kb_id: int) -> KnowledgeBaseEntity:
        """获取知识库文件信息（用于下载）/ Get knowledge base entity for download"""
        entity = await self.knowledgebase_repository.find_by_id(db, kb_id)
        if not entity:
            raise BusinessException(ErrorCode.NOT_FOUND, "知识库不存在 / Knowledge base not found")
        return entity

    async def download_file(self, db: AsyncSession, kb_id: int) -> bytes:
        """下载知识库文件 / Download knowledge base file"""
        entity = await self.get_entity_for_download(db, kb_id)
        
        if not entity.storage_key or not entity.storage_key.strip():
            raise BusinessException(ErrorCode.SYSTEM_ERROR, "文件存储信息不存在 / File storage info not found")

        logger.info(f"下载知识库文件: id={kb_id}, filename={entity.original_filename}")

        content = self.file_storage_service.download_file(entity.storage_key)
        return content

    # ========== 内部辅助方法 / Internal Helpers ==========

    def _sort_entities(self, entities: List[KnowledgeBaseEntity], sort_by: str) -> List[KnowledgeBaseEntity]:
        """在内存中对实体列表排序 / Sort entities in memory"""
        sort_by = sort_by.lower()
        if sort_by == "size":
            return sorted(entities, key=lambda x: x.file_size, reverse=True)
        elif sort_by == "access":
            return sorted(entities, key=lambda x: x.access_count, reverse=True)
        elif sort_by == "question":
            return sorted(entities, key=lambda x: x.question_count, reverse=True)
        return entities

    def _to_list_item_dto(self, entity: KnowledgeBaseEntity) -> KnowledgeBaseListItemDTO:
        """转换为 DTO 模型 / Convert to DTO"""
        return KnowledgeBaseListItemDTO(
            id=entity.id,
            name=entity.name,
            category=entity.category,
            originalFilename=entity.original_filename,
            fileSize=entity.file_size,
            uploadedAt=entity.uploaded_at,
            accessCount=entity.access_count,
            questionCount=entity.question_count,
            vectorStatus=entity.vector_status,
            vectorError=entity.vector_error,
        )
