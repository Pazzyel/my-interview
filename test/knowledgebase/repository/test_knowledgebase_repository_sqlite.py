"""
KnowledgeBaseRepository 全方法 SQLite 内存数据库测试。

每个测试用例使用独立的内存数据库实例，验证真实 SQL 执行和 ORM 映射。
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from common.exceptions import BusinessException
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository
from knowledgebase_repository_mocks import InMemorySqliteSessionFactory, build_knowledgebase_entity


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def sqlite_factory() -> InMemorySqliteSessionFactory:
    factory = InMemorySqliteSessionFactory()
    _run(factory.init())
    try:
        yield factory
    finally:
        _run(factory.dispose())


# ==================== 基础 CRUD ====================

# 测试功能：save + find_by_id 的基础读写流程。
def test_save_and_find_by_id(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-save-find",
                name="Java基础知识",
                original_filename="java.pdf",
                uploaded_at=datetime(2026, 3, 10, 10, 0, 0),
            )

            saved = await repo.save(db, entity)
            await db.commit()

            assert saved.id is not None

            found = await repo.find_by_id(db, saved.id)
            assert found is not None
            assert found.file_hash == "hash-save-find"
            assert found.name == "Java基础知识"
            assert found.original_filename == "java.pdf"

    _run(_scenario())


# 测试功能：find_by_file_hash 按文件哈希定位知识库。
def test_find_by_file_hash(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-dedup",
                name="去重测试",
                uploaded_at=datetime(2026, 3, 10, 11, 0, 0),
            )
            await repo.save(db, entity)
            await db.commit()

            found = await repo.find_by_file_hash(db, "hash-dedup")
            missing = await repo.find_by_file_hash(db, "not-exist")

            assert found is not None
            assert found.name == "去重测试"
            assert missing is None

    _run(_scenario())


# 测试功能：find_by_id 查不到时返回 None。
def test_find_by_id_missing_returns_none(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            result = await repo.find_by_id(db, 99999)
            assert result is None

    _run(_scenario())


# ==================== 状态更新 ====================

# 测试功能：update_vector_status 可以更新向量化状态和错误信息。
def test_update_vector_status(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-status",
                uploaded_at=datetime(2026, 3, 10, 12, 0, 0),
            )
            saved = await repo.save(db, entity)
            await db.commit()

            await repo.update_vector_status(db, saved.id, VectorStatus.FAILED, "ES连接超时")
            await db.commit()

            found = await repo.find_by_id(db, saved.id)
            assert found is not None
            assert found.vector_status == VectorStatus.FAILED
            assert found.vector_error == "ES连接超时"

    _run(_scenario())


# 测试功能：update_category 可以更新分类。
def test_update_category(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-cat",
                category="旧分类",
                uploaded_at=datetime(2026, 3, 10, 13, 0, 0),
            )
            saved = await repo.save(db, entity)
            await db.commit()

            await repo.update_category(db, saved.id, "新分类")
            await db.commit()

            found = await repo.find_by_id(db, saved.id)
            assert found is not None
            assert found.category == "新分类"

    _run(_scenario())


# 测试功能：update_category 对不存在的 ID 抛 BusinessException。
def test_update_category_not_found_raises(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            with pytest.raises(BusinessException):
                await repo.update_category(db, 99999, "任意分类")

    _run(_scenario())


# 测试功能：increment_access_count 增加访问计数。
def test_increment_access_count(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-access",
                access_count=1,
                uploaded_at=datetime(2026, 3, 10, 14, 0, 0),
            )
            saved = await repo.save(db, entity)
            await db.commit()

            await repo.increment_access_count(db, saved.id)
            await db.commit()

            found = await repo.find_by_id(db, saved.id)
            assert found is not None
            assert found.access_count == 2

    _run(_scenario())


# ==================== 列表查询 ====================

# 测试功能：find_all_ordered_by_uploaded_at_desc 按上传时间倒序返回。
def test_find_all_ordered_by_uploaded_at_desc(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            old = build_knowledgebase_entity(
                file_hash="hash-old",
                name="旧知识库",
                uploaded_at=base_time,
            )
            new = build_knowledgebase_entity(
                file_hash="hash-new",
                name="新知识库",
                uploaded_at=base_time + timedelta(hours=1),
            )

            await repo.save(db, old)
            await repo.save(db, new)
            await db.commit()

            results = await repo.find_all_ordered_by_uploaded_at_desc(db)
            assert [item.file_hash for item in results] == ["hash-new", "hash-old"]

    _run(_scenario())


# 测试功能：find_by_vector_status_ordered 按向量化状态过滤。
def test_find_by_vector_status_ordered(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            pending = build_knowledgebase_entity(
                file_hash="hash-pending",
                vector_status=VectorStatus.PENDING,
                uploaded_at=base_time,
            )
            completed = build_knowledgebase_entity(
                file_hash="hash-completed",
                vector_status=VectorStatus.COMPLETED,
                uploaded_at=base_time + timedelta(hours=1),
            )

            await repo.save(db, pending)
            await repo.save(db, completed)
            await db.commit()

            results = await repo.find_by_vector_status_ordered(db, VectorStatus.COMPLETED)
            assert len(results) == 1
            assert results[0].file_hash == "hash-completed"

    _run(_scenario())


# 测试功能：find_all_categories 获取所有非空分类。
def test_find_all_categories(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            kb1 = build_knowledgebase_entity(file_hash="h1", category="后端", uploaded_at=base_time)
            kb2 = build_knowledgebase_entity(file_hash="h2", category="前端", uploaded_at=base_time)
            kb3 = build_knowledgebase_entity(file_hash="h3", category=None, uploaded_at=base_time)

            await repo.save(db, kb1)
            await repo.save(db, kb2)
            await repo.save(db, kb3)
            await db.commit()

            categories = await repo.find_all_categories(db)
            # 按字母序排列
            assert "前端" in categories
            assert "后端" in categories
            assert len(categories) == 2

    _run(_scenario())


# 测试功能：find_by_category_ordered 按分类过滤（含 None 分类）。
def test_find_by_category_ordered(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            kb1 = build_knowledgebase_entity(file_hash="h1", category="后端", uploaded_at=base_time)
            kb2 = build_knowledgebase_entity(file_hash="h2", category=None, uploaded_at=base_time)

            await repo.save(db, kb1)
            await repo.save(db, kb2)
            await db.commit()

            backend = await repo.find_by_category_ordered(db, "后端")
            assert len(backend) == 1
            assert backend[0].category == "后端"

            uncategorized = await repo.find_by_category_ordered(db, None)
            assert len(uncategorized) == 1
            assert uncategorized[0].category is None

    _run(_scenario())


# 测试功能：search_by_keyword 按名称或文件名模糊搜索。
def test_search_by_keyword(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            kb1 = build_knowledgebase_entity(
                file_hash="h1",
                name="Java基础",
                original_filename="java_basic.pdf",
                uploaded_at=base_time,
            )
            kb2 = build_knowledgebase_entity(
                file_hash="h2",
                name="Python进阶",
                original_filename="python.pdf",
                uploaded_at=base_time,
            )

            await repo.save(db, kb1)
            await repo.save(db, kb2)
            await db.commit()

            results = await repo.search_by_keyword(db, "Java")
            assert len(results) == 1
            assert results[0].name == "Java基础"

            results_by_filename = await repo.search_by_keyword(db, "python")
            assert len(results_by_filename) == 1

    _run(_scenario())


# ==================== 批量操作 ====================

# 测试功能：increment_question_count_batch 批量更新问题计数。
def test_increment_question_count_batch(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            kb1 = build_knowledgebase_entity(file_hash="h1", question_count=0, uploaded_at=base_time)
            kb2 = build_knowledgebase_entity(file_hash="h2", question_count=5, uploaded_at=base_time)

            saved1 = await repo.save(db, kb1)
            saved2 = await repo.save(db, kb2)
            await db.commit()

            updated = await repo.increment_question_count_batch(db, [saved1.id, saved2.id])
            await db.commit()

            assert updated == 2

            found1 = await repo.find_by_id(db, saved1.id)
            found2 = await repo.find_by_id(db, saved2.id)
            assert found1.question_count == 1
            assert found2.question_count == 6

    _run(_scenario())


# 测试功能：increment_question_count_batch 空列表返回 0。
def test_increment_question_count_batch_empty(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            result = await repo.increment_question_count_batch(db, [])
            assert result == 0

    _run(_scenario())


# ==================== 统计查询 ====================

# 测试功能：count_total 统计总数。
def test_count_total(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            assert await repo.count_total(db) == 0

            base_time = datetime(2026, 3, 10, 9, 0, 0)
            await repo.save(db, build_knowledgebase_entity(file_hash="h1", uploaded_at=base_time))
            await repo.save(db, build_knowledgebase_entity(file_hash="h2", uploaded_at=base_time))
            await db.commit()

            assert await repo.count_total(db) == 2

    _run(_scenario())


# 测试功能：count_by_vector_status 按状态统计数量。
def test_count_by_vector_status(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            base_time = datetime(2026, 3, 10, 9, 0, 0)
            await repo.save(db, build_knowledgebase_entity(
                file_hash="h1", vector_status=VectorStatus.COMPLETED, uploaded_at=base_time,
            ))
            await repo.save(db, build_knowledgebase_entity(
                file_hash="h2", vector_status=VectorStatus.COMPLETED, uploaded_at=base_time,
            ))
            await repo.save(db, build_knowledgebase_entity(
                file_hash="h3", vector_status=VectorStatus.PENDING, uploaded_at=base_time,
            ))
            await db.commit()

            assert await repo.count_by_vector_status(db, VectorStatus.COMPLETED) == 2
            assert await repo.count_by_vector_status(db, VectorStatus.PENDING) == 1
            assert await repo.count_by_vector_status(db, VectorStatus.FAILED) == 0

    _run(_scenario())


# ==================== 删除 ====================

# 测试功能：delete_by_id 删除知识库记录。
def test_delete_by_id(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = KnowledgeBaseRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            entity = build_knowledgebase_entity(
                file_hash="hash-delete",
                uploaded_at=datetime(2026, 3, 10, 15, 0, 0),
            )
            saved = await repo.save(db, entity)
            await db.commit()

            await repo.delete_by_id(db, saved.id)
            await db.commit()

            deleted = await repo.find_by_id(db, saved.id)
            assert deleted is None

    _run(_scenario())
