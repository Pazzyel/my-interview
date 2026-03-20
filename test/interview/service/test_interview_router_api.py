from pathlib import Path
import sys
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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

from api_test_fixture import apply_sqlite_db_override, create_sqlite_factory, load_router_module
from interview_api_mocks import InterviewApiTestContext, create_interview_api_test_context

interview_router_module = load_router_module(
    "modules.interview.router.interview_router",
    dependency_fields=["interview_agent_service", "interview_history_service", "interview_persistence_service"],
)


@pytest.fixture()
def api_client_and_context() -> Generator[tuple[TestClient, InterviewApiTestContext], None, None]:
    context = create_interview_api_test_context()
    sqlite_factory = create_sqlite_factory()

    interview_router_module.interview_agent_service = context.interview_agent_service
    interview_router_module.interview_history_service = context.interview_history_service
    interview_router_module.interview_persistence_service = context.interview_persistence_service

    app = FastAPI()
    app.include_router(interview_router_module.router)
    apply_sqlite_db_override(app, interview_router_module.get_async_session, sqlite_factory)

    with TestClient(app) as client:
        yield client, context

    import asyncio

    asyncio.run(sqlite_factory.dispose())


# 测试了什么功能：创建面试会话接口会调用 agent_service 并返回会话数据。
def test_create_session_api_returns_session(api_client_and_context: tuple[TestClient, InterviewApiTestContext]) -> None:
    client, context = api_client_and_context

    response = client.post(
        "/api/interview/sessions",
        json={"resumeText": "简历文本", "questionCount": 1, "resumeId": 1, "forceCreate": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["sessionId"] == "session-1"
    assert context.interview_agent_service.create_session.await_count == 1


# 测试了什么功能：获取当前问题接口会返回当前问题并透传服务层结果。
def test_get_current_question_api_returns_question(api_client_and_context: tuple[TestClient, InterviewApiTestContext]) -> None:
    client, context = api_client_and_context

    response = client.get("/api/interview/sessions/session-1/question")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["completed"] is False
    assert payload["data"]["question"]["questionIndex"] == 1
    assert context.interview_agent_service.get_current_question.await_count == 1
