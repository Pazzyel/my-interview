import asyncio
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

REPO_TEST_ROOT = Path(__file__).resolve().parents[1] / "repository"
if str(REPO_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_TEST_ROOT))

# 该 Stub 替代了真实配置模块，避免测试导入阶段依赖生产环境配置与 Pydantic 配置模型。
if "common.config" not in sys.modules:
    config_stub = types.ModuleType("common.config")
    config_stub.app_config = types.SimpleNamespace(
        max_file_size_bytes=10 * 1024 * 1024,
        allowed_types=["application/pdf"],
    )
    sys.modules["common.config"] = config_stub

# 该 Stub 替代了真实 MQ 生产者模块，避免 Windows 环境触发 rocketmq 客户端导入异常。
if "modules.resume.listener.analyze_message_producer" not in sys.modules:
    producer_stub = types.ModuleType("modules.resume.listener.analyze_message_producer")

    class _AnalyzeMessageProducer:  # pragma: no cover
        pass

    producer_stub.AnalyzeMessageProducer = _AnalyzeMessageProducer
    sys.modules["modules.resume.listener.analyze_message_producer"] = producer_stub

# 该 Stub 替代了面试服务包导入入口，避免触发其 __init__ 中的 MQ 相关依赖。
if "modules.interview.service" not in sys.modules:
    interview_service_pkg = types.ModuleType("modules.interview.service")
    interview_service_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["modules.interview.service"] = interview_service_pkg

if "modules.interview.service.interview_persistence_service" not in sys.modules:
    persistence_stub = types.ModuleType("modules.interview.service.interview_persistence_service")

    class _InterviewPersistenceService:  # pragma: no cover
        pass

    persistence_stub.InterviewPersistenceService = _InterviewPersistenceService
    sys.modules["modules.interview.service.interview_persistence_service"] = persistence_stub

# 该 Stub 替代了真实文件基础设施模块（仅用于类型导入），避免加载外部 SDK 依赖。
for _module_name, _class_name in [
    ("infrastructure.file.file_storage_service", "FileStorageService"),
    ("infrastructure.file.file_hash_service", "FileHashService"),
    ("infrastructure.file.file_validation_service", "FileValidationService"),
]:
    if _module_name not in sys.modules:
        _stub = types.ModuleType(_module_name)
        _stub.__dict__[_class_name] = type(_class_name, (), {})
        sys.modules[_module_name] = _stub

from common.models import AsyncTaskStatus
from modules.interview.repository.interview_repository import InterviewRepository
from modules.resume.model.resume_entity import ResumeAnalysisEntity, ResumeEntity
from modules.resume.repository.resume_repository import ResumeRepository
from modules.resume.service.resume_delete_service import ResumeDeleteService
from modules.resume.service.resume_history_service import ResumeHistoryService
from modules.resume.service.resume_upload_service import ResumeUploadService
from resume_repository_mocks import InMemorySqliteSessionFactory


class FakeFileValidationService:
    """该 Mock 替代了真实文件校验组件，避免测试依赖真实文件大小与格式校验过程。"""

    async def validate_file(self, file: Any, max_bytes: int, field_name: str) -> int:
        return 1024

    def validate_content_type_by_list(self, content_type: str, allowed_types: list[str], message: str) -> None:
        return None


class FakeFileHashService:
    """该 Mock 替代了真实哈希计算组件，输出稳定可预测的文件哈希。"""

    async def calculate_hash_file(self, file: Any) -> str:
        return f"hash:{file.filename}"


class FakeParseService:
    """该 Mock 替代了真实文档解析组件（如 unstructured/ocr），返回可控解析文本。"""

    def detect_content_type(self, file: Any) -> str:
        return "application/pdf"

    async def parse_resume(self, file: Any) -> str:
        return f"parsed text for {file.filename}"


class FakeFileStorageService:
    """该 Mock 替代了真实对象存储客户端（如 S3/RustFS），避免网络与外部存储依赖。"""

    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    async def upload_resume(self, file: Any) -> str:
        return f"resume/{file.filename}"

    async def get_file_url(self, file_key: str) -> str:
        return f"https://mock-storage.local/{file_key}"

    async def delete_file(self, key: str) -> None:
        self.deleted_keys.append(key)


class FakeAnalyzeMessageProducer:
    """该 Mock 替代了真实 MQ 生产者（如 RocketMQ），记录任务投递而不进行网络发送。"""

    def __init__(self) -> None:
        self.sent_tasks: list[tuple[int, str]] = []

    def send_analyze_task(self, resume_id: int, content: str) -> None:
        self.sent_tasks.append((resume_id, content))


class InterviewPersistenceRepositoryAdapter:
    """该适配器替代受平台导入副作用影响的持久化服务实现，转发到真实 InterviewRepository 删除逻辑。"""

    def __init__(self, interview_repository: InterviewRepository) -> None:
        self.interview_repository = interview_repository

    async def delete_sessions_by_resume_id(self, db: Any, resume_id: int) -> None:
        await self.interview_repository.delete_by_resume_id(db, resume_id)


