import json
import logging
from typing import Any, AsyncGenerator, List, Optional

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
from modules.knowledgebase.service.knowledgebase_query_service import KnowledgeBaseQueryService


class RagChatSessionService:
    """RAG 聊天会话业务层。"""

    def __init__(
        self,
        rag_chat_session_repository: RagChatSessionRepository,
        knowledgebase_query_service: KnowledgeBaseQueryService,
    ):
        self.rag_chat_session_repository: RagChatSessionRepository = rag_chat_session_repository
        self.knowledgebase_query_service: KnowledgeBaseQueryService = knowledgebase_query_service

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
        logging.info("创建 RAG 聊天会话: id=%d, title=%s", session_entity.id, session_entity.title)

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
        logging.info("更新会话标题: sessionId=%d, title=%s", session_id, title)

    async def toggle_pin(self, db: AsyncSession, session_id: int) -> None:
        """切换会话置顶状态。"""
        pinned: bool | None = await self.rag_chat_session_repository.toggle_pin(db, session_id)
        if pinned is None:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("切换会话置顶状态: sessionId=%d, isPinned=%s", session_id, str(pinned))

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
        logging.info("更新会话知识库: sessionId=%d, kbIds=%s", session_id, str(knowledge_base_ids))

    async def delete_session(self, db: AsyncSession, session_id: int) -> None:
        """删除会话。"""
        deleted: bool = await self.rag_chat_session_repository.delete_session(db, session_id)
        if not deleted:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")
        logging.info("删除会话: sessionId=%d", session_id)

    async def prepare_stream_message(self, db: AsyncSession, session_id: int, question: str) -> int:
        """准备流式回答消息（用户消息 + AI 占位）。"""
        message_id: Optional[int] = await self.rag_chat_session_repository.prepare_stream_messages(db, session_id, question)
        if message_id is None:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")

        logging.info("准备流式消息: sessionId=%d, messageId=%d", session_id, message_id)
        return message_id

    async def complete_stream_message(self, db: AsyncSession, message_id: int, content: str) -> None:
        """流式回答结束后回写内容。"""
        updated: bool = await self.rag_chat_session_repository.complete_stream_message(db, message_id, content)
        if not updated:
            raise BusinessException(ErrorCode.NOT_FOUND, "消息不存在")

        logging.info("完成流式消息: messageId=%d, contentLength=%d", message_id, len(content))

    async def get_stream_answer(self, db: AsyncSession, session_id: int, question: str) -> AsyncGenerator[str, None]:
        """读取会话绑定知识库并返回流式回答。"""
        session_entity: Optional[RagChatSessionEntity] = await self.rag_chat_session_repository.get_session_by_id(db, session_id)
        if session_entity is None:
            raise BusinessException(ErrorCode.NOT_FOUND, "会话不存在")

        kb_ids: List[int] = [item.id for item in session_entity.knowledge_bases if item.id is not None]
        if len(kb_ids) == 0:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, "会话未关联知识库")

        async for stream_item in self.knowledgebase_query_service.answer_question_stream(question, kb_ids, session_id):
            yield stream_item

    async def send_message_stream(
        self,
        db: AsyncSession,
        session_id: int,
        question: str,
    ) -> AsyncGenerator[str, None]:
        """
        完成“预落库 -> 流式输出 -> 回写消息”

        workflow with "prepare -> stream -> complete" lifecycle.
        """
        # 1) 先写入用户消息并创建 AI 占位消息
        message_id: int = await self.prepare_stream_message(db, session_id, question)
        final_content: str = ""

        try:
            # 2) 转发底层 SSE 流，并提取可回写的回答内容
            async for stream_item in self.get_stream_answer(db, session_id, question):
                final_content = self._merge_stream_content(final_content, self._extract_response_content(stream_item))
                yield stream_item

            # 3) 正常结束后回写 AI 消息
            await self.complete_stream_message(db, message_id, final_content)
        except Exception as error:
            # 4) 异常时也回写内容
            fallback_content: str = final_content if final_content != "" else f"【错误】回答生成失败：{str(error)}"
            await self.complete_stream_message(db, message_id, fallback_content)
            raise

    def _extract_response_content(self, stream_item: str) -> str:
        """从 SSE data 行中提取 response 字段文本。"""
        if not stream_item.startswith("data: "):
            return ""

        payload: str = stream_item[6:].strip()
        if payload == "[DONE]" or payload == "":
            return ""

        try:
            payload_object: Any = json.loads(payload)
        except json.JSONDecodeError:
            return ""

        collected_text_list: List[str] = []
        self._collect_response_text(payload_object, collected_text_list)
        if len(collected_text_list) == 0:
            return ""

        longest_text: str = max(collected_text_list, key=len)
        return longest_text

    def _collect_response_text(self, current_value: Any, output_list: List[str]) -> None:
        """递归提取事件中 key=response 的字符串字段。"""
        if isinstance(current_value, dict):
            for key, value in current_value.items():
                if key == "response" and isinstance(value, str):
                    output_list.append(value)
                else:
                    self._collect_response_text(value, output_list)
            return

        if isinstance(current_value, list):
            for item in current_value:
                self._collect_response_text(item, output_list)

    def _merge_stream_content(self, current_content: str, incoming_content: str) -> str:
        """兼容“增量片段”和“全量覆盖”两类流式内容格式。"""
        if incoming_content == "":
            return current_content
        if current_content == "":
            return incoming_content
        if incoming_content.startswith(current_content):
            return incoming_content
        if current_content.endswith(incoming_content):
            return current_content
        return current_content + incoming_content

    def _resolve_title(self, input_title: str | None, knowledge_base_names: List[str]) -> str:
        """生成默认标题。"""
        if input_title is not None and input_title.strip() != "":
            return input_title.strip()
        if len(knowledge_base_names) == 0:
            return "新对话"
        if len(knowledge_base_names) == 1:
            return knowledge_base_names[0]
        return f"{len(knowledge_base_names)} 个知识库对话"
