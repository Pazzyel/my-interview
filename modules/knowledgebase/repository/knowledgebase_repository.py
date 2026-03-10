from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from infrastructure.database.models import KnowledgeBaseORM


class KnowledgeBaseRepository:
    """
    知识库数据访问层

    Repository for KnowledgeBase entity, using SQLAlchemy 2.0 explicitly.
    Converts between ORM entities and pure data models.
    """
    def __init__(self, db: AsyncSession):
        self.db: AsyncSession = db

    async def find_by_id(self, kb_id: int) -> Optional[KnowledgeBaseEntity]:
        """根据ID查找知识库"""
        stmt = select(KnowledgeBaseORM).where(KnowledgeBaseORM.id == kb_id)
        result = await self.db.execute(stmt)
        orm_obj: Optional[KnowledgeBaseORM] = result.scalar_one_or_none()

        if orm_obj:
            return self._to_entity(orm_obj)
        return None

    async def find_by_file_hash(self, file_hash: str) -> Optional[KnowledgeBaseEntity]:
        """根据文件哈希查找知识库（用于去重）"""
        stmt = select(KnowledgeBaseORM).where(KnowledgeBaseORM.file_hash == file_hash)
        result = await self.db.execute(stmt)
        orm_obj: Optional[KnowledgeBaseORM] = result.scalar_one_or_none()

        if orm_obj:
            return self._to_entity(orm_obj)
        return None

    async def save(self, entity: KnowledgeBaseEntity) -> KnowledgeBaseEntity:
        """
        插入新知识库记录。

        Insert a new knowledge base record and return entity with generated ID.
        """
        new_orm = KnowledgeBaseORM(
            file_hash=entity.file_hash,
            name=entity.name,
            category=entity.category,
            original_filename=entity.original_filename,
            file_size=entity.file_size,
            content_type=entity.content_type,
            storage_key=entity.storage_key,
            storage_url=entity.storage_url,
            uploaded_at=entity.uploaded_at,
            last_accessed_at=entity.last_accessed_at,
            access_count=entity.access_count,
            question_count=entity.question_count,
            vector_status=entity.vector_status,
            vector_error=entity.vector_error,
            chunk_count=entity.chunk_count,
        )

        self.db.add(new_orm)
        await self.db.flush()  # 获取自增ID
        await self.db.commit()

        entity.id = new_orm.id
        return entity

    async def update_vector_status(
        self, kb_id: int, status: VectorStatus, error: Optional[str] = None
    ) -> None:
        """更新知识库的向量化状态"""
        stmt = (
            update(KnowledgeBaseORM)
            .where(KnowledgeBaseORM.id == kb_id)
            .values(vector_status=status, vector_error=error)
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def increment_access_count(self, kb_id: int) -> None:
        """
        增加访问计数并更新最后访问时间。

        Increment access count and update last_accessed_at timestamp.
        """
        stmt = (
            update(KnowledgeBaseORM)
            .where(KnowledgeBaseORM.id == kb_id)
            .values(
                access_count=KnowledgeBaseORM.access_count + 1,
                last_accessed_at=datetime.now(),
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    def _to_entity(self, orm: KnowledgeBaseORM) -> KnowledgeBaseEntity:
        """将 ORM 对象转换为纯数据模型"""
        return KnowledgeBaseEntity(
            id=orm.id,
            file_hash=orm.file_hash,
            name=orm.name,
            category=orm.category,
            original_filename=orm.original_filename,
            file_size=orm.file_size,
            content_type=orm.content_type,
            storage_key=orm.storage_key,
            storage_url=orm.storage_url,
            uploaded_at=orm.uploaded_at,
            last_accessed_at=orm.last_accessed_at,
            access_count=orm.access_count,
            question_count=orm.question_count,
            vector_status=orm.vector_status,
            vector_error=orm.vector_error,
            chunk_count=orm.chunk_count,
        )
