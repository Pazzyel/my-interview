from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.api_error_handlers import (
    business_exception_handler,
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from common.exceptions import BusinessException, ErrorCode


class Payload(BaseModel):
    count: int


def create_client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/business-error")
    async def business_error() -> None:
        raise BusinessException(ErrorCode.RESUME_NOT_FOUND, "简历不存在")

    @app.post("/validate")
    async def validate(payload: Payload) -> Payload:
        return payload

    return TestClient(app, raise_server_exceptions=False)


def test_business_errors_use_http_200_result_contract() -> None:
    with create_client() as client:
        response = client.get("/business-error")

    assert response.status_code == 200
    assert response.json() == {"code": 2001, "message": "简历不存在", "data": None}


def test_validation_and_missing_routes_use_result_contract() -> None:
    with create_client() as client:
        validation = client.post("/validate", json={"count": "invalid"})
        missing = client.get("/missing")

    assert validation.status_code == 200
    assert validation.json()["code"] == 400
    assert missing.status_code == 200
    assert missing.json() == {"code": 404, "message": "API 接口不存在", "data": None}
