from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class InterviewStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


class InterviewType(str, Enum):
    ONSITE = "ONSITE"
    VIDEO = "VIDEO"
    PHONE = "PHONE"


class ParseMethod(str, Enum):
    RULE = "rule"
    AI = "ai"


class CreateInterviewRequest(BaseCamelSchema):
    company_name: str = Field(min_length=1, max_length=255)
    position: str = Field(min_length=1, max_length=255)
    interview_time: datetime
    interview_type: InterviewType | None = None
    meeting_link: str | None = None
    round_number: int = Field(default=1, ge=1, le=10)
    interviewer: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("company_name", "position")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @field_validator("interview_time")
    @classmethod
    def validate_naive_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("interviewTime 必须是不带时区的本地时间")
        return value

    @field_validator("meeting_link", "interviewer", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InterviewScheduleDTO(CreateInterviewRequest):
    id: int
    status: InterviewStatus
    created_at: datetime
    updated_at: datetime


class ParseRequest(BaseCamelSchema):
    raw_text: str = Field(min_length=1, max_length=20_000)
    source: Literal["feishu", "tencent", "zoom", "other"] | None = None

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("rawText 不能为空")
        return value


class ParseResponse(BaseCamelSchema):
    success: bool
    data: CreateInterviewRequest | None
    confidence: float = Field(ge=0, le=1)
    parse_method: ParseMethod
    log: str
