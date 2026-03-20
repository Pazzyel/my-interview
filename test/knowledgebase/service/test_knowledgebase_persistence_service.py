"""
KnowledgeBasePersistenceService 单元测试。

Mock Repository，验证持久化逻辑各分支。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    build_knowledgebase_entity,
)

from common.exceptions import BusinessException
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.service.knowledgebase_persistence_service import KnowledgeBasePersistenceService

import asyncio

db = AsyncMock()


@pytest.fixture()
def service_and_mocks():
    repo = MockKnowledgeBaseRepository()
    svc = KnowledgeBasePersistenceService(repo)
    return svc, repo


# 测试功能：处理重复知识库时返回 duplicate=True 并调用 increment_access_count。
def test_handle_duplicate(service_and_mocks) -> None:
    svc, repo = service_and_mocks
    existing = build_knowledgebase_entity(kb_id=1, name="已有知识库")

    result = asyncio.run(svc.handle_duplicate_knowledge_base(db, existing, "hash-dup"))

    assert result["duplicate"] is True
    assert result["knowledgeBase"]["id"] == 1
    repo.increment_access_count.assert_awaited_once_with(db, 1)


# 测试功能：save_knowledge_base 正常保存流程。
def test_save_knowledge_base_success(service_and_mocks) -> None:
    svc, repo = service_and_mocks

    saved_entity = build_knowledgebase_entity(kb_id=42, name="保存测试")
    repo.save.return_value = saved_entity

    # 创建模拟 UploadFile
    mock_file = MagicMock()
    mock_file.filename = "test_doc.pdf"
    mock_file.size = 4096
    mock_file.content_type = "application/pdf"

    result = asyncio.run(svc.save_knowledge_base(
        db, mock_file, "自定义名称", "后端", "kb/test.pdf", "https://url", "hash-123"
    ))

    assert result.id == 42
    repo.save.assert_awaited_once()


# 测试功能：用户未提供 name 时从 filename 提取。
def test_save_knowledge_base_extract_name(service_and_mocks) -> None:
    svc, repo = service_and_mocks

    saved_entity = build_knowledgebase_entity(kb_id=43, name="interview_guide")
    repo.save.return_value = saved_entity

    mock_file = MagicMock()
    mock_file.filename = "interview_guide.docx"
    mock_file.size = 1024
    mock_file.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    asyncio.run(svc.save_knowledge_base(
        db, mock_file, None, None, "kb/doc.docx", "https://url", "hash-456"
    ))

    # 验证传入 repository.save 的 entity 的 name 是从 filename 提取的
    call_args = repo.save.call_args
    entity_arg = call_args[0][1]  # 第二个位置参数
    assert entity_arg.name == "interview_guide"
    assert entity_arg.category is None


# 测试功能：update_vector_status_to_pending 正确调用 update_vector_status。
def test_update_vector_status_to_pending(service_and_mocks) -> None:
    svc, repo = service_and_mocks
    entity = build_knowledgebase_entity(kb_id=1)
    repo.find_by_id.return_value = entity

    asyncio.run(svc.update_vector_status_to_pending(db, 1))

    repo.update_vector_status.assert_awaited_once_with(db, 1, VectorStatus.PENDING, None)


# 测试功能：update_vector_status_to_pending 不存在时抛异常。
def test_update_vector_status_not_found(service_and_mocks) -> None:
    svc, repo = service_and_mocks
    repo.find_by_id.return_value = None

    with pytest.raises(BusinessException):
        asyncio.run(svc.update_vector_status_to_pending(db, 99999))
