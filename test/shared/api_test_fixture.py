import importlib
import sys
import types
from pathlib import Path
from typing import Iterable

from fastapi import APIRouter, FastAPI
from starlette.responses import StreamingResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
REPO_TEST_ROOT = PROJECT_ROOT / "test" / "resume" / "repository"
SHARED_TEST_ROOT = PROJECT_ROOT / "test" / "shared"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_TEST_ROOT))
if str(SHARED_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_TEST_ROOT))

from resume_repository_mocks import InMemorySqliteSessionFactory


def _patch_fastapi_streaming_response_model() -> None:
    """测试态兼容补丁：当 response_model=StreamingResponse 时自动降级为 None，避免路由导入失败。"""
    if getattr(APIRouter, "_copilot_streaming_patch_applied", False):
        return

    original_add_api_route = APIRouter.add_api_route

    def _patched_add_api_route(self, path: str, endpoint, **kwargs):
        if kwargs.get("response_model") is StreamingResponse:
            kwargs["response_model"] = None
        return original_add_api_route(self, path, endpoint, **kwargs)

    APIRouter.add_api_route = _patched_add_api_route  # type: ignore[assignment]
    APIRouter._copilot_streaming_patch_applied = True  # type: ignore[attr-defined]


def install_import_safety_stubs() -> None:
    """安装导入防护 Stub：替代会触发外部中间件加载的模块（如 RocketMQ、生产配置）。"""
    _patch_fastapi_streaming_response_model()
    if "common.config" not in sys.modules:
        config_stub = types.ModuleType("common.config")
        config_stub.app_config = types.SimpleNamespace(
            max_file_size_bytes=10 * 1024 * 1024,
            allowed_types=["application/pdf"],
        )
        sys.modules["common.config"] = config_stub

    if "modules.resume.listener.analyze_message_producer" not in sys.modules:
        producer_stub = types.ModuleType("modules.resume.listener.analyze_message_producer")

        class _AnalyzeMessageProducer:  # pragma: no cover
            pass

        producer_stub.AnalyzeMessageProducer = _AnalyzeMessageProducer
        sys.modules["modules.resume.listener.analyze_message_producer"] = producer_stub

    # Removed modules.interview.service stub block so the services can be tested

    # Removed interview_persistence_service stub so it can be unit tested
    # The true module has no heavy side effects on import.

    for module_name, class_name in [
        ("infrastructure.file.file_storage_service", "FileStorageService"),
        ("infrastructure.file.file_hash_service", "FileHashService"),
        ("infrastructure.file.file_validation_service", "FileValidationService"),
    ]:
        if module_name not in sys.modules:
            stub = types.ModuleType(module_name)
            stub.__dict__[class_name] = type(class_name, (), {})
            sys.modules[module_name] = stub


def load_router_module(module_name: str, dependency_fields: Iterable[str]):
    """通过注入 common.dependencies 与连接模块 Stub，安全加载路由模块。"""
    install_import_safety_stubs()

    dependencies_stub = types.ModuleType("common.dependencies")
    for field in dependency_fields:
        setattr(dependencies_stub, field, object())
    sys.modules["common.dependencies"] = dependencies_stub

    connection_stub = types.ModuleType("infrastructure.database.connection")

    async def _stub_get_async_session():
        yield object()

    connection_stub.get_async_session = _stub_get_async_session
    sys.modules["infrastructure.database.connection"] = connection_stub

    return importlib.import_module(module_name)


def create_sqlite_factory() -> InMemorySqliteSessionFactory:
    """创建并初始化 sqlite 内存数据库工厂。"""
    factory = InMemorySqliteSessionFactory()
    import asyncio

    asyncio.run(factory.init())
    return factory


def apply_sqlite_db_override(app: FastAPI, get_async_session_func, sqlite_factory: InMemorySqliteSessionFactory) -> None:
    """把 FastAPI 的数据库依赖覆盖为 sqlite 内存会话（含 commit/rollback）。"""

    async def _override_db():
        async with sqlite_factory.session() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_async_session_func] = _override_db
