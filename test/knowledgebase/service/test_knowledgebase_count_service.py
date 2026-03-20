"""
KnowledgeBaseCountService 单元测试。

Mock Repository，验证批量计数更新逻辑。
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
from knowledgebase_service_mocks import MockKnowledgeBaseRepository

from modules.knowledgebase.service.knowledgebase_count_service import KnowledgeBaseCountService

import asyncio

db = AsyncMock()


@pytest.fixture()
def service_and_mocks():
    repo = MockKnowledgeBaseRepository()
    svc = KnowledgeBaseCountService(repo)
    return svc, repo


# 测试功能：去重后调用 increment_question_count_batch。
def test_update_question_counts_dedup(service_and_mocks) -> None:
    svc, repo = service_and_mocks
    repo.increment_question_count_batch.return_value = 2

    asyncio.run(svc.update_question_counts(db, [1, 2, 1, 2]))

    # 去重后应该传入 2 个唯一 ID
    call_args = repo.increment_question_count_batch.call_args
    actual_ids = call_args[0][1]  # 第二个位置参数
    assert set(actual_ids) == {1, 2}
    assert len(actual_ids) == 2


# 测试功能：空列表直接返回，不调用 repository。
def test_update_question_counts_empty_list(service_and_mocks) -> None:
    svc, repo = service_and_mocks

    asyncio.run(svc.update_question_counts(db, []))

    repo.increment_question_count_batch.assert_not_awaited()
