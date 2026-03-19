from typing import List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import RagChatSessionORM, RagChatMessageORM, KnowledgeBaseORM
from modules.knowledgebase.model.rag_chat_message_entity import RagChatSessionEntity, RagChatMessageEntity
from modules.knowledgebase.repository.knowledgebase_repository import _to_entity, _to_orm


def to_session_entity(orm: RagChatSessionORM) -> RagChatSessionEntity:
    """将 ORM 对象转换为纯数据模型"""

    return RagChatSessionEntity(
        r_id=orm.id,
        title=orm.title,
        status=orm.status,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        message_count=orm.message_count,
        is_pinned=orm.is_pinned,
        knowledge_bases=[_to_entity(knowledgebase) for knowledgebase in orm.knowledge_bases],
    )

def to_message_entity(orm: RagChatMessageORM) -> RagChatMessageEntity:
    return RagChatMessageEntity(
        r_id=orm.id,
        session_id=orm.session_id,
        r_type=orm.type,
        content=orm.content,
        message_order=orm.message_order,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        completed=orm.completed
    )

def to_session_orm(entity: RagChatSessionEntity) -> RagChatSessionORM:
    return RagChatSessionORM(
            id = entity.id,
            title = entity.title,
            status = entity.status,
            created_at = entity.created_at,
            updated_at = entity.updated_at,
            message_count = entity.message_count,
            is_pinned = entity.is_pinned,
            knowledge_bases = [_to_orm(entity) for entity in entity.knowledge_bases]
    )


class RagChatRepository:
    """
    RAG 聊天数据访问层 (包含 Session 和 Message)
    
    Repository for RagChatSession and RagChatMessage operations.
    """
    def __init__(self):
        pass

    async def find_sessions_by_knowledge_base_ids(self, db: AsyncSession, kb_ids: List[int]) -> list[RagChatSessionEntity]:
        """
        根据知识库ID列表查找相关的会话。
        Find sessions related to a list of knowledge base IDs.
        """
        if not kb_ids:
            return []
        
        # 查找包含指定知识库的会话 / Find sessions that contain any of the specified knowledge bases
        stmt = (
            select(RagChatSessionORM)
            .filter(RagChatSessionORM.knowledge_bases.any(KnowledgeBaseORM.id.in_(kb_ids)))
        )
        result = await db.execute(stmt)
        return [to_session_entity(orm) for orm in result.scalars().all()]
    
    async def save_session(self, db: AsyncSession, session: RagChatSessionEntity) -> RagChatSessionEntity:
        """保存会话 (包含更新关联) / Save session and its relationships"""

        db.add(to_session_orm(session))
        return session

    async def count_messages_by_type(self, db: AsyncSession, msg_type: str) -> int:
        """
        统计指定类型的消息数量 (如 'USER', 'ASSISTANT')。
        Count messages by their exact type.
        """
        stmt = select(func.count()).select_from(RagChatMessageORM).where(RagChatMessageORM.type == msg_type)
        result = await db.execute(stmt)
        count: int = result.scalar() or 0
        return count

