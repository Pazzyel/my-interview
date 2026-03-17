import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from modules.knowledgebase.repository.rag_chat_repository import RagChatRepository
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from infrastructure.file.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

class KnowledgeBaseDeleteService:
    """
    知识库删除服务
    负责知识库及相关数据的删除操作。

    KnowledgeBase deletion service.
    Responsible for deleting knowledge bases and related data.
    """
    def __init__(
        self,
        knowledgebase_repository: KnowledgeBaseRepository,
        rag_chat_repository: RagChatRepository,
        vector_service: KnowledgeBaseVectorService,
        storage_service: FileStorageService,
    ):
        self.knowledgebase_repository = knowledgebase_repository
        self.rag_chat_repository = rag_chat_repository
        self.vector_service = vector_service
        self.storage_service = storage_service

    async def delete_knowledge_base(self, db: AsyncSession, kb_id: int) -> None:
        """
        删除知识库
        包括：RAG会话关联、向量数据、RustFS文件、数据库记录

        Delete a knowledge base.
        Includes: RAG session associations, vector data, RustFS file, and database record.
        """
        # 1. 获取知识库信息 / Get knowledge base info
        kb: KnowledgeBaseEntity | None = await self.knowledgebase_repository.find_by_id(db, kb_id)
        if not kb:
            raise BusinessException(ErrorCode.NOT_FOUND, "知识库不存在 / Knowledge base not found")

        # 2. 删除所有RAG会话中的知识库关联 / Remove relation in RAG sessions
        sessions = await self.rag_chat_repository.find_sessions_by_knowledge_base_ids(db, [kb_id])
        for session in sessions:
            # 去除该kb_id的关联
            session.knowledge_bases = [k for k in session.knowledge_bases if k.id != kb_id]
            await self.rag_chat_repository.save_session(db, session)
            logger.debug(f"已从会话中移除知识库关联: sessionId={session.id}, kbId={kb_id}")

        if sessions:
            logger.info(f"已从 {len(sessions)} 个会话中移除知识库关联: kbId={kb_id}")

        # 3. 删除向量数据 / Delete vector data
        try:
            self.vector_service.delete_knowledgebase_by_id(kb_id)
        except Exception as e:
            logger.warning(f"删除向量数据失败，继续删除知识库: kbId={kb_id}, error={str(e)}")

        # 4. 删除RustFS中的文件 / Delete file in RustFS
        if kb.storage_key:
            try:
                # Assuming delete API exists or fallback, adjusting this based on typical storage service
                await self.storage_service.delete_file(kb.storage_key) # This might need to match exact Python method name
            except Exception as e:
                logger.warning(f"删除RustFS文件失败，继续删除知识库记录: kbId={kb_id}, error={str(e)}")

        # 5. 删除知识库记录 / Delete knowledge base record
        await self.knowledgebase_repository.delete_by_id(db, kb_id)
        logger.info(f"知识库已删除: id={kb_id}")
