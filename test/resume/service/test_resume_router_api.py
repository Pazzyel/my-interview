import asyncio
import importlib
import json
import os
import sys
import types
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from resume_api_mocks import ResumeApiTestContext, create_resume_api_test_context, _FakeSessionFactory, \
    _FakeSessionContext, _FakeAsyncSession


# 注意，本轮测试没有测试LLM分析简历的API调用

def _run(coro):
    return asyncio.run(coro)


def _load_resume_router_module():
    dependencies_stub = types.ModuleType("common.dependencies")
    dependencies_stub.resume_upload_service = object()
    dependencies_stub.resume_history_service = object()
    dependencies_stub.resume_delete_service = object()
    sys.modules["common.dependencies"] = dependencies_stub

    connection_stub = types.ModuleType("infrastructure.database.connection")

    async def _stub_get_async_session():
        yield object()

    connection_stub.get_async_session = _stub_get_async_session
    sys.modules["infrastructure.database.connection"] = connection_stub

    return importlib.import_module("modules.resume.router.resume_router")


resume_router_module = _load_resume_router_module()


@pytest.fixture()
def api_client_and_context(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, ResumeApiTestContext], None, None]:
    context = create_resume_api_test_context()

    monkeypatch.setattr(resume_router_module, "resume_upload_service", context.upload_service)
    monkeypatch.setattr(resume_router_module, "resume_history_service", context.history_service)
    monkeypatch.setattr(resume_router_module, "resume_delete_service", context.delete_service)

    app = FastAPI()
    app.include_router(resume_router_module.router)

    async def _override_db():
        yield object()

    app.dependency_overrides[resume_router_module.get_async_session] = _override_db

    with TestClient(app) as client:
        yield client, context


