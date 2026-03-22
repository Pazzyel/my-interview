"""
KnowledgeBaseDeleteService 单元测试。

Mock Repository + VectorService + FileStorageService，验证删除流程各分支。
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
    MockKnowledgeBaseVectorService,
    build_knowledgebase_entity,
)

from common.exceptions import BusinessException
from modules.knowledgebase.service.knowledgebase_delete_service import KnowledgeBaseDeleteService

import asyncio

db = AsyncMock()


@pytest.fixture()
def service_and_mocks():
    repo = MockKnowledgeBaseRepository()
    rag_repo = MockRagChatRepository()
    vector_svc = MockKnowledgeBaseVectorService()
    storage = MockFileStorageService()
    svc = KnowledgeBaseDeleteService(repo, rag_repo, vector_svc, storage)
    return svc, repo, rag_repo, vector_svc, storage


# 测试功能：delete_knowledge_base 对不存在的知识库抛异常。
def test_delete_not_found_raises(service_and_mocks) -> None:
    svc, repo, _, _, _ = service_and_mocks
    repo.find_by_id.return_value = None

    with pytest.raises(BusinessException):
        asyncio.run(svc.delete_knowledge_base(db, 99999))


# 测试功能：完整删除流程（会话解关联 → 向量删除 → 文件删除 → 记录删除）。
def test_delete_success_full_flow(service_and_mocks) -> None:
    svc, repo, rag_repo, vector_svc, storage = service_and_mocks
    entity = build_knowledgebase_entity(kb_id=1, storage_key="kb/test.pdf")
    repo.find_by_id.return_value = entity
    rag_repo.find_sessions_by_knowledge_base_ids.return_value = []

    asyncio.run(svc.delete_knowledge_base(db, 1))

    vector_svc.delete_knowledgebase_by_id.assert_awaited_once_with(1)
    storage.delete_file.assert_awaited_once_with("kb/test.pdf")
    repo.delete_by_id.assert_awaited_once_with(db, 1)


# 测试功能：向量删除失败时不影响后续步骤。
def test_delete_vector_failure_continues(service_and_mocks) -> None:
    svc, repo, rag_repo, vector_svc, storage = service_and_mocks
    entity = build_knowledgebase_entity(kb_id=2, storage_key="kb/fail.pdf")
    repo.find_by_id.return_value = entity
    rag_repo.find_sessions_by_knowledge_base_ids.return_value = []
    vector_svc.delete_knowledgebase_by_id.side_effect = Exception("ES 连接失败")

    asyncio.run(svc.delete_knowledge_base(db, 2))

    # 即使向量删除失败，文件删除和数据库删除仍然执行
    storage.delete_file.assert_awaited_once()
    repo.delete_by_id.assert_awaited_once()


# 测试功能：文件删除失败时不影响后续步骤。
def test_delete_storage_failure_continues(service_and_mocks) -> None:
    svc, repo, rag_repo, vector_svc, storage = service_and_mocks
    entity = build_knowledgebase_entity(kb_id=3, storage_key="kb/storage-fail.pdf")
    repo.find_by_id.return_value = entity
    rag_repo.find_sessions_by_knowledge_base_ids.return_value = []
    storage.delete_file.side_effect = Exception("RustFS 连接失败")

    asyncio.run(svc.delete_knowledge_base(db, 3))

    # 即使文件删除失败，数据库删除仍然执行
    repo.delete_by_id.assert_awaited_once()
