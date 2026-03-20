import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.knowledgebase.model.knowledgebase_dto import KnowledgeBaseListItemDTO, KnowledgeBaseStatsDTO
from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
from modules.knowledgebase.model.query_response import QueryResponse


class MockKnowledgeBaseUploadService:
    """该 Mock 替代了真实知识库上传与向量化编排服务，避免文件解析和消息投递外部依赖。"""

    def __init__(self) -> None:
        self.upload_knowledge_base = AsyncMock(
            return_value={
                "duplicate": False,
                "knowledgeBase": {
                    "id": 1,
                    "name": "Java 基础",
                },
            }
        )
        self.revectorize = AsyncMock(return_value=None)


class MockKnowledgeBaseListService:
    """该 Mock 替代了真实知识库查询服务，返回固定列表/统计结果。"""

    def __init__(self) -> None:
        self.list_knowledge_bases = AsyncMock(
            return_value=[
                KnowledgeBaseListItemDTO(
                    id=1,
                    name="Java 基础",
                    category="后端",
                    originalFilename="java.pdf",
                    fileSize=2048,
                    uploadedAt=datetime.now(),
                    accessCount=2,
                    questionCount=3,
                    vectorStatus=VectorStatus.COMPLETED,
                    vectorError=None,
                )
            ]
        )
        self.get_statistics = AsyncMock(
            return_value=KnowledgeBaseStatsDTO(
                totalCount=1,
                totalQuestions=3,
                totalAccess=2,
                completedVectors=1,
                processingVectors=0,
            )
        )
        self.get_all_categories = AsyncMock(return_value=["后端"])
        self.list_by_category = AsyncMock(return_value=[])
        self.update_category = AsyncMock(return_value=None)
        self.search = AsyncMock(return_value=[])
        self.get_knowledge_base = AsyncMock(return_value=None)
        self.get_entity_for_download = AsyncMock(return_value=None)
        self.download_file = AsyncMock(return_value=b"")


class MockKnowledgeBaseDeleteService:
    """该 Mock 替代了真实知识库删除服务，避免触发向量库/存储删除副作用。"""

    def __init__(self) -> None:
        self.delete_knowledge_base = AsyncMock(return_value=None)


class MockKnowledgeBaseQueryService:
    """该 Mock 替代了真实 RAG 查询服务，返回固定问答结果。"""

    def __init__(self) -> None:
        self.query_knowledge_base = AsyncMock(
            return_value=QueryResponse(answer="这是测试回答", knowledge_base_id=1, knowledge_base_name="Java 基础")
        )


@dataclass
class KnowledgeBaseApiTestContext:
    knowledgebase_upload_service: MockKnowledgeBaseUploadService
    knowledgebase_list_service: MockKnowledgeBaseListService
    knowledgebase_delete_service: MockKnowledgeBaseDeleteService
    knowledgebase_query_service: MockKnowledgeBaseQueryService


def create_knowledgebase_api_test_context() -> KnowledgeBaseApiTestContext:
    return KnowledgeBaseApiTestContext(
        knowledgebase_upload_service=MockKnowledgeBaseUploadService(),
        knowledgebase_list_service=MockKnowledgeBaseListService(),
        knowledgebase_delete_service=MockKnowledgeBaseDeleteService(),
        knowledgebase_query_service=MockKnowledgeBaseQueryService(),
    )
