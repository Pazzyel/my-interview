import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import KnowledgeBaseORM
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus


def _to_entity(orm: KnowledgeBaseORM) -> KnowledgeBaseEntity:
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

def _to_orm(entity: KnowledgeBaseEntity) -> KnowledgeBaseORM:
    """将entity 转换为orm对象"""
    return KnowledgeBaseORM(
        id=entity.id,
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

class KnowledgeBaseRepository:
    """
    知识库数据访问层

    Repository for KnowledgeBase entity, using SQLAlchemy 2.0 explicitly.
    Converts between ORM entities and pure data models.
    """
    def __init__(self):
        pass

    async def find_by_id(self, db: AsyncSession, kb_id: int) -> Optional[KnowledgeBaseEntity]:
        """根据ID查找知识库"""
        stmt = select(KnowledgeBaseORM).where(KnowledgeBaseORM.id == kb_id)
        result = await db.execute(stmt)
        orm_obj: Optional[KnowledgeBaseORM] = result.scalar_one_or_none()

        if orm_obj:
            return _to_entity(orm_obj)
        return None

    async def find_by_file_hash(self, db: AsyncSession, file_hash: str) -> Optional[KnowledgeBaseEntity]:
        """根据文件哈希查找知识库（用于去重）"""
        stmt = select(KnowledgeBaseORM).where(KnowledgeBaseORM.file_hash == file_hash)
        result = await db.execute(stmt)
        orm_obj: Optional[KnowledgeBaseORM] = result.scalar_one_or_none()

        if orm_obj:
            return _to_entity(orm_obj)
        return None

    async def save(self, db: AsyncSession, entity: KnowledgeBaseEntity) -> KnowledgeBaseEntity:
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

        db.add(new_orm)
        await db.flush()  # 获取自增ID

        entity.id = new_orm.id
        return entity

    async def update_vector_status(
        self, db: AsyncSession, kb_id: int, status: VectorStatus, error: Optional[str] = None
    ) -> None:
        """更新知识库的向量化状态"""
        stmt = (
            update(KnowledgeBaseORM)
            .where(KnowledgeBaseORM.id == kb_id)
            .values(vector_status=status, vector_error=error)
        )
        await db.execute(stmt)

    async def update_category(self, db: AsyncSession, kb_id: int, category: str) -> None:
        stmt = update(KnowledgeBaseORM).where(KnowledgeBaseORM.id == kb_id).values(category=category)
        result = await db.execute(stmt)
        if result.rowcount == 0: # type: ignore
            raise BusinessException(ErrorCode.KB_NOT_FOUND, "未找到该id对应知识库")

        logging.info(f"更新知识库分类: id={kb_id}, category={category}")

    async def increment_access_count(self, db: AsyncSession, kb_id: int) -> None:
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
        await db.execute(stmt)

    # ==================== List Queries (列表查询) ====================

    async def find_all_ordered_by_uploaded_at_desc(self, db: AsyncSession) -> List[KnowledgeBaseEntity]:
        """按上传时间倒序查找所有知识库 / Find all knowledge bases ordered by upload time descending"""
        stmt = select(KnowledgeBaseORM).order_by(KnowledgeBaseORM.uploaded_at.desc())
        result = await db.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def find_by_vector_status_ordered(self, db: AsyncSession, status: VectorStatus) -> List[KnowledgeBaseEntity]:
        """按向量化状态查找知识库（按上传时间倒序） / Find by vector status ordered by upload time descending"""
        stmt = (
            select(KnowledgeBaseORM)
            .where(KnowledgeBaseORM.vector_status == status)
            .order_by(KnowledgeBaseORM.uploaded_at.desc())
        )
        result = await db.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def find_all_categories(self, db: AsyncSession) -> List[str]:
        """获取所有不同的分类 / Get all distinct categories"""
        stmt = (
            select(KnowledgeBaseORM.category)
            .where(KnowledgeBaseORM.category.isnot(None))
            .distinct()
            .order_by(KnowledgeBaseORM.category)
        )
        result = await db.execute(stmt)
        return [r for r in result.scalars().all() if r]

    async def find_by_category_ordered(self, db: AsyncSession, category: Optional[str]) -> List[KnowledgeBaseEntity]:
        """根据分类查找知识库 / Find knowledge bases by category"""
        stmt = select(KnowledgeBaseORM)
        if category:
            stmt = stmt.where(KnowledgeBaseORM.category == category)
        else:
            stmt = stmt.where(KnowledgeBaseORM.category.is_(None))
            
        stmt = stmt.order_by(KnowledgeBaseORM.uploaded_at.desc())
        result = await db.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    async def search_by_keyword(self, db: AsyncSession, keyword: str) -> List[KnowledgeBaseEntity]:
        """按名称或文件名模糊搜索 / Search by keyword in name or original_filename"""
        like_expr = f"%{keyword}%"
        stmt = (
            select(KnowledgeBaseORM)
            .where(
                or_(
                    KnowledgeBaseORM.name.ilike(like_expr),
                    KnowledgeBaseORM.original_filename.ilike(like_expr)
                )
            )
            .order_by(KnowledgeBaseORM.uploaded_at.desc())
        )
        result = await db.execute(stmt)
        return [_to_entity(r) for r in result.scalars().all()]

    # ==================== Batch Operations (批量操作) ====================

    async def increment_question_count_batch(self, db: AsyncSession, ids: List[int]) -> int:
        """
        批量增加知识库提问计数
        Batch increment question count for given IDs
        """
        if not ids:
            return 0
            
        stmt = (
            update(KnowledgeBaseORM)
            .where(KnowledgeBaseORM.id.in_(ids))
            .values(question_count=KnowledgeBaseORM.question_count + 1)
        )
        result = await db.execute(stmt)
        return result.rowcount # type: ignore

    # ==================== Stats Queries (统计查询) ====================

    async def count_total(self, db: AsyncSession) -> int:
        """统计总知识库数量"""
        stmt = select(func.count()).select_from(KnowledgeBaseORM)
        result = await db.execute(stmt)
        return result.scalar() or 0

    # 因为一个提问可能涉及多个知识库，会给这些知识库的计数都+1，所以用这个不准（会更多）
    # 正确方法是从RagChat那边统计，这个方法没有使用
    async def sum_question_count(self, db: AsyncSession) -> int:
        """统计总提问次数"""
        stmt = select(func.sum(KnowledgeBaseORM.question_count))
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def sum_access_count(self, db: AsyncSession) -> int:
        """统计总访问次数"""
        stmt = select(func.sum(KnowledgeBaseORM.access_count))
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def count_by_vector_status(self, db: AsyncSession, status: VectorStatus) -> int:
        """按向量化状态统计数量"""
        stmt = select(func.count()).select_from(KnowledgeBaseORM).where(KnowledgeBaseORM.vector_status == status)
        result = await db.execute(stmt)
        return result.scalar() or 0

    # ==================== Delete (删除) ====================

    async def delete_by_id(self, db: AsyncSession, kb_id: int) -> None:
        """删除知识库记录 / Delete knowledge base record"""
        stmt = delete(KnowledgeBaseORM).where(KnowledgeBaseORM.id == kb_id)
        await db.execute(stmt)
