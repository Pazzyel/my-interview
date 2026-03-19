from datetime import datetime
from enum import Enum

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class QuestionType(str, Enum):
    """面试官提问的问题类型"""
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
    type: QuestionType
    category: str
    user_answer: str | None = None
    is_follow_up: bool = False
    parent_question_index: int | None = None


class CreateInterviewRequest(BaseCamelSchema):
    resume_text: str
    question_count: int = 6
    resume_id: int | None = None
    force_create: bool = False


class InterviewSessionDTO(BaseCamelSchema):
    session_id: str
    resume_text: str
    total_questions: int
    current_question_index: int
    questions: list[InterviewQuestionDTO]
    status: str
    evaluate_status: str | None = None
    evaluate_error: str | None = None


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


class ReferenceAnswerDTO(BaseCamelSchema):
    question_index: int
    question: str
    reference_answer: str
    key_points: list[str]


class InterviewReportDTO(BaseCamelSchema):
    overall_score: int
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]
    question_details: list[QuestionEvaluationDTO]
    reference_answers: list[ReferenceAnswerDTO]


class ExportedInterviewReportDTO(BaseCamelSchema):
    filename: str
    content_type: str
    generated_at: datetime
