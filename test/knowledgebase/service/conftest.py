"""
conftest.py for knowledgebase/service tests.

在 pytest 收集测试文件之前安装导入安全 Stub，
避免加载外部中间件（RocketMQ、tiktoken、ES、AI config 等）。
"""
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
SHARED_ROOT = PROJECT_ROOT / "test" / "shared"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from api_test_fixture import install_import_safety_stubs
install_import_safety_stubs()


def _install_knowledgebase_service_stubs() -> None:
    """
    Stub 掉 knowledgebase service 层测试时可能触发的所有重型依赖。
    必须在 pytest 收集阶段之前执行（放在 conftest.py 中保证最早执行）。
    """

    # ai_config（被 vector_service 和 query_service 导入）
    if "common.ai_config" not in sys.modules:
        ai_stub = types.ModuleType("common.ai_config")
        ai_stub.ai_config = types.SimpleNamespace(
            model="test-model",
            api_key="test-key",
            base_url="https://test.url",
            MAX_BATCH_SIZE=10,
            short_query_length=10,
            medium_query_length=50,
            top_k_short=5,
            top_k_medium=10,
            top_k_long=20,
            min_score_short=0.5,
            min_score_default=0.3,
        )
        sys.modules["common.ai_config"] = ai_stub

    # vector_store（被 vector_service 导入）
    if "infrastructure.vector" not in sys.modules:
        vec_pkg = types.ModuleType("infrastructure.vector")
        vec_pkg.__path__ = []
        sys.modules["infrastructure.vector"] = vec_pkg
    if "infrastructure.vector.vector_store" not in sys.modules:
        vs_stub = types.ModuleType("infrastructure.vector.vector_store")
        vs_stub.vector_store = MagicMock()
        sys.modules["infrastructure.vector.vector_store"] = vs_stub

    # prompt_service（被 query_service 导入）
    if "infrastructure.prompt" not in sys.modules:
        prompt_pkg = types.ModuleType("infrastructure.prompt")
        prompt_pkg.__path__ = []
        sys.modules["infrastructure.prompt"] = prompt_pkg
    if "infrastructure.prompt.prompt_service" not in sys.modules:
        prompt_stub = types.ModuleType("infrastructure.prompt.prompt_service")
        prompt_stub.load_prompt = AsyncMock()
        prompt_stub.has_short_memory = MagicMock(return_value=False)
        sys.modules["infrastructure.prompt.prompt_service"] = prompt_stub

    # document_parse_service
    if "infrastructure.file.document_parse_service" not in sys.modules:
        dp_stub = types.ModuleType("infrastructure.file.document_parse_service")
        dp_stub.DocumentParseService = type("DocumentParseService", (), {})
        sys.modules["infrastructure.file.document_parse_service"] = dp_stub

    # database connection
    if "infrastructure.database.connection" not in sys.modules:
        if "infrastructure.database" not in sys.modules:
            db_pkg = types.ModuleType("infrastructure.database")
            db_pkg.__path__ = []
            sys.modules["infrastructure.database"] = db_pkg
        db_conn_stub = types.ModuleType("infrastructure.database.connection")
        db_conn_stub.get_async_session = AsyncMock()
        db_conn_stub.async_session_factory = MagicMock()
        sys.modules["infrastructure.database.connection"] = db_conn_stub

    # common.dependencies（被 query_service 导入）
    if "common.dependencies" not in sys.modules:
        deps_stub = types.ModuleType("common.dependencies")
        for attr in [
            "knowledgebase_vector_service", "knowledgebase_count_service",
            "knowledgebase_upload_service", "knowledgebase_list_service",
            "knowledgebase_delete_service", "knowledgebase_query_service",
        ]:
            setattr(deps_stub, attr, MagicMock())
        sys.modules["common.dependencies"] = deps_stub

    # vectorize_message_producer（RocketMQ 依赖）
    if "modules.knowledgebase.listener" not in sys.modules:
        listener_pkg = types.ModuleType("modules.knowledgebase.listener")
        listener_pkg.__path__ = []
        sys.modules["modules.knowledgebase.listener"] = listener_pkg
    if "modules.knowledgebase.listener.vectorize_message_producer" not in sys.modules:
        vmp_stub = types.ModuleType("modules.knowledgebase.listener.vectorize_message_producer")
        vmp_stub.VectorizeMessageProducer = type("VectorizeMessageProducer", (), {})
        sys.modules["modules.knowledgebase.listener.vectorize_message_producer"] = vmp_stub

    # knowledgebase_vector_service 整体替换（避免加载 tiktoken 模块级代码）
    if "modules.knowledgebase.service.knowledgebase_vector_service" not in sys.modules:
        vs_module_stub = types.ModuleType("modules.knowledgebase.service.knowledgebase_vector_service")

        class _StubKnowledgeBaseVectorService:
            def __init__(self):
                pass
            def delete_knowledgebase_by_id(self, knowledgebase_id):
                pass
            async def vectorize_and_store(self, kb_id, kb_name, kb_category, content):
                pass
            async def similar_search(self, query, knowledgebase_ids, top_k, min_score):
                return []

        vs_module_stub.KnowledgeBaseVectorService = _StubKnowledgeBaseVectorService
        sys.modules["modules.knowledgebase.service.knowledgebase_vector_service"] = vs_module_stub


_install_knowledgebase_service_stubs()
