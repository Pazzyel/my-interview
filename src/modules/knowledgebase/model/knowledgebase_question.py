from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class KnowledgeBaseQuestionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    STALE = "STALE"


class QuestionGenStatus(str, Enum):
    NONE = "NONE"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class KnowledgeBaseQuestionFollowUpDTO(BaseCamelSchema):
    question: str
    reference_answer: str | None = None
    key_points: list[str] = Field(default_factory=list)
    scoring_rubric: str | None = None


class KnowledgeBaseQuestionEntity(BaseCamelSchema):
    id: int | None = None
    knowledge_base_id: int
    knowledge_base_name: str | None = None
    skill_id: str = "knowledge-base"
    difficulty: str = "mid"
    type: str | None = None
    category: str
    question: str
    topic_summary: str | None = None
    reference_answer: str | None = None
    key_points: list[str] = Field(default_factory=list)
    scoring_rubric: str | None = None
    follow_ups: list[KnowledgeBaseQuestionFollowUpDTO] = Field(default_factory=list)
    source_context: str | None = None
    kb_content_hash: str | None = Field(default=None, exclude=True)
    status: KnowledgeBaseQuestionStatus = KnowledgeBaseQuestionStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeBaseQuestionDTO(KnowledgeBaseQuestionEntity):
    pass


class GenerateKnowledgeBaseQuestionsRequest(BaseCamelSchema):
    difficulty: str = Field(default="mid", pattern="^(junior|mid|senior)$")
    question_count: int = Field(ge=1, le=30)
    follow_up_count: int = Field(default=2, ge=0, le=5)
    category_limit: int = Field(default=3, ge=1, le=5)
    llm_provider: str | None = Field(default=None, max_length=64)


class QuestionGenerationConfig(BaseCamelSchema):
    difficulty: str
    question_count: int
    follow_up_count: int
    category_limit: int
    llm_provider: str | None = None


class QuestionGenStatusResponse(BaseCamelSchema):
    knowledge_base_id: int
    question_gen_status: QuestionGenStatus
    question_gen_task_id: str | None = None
    question_gen_config: QuestionGenerationConfig | None = None
    saved_count: int = 0
    skipped_count: int = 0
    message: str | None = None
    error: str | None = None
    updated_at: datetime | None = None


class SaveKnowledgeBaseQuestionRequest(BaseCamelSchema):
    difficulty: str | None = None
    type: str | None = None
    category: str
    question: str
    topic_summary: str | None = None
    reference_answer: str | None = None
    key_points: list[str] = Field(default_factory=list)
    scoring_rubric: str | None = None
    follow_ups: list[KnowledgeBaseQuestionFollowUpDTO] = Field(default_factory=list)
    source_context: str | None = None
    status: KnowledgeBaseQuestionStatus | None = None

    @field_validator("category", "question")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class UpdateKnowledgeBaseQuestionRequest(BaseCamelSchema):
    difficulty: str | None = None
    type: str | None = None
    category: str | None = None
    question: str | None = None
    topic_summary: str | None = None
    reference_answer: str | None = None
    key_points: list[str] | None = None
    scoring_rubric: str | None = None
    follow_ups: list[KnowledgeBaseQuestionFollowUpDTO] | None = None
    source_context: str | None = None
    status: KnowledgeBaseQuestionStatus | None = None


class UpdateKnowledgeBaseQuestionStatusRequest(BaseCamelSchema):
    status: KnowledgeBaseQuestionStatus


class CategoryCount(BaseCamelSchema):
    category: str
    count: int


class CreateKnowledgeBaseInterviewRequest(BaseCamelSchema):
    knowledge_base_id: int
    category: str | None = None
    difficulty: str = Field(default="mid", pattern="^(junior|mid|senior)$")
    main_question_count: int = Field(ge=1, le=20)
    follow_up_count: int = Field(ge=0, le=5)
    llm_provider: str | None = Field(default=None, max_length=64)


class InterviewCategoryCapacity(BaseCamelSchema):
    category: str
    available_question_count: int


class InterviewFollowUpCapacity(BaseCamelSchema):
    follow_up_count: int
    available_question_count: int
    selectable: bool


class KnowledgeBaseInterviewCapacityResponse(BaseCamelSchema):
    knowledge_base_id: int
    category: str | None
    difficulty: str
    main_question_count: int
    categories: list[InterviewCategoryCapacity]
    follow_up_options: list[InterviewFollowUpCapacity]


class GeneratedQuestion(BaseCamelSchema):
    category: str | None = None
    type: str | None = None
    question: str
    topic_summary: str | None = None
    reference_answer: str | None = None
    key_points: list[str] = Field(default_factory=list)
    scoring_rubric: str | None = None
    follow_ups: list[KnowledgeBaseQuestionFollowUpDTO] = Field(default_factory=list)


class GeneratedQuestionList(BaseCamelSchema):
    questions: list[GeneratedQuestion] = Field(default_factory=list)
