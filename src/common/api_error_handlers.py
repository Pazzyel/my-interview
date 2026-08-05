import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.exceptions import BusinessException, ErrorCode


logger = logging.getLogger(__name__)

ERROR_CODES: dict[ErrorCode, int] = {
    ErrorCode.RESUME_NOT_FOUND: 2001,
    ErrorCode.RESUME_PARSE_FAILED: 2002,
    ErrorCode.RESUME_ANALYSIS_NOT_FOUND: 2008,
    ErrorCode.INTERVIEW_SESSION_NOT_FOUND: 3001,
    ErrorCode.INTERVIEW_QUESTION_NOT_FOUND: 3003,
    ErrorCode.INTERVIEW_QUESTION_GENERATION_FAILED: 3006,
    ErrorCode.INTERVIEW_NOT_COMPLETED: 3007,
    ErrorCode.INTERVIEW_QUESTION_INSUFFICIENT: 3009,
    ErrorCode.EXPORT_PDF_FAILED: 5001,
    ErrorCode.KB_NOT_FOUND: 6001,
    ErrorCode.KB_PARSE_FAILED: 6002,
    ErrorCode.KB_VECTORIZE_ERROR: 6006,
    ErrorCode.AI_SERVICE_ERROR: 7003,
    ErrorCode.INTERVIEW_SCHEDULE_NOT_FOUND: 9001,
    ErrorCode.LLM_PROVIDER_NOT_FOUND: 11001,
}


def _error_response(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"code": code, "message": message, "data": None},
    )


async def business_exception_handler(
    request: Request, exc: BusinessException
) -> JSONResponse:
    logger.warning(
        "Business error: path=%s code=%s message=%s",
        request.url.path,
        exc.code,
        exc.message,
    )
    code = ERROR_CODES.get(exc.code, 400 if exc.code in {
        ErrorCode.BAD_REQUEST,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.FILE_TOO_LARGE_ERROR,
    } else 500)
    return _error_response(code, exc.message)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = [str(error.get("msg", "请求参数错误")) for error in exc.errors()]
    message = ", ".join(messages) or "请求参数错误"
    logger.warning("Validation error: path=%s message=%s", request.url.path, message)
    return _error_response(400, message)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code == 404:
        message = "API 接口不存在"
    elif exc.status_code == 405:
        message = "请求方法不支持"
    else:
        message = str(exc.detail)
    logger.warning("HTTP error: path=%s status=%s", request.url.path, exc.status_code)
    return _error_response(exc.status_code, message)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error: path=%s",
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(500, "系统繁忙，请稍后重试")
