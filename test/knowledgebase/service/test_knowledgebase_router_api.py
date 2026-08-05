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


# ==================== List / Filter ====================

# 测试功能：知识库列表接口返回知识库数据并调用 list_service。
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


# ==================== Query ====================

# 测试功能：知识库问答接口会返回 query_service 生成的回答。
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


# ==================== Upload ====================

# 测试功能：上传接口返回成功结果。
def test_upload_success(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.post(
        "/api/knowledgebase/upload",
        files={"file": ("test.pdf", b"fake content", "application/pdf")},
        data={"name": "测试知识库", "category": "后端"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["knowledgeBase"]["name"] == "Java 基础"
    assert context.knowledgebase_upload_service.upload_knowledge_base.await_count == 1


# 测试功能：上传重复文件时返回 duplicate 提示。
def test_upload_duplicate(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context
    context.knowledgebase_upload_service.upload_knowledge_base.return_value = {
        "duplicate": True,
        "knowledgeBase": {"id": 1, "name": "Java 基础"},
    }

    response = client.post(
        "/api/knowledgebase/upload",
        files={"file": ("test.pdf", b"fake content", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "重复" in payload["message"]


# ==================== Revectorize ====================

# 测试功能：重新向量化接口调用 upload_service.revectorize。
def test_revectorize(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.post("/api/knowledgebase/1/revectorize")

    assert response.status_code == 200
    assert context.knowledgebase_upload_service.revectorize.await_count == 1


# ==================== Categories ====================

# 测试功能：获取所有分类列表。
def test_get_categories(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/categories")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == ["后端"]
    assert context.knowledgebase_list_service.get_all_categories.await_count == 1


# 测试功能：根据分类获取知识库列表。
def test_get_by_category(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/category/后端")

    assert response.status_code == 200
    assert context.knowledgebase_list_service.list_by_category.await_count == 1


# 测试功能：获取未分类的知识库。
def test_get_uncategorized(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/uncategorized")

    assert response.status_code == 200
    assert context.knowledgebase_list_service.list_by_category.await_count == 1


# 测试功能：更新知识库分类。
def test_update_category(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.put(
        "/api/knowledgebase/1/category",
        json={"category": "AI"},
    )

    assert response.status_code == 200
    assert context.knowledgebase_list_service.update_category.await_count == 1


def test_clear_category_accepts_null(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.put("/api/knowledgebase/1/category", json={"category": None})

    assert response.status_code == 200
    assert context.knowledgebase_list_service.update_category.await_args.args[2] is None


# ==================== Search ====================

# 测试功能：搜索知识库接口。
def test_search(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/search?keyword=Java")

    assert response.status_code == 200
    assert context.knowledgebase_list_service.search.await_count == 1


# ==================== Statistics ====================

# 测试功能：获取统计信息接口。
def test_get_statistics(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.get("/api/knowledgebase/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["totalCount"] == 1
    assert context.knowledgebase_list_service.get_statistics.await_count == 1


# ==================== Detail ====================

# 测试功能：获取知识库详情（不存在时返回 error message）。
def test_get_knowledge_base_not_found(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context
    # get_knowledge_base 默认返回 None

    response = client.get("/api/knowledgebase/99999")

    assert response.status_code == 200
    payload = response.json()
    assert not(payload["code"] != 200 or "不存在" in payload.get("message", ""))


# ==================== Delete ====================

# 测试功能：删除知识库接口。
def test_delete_knowledge_base(
    api_client_and_context: tuple[TestClient, KnowledgeBaseApiTestContext],
) -> None:
    client, context = api_client_and_context

    response = client.delete("/api/knowledgebase/1")

    assert response.status_code == 200
    assert context.knowledgebase_delete_service.delete_knowledge_base.await_count == 1
