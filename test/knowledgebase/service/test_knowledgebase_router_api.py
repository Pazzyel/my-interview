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

from shared.api_test_fixture import apply_sqlite_db_override, create_sqlite_factory, load_router_module
from knowledgebase_api_mocks import KnowledgeBaseApiTestContext, create_knowledgebase_api_test_context

knowledgebase_router_module = load_router_module(
    "modules.knowledgebase.router.knowledgebase_router",
    dependency_fields=[
        "knowledgebase_upload_service",
        "knowledgebase_list_service",
        "knowledgebase_delete_service",
        "knowledgebase_query_service",
    ],
)


@pytest.fixture()
def api_client_and_context() -> Generator[tuple[TestClient, KnowledgeBaseApiTestContext], None, None]:
    context = create_knowledgebase_api_test_context()
    sqlite_factory = create_sqlite_factory()

    knowledgebase_router_module.knowledgebase_upload_service = context.knowledgebase_upload_service
    knowledgebase_router_module.knowledgebase_list_service = context.knowledgebase_list_service
    knowledgebase_router_module.knowledgebase_delete_service = context.knowledgebase_delete_service
    knowledgebase_router_module.knowledgebase_query_service = context.knowledgebase_query_service

    app = FastAPI()
    app.include_router(knowledgebase_router_module.router)
    apply_sqlite_db_override(app, knowledgebase_router_module.get_async_session, sqlite_factory)

    with TestClient(app) as client:
        yield client, context

    import asyncio

    asyncio.run(sqlite_factory.dispose())


# 测试了什么功能：知识库列表接口返回知识库数据并调用 list_service。
def test_knowledgebase_list_api_returns_items(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/list")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert len(payload["data"]) == 1
    assert payload["data"][0]["name"] == "Java 基础"
    assert context.knowledgebase_list_service.list_knowledge_bases.await_count == 1


# 测试了什么功能：知识库问答接口会返回 query_service 生成的回答。
def test_knowledgebase_query_api_returns_answer(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.post(
        "/api/knowledgebase/query",
        json={"question": "什么是 JVM？", "knowledgeBaseIds": [1]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["answer"] == "这是测试回答"
    assert context.knowledgebase_query_service.query_knowledge_base.await_count == 1
