from datetime import datetime
from enum import Enum

from pydantic import Field

from common.models import AsyncTaskStatus
from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class VoiceInterviewSessionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InterviewPhase(str, Enum):
    INTRO = "INTRO"
    TECH = "TECH"
    PROJECT = "PROJECT"
    HR = "HR"
    COMPLETED = "COMPLETED"


class VoiceMessageType(str, Enum):
    USER_SPEECH = "USER_SPEECH"
    AI_SPEECH = "AI_SPEECH"
    SYSTEM = "SYSTEM"
    SUMMARY = "SUMMARY"


class VoiceInterviewSessionEntity(BaseCamelSchema):
    id: int | None = None
    user_id: str = "default"
    role_type: str
    skill_id: str = "java-backend"
    difficulty: str = "mid"
    custom_jd_text: str | None = None
    resume_id: int | None = None
    intro_enabled: bool = False
    tech_enabled: bool = True
    project_enabled: bool = True
    hr_enabled: bool = True
    llm_provider: str = "default"
    current_phase: InterviewPhase
    status: VoiceInterviewSessionStatus = VoiceInterviewSessionStatus.IN_PROGRESS
    planned_duration: int = 30
    actual_duration: int | None = None
    total_paused_seconds: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = None
    paused_at: datetime | None = None
    resumed_at: datetime | None = None
    evaluate_status: AsyncTaskStatus | None = None
    evaluate_error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class VoiceInterviewMessageEntity(BaseCamelSchema):
    id: int | None = None
    session_id: int
    message_type: VoiceMessageType
    phase: InterviewPhase | None = None
    user_recognized_text: str | None = None
    ai_generated_text: str | None = None
    sequence_num: int
    summary_covered_sequence: int | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)


class VoiceInterviewEvaluationEntity(BaseCamelSchema):
    id: int | None = None
    session_id: int
    overall_score: int | None = None
    overall_feedback: str | None = None
    question_evaluations_json: str | None = None
    strengths_json: str | None = None
    improvements_json: str | None = None
    reference_answers_json: str | None = None
    interviewer_role: str | None = None
    interview_date: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
