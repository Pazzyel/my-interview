from datetime import datetime
from enum import Enum

from pydantic import Field

from infrastructure.model.BaseCamelSchema import BaseCamelSchema
from modules.interview.model.interview_skill_dto import CategoryDTO


class Difficulty(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class QuestionType(str, Enum):
    """Legacy constants kept for source compatibility; question types are now open strings."""

    PROJECT = "PROJECT"
    JAVA_BASIC = "JAVA_BASIC"
    JAVA_COLLECTION = "JAVA_COLLECTION"
    JAVA_CONCURRENT = "JAVA_CONCURRENT"
    MYSQL = "MYSQL"
    REDIS = "REDIS"
    SPRING = "SPRING"
    SPRING_BOOT = "SPRING_BOOT"


class InterviewQuestionDTO(BaseCamelSchema):
    question_index: int
    question: str
    type: str
    category: str
    topic_summary: str | None = None
    user_answer: str | None = None
    score: int | None = None
    feedback: str | None = None
    is_follow_up: bool = False
    parent_question_index: int | None = None
    reference_answer: str | None = None
    key_points: list[str] = Field(default_factory=list)
    scoring_rubric: str | None = None
    source_context: str | None = None


class CreateInterviewRequest(BaseCamelSchema):
    resume_text: str = ""
    question_count: int = Field(default=6, ge=3, le=20)
    resume_id: int | None = None
    force_create: bool = False
    llm_provider: str | None = Field(default=None, max_length=50)
    skill_id: str = Field(default="java-backend", min_length=1, max_length=64)
    difficulty: Difficulty = Difficulty.MID
    custom_categories: list[CategoryDTO] | None = None
    jd_text: str | None = None
    request_id: str | None = None


class InterviewSessionDTO(BaseCamelSchema):
    session_id: str
    resume_text: str
    total_questions: int
    current_question_index: int
    questions: list[InterviewQuestionDTO]
    status: str
    evaluate_status: str | None = None
    evaluate_error: str | None = None
    knowledge_base_id: int | None = None
    interview_category: str | None = None


class CurrentQuestionResponse(BaseCamelSchema):
    completed: bool
    message: str | None = None
    question: InterviewQuestionDTO | None = None


class SubmitAnswerRequest(BaseCamelSchema):
    question_index: int
    answer: str


class SubmitAnswerResponse(BaseCamelSchema):
    has_next_question: bool
    next_question: InterviewQuestionDTO | None = None
    current_index: int
    total_questions: int


class QuestionEvaluationDTO(BaseCamelSchema):
    question_index: int
    question: str
    category: str
    user_answer: str | None = None
    score: int
    feedback: str


class CategoryScoreDTO(BaseCamelSchema):
    category: str
    score: int
    question_count: int


class ReferenceAnswerDTO(BaseCamelSchema):
    question_index: int
    question: str
    reference_answer: str
    key_points: list[str]


class InterviewReportDTO(BaseCamelSchema):
    session_id: str = ""
    total_questions: int = 0
    overall_score: int
    category_scores: list[CategoryScoreDTO] = Field(default_factory=list)
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]
    question_details: list[QuestionEvaluationDTO]
    reference_answers: list[ReferenceAnswerDTO]


class SessionListItemDTO(BaseCamelSchema):
    session_id: str
    skill_id: str
    difficulty: str
    llm_provider: str
    resume_id: int | None = None
    total_questions: int
    status: str
    evaluate_status: str | None = None
    evaluate_error: str | None = None
    overall_score: int | None = None
    source_type: str | None = None
    knowledge_base_id: int | None = None
    interview_category: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class HistoricalQuestion(BaseCamelSchema):
    question: str
    type: str
    topic_summary: str | None = None


class ExportedInterviewReportDTO(BaseCamelSchema):
    filename: str
    content_type: str
    generated_at: datetime