@dataclass
class ResumeApiTestContext:
    sqlite_factory: InMemorySqliteSessionFactory
    resume_repository: ResumeRepository
    interview_repository: InterviewRepository
    interview_persistence_service: InterviewPersistenceRepositoryAdapter
    storage_service: FakeFileStorageService
    analyze_producer: FakeAnalyzeMessageProducer
    upload_service: ResumeUploadService
    history_service: ResumeHistoryService
    delete_service: ResumeDeleteService

    def dispose(self) -> None:
        asyncio.run(self.sqlite_factory.dispose())

    async def find_resume_by_hash(self, file_hash: str) -> ResumeEntity | None:
        async with self.sqlite_factory.session() as db:
            return await self.resume_repository.find_by_hash(db, file_hash)

    async def find_resume_by_id(self, resume_id: int) -> ResumeEntity | None:
        async with self.sqlite_factory.session() as db:
            return await self.resume_repository.find_by_id(db, resume_id)


async def _seed_initial_data(
    sqlite_factory: InMemorySqliteSessionFactory,
    resume_repository: ResumeRepository,
    interview_repository: InterviewRepository,
) -> None:
    now = datetime.now()

    async with sqlite_factory.session() as db:
        existing_resume = ResumeEntity(
            fileHash="hash:existing.pdf",
            originalFilename="existing.pdf",
            fileSize=2048,
            contentType="application/pdf",
            storageKey="resume/existing.pdf",
            storageUrl="https://mock-storage.local/resume/existing.pdf",
            resumeText="existing resume text",
            uploadedAt=now - timedelta(days=1),
            accessCount=3,
            analyzeStatus=AsyncTaskStatus.COMPLETED,
        )
        saved_resume = await resume_repository.save(db, existing_resume)

        existing_analysis = ResumeAnalysisEntity(
            resume_id=saved_resume.id or 0,
            overallScore=88,
            contentScore=86,
            structureScore=90,
            skillMatchScore=87,
            expressionScore=89,
            projectScore=88,
            summary="整体表现良好",
            strengthsJson='["结构清晰", "项目描述具体"]',
            suggestionsJson='[{"category": "表达", "priority": "中", "issue": "措辞可更精炼", "recommendation": "减少冗余句"}]',
            analyzedAt=now - timedelta(hours=2),
        )
        await resume_repository.save_analysis(db, existing_analysis)

        await interview_repository.create_session(
            db,
            session_id="session-1",
            resume_id=saved_resume.id or 0,
            total_questions=3,
            questions_json='[{"questionIndex":1,"question":"自我介绍","category":"基础"}]',
        )

        await db.commit()


def create_resume_api_test_context() -> ResumeApiTestContext:
    sqlite_factory = InMemorySqliteSessionFactory()
    asyncio.run(sqlite_factory.init())

    resume_repository = ResumeRepository()
    interview_repository = InterviewRepository()
    asyncio.run(_seed_initial_data(sqlite_factory, resume_repository, interview_repository))

    interview_persistence_service = InterviewPersistenceRepositoryAdapter(interview_repository)
    storage_service = FakeFileStorageService()
    analyze_producer = FakeAnalyzeMessageProducer()

    upload_service = ResumeUploadService(
        parse_service=FakeParseService(),
        storage_service=storage_service,
        file_validation_service=FakeFileValidationService(),
        file_hash_service=FakeFileHashService(),
        analyze_stream_producer=analyze_producer,
        resume_repository=resume_repository,
    )
    history_service = ResumeHistoryService(resume_repository, interview_repository)
    delete_service = ResumeDeleteService(
        resume_repository=resume_repository,
        interview_persistence_service=interview_persistence_service,
        file_storage_service=storage_service,
    )

    return ResumeApiTestContext(
        sqlite_factory=sqlite_factory,
        resume_repository=resume_repository,
        interview_repository=interview_repository,
        interview_persistence_service=interview_persistence_service,
        storage_service=storage_service,
        analyze_producer=analyze_producer,
        upload_service=upload_service,
        history_service=history_service,
        delete_service=delete_service,
    )


class _FakeAsyncSession:
    """该 Mock 替代了真实数据库会话对象，仅用于 LLM smoke test 的提交/回滚计数。"""

    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeSessionContext:
    """该 Mock 替代了真实 async session 上下文管理器，用于 LLM smoke test。"""

    def __init__(self, session: _FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeAsyncSession:
        return self._session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeSessionFactory:
    """该 Mock 替代了真实 async session 工厂，用于 LLM smoke test 中记录会话创建。"""

    def __init__(self) -> None:
        self.sessions: list[_FakeAsyncSession] = []

    def __call__(self) -> _FakeSessionContext:
        session = _FakeAsyncSession()
        self.sessions.append(session)
        return _FakeSessionContext(session)
