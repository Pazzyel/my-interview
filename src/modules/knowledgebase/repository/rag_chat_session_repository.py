from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, insert, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import (
    KnowledgeBaseORM,
    RagChatMessageORM,
    RagChatSessionORM,
    rag_session_knowledge_bases,
)
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity
from modules.knowledgebase.model.rag_chat_message_entity import RagChatMessageEntity, RagChatSessionEntity
from modules.knowledgebase.model.rag_chat_session_dto import SessionListItemDTO
from modules.knowledgebase.repository.knowledgebase_repository import _to_entity


class RagChatSessionRepository:
    """RAG 聊天会话仓储层，负责会话与关联关系的数据访问。"""

    async def count_knowledge_bases_by_ids(self, db: AsyncSession, knowledge_base_ids: List[int]) -> int:
        """统计给定知识库 ID 在库中的存在数量。"""
        if len(knowledge_base_ids) == 0:
            return 0

        stmt = select(func.count()).select_from(KnowledgeBaseORM).where(KnowledgeBaseORM.id.in_(knowledge_base_ids))
        result = await db.execute(stmt)
        count: int = int(result.scalar() or 0)
        return count

    async def get_knowledge_bases_by_ids(self, db: AsyncSession, knowledge_base_ids: List[int]) -> List[KnowledgeBaseEntity]:
        """按 ID 列表读取知识库实体。"""
        if len(knowledge_base_ids) == 0:
            return []

        stmt = select(KnowledgeBaseORM).where(KnowledgeBaseORM.id.in_(knowledge_base_ids))
        result = await db.execute(stmt)
        orm_list: List[KnowledgeBaseORM] = list(result.scalars().all())
        return [_to_entity(item) for item in orm_list]

    async def create_session(self, db: AsyncSession, title: str, knowledge_base_ids: List[int]) -> RagChatSessionEntity:
        """创建会话并写入会话-知识库关联。"""
        session_data: Dict[str, Any] = {
            "title": title,
            "status": "ACTIVE",
            "message_count": 0,
            "is_pinned": False,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        insert_result = await db.execute(insert(RagChatSessionORM).values(**session_data))
        session_id: int = int(insert_result.inserted_primary_key[0]) # type: ignore

        if len(knowledge_base_ids) > 0:
            relation_rows: List[Dict[str, int]] = [
                {"session_id": session_id, "knowledge_base_id": knowledge_base_id}
                for knowledge_base_id in knowledge_base_ids
            ]
            await db.execute(insert(rag_session_knowledge_bases), relation_rows)

        session_entity: Optional[RagChatSessionEntity] = await self.get_session_by_id(db, session_id)
        if session_entity is None:
            raise ValueError("Failed to load created session")
        return session_entity

    async def get_session_by_id(self, db: AsyncSession, session_id: int) -> Optional[RagChatSessionEntity]:
        """读取单个会话及其关联知识库。"""
        session_stmt = select(RagChatSessionORM).where(RagChatSessionORM.id == session_id)
        session_result = await db.execute(session_stmt)
        session_orm: Optional[RagChatSessionORM] = session_result.scalar_one_or_none()
        if session_orm is None:
            return None

        knowledge_bases: List[KnowledgeBaseEntity] = await self.get_knowledge_bases_for_session(db, session_id)
        return RagChatSessionEntity(
            r_id=session_orm.id,
            title=session_orm.title,
            status=session_orm.status,
            created_at=session_orm.created_at,
            updated_at=session_orm.updated_at,
            message_count=session_orm.message_count,
            is_pinned=bool(session_orm.is_pinned),
            knowledge_bases=knowledge_bases,
        )

    async def get_knowledge_bases_for_session(self, db: AsyncSession, session_id: int) -> List[KnowledgeBaseEntity]:
        """读取会话关联的知识库实体列表。"""
        stmt = (
            select(KnowledgeBaseORM)
            .join(rag_session_knowledge_bases, KnowledgeBaseORM.id == rag_session_knowledge_bases.c.knowledge_base_id)
            .where(rag_session_knowledge_bases.c.session_id == session_id)
        )
        result = await db.execute(stmt)
        orm_list: List[KnowledgeBaseORM] = list(result.scalars().all())
        return [_to_entity(item) for item in orm_list]

    async def list_sessions(self, db: AsyncSession) -> List[SessionListItemDTO]:
        """按置顶和更新时间排序读取会话列表。"""
        session_stmt = select(RagChatSessionORM).order_by(RagChatSessionORM.is_pinned.desc(), RagChatSessionORM.updated_at.desc())
        session_result = await db.execute(session_stmt)
        session_list: List[RagChatSessionORM] = list(session_result.scalars().all())
        if len(session_list) == 0:
            return []

        # SessionListItemDTO的knowledge_base_names得另外JOIN查
        session_ids: List[int] = [item.id for item in session_list]
        names_stmt = (
            select(
                rag_session_knowledge_bases.c.session_id, # .c 是指的是列
                KnowledgeBaseORM.name,
            )
            .join(KnowledgeBaseORM, KnowledgeBaseORM.id == rag_session_knowledge_bases.c.knowledge_base_id)
            .where(rag_session_knowledge_bases.c.session_id.in_(session_ids))
        )
        names_result = await db.execute(names_stmt)

        # 只需要名字，所以只取出名字
        names_map: Dict[int, List[str]] = {session_id: [] for session_id in session_ids}
        for row in names_result:
            row_data: Any = row._mapping
            names_map[int(row_data["session_id"])].append(str(row_data["name"]))

        response_data: List[SessionListItemDTO] = []
        for session_item in session_list:
            mapped_item: SessionListItemDTO = SessionListItemDTO(
                id=session_item.id,
                title=session_item.title,
                message_count=session_item.message_count,
                knowledge_base_names=names_map.get(session_item.id, []),
                updated_at=session_item.updated_at,
                is_pinned=bool(session_item.is_pinned),
            )
            response_data.append(mapped_item)

        return response_data

    async def get_session_messages(self, db: AsyncSession, session_id: int) -> List[RagChatMessageEntity]:
        """按消息顺序读取会话消息。"""
        stmt = (
            select(RagChatMessageORM)
            .where(RagChatMessageORM.session_id == session_id)
            .order_by(RagChatMessageORM.message_order.asc())
        )
        result = await db.execute(stmt)
        orm_list: List[RagChatMessageORM] = list(result.scalars().all())

        message_entities: List[RagChatMessageEntity] = []
        for orm_item in orm_list:
            message_entity = RagChatMessageEntity(
                r_id=orm_item.id,
                session_id=orm_item.session_id,
                r_type=orm_item.type,
                content=orm_item.content,
                message_order=orm_item.message_order,
                created_at=orm_item.created_at,
                updated_at=orm_item.updated_at,
                completed=bool(orm_item.completed),
            )
            message_entities.append(message_entity)

        return message_entities

    async def prepare_stream_messages(self, db: AsyncSession, session_id: int, question: str) -> Optional[int]:
        """保存用户消息并创建 AI 占位消息，返回 AI 消息 ID。"""
        session_stmt = select(RagChatSessionORM).where(RagChatSessionORM.id == session_id)
        session_result = await db.execute(session_stmt)
        session_orm: Optional[RagChatSessionORM] = session_result.scalar_one_or_none()
        if session_orm is None:
            return None

        next_order: int = int(session_orm.message_count)
        now: datetime = datetime.now()

        user_message_data: Dict[str, Any] = {
            "session_id": session_id,
            "type": "USER",
            "content": question,
            "message_order": next_order,
            "completed": True,
            "created_at": now,
            "updated_at": now,
        }
        await db.execute(insert(RagChatMessageORM).values(**user_message_data))

        assistant_message_data: Dict[str, Any] = {
            "session_id": session_id,
            "type": "ASSISTANT",
            "content": "",
            "message_order": next_order + 1,
            "completed": False,
            "created_at": now,
            "updated_at": now,
        }
        assistant_insert_result = await db.execute(insert(RagChatMessageORM).values(**assistant_message_data))
        assistant_message_id: int = int(assistant_insert_result.inserted_primary_key[0]) # type: ignore

        session_update_data: Dict[str, Any] = {
            "message_count": next_order + 2,
            "updated_at": now,
        }
        await db.execute(
            update(RagChatSessionORM)
            .where(RagChatSessionORM.id == session_id)
            .values(**session_update_data)
        )
        return assistant_message_id

    async def complete_stream_message(self, db: AsyncSession, message_id: int, content: str) -> bool:
        """流式回答完成后回写 AI 消息内容。"""
        update_data: Dict[str, Any] = {
            "content": content,
            "completed": True,
            "updated_at": datetime.now(),
        }
        stmt = update(RagChatMessageORM).where(RagChatMessageORM.id == message_id).values(**update_data)
        result = await db.execute(stmt)
        row_count: int = int(result.rowcount or 0) # type: ignore
        return row_count > 0

    async def update_session_title(self, db: AsyncSession, session_id: int, title: str) -> bool:
        """更新会话标题。"""
        update_data: Dict[str, Any] = {
            "title": title,
            "updated_at": datetime.now(),
        }
        stmt = update(RagChatSessionORM).where(RagChatSessionORM.id == session_id).values(**update_data)
        result = await db.execute(stmt)
        row_count: int = int(result.rowcount or 0) # type: ignore
        return row_count > 0

    async def toggle_pin(self, db: AsyncSession, session_id: int) -> Optional[bool]:
        """切换会话置顶状态，并返回切换后的值。"""
        session_stmt = select(RagChatSessionORM).where(RagChatSessionORM.id == session_id)
        session_result = await db.execute(session_stmt)
        session_orm: Optional[RagChatSessionORM] = session_result.scalar_one_or_none()
        if session_orm is None:
            return None

        next_pinned: bool = not bool(session_orm.is_pinned)
        update_data: Dict[str, Any] = {
            "is_pinned": next_pinned,
            "updated_at": datetime.now(),
        }
        stmt = update(RagChatSessionORM).where(RagChatSessionORM.id == session_id).values(**update_data)
        await db.execute(stmt)
        return next_pinned

    async def update_session_knowledge_bases(self, db: AsyncSession, session_id: int, knowledge_base_ids: List[int]) -> bool:
        """更新会话关联知识库。"""
        exists_stmt = select(RagChatSessionORM.id).where(RagChatSessionORM.id == session_id)
        exists_result = await db.execute(exists_stmt)
        session_exists: Optional[int] = exists_result.scalar_one_or_none()
        if session_exists is None:
            return False

        # 1) 清除旧关联
        delete_stmt = delete(rag_session_knowledge_bases).where(rag_session_knowledge_bases.c.session_id == session_id)
        await db.execute(delete_stmt)

        # 2) 插入新关联
        if len(knowledge_base_ids) > 0:
            relation_rows: List[Dict[str, int]] = [
                {"session_id": session_id, "knowledge_base_id": knowledge_base_id}
                for knowledge_base_id in knowledge_base_ids
            ]
            await db.execute(insert(rag_session_knowledge_bases), relation_rows)

        # 3) 更新时间
        update_stmt = (
            update(RagChatSessionORM)
            .where(RagChatSessionORM.id == session_id)
            .values(updated_at=datetime.now())
        )
        await db.execute(update_stmt)
        return True

    async def delete_session(self, db: AsyncSession, session_id: int) -> bool:
        """删除会话（包含消息和关联关系）。"""
        session_stmt = select(RagChatSessionORM.id).where(RagChatSessionORM.id == session_id)
        session_result = await db.execute(session_stmt)
        session_exists: Optional[int] = session_result.scalar_one_or_none()
        if session_exists is None:
            return False

        await db.execute(delete(RagChatMessageORM).where(RagChatMessageORM.session_id == session_id))
        await db.execute(delete(rag_session_knowledge_bases).where(rag_session_knowledge_bases.c.session_id == session_id))
        await db.execute(delete(RagChatSessionORM).where(RagChatSessionORM.id == session_id))
        return True
