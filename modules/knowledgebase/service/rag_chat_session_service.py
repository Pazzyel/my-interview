import logging
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO
from modules.knowledgebase.model.rag_chat_message_entity import RagChatMessageEntity, RagChatSessionEntity
from modules.knowledgebase.model.rag_chat_session_dto import (
    CreateSessionRequest,
    MessageDTO,
    SessionDTO,
    SessionDetailDTO,
    SessionListItemDTO,
)
from modules.knowledgebase.repository.rag_chat_session_repository import RagChatSessionRepository


class RagChatSessionService:
    """RAG 聊天会话业务层。"""

    def __init__(self, rag_chat_session_repository: RagChatSessionRepository):
        self.rag_chat_session_repository: RagChatSessionRepository = rag_chat_session_repository

    async def create_session(self, db: AsyncSession, request: CreateSessionRequest) -> SessionDTO:
        """
        创建会话。
        """
        # 1. 校验知识库是否全部存在
        knowledge_base_ids: List[int] = request.knowledge_base_ids
        existing_count: int = await self.rag_chat_session_repository.count_knowledge_bases_by_ids(db, knowledge_base_ids)
        if existing_count != len(knowledge_base_ids):
            raise BusinessException(ErrorCode.NOT_FOUND, "部分知识库不存在")

        # 2. 生成会话标题
        knowledge_bases = await self.rag_chat_session_repository.get_knowledge_bases_by_ids(db, knowledge_base_ids)
        title: str = self._resolve_title(request.title, [item.name for item in knowledge_bases])

        # 3. 写入会话和关联并返回 DTO。
        session_entity: RagChatSessionEntity = await self.rag_chat_session_repository.create_session(
            db,
            title,
            knowledge_base_ids,
        )
        logging.info("创建 RAG 聊天会话: id={}, title={}", session_entity.id, session_entity.title)

        return SessionDTO(
            id=session_entity.id,
            title=session_entity.title,
            knowledge_base_ids=[item.id for item in session_entity.knowledge_bases if item.id is not None],
            created_at=session_entity.created_at,
        )

    async def list_sessions(self, db: AsyncSession) -> List[SessionListItemDTO]:
        """读取会话列表。"""
        return await self.rag_chat_session_repository.list_sessions(db)

    async def get_session_detail(self, db: AsyncSession, session_id: int) -> SessionDetailDTO:
        """读取会话详情（包含知识库和消息）。"""

        # 先加载会话和知识库
        session_entity = await self.rag_chat_session_repository.get_session_by_id(db, session_id)
        if session_entity is None:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")

        # 转换知识库列表
        knowledge_bases: List[KnowledgeBaseListItemDTO] = [
            KnowledgeBaseListItemDTO(
                id=kb.id,
                name=kb.name,
                category=kb.category,
                originalFilename=kb.original_filename,
                fileSize=kb.file_size,
                uploadedAt=kb.uploaded_at,
                accessCount=kb.access_count,
                questionCount=kb.question_count,
                vectorStatus=kb.vector_status,
                vectorError=kb.vector_error,
            )
            for kb in session_entity.knowledge_bases
        ]

        # 再单独加载消息（避免笛卡尔积）
        message_entities: List[RagChatMessageEntity] = await self.rag_chat_session_repository.get_session_messages(db, session_id)
        messages: List[MessageDTO] = [
            MessageDTO(
                id=item.id,
                type=str(item.type).lower(),
                content=item.content,
                created_at=item.created_at,
            )
            for item in message_entities
        ]

        return SessionDetailDTO(
            id=session_entity.id,
            title=session_entity.title,
            knowledge_bases=knowledge_bases,
            messages=messages,
            created_at=session_entity.created_at,
            updated_at=session_entity.updated_at,
        )

    async def update_session_title(self, db: AsyncSession, session_id: int, title: str) -> None:
        """更新会话标题。"""
        updated: bool = await self.rag_chat_session_repository.update_session_title(db, session_id, title)
        if not updated:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("更新会话标题: sessionId={}, title={}", session_id, title)

    async def toggle_pin(self, db: AsyncSession, session_id: int) -> None:
        """切换会话置顶状态。"""
        pinned: bool | None = await self.rag_chat_session_repository.toggle_pin(db, session_id)
        if pinned is None:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("切换会话置顶状态: sessionId={}, isPinned={}", session_id, pinned)

    async def update_session_knowledge_bases(self, db: AsyncSession, session_id: int, knowledge_base_ids: List[int]) -> None:
        """更新会话关联知识库。"""
        existing_count: int = await self.rag_chat_session_repository.count_knowledge_bases_by_ids(db, knowledge_base_ids)
        if existing_count != len(knowledge_base_ids):
            raise BusinessException(ErrorCode.NOT_FOUND, "部分知识库不存在")

        updated: bool = await self.rag_chat_session_repository.update_session_knowledge_bases(
            db,
            session_id,
            knowledge_base_ids,
        )
        if not updated:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("更新会话知识库: sessionId={}, kbIds={}", session_id, knowledge_base_ids)

    async def delete_session(self, db: AsyncSession, session_id: int) -> None:
        """删除会话。"""
        deleted: bool = await self.rag_chat_session_repository.delete_session(db, session_id)
        if not deleted:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("删除会话: sessionId={}", session_id)

    def _resolve_title(self, input_title: str | None, knowledge_base_names: List[str]) -> str:
        """生成默认标题。"""
        if input_title is not None and input_title.strip() != "":
            return input_title.strip()
        if len(knowledge_base_names) == 0:
            return "新对话"
        if len(knowledge_base_names) == 1:
            return knowledge_base_names[0]
        return f"{len(knowledge_base_names)} 个知识库对话"
