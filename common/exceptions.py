from enum import Enum
from typing import Optional

class ErrorCode(str, Enum):
    RESUME_NOT_FOUND = "RESUME_NOT_FOUND"
    RESUME_PARSE_FAILED = "RESUME_PARSE_FAILED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    FILE_TOO_LARGE_ERROR = "FILE_TOO_LARGE_ERROR"
    KB_NOT_FOUND = "KB_NOT_FOUND"
    KB_PARSE_FAILED = "KB_PARSE_FAILED"
    KB_VECTORIZE_ERROR = "KB_VECTORIZE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    INTERVIEW_SESSION_NOT_FOUND = "INTERVIEW_SESSION_NOT_FOUND"


class BusinessException(Exception):
    def __init__(self, code: ErrorCode, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
