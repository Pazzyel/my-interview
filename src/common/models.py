from enum import Enum
from typing import TypeVar, Generic, Optional, Any

from common.exceptions import ErrorCode
from pydantic import BaseModel

T = TypeVar('T')

class AsyncTaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Result(BaseModel, Generic[T]):
    code: int
    message: str
    data: Optional[T] = None
    
    @classmethod
    def success(cls, data: Optional[T] = None, message: str = "Success") -> "Result[T]":
        return cls(code=200, message=message, data=data)
        
    @classmethod
    def error(cls, code: int = 500, message: str = "Internal Server Error") -> "Result[Any]": # code的默认值是500
        return cls(code=code, message=message, data=None)
