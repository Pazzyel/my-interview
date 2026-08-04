from pathlib import Path
import sys
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
SHARED_ROOT = PROJECT_ROOT / "test" / "shared"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from api_test_fixture import load_router_module
from common.exceptions import BusinessException, ErrorCode
from modules.interview.model.interview_skill_dto import (
    CategoryDTO,
    DisplayDTO,
    SkillCategoryDTO,
    SkillDTO,
    SkillPriority,
)


skill_router_module = load_router_module(
    "modules.interview.router.interview_skill_router",
    dependency_fields=["interview_skill_service"],
)


@pytest.fixture()
def api_client_and_service() -> Generator[tuple[TestClient, MagicMock], None, None]:
    skill = SkillDTO(
        id="python-backend",
        name="Python 后端开发",
        description="Python interview",
        categories=[
            SkillCategoryDTO(
                key="PYTHON_BASIC", label="Python 基础", priority=SkillPriority.CORE
            )
        ],
        is_preset=True,
        persona="# Python interviewer",
        display=DisplayDTO(icon="🐍", icon_bg="bg-green"),
    )
    category = CategoryDTO(
        key="PYTHON_BASIC", label="Python 基础", priority=SkillPriority.CORE
    )
    service = MagicMock()
    service.get_all_skills.return_value = [skill]
    service.get_skill.return_value = skill
    service.parse_jd = AsyncMock(return_value=[category])
    skill_router_module.interview_skill_service = service

    app = FastAPI()
    app.include_router(skill_router_module.router)

    @app.exception_handler(BusinessException)
    async def business_exception_handler(
        _request: Request, exception: BusinessException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": exception.message, "data": None},
        )

    with TestClient(app) as client:
        yield client, service


def test_list_skills_returns_camel_case_contract(
    api_client_and_service: tuple[TestClient, MagicMock]
) -> None:
    client, service = api_client_and_service

    response = client.get("/api/interview/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"][0]["id"] == "python-backend"
    assert payload["data"][0]["isPreset"] is True
    assert payload["data"][0]["display"]["iconBg"] == "bg-green"
    service.get_all_skills.assert_called_once_with()


def test_get_skill_returns_detail(api_client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, service = api_client_and_service

    response = client.get("/api/interview/skills/python-backend")

    assert response.status_code == 200
    assert response.json()["data"]["persona"] == "# Python interviewer"
    service.get_skill.assert_called_once_with("python-backend")


def test_get_unknown_skill_returns_business_error(
    api_client_and_service: tuple[TestClient, MagicMock]
) -> None:
    client, service = api_client_and_service
    service.get_skill.side_effect = BusinessException(
        ErrorCode.BAD_REQUEST, "未找到面试主题: missing"
    )

    response = client.get("/api/interview/skills/missing")

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "message": "未找到面试主题: missing",
        "data": None,
    }


def test_parse_jd_has_no_rate_limit_dependency(
    api_client_and_service: tuple[TestClient, MagicMock]
) -> None:
    client, service = api_client_and_service
    jd_text = "Python backend role " * 5

    first = client.post("/api/interview/skills/parse-jd", json={"jdText": jd_text})
    second = client.post("/api/interview/skills/parse-jd", json={"jdText": jd_text})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"][0]["priority"] == "CORE"
    assert service.parse_jd.await_count == 2
