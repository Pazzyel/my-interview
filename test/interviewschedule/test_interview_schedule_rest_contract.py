import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.interviewschedule.model import (
    CreateInterviewRequest,
    InterviewScheduleDTO,
    InterviewStatus,
    InterviewType,
    ParseMethod,
    ParseResponse,
)


def load_router_module():
    dependencies_stub = types.ModuleType("common.dependencies")
    dependencies_stub.interview_parse_service = object()
    dependencies_stub.interview_schedule_service = object()
    connection_stub = types.ModuleType("infrastructure.database.connection")

    async def get_async_session():
        yield object()

    connection_stub.get_async_session = get_async_session
    old_dependencies = sys.modules.get("common.dependencies")
    old_connection = sys.modules.get("infrastructure.database.connection")
    sys.modules["common.dependencies"] = dependencies_stub
    sys.modules["infrastructure.database.connection"] = connection_stub
    try:
        path = Path(__file__).resolve().parents[2] / "src/modules/interviewschedule/router/interview_schedule_router.py"
        spec = importlib.util.spec_from_file_location("interview_schedule_router_contract", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        if old_dependencies is None:
            sys.modules.pop("common.dependencies", None)
        else:
            sys.modules["common.dependencies"] = old_dependencies
        if old_connection is None:
            sys.modules.pop("infrastructure.database.connection", None)
        else:
            sys.modules["infrastructure.database.connection"] = old_connection


def schedule_dto(company_name="示例公司", status=InterviewStatus.PENDING):
    return InterviewScheduleDTO(
        id=1,
        companyName=company_name,
        position="Python 工程师",
        interviewTime="2026-08-06T10:00:00",
        interviewType=InterviewType.VIDEO,
        roundNumber=1,
        status=status,
        createdAt=datetime(2026, 8, 5, 9, 0),
        updatedAt=datetime(2026, 8, 5, 9, 0),
    )


def test_frontend_rest_contract_for_all_operations(monkeypatch):
    module = load_router_module()
    parse_service = types.SimpleNamespace(
        parse=AsyncMock(return_value=ParseResponse(
            success=True,
            data=CreateInterviewRequest(
                companyName="示例公司",
                position="Python 工程师",
                interviewTime="2026-08-06T10:00:00",
            ),
            confidence=0.8,
            parseMethod=ParseMethod.AI,
            log="AI 解析成功",
        ))
    )
    schedule_service = types.SimpleNamespace(
        create=AsyncMock(return_value=schedule_dto()),
        get_by_id=AsyncMock(return_value=schedule_dto()),
        get_all=AsyncMock(return_value=[schedule_dto()]),
        update=AsyncMock(return_value=schedule_dto("更新公司")),
        delete=AsyncMock(return_value=None),
        update_status=AsyncMock(return_value=schedule_dto(status=InterviewStatus.COMPLETED)),
    )
    monkeypatch.setattr(module, "interview_parse_service", parse_service)
    monkeypatch.setattr(module, "interview_schedule_service", schedule_service)
    app = FastAPI()
    app.include_router(module.router)
    body = {
        "companyName": "示例公司",
        "position": "Python 工程师",
        "interviewTime": "2026-08-06T10:00:00",
        "interviewType": "VIDEO",
    }

    with TestClient(app) as client:
        parsed = client.post("/api/interview-schedule/parse", json={"rawText": "面试邀请"})
        created = client.post("/api/interview-schedule", json=body)
        fetched = client.get("/api/interview-schedule/1")
        listed = client.get(
            "/api/interview-schedule",
            params={"status": "PENDING", "start": "2026-08-01T00:00:00", "end": "2026-08-31T23:59:59"},
        )
        updated = client.put("/api/interview-schedule/1", json={**body, "companyName": "更新公司"})
        status_updated = client.patch("/api/interview-schedule/1/status", params={"status": "COMPLETED"})
        deleted = client.delete("/api/interview-schedule/1")

    for response in (parsed, created, fetched, listed, updated, status_updated, deleted):
        assert response.status_code == 200
        assert response.json()["code"] == 200
    assert created.json()["data"]["companyName"] == "示例公司"
    assert created.json()["data"]["interviewTime"] == "2026-08-06T10:00:00"
    assert listed.json()["data"][0]["status"] == "PENDING"
    assert updated.json()["data"]["companyName"] == "更新公司"
    assert status_updated.json()["data"]["status"] == "COMPLETED"
    assert deleted.json()["data"] is None
    parse_service.parse.assert_awaited_once_with("面试邀请", None)


def test_frontend_contract_rejects_invalid_type_status_and_timezone():
    module = load_router_module()
    app = FastAPI()
    app.include_router(module.router)
    base_body = {
        "companyName": "示例公司",
        "position": "Python 工程师",
        "interviewTime": "2026-08-06T10:00:00",
    }

    with TestClient(app) as client:
        invalid_type = client.post(
            "/api/interview-schedule",
            json={**base_body, "interviewType": "HYBRID"},
        )
        invalid_status = client.patch(
            "/api/interview-schedule/1/status",
            params={"status": "UNKNOWN"},
        )
        timezone_aware = client.post(
            "/api/interview-schedule",
            json={**base_body, "interviewTime": "2026-08-06T10:00:00+08:00"},
        )

    assert invalid_type.status_code == 422
    assert invalid_status.status_code == 422
    assert timezone_aware.status_code == 422
