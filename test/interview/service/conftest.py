"""
conftest.py for interview/service tests.

在 pytest 收集测试文件之前安装导入安全 Stub，
避免加载外部中间件（RocketMQ、tiktoken、LLM config 等）。
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

# 先调用 shared 这个函数，解决 pydantic Config/Env 报错
from api_test_fixture import install_import_safety_stubs
install_import_safety_stubs()


def _install_interview_service_stubs() -> None:
    """
    Stub 掉 interview service 层测试时可能触发的所有重型外部依赖。
    必须在 pytest 收集阶段之前执行（放在 conftest.py 中保证最早执行）。
    """
    # 模拟 LLM 和 prompt
    if "infrastructure.prompt" not in sys.modules:
        prompt_pkg = types.ModuleType("infrastructure.prompt")
        prompt_pkg.__path__ = []
        sys.modules["infrastructure.prompt"] = prompt_pkg
    
    if "infrastructure.prompt.prompt_service" not in sys.modules:
        prompt_stub = types.ModuleType("infrastructure.prompt.prompt_service")
        prompt_stub.load_prompt = AsyncMock(return_value="mock prompt template")
        prompt_stub.get_prompt_hash = AsyncMock(return_value="test-prompt-hash")
        prompt_stub.has_short_memory = MagicMock(return_value=False)
        prompt_stub.Role = types.SimpleNamespace(
            USER=types.SimpleNamespace(value="user"),
            ASSISTANT=types.SimpleNamespace(value="assistant"),
        )
        sys.modules["infrastructure.prompt.prompt_service"] = prompt_stub

    if "infrastructure.llm" not in sys.modules:
        llm_pkg = types.ModuleType("infrastructure.llm")
        llm_pkg.__path__ = []
        sys.modules["infrastructure.llm"] = llm_pkg

    if "infrastructure.llm.llm_service" not in sys.modules:
        llm_service_stub = types.ModuleType("infrastructure.llm.llm_service")
        # 常见的方法模拟
        sys.modules["infrastructure.llm.llm_service"] = llm_service_stub

    # 模拟 RocketMQ
    if "modules.interview.listener" not in sys.modules:
        listener_pkg = types.ModuleType("modules.interview.listener")
        listener_pkg.__path__ = []
        sys.modules["modules.interview.listener"] = listener_pkg
        
    if "modules.interview.listener.evaluate_message_producer" not in sys.modules:
        emp_stub = types.ModuleType("modules.interview.listener.evaluate_message_producer")
        emp_stub.EvaluateMessageProducer = type("EvaluateMessageProducer", (), {})
        sys.modules["modules.interview.listener.evaluate_message_producer"] = emp_stub

    # 模拟 DB Connection 防止在模块导入时去拿环境变量
    if "infrastructure.database.connection" not in sys.modules:
        if "infrastructure.database" not in sys.modules:
            db_pkg = types.ModuleType("infrastructure.database")
            db_pkg.__path__ = []
            sys.modules["infrastructure.database"] = db_pkg
        db_conn_stub = types.ModuleType("infrastructure.database.connection")
        db_conn_stub.get_async_session = AsyncMock()
        db_conn_stub.async_session_factory = MagicMock()
        sys.modules["infrastructure.database.connection"] = db_conn_stub


_install_interview_service_stubs()
