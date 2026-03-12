from typing import List, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from infrastructure.database.models import RagChatSessionORM, RagChatMessageORM, KnowledgeBaseORM

class RagChatRepository:
    """
    RAG 聊天数据访问层 (包含 Session 和 Message)
    
    Repository for RagChatSession and RagChatMessage operations.
    """
    def __init__(self, db: AsyncSession):
        self.db: AsyncSession = db

    async def find_sessions_by_knowledge_base_ids(self, kb_ids: List[int]) -> Sequence[RagChatSessionORM]:
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
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def save_session(self, session: RagChatSessionORM) -> RagChatSessionORM:
        """保存会话 (包含更新关联) / Save session and its relationships"""
        self.db.add(session)
        await self.db.commit()
        return session

    async def count_messages_by_type(self, msg_type: str) -> int:
        """
        统计指定类型的消息数量 (如 'USER', 'ASSISTANT')。
        Count messages by their exact type.
        """
        stmt = select(func.count()).select_from(RagChatMessageORM).where(RagChatMessageORM.type == msg_type)
        result = await self.db.execute(stmt)
        count: int = result.scalar() or 0
        return count

