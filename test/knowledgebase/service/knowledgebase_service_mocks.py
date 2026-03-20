"""
该模块提供 knowledgebase Service 层测试所需的 Mock 对象。

包括：
- Mock Repository（AsyncMock）
- Mock 外部依赖（FileStorageService, VectorService, MQ Producer 等）
- 测试用 Entity 构造器

注意：conftest.py 已在 pytest 收集阶段安装了所有导入安全 Stub。
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus


def build_knowledgebase_entity(
    *,
    kb_id: int = 1,
    file_hash: str = "test-hash",
    name: str = "测试知识库",
    category: Optional[str] = "默认分类",
    original_filename: str = "test.pdf",
    file_size: int = 2048,
    content_type: str = "application/pdf",
    storage_key: Optional[str] = "kb/test.pdf",
    storage_url: Optional[str] = "https://example.test/test.pdf",
    uploaded_at: Optional[datetime] = None,
    vector_status: VectorStatus = VectorStatus.COMPLETED,
    vector_error: Optional[str] = None,
    access_count: int = 1,
    question_count: int = 0,
) -> KnowledgeBaseEntity:
    """构造含 ID 的测试实体（模拟数据库已保存状态）。"""
    return KnowledgeBaseEntity(
        id=kb_id,
        file_hash=file_hash,
        name=name,
        category=category,
        original_filename=original_filename,
        file_size=file_size,
        content_type=content_type,
        storage_key=storage_key,
        storage_url=storage_url,
        uploaded_at=uploaded_at or datetime(2026, 3, 10, 10, 0, 0),
        last_accessed_at=uploaded_at or datetime(2026, 3, 10, 10, 0, 0),
        access_count=access_count,
        question_count=question_count,
        vector_status=vector_status,
        vector_error=vector_error,
    )


class MockKnowledgeBaseRepository:
    """替代真实 Repository，用 AsyncMock 模拟每个数据库方法。"""

    def __init__(self) -> None:
        self.find_by_id = AsyncMock(return_value=None)
        self.find_by_file_hash = AsyncMock(return_value=None)
        self.save = AsyncMock()
        self.update_vector_status = AsyncMock(return_value=None)
        self.update_category = AsyncMock(return_value=None)
        self.increment_access_count = AsyncMock(return_value=None)
        self.find_all_ordered_by_uploaded_at_desc = AsyncMock(return_value=[])
        self.find_by_vector_status_ordered = AsyncMock(return_value=[])
        self.find_all_categories = AsyncMock(return_value=[])
        self.find_by_category_ordered = AsyncMock(return_value=[])
        self.search_by_keyword = AsyncMock(return_value=[])
        self.increment_question_count_batch = AsyncMock(return_value=0)
        self.count_total = AsyncMock(return_value=0)
        self.sum_question_count = AsyncMock(return_value=0)
        self.sum_access_count = AsyncMock(return_value=0)
        self.count_by_vector_status = AsyncMock(return_value=0)
        self.delete_by_id = AsyncMock(return_value=None)


class MockRagChatRepository:
    """替代真实 RAG 聊天 Repository。"""

    def __init__(self) -> None:
        self.count_messages_by_type = AsyncMock(return_value=0)
        self.find_sessions_by_knowledge_base_ids = AsyncMock(return_value=[])
        self.save_session = AsyncMock(return_value=None)


class MockFileStorageService:
    """替代 RustFS 文件存储服务，避免真实网络请求。"""

    def __init__(self) -> None:
        self.download_file = AsyncMock(return_value=b"fake file content")
        self.upload_knowledgebase = AsyncMock(return_value="kb/test.pdf")
        self.get_file_url = AsyncMock(return_value="https://fake.url/test.pdf")
        self.delete_file = AsyncMock(return_value=None)


class MockKnowledgeBaseVectorService:
    """替代 ES 向量库操作。"""

    def __init__(self) -> None:
        self.delete_knowledgebase_by_id = MagicMock(return_value=None)
        self.vectorize_and_store = AsyncMock(return_value=None)
        self.similar_search = AsyncMock(return_value=[])


class MockVectorizeMessageProducer:
    """替代 RocketMQ 消息投递。"""

    def __init__(self) -> None:
        self.send_vectorize_task = MagicMock(return_value=None)


class MockFileValidationService:
    """替代文件校验服务。"""

    def __init__(self) -> None:
        self.validate_file = AsyncMock(return_value=2048)
        self.validate_content_type_by_list = MagicMock(return_value=None)


class MockFileHashService:
    """替代文件哈希计算服务。"""

    def __init__(self) -> None:
        self.calculate_hash_file = AsyncMock(return_value="mock-hash-value")


class MockParseService:
    """替代知识库解析服务。"""

    def __init__(self) -> None:
        self.detect_content_type = MagicMock(return_value="application/pdf")
        self.parse_content = AsyncMock(return_value="解析出来的文本内容")
        self.parse_content_from_bytes = AsyncMock(return_value="从字节解析的文本内容")


class MockPersistenceService:
    """替代知识库持久化服务。"""

    def __init__(self) -> None:
        self.handle_duplicate_knowledge_base = AsyncMock(return_value={
            "duplicate": True,
            "knowledgeBase": {"id": 1, "name": "已有知识库"},
        })
        self.save_knowledge_base = AsyncMock()
        self.update_vector_status_to_pending = AsyncMock(return_value=None)
