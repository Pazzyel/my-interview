"""
KnowledgeBaseListService 单元测试。

Mock Repository + FileStorageService，验证各业务逻辑分支。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent
SHARED_ROOT = PROJECT_ROOT / "test" / "shared"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

# 必须先导入 mocks（会安装 import safety stubs），再导入 service
from knowledgebase_service_mocks import (
    MockKnowledgeBaseRepository,
    MockRagChatRepository,
    MockFileStorageService,
    build_knowledgebase_entity,
)

from common.exceptions import BusinessException
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService

import asyncio


@pytest.fixture()
def service_and_mocks():
    repo = MockKnowledgeBaseRepository()
    rag_repo = MockRagChatRepository()
    storage = MockFileStorageService()
    svc = KnowledgeBaseListService(repo, rag_repo, storage)
    return svc, repo, rag_repo, storage


# 伪 AsyncSession
db = AsyncMock()


# ==================== 列表查询 ====================

# 测试功能：无过滤参数时调用 find_all_ordered。
def test_list_knowledge_bases_no_filter(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(name="Java基础")
    repo.find_all_ordered_by_uploaded_at_desc.return_value = [entity]

    result = asyncio.run(svc.list_knowledge_bases(db))

    assert len(result) == 1
    assert result[0].name == "Java基础"
    repo.find_all_ordered_by_uploaded_at_desc.assert_awaited_once()


# 测试功能：传入 vector_status 时调用 find_by_vector_status_ordered。
def test_list_knowledge_bases_with_status_filter(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(vector_status=VectorStatus.COMPLETED)
    repo.find_by_vector_status_ordered.return_value = [entity]

    result = asyncio.run(svc.list_knowledge_bases(db, vector_status=VectorStatus.COMPLETED))

    assert len(result) == 1
    repo.find_by_vector_status_ordered.assert_awaited_once_with(db, VectorStatus.COMPLETED)


# 测试功能：sort_by="size" 时按文件大小倒序排列。
def test_list_knowledge_bases_sort_by_size(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    small = build_knowledgebase_entity(kb_id=1, name="小文件", file_size=100)
    large = build_knowledgebase_entity(kb_id=2, name="大文件", file_size=9999)
    repo.find_all_ordered_by_uploaded_at_desc.return_value = [small, large]

    result = asyncio.run(svc.list_knowledge_bases(db, sort_by="size"))

    assert result[0].name == "大文件"
    assert result[1].name == "小文件"


# ==================== 详情查询 ====================

# 测试功能：find_by_id 找到时返回 DTO。
def test_get_knowledge_base_found(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(name="找到了")
    repo.find_by_id.return_value = entity

    result = asyncio.run(svc.get_knowledge_base(db, 1))

    assert result is not None
    assert result.name == "找到了"


# 测试功能：find_by_id 返回 None 时返回 None。
def test_get_knowledge_base_not_found(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    repo.find_by_id.return_value = None

    result = asyncio.run(svc.get_knowledge_base(db, 99999))

    assert result is None


# ==================== 分类管理 ====================

# 测试功能：get_all_categories 代理调用 repository。
def test_get_all_categories(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    repo.find_all_categories.return_value = ["后端", "前端"]

    result = asyncio.run(svc.get_all_categories(db))

    assert result == ["后端", "前端"]
    repo.find_all_categories.assert_awaited_once()


# 测试功能：list_by_category 代理调用 repository。
def test_list_by_category(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(category="后端")
    repo.find_by_category_ordered.return_value = [entity]

    result = asyncio.run(svc.list_by_category(db, "后端"))

    assert len(result) == 1
    repo.find_by_category_ordered.assert_awaited_once_with(db, "后端")


# 测试功能：update_category 调用 repository；None 时跳过。
def test_update_category(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks

    # 正常更新
    asyncio.run(svc.update_category(db, 1, "新分类"))
    repo.update_category.assert_awaited_once_with(db, 1, "新分类")

    # None 时跳过
    repo.update_category.reset_mock()
    asyncio.run(svc.update_category(db, 1, None))
    repo.update_category.assert_not_awaited()


# ==================== 搜索功能 ====================

# 测试功能：search 调用 search_by_keyword。
def test_search_with_keyword(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(name="Java基础")
    repo.search_by_keyword.return_value = [entity]

    result = asyncio.run(svc.search(db, "Java"))

    assert len(result) == 1
    repo.search_by_keyword.assert_awaited_once_with(db, "Java")


# 测试功能：空关键词回退到 list_knowledge_bases。
def test_search_empty_keyword_returns_all(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity()
    repo.find_all_ordered_by_uploaded_at_desc.return_value = [entity]

    result = asyncio.run(svc.search(db, "  "))

    assert len(result) == 1
    repo.search_by_keyword.assert_not_awaited()


# ==================== 统计功能 ====================

# 测试功能：get_statistics 组合多个统计方法返回 DTO。
def test_get_statistics(service_and_mocks) -> None:
    svc, repo, rag_repo, _ = service_and_mocks
    repo.count_total.return_value = 5
    rag_repo.count_messages_by_type.return_value = 10
    repo.sum_access_count.return_value = 20
    repo.count_by_vector_status.side_effect = [3, 1]  # COMPLETED, PROCESSING

    stats = asyncio.run(svc.get_statistics(db))

    assert stats.total_count == 5
    assert stats.total_questions == 10
    assert stats.total_access == 20
    assert stats.completed_vectors == 3
    assert stats.processing_vectors == 1


# ==================== 下载功能 ====================

# 测试功能：get_entity_for_download 不存在时抛异常。
def test_get_entity_for_download_not_found(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    repo.find_by_id.return_value = None

    with pytest.raises(BusinessException):
        asyncio.run(svc.get_entity_for_download(db, 99999))


# 测试功能：download_file 成功调用 storage。
def test_download_file_success(service_and_mocks) -> None:
    svc, repo, _, storage = service_and_mocks
    entity = build_knowledgebase_entity(storage_key="kb/java.pdf")
    repo.find_by_id.return_value = entity
    storage.download_file.return_value = b"file content bytes"

    content = asyncio.run(svc.download_file(db, 1))

    assert content == b"file content bytes"
    storage.download_file.assert_awaited_once_with("kb/java.pdf")


# 测试功能：download_file 没有 storage_key 时抛异常。
def test_download_file_no_storage_key(service_and_mocks) -> None:
    svc, repo, _, _ = service_and_mocks
    entity = build_knowledgebase_entity(storage_key="")
    repo.find_by_id.return_value = entity

    with pytest.raises(BusinessException):
        asyncio.run(svc.download_file(db, 1))
