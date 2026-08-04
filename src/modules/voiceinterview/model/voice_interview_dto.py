from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from infrastructure.model.BaseCamelSchema import BaseCamelSchema
from modules.voiceinterview.model.voice_interview_entity import InterviewPhase


class CreateVoiceInterviewRequest(BaseCamelSchema):
    user_id: str = Field(default="default", max_length=64)
    role_type: str | None = Field(default=None, max_length=128)
    skill_id: str = Field(default="java-backend", min_length=1, max_length=64)
    difficulty: str = Field(default="mid", pattern="^(junior|mid|senior)$")
    custom_jd_text: str | None = Field(default=None, max_length=20_000)
    resume_id: int | None = None
    intro_enabled: bool = False
    tech_enabled: bool = True
    project_enabled: bool = True
    hr_enabled: bool = True
    planned_duration: int = Field(default=30, ge=1, le=240)
    llm_provider: str = Field(default="default", min_length=1, max_length=50)

    @field_validator("user_id", mode="before")
    @classmethod
    def normalize_user_id(cls, value: Any) -> str:
        # TODO(multi-user): userId is reserved only; authentication and ownership
        # checks are deliberately not implemented yet.
        return str(value).strip() if value is not None and str(value).strip() else "default"

    @field_validator("skill_id", "difficulty", "llm_provider", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Any, info: Any) -> str:
        defaults = {"skill_id": "java-backend", "difficulty": "mid", "llm_provider": "default"}
        return str(value).strip() if value is not None and str(value).strip() else defaults[info.field_name]

    @field_validator("role_type", mode="before")
    @classmethod
    def normalize_role_type(cls, value: Any) -> str | None:
        return str(value).strip() if value is not None and str(value).strip() else None


class PauseVoiceInterviewRequest(BaseCamelSchema):
    reason: str = "user_initiated"


class SessionResponseDTO(BaseCamelSchema):
    session_id: int
    user_id: str
    role_type: str
    skill_id: str
    difficulty: str
    current_phase: str
    status: str
    start_time: datetime
    planned_duration: int
    actual_duration: int | None = None
    web_socket_url: str


class SessionMetaDTO(BaseCamelSchema):
    session_id: int
    user_id: str
    role_type: str
    skill_id: str
    difficulty: str
    status: str
    current_phase: str
    created_at: datetime
    updated_at: datetime
    actual_duration: int | None = None
    message_count: int = 0
    evaluate_status: str | None = None
    evaluate_error: str | None = None


class VoiceInterviewMessageDTO(BaseCamelSchema):
    id: int
    session_id: int
    message_type: str
    phase: str | None = None
    user_recognized_text: str | None = None
    ai_generated_text: str | None = None
    sequence_num: int
    timestamp: datetime


class VoiceEvaluationDetailDTO(BaseCamelSchema):
    session_id: int
    total_questions: int = 0
    overall_score: int | None = None
    overall_feedback: str | None = None
    question_evaluations: list[Any] = Field(default_factory=list)
    # Java frontend compatibility: InterviewDetailPanel reads `answers`.
    answers: list[Any] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    reference_answers: list[Any] = Field(default_factory=list)
    interviewer_role: str | None = None
    interview_date: datetime | None = None


class VoiceEvaluationStatusDTO(BaseCamelSchema):
    evaluate_status: str | None = None
    evaluate_error: str | None = None
    evaluate_status_updated_at: datetime | None = None
    evaluation: VoiceEvaluationDetailDTO | None = None


class StartPhaseRequest(BaseCamelSchema):
    phase: InterviewPhase