def test_health_api_returns_up(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, _ = api_client_and_context

    response = client.get("/api/resumes/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["status"] == "UP"


def test_get_all_resumes_api_returns_list(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, _ = api_client_and_context

    response = client.get("/api/resumes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert len(payload["data"]) == 1
    assert payload["data"][0]["id"] == 1
    assert payload["data"][0]["latestScore"] == 88


def test_get_resume_detail_api_returns_detail(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, _ = api_client_and_context

    response = client.get("/api/resumes/1/detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["id"] == 1
    assert len(payload["data"]["analyses"]) == 1
    assert payload["data"]["analyses"][0]["overallScore"] == 88
    assert len(payload["data"]["interviews"]) == 1


def test_upload_api_creates_new_resume(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, context = api_client_and_context

    response = client.post(
        "/api/resumes/upload",
        files={"file": ("new_resume.pdf", b"mock-pdf-binary", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["duplicate"] is False
    assert payload["data"]["resume"]["filename"] == "new_resume.pdf"

    saved_resume = _run(context.resume_repository.find_by_hash(None, "hash:new_resume.pdf"))
    assert saved_resume is not None
    assert context.analyze_producer.sent_tasks


def test_upload_api_returns_duplicate_result(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, _ = api_client_and_context

    response = client.post(
        "/api/resumes/upload",
        files={"file": ("existing.pdf", b"same-content", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["message"] == "Same resume detected, returning history analysis result."
    assert payload["data"]["duplicate"] is True
    assert payload["data"]["analysis"]["overallScore"] == 88


def test_reanalyze_api_resets_status_and_sends_task(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, context = api_client_and_context

    response = client.post("/api/resumes/1/reanalyze")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200

    resume = _run(context.resume_repository.find_by_id(None, 1))
    assert resume is not None
    assert resume.analyzeStatus.value == "PENDING"
    assert context.analyze_producer.sent_tasks[-1][0] == 1


def test_delete_api_deletes_resume_without_real_db(api_client_and_context: tuple[TestClient, ResumeApiTestContext]) -> None:
    client, context = api_client_and_context

    response = client.delete("/api/resumes/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] is None

    deleted_resume = _run(context.resume_repository.find_by_id(None, 1))
    assert deleted_resume is None
    assert context.interview_persistence_service.deleted_resume_ids == [1]
    assert context.storage_service.deleted_keys == ["resume/existing.pdf"]






def _load_consumer_service_module():
    connection_stub = types.ModuleType("infrastructure.database.connection")

    def _stub_async_session_factory():
        return _FakeSessionContext(_FakeAsyncSession())

    connection_stub.async_session_factory = _stub_async_session_factory
    sys.modules["infrastructure.database.connection"] = connection_stub

    return importlib.import_module("modules.resume.service.resume_analyze_consumer_service")

# 测试简历分析服务是否可用
@pytest.mark.skipif(
    not os.environ.get("DASHSCOPE_API_KEY"),
    reason="需要配置 DASHSCOPE_API_KEY 才能执行 LLM smoke test",
)
def test_resume_analyze_consumer_smoke_with_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    consumer_module = _load_consumer_service_module()

    from common.models import AsyncTaskStatus
    from modules.resume.service.resume_grading_service import ResumeGradingService

    fake_factory = _FakeSessionFactory()
    monkeypatch.setattr(consumer_module, "async_session_factory", fake_factory)

    async def _save_analysis_with_log(_db, analysis_entity):
        strengths = json.loads(analysis_entity.strengthsJson)
        suggestions = json.loads(analysis_entity.suggestionsJson)
        print(
            "\n[LLM分析结果]",
            json.dumps(
                {
                    "resume_id": analysis_entity.resume_id,
                    "overall_score": analysis_entity.overallScore,
                    "summary": analysis_entity.summary,
                    "strengths": strengths,
                    "suggestions": suggestions,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    resume_repository = types.SimpleNamespace(
        exists_by_id=AsyncMock(side_effect=[True, True]),
        update_analyze_status=AsyncMock(return_value=True),
        save_analysis=AsyncMock(side_effect=_save_analysis_with_log),
    )

    service = consumer_module.ResumeAnalyzeConsumerService(
        resume_repository=resume_repository,
        resume_grading_service=ResumeGradingService(),
    )

    sample_resume_text = """
张三
XX理工大学 计算机科学与技术 本科
2023.9-2027.6
项目经历
坪苍外卖 2025年9月-2025年12月
项目技术栈:Spring Boot、Mybatis-Plus、MySQL、Redis、JWT、RabbitMQ
项目描述:集外卖点餐、用户点评和社交互动于一体的本地生活服务平台
项目亮点:
·构建 Caffeine 本地缓存 + Redis 分布式缓存的多级缓存架构，配合布隆过滤器解决缓存穿透，热点数据查询 QPS 达到 2w+，有效保护后端数据库
·针对‘黄牛刷单’场景，设计基于 Redisson + Lua 脚本的分布式原子校验方案，将锁粒度细化至 UserID 粒度，在保障数据一致性的前提下，吞吐量提升 30%，有效规避集群环境下的并发竞争风险
·采用 Redis 预扣库存 + 消息队列异步下单的削峰填谷策略，配合数据库乐观锁兜底，实现秒杀系统的高可用，TPS 从 200 提升至 2000+
·基于 Spring AOP 机制，实现公共字段自动填充，减少 30% 的重复代码量
·使用JWT令牌结合拦截器实现用户登录认证与权限校验，确保系统安全性
期刊影响力评估系统 2025年4月-2025年7月
项目技术栈:Spring Boot、MyBatis-Plus、Spring Security
项目描述:期刊影响力评估系统WEB辅助系统，支持标准管理、数据处理、指标体系构建及影响力评估，结合大模型，支持对新期刊文章的影响力评估并生成文章修改建议。
项目亮点:
·基于 Spring Security 实现多角色权限控制，支持菜单和按钮级别权限设置，提升系统安全性
·集成大模型 API 实现期刊摘要自动生成与影响力预测，采用策略模式封装不同评估算法，将原本人工审核耗时从 2 小时缩短至 5 分钟，提升编辑工作效率
·使用 Spring Task 定时任务调度，支持定时的数据处理
专业技能
·熟悉 Java 基础知识，理解面向对象编程思想
·熟悉 JVM 内存模型与 GC 算法，了解常用的故障排查工具
·熟悉 SpringBoot开发框架，熟悉IOC、AOP等知识
·熟悉 MySQL 数据库，了解索引、事务、锁、MVCC等
·熟悉 Redis 常用数据结构，了解缓存穿透、雪崩、击穿
·了解常用的设计模式，如单例模式、工厂模式、代理模式等
获奖情况
2024蓝桥杯省赛三等奖
语言:
英语-熟练(CET-6 525分)
""".strip()

    asyncio.run(service.process_task(resume_id=1001, content=sample_resume_text))

    assert len(fake_factory.sessions) == 2
    assert fake_factory.sessions[0].commit_calls == 1
    assert fake_factory.sessions[1].commit_calls == 1
    assert fake_factory.sessions[0].rollback_calls == 0
    assert fake_factory.sessions[1].rollback_calls == 0

    assert resume_repository.exists_by_id.await_count == 2
    assert resume_repository.save_analysis.await_count == 1
    assert resume_repository.update_analyze_status.await_count == 2

    first_status_call = resume_repository.update_analyze_status.await_args_list[0].args
    second_status_call = resume_repository.update_analyze_status.await_args_list[1].args
    assert first_status_call[2] == AsyncTaskStatus.PROCESSING
    assert second_status_call[2] == AsyncTaskStatus.COMPLETED

    save_analysis_args = resume_repository.save_analysis.await_args_list[0].args
    analysis_entity = save_analysis_args[1]

    assert analysis_entity.resume_id == 1001
    assert analysis_entity.summary is not None
    assert analysis_entity.summary.strip() != ""
    assert isinstance(analysis_entity.overallScore, int)

    strengths = json.loads(analysis_entity.strengthsJson)
    suggestions = json.loads(analysis_entity.suggestionsJson)
    assert isinstance(strengths, list)
    assert isinstance(suggestions, list)
